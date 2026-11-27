"""Typing into the C64 keyboard buffer: PETSCII, the buffer and writemem."""

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
def kb():
    return _load("uc_keyboard", BASE / "keyboard.py")


def test_the_load_command_is_the_classic_one(kb):
    assert kb.load_command() == 'LOAD"*",8,1'
    assert kb.load_command(device=9, secondary=0) == 'LOAD"*",9,0'


def test_petscii_uses_the_upper_case_range(kb):
    assert kb.petscii("LOAD") == bytes([0x4C, 0x4F, 0x41, 0x44])
    assert kb.petscii("8,1") == bytes([0x38, 0x2C, 0x31])
    assert kb.petscii('"*"') == bytes([0x22, 0x2A, 0x22])
    assert kb.petscii("run") == kb.petscii("RUN")


def test_a_character_that_cannot_be_typed_is_refused(kb):
    with pytest.raises(kb.KeyboardError):
        kb.petscii("ä")


def test_the_sequence_ends_with_return(kb):
    assert kb.type_sequence("RUN") == bytes([0x52, 0x55, 0x4E, 0x0D])
    assert kb.type_sequence("RUN", enter=False) == bytes([0x52, 0x55, 0x4E])


def test_a_long_line_is_split_into_buffer_sized_pieces(kb):
    line = 'LOAD"*",8,1'
    assert len(kb.type_sequence(line)) == 12  # 11 + RETURN
    pieces = kb.chunks(line)
    assert [len(piece) for piece in pieces] == [10, 2]
    assert b"".join(pieces) == kb.type_sequence(line)


def test_the_length_is_written_after_each_piece(kb):
    calls = kb.start_calls('LOAD"*",8,1')
    assert [address for address, _ in calls] == [0x0277, 0x00C6, 0x0277, 0x00C6]
    assert calls[0][1] == kb.type_sequence('LOAD"*",8,1')[:10]
    assert calls[1][1] == bytes([10])
    assert calls[2][1] == kb.type_sequence('LOAD"*",8,1')[10:]
    assert calls[3][1] == bytes([2])
