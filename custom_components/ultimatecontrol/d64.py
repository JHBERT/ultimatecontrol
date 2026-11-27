"""Read a D64 disk image: directory and the first PRG on it.

A D64 is a raw dump of the 1541 disk: 35 tracks (40 with a "extended" image),
each split into sectors, and a sector is 256 bytes. Track 18 holds the
directory, and every file is a chain of sectors whose first two bytes point to
the next one.

This module exists so a disk image can be *started*, not only mounted: the
first PRG of the directory is pulled out of the image and handed to the
``run_prg`` runner, which loads and runs it in one go. That is the autorun a
disk does not have on its own. Nothing here needs Home Assistant, so it can be
tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTOR_SIZE = 256
DIRECTORY_TRACK = 18
DIRECTORY_SECTOR = 1

# Sectors per track of a 1541 disk: 21 on the outer tracks, fewer further in.
_SECTORS_PER_TRACK = {
    **{track: 21 for track in range(1, 18)},
    **{track: 19 for track in range(18, 25)},
    **{track: 18 for track in range(25, 31)},
    **{track: 17 for track in range(31, 36)},
    **{track: 17 for track in range(36, 41)},
}

# File types as stored in the directory entry (low nibble).
FILE_TYPES = {0: "DEL", 1: "SEQ", 2: "PRG", 3: "USR", 4: "REL"}
PRG = 2


class D64Error(Exception):
    """The image is not a readable D64."""


@dataclass(frozen=True)
class D64File:
    """One directory entry."""

    name: str
    type: str
    track: int
    sector: int
    blocks: int
    closed: bool

    @property
    def is_prg(self) -> bool:
        return self.type == "PRG"


def _petscii(raw: bytes) -> str:
    """Turn a padded PETSCII name into readable text."""
    out = []
    for byte in raw:
        if byte == 0xA0:  # padding
            continue
        if 0x41 <= byte <= 0x5A:  # PETSCII upper case letters
            out.append(chr(byte))
        elif 0xC1 <= byte <= 0xDA:  # shifted letters
            out.append(chr(byte - 0x80))
        elif byte < 0x20:
            out.append(" ")
        else:
            out.append(chr(byte))
    return "".join(out).strip()


class D64Image:
    """A D64 image in memory."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 683 * SECTOR_SIZE:
            raise D64Error(
                f"Too small for a D64 ({len(data)} bytes, at least "
                f"{683 * SECTOR_SIZE} expected)"
            )
        self._data = data
        self.tracks = 40 if len(data) >= 768 * SECTOR_SIZE else 35

    # ------------------------------------------------------------------
    # addressing
    # ------------------------------------------------------------------
    def _offset(self, track: int, sector: int) -> int:
        """Byte offset of a sector, or raise when the address is outside."""
        if track < 1 or track > self.tracks:
            raise D64Error(f"Track {track} is outside the image")
        per_track = _SECTORS_PER_TRACK.get(track)
        if per_track is None or sector >= per_track:
            raise D64Error(f"Sector {track}/{sector} is outside the image")
        offset = 0
        for number in range(1, track):
            offset += _SECTORS_PER_TRACK[number] * SECTOR_SIZE
        return offset + sector * SECTOR_SIZE

    def sector(self, track: int, sector: int) -> bytes:
        start = self._offset(track, sector)
        return self._data[start : start + SECTOR_SIZE]

    # ------------------------------------------------------------------
    # directory
    # ------------------------------------------------------------------
    def files(self) -> list[D64File]:
        """Return every entry of the directory, in disk order."""
        entries: list[D64File] = []
        track, sector = DIRECTORY_TRACK, DIRECTORY_SECTOR
        seen: set[tuple[int, int]] = set()
        while track and (track, sector) not in seen:
            seen.add((track, sector))
            block = self.sector(track, sector)
            for index in range(8):
                entry = block[2 + index * 32 : 2 + (index + 1) * 32]
                if len(entry) < 32:
                    continue
                kind = entry[0] & 0x0F
                file_track, file_sector = entry[1], entry[2]
                if kind == 0 or file_track == 0:
                    continue
                entries.append(
                    D64File(
                        name=_petscii(entry[3:19]),
                        type=FILE_TYPES.get(kind, "???"),
                        track=file_track,
                        sector=file_sector,
                        blocks=entry[30] | (entry[31] << 8),
                        closed=bool(entry[0] & 0x80),
                    )
                )
            track, sector = block[0], block[1]
        return entries

    def read(self, entry: D64File) -> bytes:
        """Return the bytes of one file, load address included."""
        chunks: list[bytes] = []
        track, sector = entry.track, entry.sector
        seen: set[tuple[int, int]] = set()
        while True:
            if (track, sector) in seen:
                raise D64Error(f"{entry.name} loops back on itself")
            seen.add((track, sector))
            block = self.sector(track, sector)
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                # Last sector: byte 1 says how many bytes of it are used.
                used = next_sector
                chunks.append(block[2 : 2 + max(0, used - 1)])
                break
            chunks.append(block[2:])
            track, sector = next_track, next_sector
        return b"".join(chunks)

    def first_prg(self) -> tuple[D64File, bytes]:
        """Return the first PRG of the directory and its bytes."""
        for entry in self.files():
            if entry.is_prg:
                data = self.read(entry)
                if len(data) < 3:
                    continue
                return entry, data
        raise D64Error("No PRG on this disk")


def first_prg(data: bytes) -> tuple[str, bytes]:
    """Convenience: name and bytes of the first PRG of an image."""
    entry, payload = D64Image(data).first_prg()
    return entry.name, payload
