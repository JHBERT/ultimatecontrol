"""Song length lookup for SID files.

The High Voltage SID Collection ships ``DOCUMENTS/Songlengths.md5`` (INI style,
since HVSC#71):

    [Database]
    ; /MUSICIANS/H/Hubbard_Rob/Commando.sid
    c4c5ff8cfefdf683c50e66775cfac1ee=3:57 1:02 0:06

The key is the MD5 of the whole file, the value holds one length per sub tune
(``mm:ss`` or ``mm:ss.SSS``). See ``DOCUMENTS/Songlengths.faq`` in the HVSC.

This module parses that file into a dict and looks up lengths by the MD5 of the
SID bytes. It is deliberately independent of Home Assistant so it can be tested
on its own.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# ``3:57``, ``1:02.5``, ``0:06.250``
_LENGTH_RE = re.compile(r"^(\d+):(\d{2})(?:\.(\d{1,3}))?$")
# Optional trailing attribute markers of the old format, e.g. ``0:06(G)``
_ATTR_RE = re.compile(r"\([GMZB]+\)$")


def parse_song_lengths_line(value: str) -> list[float]:
    """Parse the right-hand side of a song length line into seconds."""
    lengths: list[float] = []
    for token in value.split():
        token = _ATTR_RE.sub("", token.strip())
        match = _LENGTH_RE.match(token)
        if not match:
            continue
        minutes, seconds, fraction = match.groups()
        length = int(minutes) * 60 + int(seconds)
        if fraction:
            length += int(fraction) / (10 ** len(fraction))
        lengths.append(round(length, 3))
    return lengths


def count_subtunes(sid_bytes: bytes) -> int:
    """Return the number of sub tunes in SID bytes (1 for anything unreadable).

    The header of a PSID/RSID file carries the count at offset 14 (big endian);
    ``0`` means "one tune" and RSID files always have a single one.
    """
    if len(sid_bytes) < 16 or sid_bytes[:4] not in (b"PSID", b"RSID"):
        return 1
    if sid_bytes[:4] == b"RSID":
        return 1
    songs = int.from_bytes(sid_bytes[14:16], "big")
    return max(songs, 1)


def sid_md5(sid_bytes: bytes) -> str:
    """Return the HVSC song length key (MD5 of the whole file) for SID bytes."""
    return hashlib.md5(sid_bytes).hexdigest()


class SongLengthsDatabase:
    """In-memory view of ``Songlengths.md5``."""

    def __init__(self, lengths: dict[str, list[float]] | None = None) -> None:
        """Initialise the database with an optional pre-parsed mapping."""
        self._lengths = lengths or {}

    def __len__(self) -> int:
        """Return the number of indexed SID files."""
        return len(self._lengths)

    @property
    def is_empty(self) -> bool:
        """Return True when no song lengths are loaded."""
        return not self._lengths

    @classmethod
    def from_text(cls, text: str) -> SongLengthsDatabase:
        """Parse the content of a Songlengths.md5 file."""
        lengths: dict[str, list[float]] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith((";", "[")) or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().lower()
            parsed = parse_song_lengths_line(value)
            if key and parsed:
                lengths[key] = parsed
        return cls(lengths)

    @classmethod
    def from_file(cls, path: Path) -> SongLengthsDatabase:
        """Parse a Songlengths.md5 file from disk (blocking, run in executor)."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            _LOGGER.warning("Cannot read song lengths database %s: %s", path, err)
            return cls()
        database = cls.from_text(text)
        _LOGGER.debug(
            "Loaded %s song lengths entries from %s", len(database), path
        )
        return database

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[float]]) -> SongLengthsDatabase:
        """Build the database from a pre-parsed mapping (JSON cache file)."""
        cleaned: dict[str, list[float]] = {}
        for key, values in mapping.items():
            try:
                lengths = [float(value) for value in values]
            except (TypeError, ValueError):
                continue
            if lengths:
                cleaned[str(key).strip().lower()] = lengths
        return cls(cleaned)

    @classmethod
    def from_json_file(cls, path: Path) -> SongLengthsDatabase:
        """Load the JSON cache written by ``tools/build_songlengths.py``."""
        import json

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _LOGGER.warning("Cannot read song lengths cache %s: %s", path, err)
            return cls()
        if not isinstance(data, dict):
            _LOGGER.warning("Song lengths cache %s has an unexpected format", path)
            return cls()
        database = cls.from_mapping(data)
        _LOGGER.debug("Loaded %s song lengths from %s", len(database), path)
        return database

    def get_length(self, sid_bytes: bytes, song_nr: int = 0) -> float | None:
        """Return the length in seconds of one sub tune.

        ``song_nr`` is 0-based; the device's ``songnr`` parameter is 1-based, so
        callers translate. Returns ``None`` when the SID is unknown or the sub
        tune has no entry.
        """
        lengths = self._lengths.get(sid_md5(sid_bytes))
        if not lengths or song_nr < 0 or song_nr >= len(lengths):
            return None
        return lengths[song_nr]

    def get_all_lengths(self, sid_bytes: bytes) -> list[float]:
        """Return all sub tune lengths of a SID file."""
        return list(self._lengths.get(sid_md5(sid_bytes), []))

    def get_lengths(self, md5: str) -> list[float]:
        """Return all sub tune lengths for a known file hash (no file needed)."""
        return list(self._lengths.get(md5.strip().lower(), []))

    def length_of(self, md5: str, song_nr: int = 0) -> float | None:
        """Return one sub tune's length in seconds (0-based), None if unknown."""
        lengths = self._lengths.get(md5.strip().lower())
        if not lengths or song_nr < 0 or song_nr >= len(lengths):
            return None
        return lengths[song_nr]
