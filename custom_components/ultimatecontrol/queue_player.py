"""Playing a whole folder: a queue on the Home Assistant side.

The C64 has no queue of its own and the Ultimate's SID player only knows the
length that travels with an upload. So the queue and its timer live here:

* a queue is an ordered list of tunes, each ``{source, path, name, song}``,
* when a tune starts, its HVSC length (taken from the file's hash) decides when
  the next one is sent - the timer is restarted for every tune,
* the player's own length array is sent along, so the C64 also stops at the
  documented time instead of after five minutes.

The timer runs as a background task of the integration. It is cancelled when
the queue is stopped, when the device changes tune by hand, and when the config
entry is unloaded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

# What the device falls back to when a tune's length is unknown. The queue must
# not hang on such a tune, so it waits this long before moving on.
FALLBACK_LENGTH = 300

# A little air after the documented length, so the C64 has finished the tune.
END_GRACE = 0.5


@dataclass(slots=True)
class QueueItem:
    """One tune in the queue."""

    source: str
    path: str
    name: str = ""
    song: int = 1
    length: float | None = None
    # The tune the SID asks for first (its "main" tune); 0 when not known.
    start_song: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueItem:
        """Build an item from a websocket payload."""
        song = int(data.get("song") or 1)
        length = data.get("length")
        return cls(
            source=str(data.get("source") or "library"),
            path=str(data["path"]),
            name=str(data.get("name") or str(data["path"]).rsplit("/", 1)[-1]),
            song=max(1, song),
            length=float(length) if length else None,
            start_song=max(0, int(data.get("start_song") or 0)),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the item as sent to the dashboard."""
        return {
            "source": self.source,
            "path": self.path,
            "name": self.name,
            "song": self.song,
            "length": self.length,
            "start_song": self.start_song,
        }


@dataclass(slots=True)
class QueueState:
    """The queue, its position and its timer."""

    items: list[QueueItem] = field(default_factory=list)
    index: int = -1
    playing: bool = False
    # Seconds the current tune plays; None when no timer runs.
    remaining: float | None = None
    # When the timer fires, as a Unix timestamp, so a freshly opened dashboard
    # can show the running tune and the time left without asking the C64.
    ends_at: float | None = None
    # Set by the dashboard to name the folder the queue came from.
    title: str = ""
    task: asyncio.Task | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the queue as sent to the dashboard."""
        return {
            "title": self.title,
            "playing": self.playing,
            "index": self.index,
            "count": len(self.items),
            "remaining": round(self.remaining, 1) if self.remaining else None,
            "ends_at": self.ends_at,
            "items": [item.as_dict() for item in self.items],
        }


class QueuePlayer:
    """Owns the queue of one device and the timer that advances it."""

    def __init__(
        self,
        play: Callable[[QueueItem], Awaitable[None]],
        length_of: Callable[[QueueItem], Awaitable[float | None]] | None = None,
        factory: Callable[..., asyncio.Task] | None = None,
        start_song_of: Callable[[QueueItem], Awaitable[int]] | None = None,
    ) -> None:
        """Set up the player.

        ``play`` sends one tune to the device. ``length_of`` fills in a length
        for items that arrived without one (the dashboard sends it along, but a
        tune added from the media browser may not).
        """
        self._play = play
        self._length_of = length_of
        # Home Assistant wants background work created through the hass so it
        # survives and is stopped on shutdown; plain asyncio is the fallback.
        self._factory = factory or (lambda coro: asyncio.get_running_loop().create_task(coro))
        # A tune's "main" sub tune comes from its SID header; the queue plays
        # that one, not always the first.
        self._start_song = start_song_of
        self.state = QueueState()
        self._generation = 0

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    @property
    def current(self) -> QueueItem | None:
        """Return the item that is playing, if any."""
        if 0 <= self.state.index < len(self.state.items):
            return self.state.items[self.state.index]
        return None

    def is_current(self, source: str, path: str, song: int) -> bool:
        """Return whether this tune is the one the queue started."""
        item = self.current
        return bool(
            item and item.source == source and item.path == path and item.song == song
        )

    # ------------------------------------------------------------------
    # control
    # ------------------------------------------------------------------
    def replace(self, items: list[QueueItem], title: str = "") -> QueueState:
        """Replace the queue with a new list, without starting it."""
        self.cancel()
        self.state = QueueState(items=list(items), title=title)
        return self.state

    async def start(self, items: list[QueueItem] | None = None, title: str = "") -> QueueState:
        """Start playing, from the beginning or from the current position."""
        if items is not None:
            self.replace(items, title)
        if not self.state.items:
            return self.state
        if self.state.index < 0:
            self.state.index = 0
        await self._play_current()
        return self.state

    async def next(self) -> QueueState:
        """Skip to the next tune; ends the queue after the last one."""
        if not self.state.items:
            return self.state
        if self.state.index + 1 >= len(self.state.items):
            self.stop()
            return self.state
        self.state.index += 1
        await self._play_current()
        return self.state

    async def previous(self) -> QueueState:
        """Go back one tune."""
        if not self.state.items:
            return self.state
        self.state.index = max(0, self.state.index - 1)
        await self._play_current()
        return self.state

    def stop(self) -> QueueState:
        """Stop the timer and end playback (the C64 keeps playing)."""
        self.cancel()
        self.state.playing = False
        self.state.remaining = None
        self.state.ends_at = None
        return self.state

    def cancel(self) -> None:
        """Cancel the timer without touching the position."""
        task = self.state.task
        self.state.task = None
        self.state.ends_at = None
        self._generation += 1
        if task is not None and not task.done():
            task.cancel()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    async def _play_current(self) -> None:
        """Send the current tune and restart the timer."""
        item = self.current
        if item is None:
            self.stop()
            return
        self.cancel()
        generation = self._generation
        if item.start_song == 0 and self._start_song is not None:
            try:
                item.start_song = await self._start_song(item)
            except Exception:  # noqa: BLE001 - unknown means "first tune"
                item.start_song = 1
            # A folder or playlist entry that was never told a tune plays the
            # SID's own main tune.
            if item.song == 1:
                item.song = max(1, item.start_song)
        if item.length is None and self._length_of is not None:
            try:
                item.length = await self._length_of(item)
            except Exception:  # noqa: BLE001 - a missing length must not stop the queue
                _LOGGER.debug("No length for %s", item.path, exc_info=True)
        try:
            await self._play(item)
        except Exception:
            _LOGGER.warning("Could not start %s from the queue", item.path, exc_info=True)
            self.state.playing = False
            self.state.remaining = None
            raise
        self.state.playing = True
        self.state.remaining = self._delay(item)
        self.state.ends_at = time.time() + self.state.remaining
        self.state.task = self._factory(self._run(generation, self.state.remaining))

    @staticmethod
    def _delay(item: QueueItem) -> float:
        """Return how long this tune plays before the next one starts."""
        length = item.length if item.length else FALLBACK_LENGTH
        return max(float(length), 1.0) + END_GRACE

    async def _run(self, generation: int, delay: float) -> None:
        """Wait for the tune to end, then advance - unless overtaken."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        if generation != self._generation:
            return
        self.state.task = None
        try:
            await self.next()
        except Exception:  # noqa: BLE001 - a device that is gone ends the queue
            _LOGGER.warning("Queue stopped: the device did not accept the next tune")
            self.state.playing = False
            self.state.remaining = None
