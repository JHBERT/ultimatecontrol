"""A saved playlist of tunes, kept next to the library.

A playlist is a plain list of tunes in a JSON file under
``<config>/ultimatecontrol/playlists``. It holds no copy of the SIDs - only
where they live (``library`` or ``favorites``) and which sub tune is meant, so
a playlist stays small and follows the library when files move inside it.

The list is the queue's input: "Playlist abspielen" replaces the device queue
with it, and the timer then works exactly as it does for a folder.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

_LOGGER = logging.getLogger(__name__)

PLAYLISTS_DIR = "playlists"

# A playlist name becomes a file name; keep it boring.
_UNSAFE = re.compile(r"[^A-Za-z0-9 _.\-]+")


class PlaylistError(Exception):
    """A playlist name or entry is not acceptable."""


@dataclass(slots=True)
class Playlist:
    """One saved playlist."""

    name: str
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Return how many tunes the playlist holds."""
        return len(self.items)

    def as_dict(self) -> dict[str, Any]:
        """Return the playlist as sent to the dashboard."""
        return {"name": self.name, "count": self.count, "items": list(self.items)}


def _clean_name(name: str) -> str:
    """Return a safe playlist name."""
    cleaned = _UNSAFE.sub("", (name or "").strip()).strip(". ")
    if not cleaned:
        raise PlaylistError("A playlist needs a name")
    if len(cleaned) > 60:
        raise PlaylistError("A playlist name may have at most 60 characters")
    return cleaned


def _entry_key(item: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(item.get("source") or "library"),
        str(item.get("path") or ""),
        int(item.get("song") or 1),
    )


class PlaylistStore:
    """All playlists of one device, read from and written to disk."""

    def __init__(self, base_dir: Path) -> None:
        """Use ``<base_dir>/playlists`` as the folder of the playlists."""
        self.base_dir = base_dir / PLAYLISTS_DIR

    def ensure_dir(self) -> None:
        """Create the playlist folder."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_of(self, name: str) -> Path:
        """Return the file of a playlist."""
        return self.base_dir / f"{_clean_name(name)}.json"

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        """Return every playlist with its name and count, sorted by name."""
        if not self.base_dir.is_dir():
            return []
        result: list[dict[str, Any]] = []
        for file in sorted(self.base_dir.glob("*.json"), key=lambda p: p.name.casefold()):
            playlist = self.load(file.stem)
            if playlist is not None:
                result.append({"name": playlist.name, "count": playlist.count})
        return result

    def load(self, name: str) -> Playlist | None:
        """Return one playlist, or None when it does not exist."""
        try:
            path = self.path_of(name)
        except PlaylistError:
            return None
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _LOGGER.warning("Playlist %s is unreadable", path.name, exc_info=True)
            return None
        items = [item for item in data.get("items", []) if isinstance(item, dict)]
        return Playlist(name=path.stem, items=items)

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------
    def save(self, playlist: Playlist) -> Playlist:
        """Write a playlist to disk (atomically, so a crash cannot truncate it)."""
        self.ensure_dir()
        target = self.path_of(playlist.name)
        temp = target.with_suffix(".json.part")
        payload = {"name": playlist.name, "items": playlist.items}
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(target)
        return playlist

    def delete(self, name: str) -> bool:
        """Delete a playlist; returns whether a file was removed."""
        try:
            path = self.path_of(name)
        except PlaylistError:
            return False
        if not path.is_file():
            return False
        path.unlink()
        return True

    # ------------------------------------------------------------------
    # entries
    # ------------------------------------------------------------------
    def add(
        self, name: str, items: list[dict[str, Any]], *, append: bool = True
    ) -> Playlist:
        """Add tunes to a playlist (creating it when needed)."""
        playlist = self.load(name) if append else None
        playlist = playlist or Playlist(name=_clean_name(name))
        known = {_entry_key(item) for item in playlist.items}
        for item in items:
            entry = {
                "source": str(item.get("source") or "library"),
                "path": str(item.get("path") or ""),
                "name": str(item.get("name") or PurePosixPath(str(item.get("path"))).name),
                "song": max(1, int(item.get("song") or 1)),
            }
            if not entry["path"]:
                continue
            if _entry_key(entry) in known:
                continue
            known.add(_entry_key(entry))
            playlist.items.append(entry)
        return self.save(playlist)

    def remove_entry(self, name: str, index: int) -> Playlist:
        """Remove the tune at ``index`` (0 based)."""
        playlist = self.load(name)
        if playlist is None:
            raise PlaylistError(f"No playlist called {name}")
        if not 0 <= index < len(playlist.items):
            raise PlaylistError(f"The playlist has no entry {index + 1}")
        playlist.items.pop(index)
        return self.save(playlist)

    def clear(self, name: str) -> Playlist:
        """Empty a playlist but keep it."""
        playlist = self.load(name)
        if playlist is None:
            raise PlaylistError(f"No playlist called {name}")
        playlist.items = []
        return self.save(playlist)
