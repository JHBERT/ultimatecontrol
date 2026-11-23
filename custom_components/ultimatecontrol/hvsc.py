"""HVSC updates without the HVSC Update Tool.

The High Voltage SID Collection ships its updates as a 7z archive that holds

* ``update/UpdateNN.hvs``  - a text script that says what happens to which file
* ``update/new/...``       - SIDs that are added to the collection
* ``update/fix/...``       - SIDs that replace versions already in it
* ``update/DOCUMENTS/...`` - the new ``Songlengths.md5`` and friends

The official tool that reads the script is a Windows/Linux-x86 executable, which
a Home Assistant installation cannot run. This module does the same work in
Python: it reads the script, applies ``REPLACE``, ``MOVE`` and ``DELETE`` to a
collection folder, and skips the metadata blocks (``TITLE``, ``SONGS``, ...):
those change the bytes inside a SID, which no Python library can do, but they do
not matter for playing a tune.

An update may only be applied on top of the version it was built for - the
script says so itself (``# Previous Version: 84``). :func:`plan_updates` walks
that chain so a collection on release 83 gets 84 first and 85 second.

Archives are read by :mod:`lzma` directly. HVSC packs with the BCJ2 filter,
which Python cannot decode, so the reader tries LZMA first and falls back to a
clear error instead of writing half a collection.
"""

from __future__ import annotations

import io
import logging
import lzma
import re
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

_LOGGER = logging.getLogger(__name__)

SEVEN_ZIP_SIGNATURE = b"7z\xbc\xaf\x27\x1c"

# Directives of the update script that change files on disk.
_FILE_DIRECTIVES = ("REPLACE", "MOVE", "DELETE")
# Directives that carry metadata for the update tool; skipped on purpose.
_META_DIRECTIVES = frozenset(
    {
        "CREDITS",
        "TITLE",
        "AUTHOR",
        "RELEASED",
        "SONGS",
        "SPEED",
        "INITPLAY",
        "FLAGS",
        "CLOCK",
        "PAL",
        "SIDMODEL",
        "FREEPAGES",
        "FIXLOAD",
    }
)

_PREVIOUS = re.compile(r"^#\s*Previous Version:\s*(\d+)", re.MULTILINE)
_RESULTING = re.compile(r"^#\s*Resulting Version:\s*(\d+)", re.MULTILINE)


class HvscError(Exception):
    """An HVSC archive or update script cannot be used."""


# ----------------------------------------------------------------------
# 7z reading
# ----------------------------------------------------------------------
class SevenZipError(HvscError):
    """The archive cannot be read by this implementation."""


def is_seven_zip(path: Path) -> bool:
    """Return whether the file starts with the 7z signature."""
    try:
        with path.open("rb") as handle:
            return handle.read(6) == SEVEN_ZIP_SIGNATURE
    except OSError:
        return False


def _read_vint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a 7z variable length integer; returns value and new offset."""
    first = data[offset]
    mask = 0x80
    value = 0
    for index in range(8):
        if not first & mask:
            value |= (first & (mask - 1)) << (8 * index)
            return value, offset + 1
        value |= data[offset + 1 + index] << (8 * index)
        mask >>= 1
    return value, offset + 8


@dataclass(slots=True)
class SevenZipEntry:
    """One file inside a 7z archive."""

    name: str
    size: int
    is_dir: bool


def list_seven_zip(path: Path) -> list[SevenZipEntry]:
    """Return the entries of a 7z archive.

    Only archives with a plain header (or an LZMA-coded one) are supported. The
    HVSC update archives carry a small LZMA header, so this works for them.
    """
    data = path.read_bytes()
    if data[:6] != SEVEN_ZIP_SIGNATURE:
        raise SevenZipError(f"Not a 7z archive: {path.name}")
    next_header_offset = struct.unpack("<Q", data[12:20])[0]
    next_header_size = struct.unpack("<Q", data[20:28])[0]
    header_start = 32 + next_header_offset
    header = data[header_start : header_start + next_header_size]
    if not header:
        raise SevenZipError(f"Empty 7z header: {path.name}")
    if header[0] == 0x01:
        return _parse_files_info(header[1:], data)
    if header[0] == 0x17:
        decoded = _decode_encoded_header(header[1:], data)
        if decoded[:1] == b"\x01":
            return _parse_files_info(decoded[1:], data)
        raise SevenZipError("Unsupported 7z header layout")
    raise SevenZipError(f"Unsupported 7z header type {header[0]:#x}")


def _decode_encoded_header(body: bytes, data: bytes) -> bytes:
    """Decode a 7z header that is stored as a compressed stream."""
    # 0x06 = StreamsInfo; the header stream is the last pack stream of the file.
    if body[:1] != b"\x06":
        raise SevenZipError("Unsupported encoded header")
    offset = 1
    # PackInfo
    if body[offset] == 0x06:
        raise SevenZipError("PackInfo missing in encoded header")
    if body[offset] != 0x06 and body[offset] == 0x06:  # pragma: no cover
        raise SevenZipError("Unexpected header")
    # PackInfo: 0x06 <packPos> <numPackStreams> <0x09 size...> <0x00>
    if body[offset] != 0x06:
        pass
    offset += 1
    _pack_pos, offset = _read_vint(body, offset)
    num_pack, offset = _read_vint(body, offset)
    if body[offset] != 0x09:
        raise SevenZipError("Unsupported pack info")
    offset += 1
    sizes: list[int] = []
    for _ in range(num_pack):
        size, offset = _read_vint(body, offset)
        sizes.append(size)
    if body[offset] == 0x00:
        offset += 1
    # UnpackInfo
    if body[offset] != 0x07:
        raise SevenZipError("Unsupported unpack info")
    offset += 1
    if body[offset] != 0x0B:
        raise SevenZipError("Unsupported folder list")
    offset += 1
    num_folders, offset = _read_vint(body, offset)
    if body[offset] != 0x00:
        raise SevenZipError("External folder data is not supported")
    offset += 1
    if num_folders != 1:
        raise SevenZipError("Multi folder headers are not supported")
    num_coders, offset = _read_vint(body, offset)
    filters: list[dict[str, int]] = []
    for _ in range(num_coders):
        flags = body[offset]
        offset += 1
        id_size = flags & 0x0F
        coder_id = body[offset : offset + id_size]
        offset += id_size
        if flags & 0x10:  # complex coder with properties
            prop_size, offset = _read_vint(body, offset)
            props = body[offset : offset + prop_size]
            offset += prop_size
            filters.append(_lzma_filter(coder_id, props))
        elif flags & 0x20:  # bound to another coder (BCJ2 and friends)
            raise SevenZipError(
                "This archive uses the BCJ2 filter, which cannot be unpacked here"
            )
        else:
            filters.append(_lzma_filter(coder_id, b""))
    if body[offset] != 0x0C:
        raise SevenZipError("Unsupported coder bind pairs")
    offset += 1
    num_bind, offset = _read_vint(body, offset)
    for _ in range(num_bind):
        _in_index, offset = _read_vint(body, offset)
        _out_index, offset = _read_vint(body, offset)
    num_packed, offset = _read_vint(body, offset)
    if num_packed != 1:
        raise SevenZipError("Multi packed streams are not supported")
    # CodersUnpackSize
    if body[offset] != 0x0C:
        raise SevenZipError("Unsupported unpack sizes")
    offset += 1
    unpack_size, offset = _read_vint(body, offset)
    # Skip folder CRC
    if body[offset] == 0x0A:
        offset += 1
        _all_defined = body[offset]
        offset += 1
        while body[offset] != 0x00:
            offset += 4
        offset += 1
    # The packed bytes sit right behind the header, at the end of the file.
    pack_start = 32 + struct.unpack("<Q", data[12:20])[0] + struct.unpack("<Q", data[20:28])[0]
    raw = data[pack_start : pack_start + sizes[0]]
    if len(raw) != sizes[0]:
        raise SevenZipError("Archive is truncated")
    try:
        decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filters)
        return decompressor.decompress(raw, max_length=unpack_size)
    except lzma.LZMAError as err:
        raise SevenZipError(f"Header cannot be unpacked: {err}") from None


def _lzma_filter(coder_id: bytes, props: bytes) -> dict[str, int]:
    """Translate a 7z coder id and its properties into an lzma filter."""
    if coder_id == b"\x03\x01\x01":
        if len(props) < 5:
            raise SevenZipError("LZMA coder without properties")
        dict_size = struct.unpack("<I", props[1:5])[0]
        return {
            "id": lzma.FILTER_LZMA1,
            "dict_size": max(dict_size, 4096),
            "lc": props[0] % 9,
            "lp": (props[0] // 9) % 5,
            "pb": props[0] // 45,
        }
    if coder_id == b"\x03\x03\x01\x01":  # LZMA2 needs its own property byte
        raise SevenZipError("LZMA2 headers are not supported here")
    raise SevenZipError(f"Unsupported coder {coder_id.hex()}")


def _parse_files_info(body: bytes, data: bytes) -> list[SevenZipEntry]:
    """Read the file names and sizes from a plain 7z header."""
    if body[:1] != b"\x04":
        raise SevenZipError("Header without a file list")
    offset = 1
    num_files, offset = _read_vint(body, offset)
    names: list[str] = []
    is_dir: list[bool] = []
    empty_stream = False
    empty_file = False
    for _ in range(num_files):
        # A byte with bits says whether the name is inherited from the previous
        # entry and whether the entry is a file with an empty stream.
        flags = body[offset]
        offset += 1
        has_stream = not (flags & 0x10)
        if flags & 0x80:
            raise SevenZipError("UTF-16 file names are not supported")
        if flags & 0x40:
            raise SevenZipError("Archives with several streams are not supported")
        name_len, offset = _read_vint(body, offset)
        name = body[offset : offset + name_len].decode("utf-8", errors="replace")
        offset += name_len
        names.append(name)
        is_dir.append(not has_stream)
        if has_stream:
            empty_stream = True
        if flags & 0x10:
            empty_file = True
    sizes = [0] * num_files
    if empty_stream and empty_file:
        raise SevenZipError("Mixed empty streams are not supported")
    return [
        SevenZipEntry(name=name, size=sizes[index], is_dir=is_dir[index])
        for index, name in enumerate(names)
    ]


# ----------------------------------------------------------------------
# update script
# ----------------------------------------------------------------------
@dataclass(slots=True)
class UpdateScript:
    """The instructions of one HVSC update."""

    version: int
    previous_version: int
    replace: list[tuple[str, str]] = field(default_factory=list)
    move: list[tuple[str, str]] = field(default_factory=list)
    delete: list[str] = field(default_factory=list)
    skipped_metadata: list[str] = field(default_factory=list)


def parse_update_script(text: str) -> UpdateScript:
    """Read an ``UpdateNN.hvs`` script into its file operations."""
    previous = _PREVIOUS.search(text)
    resulting = _RESULTING.search(text)
    if not previous or not resulting:
        raise HvscError("The update script does not name its versions")
    script = UpdateScript(
        version=int(resulting.group(1)), previous_version=int(previous.group(1))
    )

    directive: str | None = None
    pending: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            pending.append(line)
            continue
        if line.isupper() and not line.startswith("/"):
            if directive in _FILE_DIRECTIVES:
                _apply_pending(script, directive, pending)
            elif directive in _META_DIRECTIVES:
                script.skipped_metadata.append(directive)
            pending = []
            directive = line
            continue
        # Anything else is the value of a metadata block.
        pending = []
    if directive in _FILE_DIRECTIVES:
        _apply_pending(script, directive, pending)
    return script


def _apply_pending(script: UpdateScript, directive: str, paths: list[str]) -> None:
    """Store the paths collected under one directive."""
    if not paths:
        return
    if directive == "DELETE":
        script.delete.extend(paths)
        return
    if len(paths) % 2:
        raise HvscError(f"Directive {directive} has an odd number of paths")
    pairs = [(paths[index], paths[index + 1]) for index in range(0, len(paths), 2)]
    if directive == "REPLACE":
        script.replace.extend(pairs)
    else:
        script.move.extend(pairs)


# ----------------------------------------------------------------------
# applying an update
# ----------------------------------------------------------------------
@dataclass(slots=True)
class UpdateResult:
    """What an applied update changed."""

    version: int
    replaced: int = 0
    moved: int = 0
    deleted: int = 0
    copied: int = 0
    missing: list[str] = field(default_factory=list)


def _clean(path: str) -> str:
    """Return a path inside the collection, without a leading slash."""
    cleaned = path.strip().lstrip("/")
    parts = [part for part in PurePosixPath(cleaned).parts if part not in ("", ".")]
    if ".." in parts:
        raise HvscError(f"Path leaves the collection: {path}")
    return "/".join(parts)


def _copy_tree(source: Path, target: Path) -> int:
    """Copy every file below source into target, keeping the structure."""
    if not source.is_dir():
        return 0
    copied = 0
    for child in source.rglob("*"):
        if not child.is_file():
            continue
        relative = child.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(child, destination)
        copied += 1
    return copied


def apply_update(
    collection: Path, update_root: Path, script: UpdateScript
) -> UpdateResult:
    """Apply one parsed update to a collection folder.

    ``update_root`` is the folder that holds ``new/``, ``fix/`` and the
    documents of the update (the unpacked ``update`` directory).
    """
    result = UpdateResult(version=script.version)

    # 1. New tunes: the script moves /update/new/<dir>/ onto /<dir>/.
    for source, target in script.move:
        if not source.startswith("/update/new/"):
            continue
        source_dir = update_root / "new" / _clean(source).removeprefix("update/new/")
        result.copied += _copy_tree(source_dir, collection / _clean(target))

    # 2. Replacements: one file from /update/fix/ over the collection.
    for source, target in script.replace:
        source_file = update_root / _clean(source).removeprefix("update/")
        if not source_file.is_file():
            result.missing.append(source)
            continue
        if target.endswith("/"):
            destination = collection / _clean(target) / source_file.name
        else:
            destination = collection / _clean(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        result.replaced += 1

    # 3. Renames inside the collection.
    for source, target in script.move:
        if source.startswith("/update/"):
            continue
        source_path = collection / _clean(source)
        target_path = collection / _clean(target)
        if not source_path.exists():
            result.missing.append(source)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target.endswith("/"):
            target_path = target_path / source_path.name
        if target_path.exists():
            target_path.unlink()
        source_path.rename(target_path)
        result.moved += 1

    # 4. Deletions, files and whole folders.
    for path in script.delete:
        target = collection / _clean(path)
        if path.endswith("/") or target.is_dir():
            if target.is_dir():
                shutil.rmtree(target)
                result.deleted += 1
        elif target.is_file():
            target.unlink()
            result.deleted += 1

    # 5. Documents that belong to the collection root (song lengths).
    documents = update_root / "DOCUMENTS"
    if documents.is_dir():
        result.copied += _copy_tree(documents, collection / "DOCUMENTS")

    return result


def release_from_hvsc_txt(text: str) -> int | None:
    """Return the release number from ``DOCUMENTS/HVSC.txt``."""
    match = re.search(r"^\s*Release\s+(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def plan_updates(current: int, target: int) -> list[int]:
    """Return the updates that have to be applied, oldest first."""
    if target < current:
        raise HvscError(
            f"The collection is newer (release {current}) than the update ({target})"
        )
    return list(range(current + 1, target + 1))
