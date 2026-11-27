"""Read a D64: directory and the first PRG, so a disk can autorun."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def d64():
    return _load("uc_d64", BASE / "d64.py")


def _offset(track: int, sector: int) -> int:
    per = {**{t: 21 for t in range(1, 18)}, **{t: 19 for t in range(18, 25)},
           **{t: 18 for t in range(25, 31)}, **{t: 17 for t in range(31, 36)}}
    return sum(per[t] for t in range(1, track)) * 256 + sector * 256


def _image(entries, payload=b"\x01\x08\x0b\x08\x0a\x00\x9e\x32\x30\x36\x31\x00\x00\x00"):
    data = bytearray(683 * 256)
    # Directory on 18/1: one entry per file, chained to 18/2 for the rest.
    block = bytearray(256)
    block[0], block[1] = 18, 2 if len(entries) > 8 else 0
    for index, entry in enumerate(entries[:8]):
        base = 2 + index * 32
        block[base] = 0x82 if entry.get("closed", True) else 0x02
        block[base + 1] = entry.get("track", 1)
        block[base + 2] = entry.get("sector", 0)
        name = entry["name"].encode("ascii")[:16]
        block[base + 3 : base + 3 + len(name)] = name
        block[base + 3 + len(name) : base + 19] = b"\xa0" * (16 - len(name))
        block[base + 30] = entry.get("blocks", 1)
    data[_offset(18, 1) : _offset(18, 1) + 256] = block
    # One PRG in the first sector of track 1.
    sector = bytearray(256)
    sector[0], sector[1] = 0, len(payload) + 1
    sector[2 : 2 + len(payload)] = payload
    data[_offset(1, 0) : _offset(1, 0) + 256] = sector
    return bytes(data)


def test_the_directory_is_read(d64):
    image = d64.D64Image(_image([{"name": "DEMO"}, {"name": "READ ME", "blocks": 3}]))
    files = image.files()
    assert [f.name for f in files] == ["DEMO", "READ ME"]
    assert files[0].type == "PRG"
    assert files[1].blocks == 3
    assert files[0].closed is True


def test_the_first_prg_is_returned(d64):
    name, payload = d64.first_prg(_image([{"name": "DEMO"}]))
    assert name == "DEMO"
    assert payload.startswith(b"\x01\x08")


def test_a_disk_without_a_prg_is_reported(d64):
    image = d64.D64Image(_image([{"name": "TEXT"}], payload=b""))
    image._data = bytearray(image._data)
    # Turn the only entry into a SEQ file.
    offset = _offset(18, 1) + 2
    image._data[offset] = 0x81
    with pytest.raises(d64.D64Error):
        d64.D64Image(bytes(image._data)).first_prg()


def test_a_short_file_is_refused(d64):
    with pytest.raises(d64.D64Error):
        d64.D64Image(b"too short")


def test_a_track_outside_the_image_is_refused(d64):
    image = d64.D64Image(_image([{"name": "DEMO"}]))
    with pytest.raises(d64.D64Error):
        image.sector(41, 0)
