"""Tests for the per-SID song length array (``.ssl``) sent with an upload.

The Ultimate's SID player plays five minutes unless the tune's play time travels
with the upload: a second ``file`` part holding two packed BCD bytes per sub
tune. These tests pin the byte layout and the multipart request.
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


def _sid(songs: int) -> bytes:
    """A minimal PSID header with the given sub tune count."""
    header = bytearray(124)
    header[0:4] = b"PSID"
    header[4:6] = (2).to_bytes(2, "big")
    header[14:16] = songs.to_bytes(2, "big")
    return bytes(header) + b"\x00" * 16


# ----------------------------------------------------------------------
# BCD encoding
# ----------------------------------------------------------------------
def test_bcd_bytes_are_packed_decimal():
    assert songlengths.bcd_byte(0) == 0x00
    assert songlengths.bcd_byte(5) == 0x05
    assert songlengths.bcd_byte(17) == 0x17
    assert songlengths.bcd_byte(59) == 0x59
    assert songlengths.bcd_byte(99) == 0x99


def test_a_value_above_99_is_clamped():
    assert songlengths.bcd_byte(250) == 0x99


# ----------------------------------------------------------------------
# payload
# ----------------------------------------------------------------------
def test_one_tune_becomes_minutes_then_seconds():
    # 5:17 -> 0x05 0x17
    assert songlengths.build_ssl_payload([317], 1) == bytes([0x05, 0x17])


def test_every_sub_tune_gets_two_bytes():
    payload = songlengths.build_ssl_payload([317, 60, 42], 3)
    assert payload == bytes([0x05, 0x17, 0x01, 0x00, 0x00, 0x42])


def test_unknown_sub_tunes_are_zeroes_so_the_player_keeps_its_default():
    payload = songlengths.build_ssl_payload([317], 3)
    assert payload == bytes([0x05, 0x17, 0x00, 0x00, 0x00, 0x00])


def test_fractions_are_rounded():
    assert songlengths.build_ssl_payload([5.202], 1) == bytes([0x00, 0x05])
    assert songlengths.build_ssl_payload([5.7], 1) == bytes([0x00, 0x06])


def test_an_unknown_tune_produces_no_payload():
    assert songlengths.build_ssl_payload([], 3) is None


def test_the_payload_never_exceeds_the_device_limit():
    payload = songlengths.build_ssl_payload([60.0] * 300, 300)
    assert payload is not None
    assert len(payload) == 512


def test_lengths_are_looked_up_by_the_file_hash():
    database = songlengths.SongLengthsDatabase.from_text(
        "[Database]\n"
        "; /DEMOS/0-9/5th_Demo.sid\n"
        "020ea2a086d380e7a0108e4cff01399f=5:17 1:00 0:42\n"
    )
    sid = _sid(3)
    # The hash of these bytes is unknown, so nothing is sent.
    assert songlengths.ssl_payload_for(sid, database) is None

    # With the real hash in the database the payload matches the sub tunes.
    known = songlengths.SongLengthsDatabase(
        {songlengths.sid_md5(sid): [317.0, 60.0, 42.0]}
    )
    assert songlengths.ssl_payload_for(sid, known) == bytes(
        [0x05, 0x17, 0x01, 0x00, 0x00, 0x42]
    )
