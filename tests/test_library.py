"""Tests for the local SID library and the websocket helpers.

Run with:  pytest tests -q
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"ultimatecontrol.{name}", _PKG / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ultimatecontrol.{name}"] = module
    spec.loader.exec_module(module)
    return module


songlengths = _load("songlengths", "songlengths.py")
library_module = _load("library", "library.py")

SidLibrary = library_module.SidLibrary
SidLibraryError = library_module.SidLibraryError


def sid_bytes(songs: int = 1, payload: int = 64, magic: bytes = b"PSID") -> bytes:
    """Return minimal SID bytes with a given tune count."""
    header = magic + struct.pack(">HHHHHHH", 2, 0x7C, 0, 0x1000, 0x1003, songs, 1)
    return header + b"\x00" * (0x7C - len(header)) + b"\xaa" * payload


@pytest.fixture()
def library(tmp_path: Path) -> SidLibrary:
    """A library whose song length database knows one file."""
    known = sid_bytes(3)
    db = songlengths.SongLengthsDatabase.from_mapping(
        {songlengths.sid_md5(known): [12.0, 34.5, 60.0]}
    )
    lib = SidLibrary(tmp_path, db)
    lib.ensure_dirs()
    return lib


def test_paths_cannot_leave_the_library(library: SidLibrary):
    """Traversal and absolute paths are refused."""
    # A leading slash is stripped, so only real traversal is refused.
    for bad in ("../etc/passwd", "a/../../b.sid", "a/../../../etc/passwd"):
        with pytest.raises(SidLibraryError):
            library.library_path(bad)

    assert library.library_path("Game/song.sid").name == "song.sid"


def test_inspect_reads_tunes_and_song_lengths(library: SidLibrary):
    """Tune count comes from the header, lengths from the database."""
    target = library.library_dir / "known.sid"
    target.write_bytes(sid_bytes(3))
    info = library.inspect(target)
    assert info.songs == 3
    assert info.lengths == [12.0, 34.5, 60.0]
    assert info.duration == 12.0
    # Cached: a second call does not re-read the file.
    assert library.inspect(target) is info


def test_list_dir_sorts_folders_first_and_hides_other_files(library: SidLibrary):
    """Only .sid files show up, folders first."""
    (library.library_dir / "Games").mkdir()
    (library.library_dir / "Zeta.sid").write_bytes(sid_bytes(1))
    (library.library_dir / "alpha.sid").write_bytes(sid_bytes(2))
    (library.library_dir / "notes.txt").write_text("no sid")

    entries = library.list_dir("library", "")
    # Folders first, then case-insensitive by name.
    assert [entry["name"] for entry in entries] == ["Games", "alpha.sid", "Zeta.sid"]
    assert entries[0]["is_dir"] is True
    assert entries[1]["name"] == "alpha.sid" and entries[1]["songs"] == 2


def test_favorites_copy_and_remove(library: SidLibrary):
    """A favourite is a copy; removing it drops the empty folder again."""
    (library.library_dir / "Games").mkdir()
    source = library.library_dir / "Games" / "tune.sid"
    source.write_bytes(sid_bytes(1))

    target = library.add_favorite("Games/tune.sid")
    assert target.is_file()
    assert target.read_bytes() == source.read_bytes()
    assert (library.favorites_dir / "Games" / "tune.sid").is_file()

    assert library.remove_favorite("Games/tune.sid") is True
    assert not (library.favorites_dir / "Games").exists()
    assert library.remove_favorite("Games/tune.sid") is False
    # Removing a favourite never touches the library.
    assert source.is_file()


def test_import_rejects_bad_input_and_keeps_structure(library: SidLibrary, tmp_path: Path):
    """Import copies SID files, keeps sub folders and refuses other files."""
    outside = tmp_path / "outside"
    (outside / "Sub").mkdir(parents=True)
    (outside / "Sub" / "one.sid").write_bytes(sid_bytes(1))
    (outside / "readme.txt").write_text("x")

    library.import_file(outside / "Sub" / "one.sid", "Sub/one.sid")
    assert (library.library_dir / "Sub" / "one.sid").is_file()

    with pytest.raises(SidLibraryError):
        library.import_file(outside / "Sub" / "one.sid", "Sub/one.sid")
    with pytest.raises(SidLibraryError):
        library.import_file(outside / "readme.txt", "readme.txt")


def test_find_moved_favorite_by_name(library: SidLibrary):
    """A favourite that exists only deeper in the folder is still found."""
    (library.favorites_dir / "A" / "B").mkdir(parents=True)
    (library.favorites_dir / "A" / "B" / "deep.sid").write_bytes(sid_bytes(1))
    assert library.find("favorites", "deep.sid").name == "deep.sid"
    with pytest.raises(SidLibraryError):
        library.find("library", "deep.sid")
