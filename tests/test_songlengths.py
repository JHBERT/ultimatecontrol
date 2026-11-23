"""Tests for the HVSC song length database parser.

Run with:  pytest tests -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"
_spec = importlib.util.spec_from_file_location(
    "ultimatecontrol.songlengths", _PKG / "songlengths.py"
)
songlengths = importlib.util.module_from_spec(_spec)
sys.modules["ultimatecontrol.songlengths"] = songlengths
_spec.loader.exec_module(songlengths)

SongLengthsDatabase = songlengths.SongLengthsDatabase
parse_song_lengths_line = songlengths.parse_song_lengths_line
sid_md5 = songlengths.sid_md5

SAMPLE = """[Database]
; /MUSICIANS/H/Hubbard_Rob/Commando.sid
c4c5ff8cfefdf683c50e66775cfac1ee=3:57 1:02 0:06 0:02
; /DEMOS/0-9/10_Orbyte.sid
6897307ef63533962667412848c92124=1:17
; old format with attributes
a08c08aa1c74990c7d753e8c1d2f023e=0:06(G) 0:01(M)
"""


def test_parse_lengths_with_and_without_milliseconds():
    assert parse_song_lengths_line("3:57 1:02.5 0:06.250") == [237.0, 62.5, 6.25]
    assert parse_song_lengths_line("1:17") == [77.0]


def test_parse_lengths_ignores_attribute_markers():
    assert parse_song_lengths_line("0:06(G) 0:01(M)") == [6.0, 1.0]


def test_parse_lengths_ignores_garbage():
    assert parse_song_lengths_line("") == []
    assert parse_song_lengths_line("abc 1:2") == []


def test_database_lookup_by_md5():
    db = SongLengthsDatabase.from_text(SAMPLE)
    assert len(db) == 3

    class FakeSid(bytes):
        pass

    # Build bytes whose md5 we control by using the known hash of b""
    db._lengths[sid_md5(b"")] = [10.0, 20.5]  # noqa: SLF001
    assert db.get_length(b"", 0) == 10.0
    assert db.get_length(b"", 1) == 20.5
    assert db.get_length(b"", 2) is None
    assert db.get_length(b"unknown sid", 0) is None
    assert db.get_all_lengths(b"") == [10.0, 20.5]


def test_empty_database():
    db = SongLengthsDatabase()
    assert db.is_empty
    assert db.get_length(b"anything", 0) is None


def test_from_file_missing(tmp_path: Path):
    db = SongLengthsDatabase.from_file(tmp_path / "nope.md5")
    assert db.is_empty


def test_from_file(tmp_path: Path):
    path = tmp_path / "Songlengths.md5"
    path.write_text(SAMPLE, encoding="utf-8")
    db = SongLengthsDatabase.from_file(path)
    assert len(db) == 3


def test_count_subtunes_reads_psid_header():
    """The header count is read; 0 means one tune and RSID is always one."""
    import struct

    def sid(magic: bytes, songs: int) -> bytes:
        header = magic + struct.pack(">HHHHHHH", 2, 0x7C, 0, 0x1000, 0x1003, songs, 1)
        return header + b"\x00" * 8

    count_subtunes = songlengths.count_subtunes
    assert count_subtunes(sid(b"PSID", 1)) == 1
    assert count_subtunes(sid(b"PSID", 0)) == 1  # 0 means "one tune"
    assert count_subtunes(sid(b"PSID", 19)) == 19
    assert count_subtunes(sid(b"RSID", 9)) == 1
    assert count_subtunes(b"not a sid") == 1
