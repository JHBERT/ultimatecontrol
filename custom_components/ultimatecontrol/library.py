"""A local SID library on the Home Assistant host.

The Ultimate II+ cannot download or store files over REST, so anything that is
not already on the device has to be sent with the ``sidplay`` request. For a
comfortable dashboard that means keeping the collection on the Home Assistant
host:

* ``<config>/ultimatecontrol/sids``  - the library, browsed folder by folder
* ``<config>/ultimatecontrol/favorites`` - favourites, copied out of the library

Each SID's sub tune count and its HVSC song lengths are read from the files in
the library, so the dashboard knows a tune's name, how many tunes a file has and
how long a tune plays - for a file that only ever arrives on the C64 as a stream.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .songlengths import SongLengthsDatabase, count_subtunes, sid_md5

_LOGGER = logging.getLogger(__name__)

LIBRARY_DIR = "sids"
FAVORITES_DIR = "favorites"

# The HVSC allows every character a C64 file name allows; a media source folder
# name must not climb out of the library.
_FORBIDDEN = re.compile(r"[/\\\x00-\x1f]")


class SidLibraryError(Exception):
    """A path or name in the library is not acceptable."""


@dataclass(slots=True)
class SidFile:
    """One SID file in the library."""

    name: str
    relative_path: str
    size: int
    songs: int = 1
    md5: str = ""
    lengths: list[float] = field(default_factory=list)

    @property
    def duration(self) -> float | None:
        """Return the length of the first tune, if the database knows it."""
        return self.lengths[0] if self.lengths else None


def _clean_relative(path: str) -> str:
    """Return a safe relative path inside the library."""
    cleaned = (path or "").strip().strip("/")
    if not cleaned:
        return ""
    parts: list[str] = []
    for part in PurePosixPath(cleaned).parts:
        if part in ("", ".", "..") or _FORBIDDEN.search(part):
            raise SidLibraryError(f"Invalid path: {path}")
        parts.append(part)
    return "/".join(parts)


class SidLibrary:
    """Files on disk, cached so a dashboard does not rescan on every view."""

    def __init__(self, base_dir: Path, songlengths: SongLengthsDatabase | None = None) -> None:
        """Initialise the library rooted at the integration's data folder."""
        self.base_dir = base_dir
        self.library_dir = base_dir / LIBRARY_DIR
        self.favorites_dir = base_dir / FAVORITES_DIR
        self.songlengths = songlengths or SongLengthsDatabase()
        self._cache: dict[str, SidFile] = {}

    # ------------------------------------------------------------------
    # paths
    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        """Create the library and favourites folders."""
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.favorites_dir.mkdir(parents=True, exist_ok=True)

    def library_path(self, relative: str) -> Path:
        """Return the file system path of a library file."""
        return self.library_dir / _clean_relative(relative)

    def favorites_path(self, relative: str) -> Path:
        """Return the file system path of a favourite."""
        return self.favorites_dir / _clean_relative(relative)

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    def list_dir(self, source: str, folder: str) -> list[dict[str, object]]:
        """Return the entries of one folder of the library or the favourites.

        Entries are ``{"name", "is_dir", "songs?", "duration?"}`` sorted with
        folders first.
        """
        base = self.favorites_dir if source == "favorites" else self.library_dir
        target = base / _clean_relative(folder)
        if not target.is_dir():
            return []
        entries: list[dict[str, object]] = []
        for child in target.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append({"name": child.name, "is_dir": True})
                continue
            if child.suffix.lower() != ".sid":
                continue
            info = self.inspect(child)
            entries.append(
                {
                    "name": child.name,
                    "is_dir": False,
                    "songs": info.songs,
                    "duration": info.duration,
                }
            )
        entries.sort(key=lambda item: (not item["is_dir"], str(item["name"]).casefold()))
        return entries

    def inspect(self, path: Path, compute_md5: bool = True) -> SidFile:
        """Return the metadata of a SID file, cached by path and modification time."""
        try:
            stat = path.stat()
        except OSError:
            raise SidLibraryError(f"File not found: {path.name}") from None

        key = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{compute_md5}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        data = path.read_bytes()
        md5 = sid_md5(data) if compute_md5 else ""
        lengths = list(self.songlengths.get_lengths(md5)) if md5 else []
        info = SidFile(
            name=path.name,
            relative_path=str(path),
            size=stat.st_size,
            songs=count_subtunes(data),
            md5=md5,
            lengths=lengths,
        )
        self._cache[key] = info
        return info

    def find(self, source: str, relative: str) -> Path:
        """Return the path of a file in the library or the favourites."""
        base = self.favorites_dir if source == "favorites" else self.library_dir
        path = base / _clean_relative(relative)
        if not path.is_file():
            # A favourite keeps its sub folders, so a file that was moved deeper
            # in the library is still found by its name.
            if source == "favorites":
                name = PurePosixPath(relative).name
                for candidate in self.favorites_dir.rglob(name):
                    if candidate.is_file():
                        return candidate
            raise SidLibraryError(f"Not in the library: {relative}")
        return path

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------
    def add_favorite(self, relative: str) -> Path:
        """Copy a library file into the favourites, keeping its sub folder."""
        relative = _clean_relative(relative)
        source = self.library_path(relative)
        if not source.is_file():
            raise SidLibraryError(f"Not in the library: {relative}")
        target = self.favorites_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        return target

    def remove_favorite(self, relative: str) -> bool:
        """Remove one favourite; returns whether a file was removed."""
        try:
            path = self.find("favorites", relative)
        except SidLibraryError:
            return False
        parent = path.parent
        path.unlink()
        # Drop the folder too when it became empty, so the list stays tidy.
        try:
            while parent != self.favorites_dir and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        except OSError:
            pass
        return True

    def import_file(self, source: Path, relative: str, overwrite: bool = False) -> Path:
        """Copy a SID from anywhere on the host into the library."""
        relative = _clean_relative(relative)
        if not relative.lower().endswith(".sid"):
            raise SidLibraryError("Only SID files can be imported")
        if not source.is_file():
            raise SidLibraryError(f"File not found: {source}")
        target = self.library_dir / relative
        if target.exists() and not overwrite:
            raise SidLibraryError(f"Already in the library: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def library_file(self, relative: str) -> Path | None:
        """Return a library file, or None when it does not exist."""
        try:
            path = self.library_path(relative)
        except SidLibraryError:
            return None
        return path if path.is_file() else None


async def async_inspect(library: SidLibrary, path: Path) -> SidFile:
    """Read a SID's metadata without blocking the event loop."""
    return await asyncio.to_thread(library.inspect, path)
