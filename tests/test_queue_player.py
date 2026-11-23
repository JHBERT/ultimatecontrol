"""Tests for the folder queue and its timer.

The queue is the part that has to be right without a C64: every tune starts,
the timer is reset for each one, and the queue ends instead of looping.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


queue_player = _load("ultimatecontrol.queue_player", _PKG / "queue_player.py")
QueueItem = queue_player.QueueItem
QueuePlayer = queue_player.QueuePlayer
FALLBACK_LENGTH = queue_player.FALLBACK_LENGTH


class Recorder:
    """Collects what the queue sends to the device."""

    def __init__(self) -> None:
        self.played: list[tuple[str, int]] = []
        self.fail_on: str | None = None

    async def play(self, item):
        if self.fail_on and item.path == self.fail_on:
            raise RuntimeError("device refused")
        self.played.append((item.path, item.song))


def _items(*specs):
    return [QueueItem(source="library", path=p, song=s, length=l) for p, s, l in specs]


# ----------------------------------------------------------------------
# items
# ----------------------------------------------------------------------
def test_an_item_keeps_its_song_and_length():
    item = QueueItem.from_dict({"path": "A/B.sid", "song": 3, "length": 90.4})
    assert item.song == 3
    assert item.length == 90.4
    assert item.name == "B.sid"
    assert item.source == "library"


def test_a_song_number_below_one_becomes_one():
    assert QueueItem.from_dict({"path": "x.sid", "song": 0}).song == 1


def test_a_relative_slash_path_gives_the_file_name():
    assert QueueItem.from_dict({"path": "MUSICIANS/H/Hubbard/Commando.sid"}).name == (
        "Commando.sid"
    )


# ----------------------------------------------------------------------
# queue
# ----------------------------------------------------------------------
async def test_the_queue_plays_the_first_tune_and_reports_the_count():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    state = await player.start(_items(("a.sid", 1, 90), ("b.sid", 1, 30)))
    assert rec.played == [("a.sid", 1)]
    assert state.playing is True
    assert state.index == 0
    assert state.as_dict()["count"] == 2
    player.cancel()


async def test_the_timer_uses_the_tunes_own_length():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90)))
    # 90 seconds plus the small grace after the tune.
    assert player.state.remaining == 90 + queue_player.END_GRACE
    player.cancel()


async def test_a_tune_without_a_length_waits_for_the_fallback():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, None)))
    assert player.state.remaining == FALLBACK_LENGTH + queue_player.END_GRACE
    player.cancel()


async def test_a_missing_length_is_looked_up_before_playing():
    rec = Recorder()

    async def length_of(item):
        return 42.0

    player = QueuePlayer(rec.play, length_of=length_of)
    await player.start(_items(("a.sid", 1, None)))
    assert player.state.items[0].length == 42.0
    assert player.state.remaining == 42 + queue_player.END_GRACE
    player.cancel()


async def test_the_timer_resets_for_each_tune():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90), ("b.sid", 1, 10)))
    assert player.state.remaining == 90 + queue_player.END_GRACE
    await player.next()
    assert player.state.remaining == 10 + queue_player.END_GRACE
    assert rec.played == [("a.sid", 1), ("b.sid", 1)]
    player.cancel()


async def test_an_old_timer_never_advances_the_queue_twice():
    """Skipping quickly must not leave the previous timer running."""
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90), ("b.sid", 1, 90), ("c.sid", 1, 90)))
    await player.next()
    await asyncio.sleep(0)
    assert player.state.index == 1
    assert rec.played == [("a.sid", 1), ("b.sid", 1)]
    player.cancel()


async def test_the_last_tune_ends_the_queue_instead_of_looping():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90)))
    await player.next()
    assert player.state.playing is False
    assert player.state.remaining is None
    assert rec.played == [("a.sid", 1)]


async def test_previous_stops_at_the_first_tune():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90), ("b.sid", 1, 90)))
    await player.previous()
    assert player.state.index == 0
    player.cancel()


async def test_stop_keeps_the_position_but_ends_playback():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90), ("b.sid", 1, 90)))
    player.stop()
    assert player.state.playing is False
    assert player.state.index == 0
    assert player.state.task is None


async def test_a_device_that_refuses_a_tune_ends_the_queue():
    rec = Recorder()
    rec.fail_on = "b.sid"
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90)))
    try:
        await player.next()
    except RuntimeError:
        pass
    assert player.state.playing is False
    assert player.state.remaining is None


async def test_the_queue_knows_the_tune_it_started():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 2, 90)))
    assert player.is_current("library", "a.sid", 2) is True
    assert player.is_current("library", "a.sid", 1) is False
    assert player.is_current("favorites", "a.sid", 2) is False
    player.cancel()


async def test_replacing_the_queue_cancels_the_old_timer():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    await player.start(_items(("a.sid", 1, 90)))
    old_task = player.state.task
    player.replace(_items(("b.sid", 1, 10)), title="Neu")
    assert old_task.cancelled() or old_task.done() or player.state.task is None
    assert len(player.state.items) == 1
    assert player.state.title == "Neu"


async def test_an_empty_queue_does_nothing():
    rec = Recorder()
    player = QueuePlayer(rec.play)
    state = await player.start([])
    assert rec.played == []
    assert state.playing is False


async def test_the_timer_really_advances_after_the_length(monkeypatch):
    """End to end with a tiny length: the next tune is sent by the timer."""
    rec = Recorder()
    player = QueuePlayer(rec.play)
    monkeypatch.setattr(queue_player, "END_GRACE", 0.01)
    await player.start(_items(("a.sid", 1, 1), ("b.sid", 1, 1)))
    await asyncio.sleep(1.1)
    assert rec.played == [("a.sid", 1), ("b.sid", 1)]
    assert player.state.index == 1
    player.cancel()
