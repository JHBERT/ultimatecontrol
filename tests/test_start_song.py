"""Tests for the SID's own "main tune".

A SID header names the sub tune to play first (offset 16). The queue must play
that one, not always tune 1, and the dashboard needs it to preselect the right
button.
"""

from __future__ import annotations

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


songlengths = _load("ultimatecontrol.songlengths", _PKG / "songlengths.py")


def _sid(songs: int = 3, start: int = 0, magic: bytes = b"PSID") -> bytes:
    header = bytearray(124)
    header[0:4] = magic
    header[4:6] = (2).to_bytes(2, "big")
    header[14:16] = songs.to_bytes(2, "big")
    header[16:18] = start.to_bytes(2, "big")
    return bytes(header) + b"\x00" * 16


def test_a_header_without_a_start_tune_means_tune_one():
    assert songlengths.start_song(_sid(songs=4, start=0)) == 1


def test_the_header_names_the_main_tune():
    assert songlengths.start_song(_sid(songs=5, start=3)) == 3


def test_a_start_tune_beyond_the_tune_count_is_clamped():
    assert songlengths.start_song(_sid(songs=2, start=9)) == 2


def test_an_rsid_file_has_one_tune():
    assert songlengths.start_song(_sid(songs=4, start=2, magic=b"RSID")) == 1


def test_a_file_that_is_not_a_sid_falls_back_to_tune_one():
    assert songlengths.start_song(b"nope") == 1
