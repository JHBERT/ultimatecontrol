"""Type into the C64 keyboard buffer over the REST API.

The Ultimate has no "start this disk" command, and ``/v1/machine:input`` (real
key presses) is Ultimate-64 only - on a 1541 Ultimate II+ it answers HTTP 501.
What works on both is the KERNAL's own keyboard buffer: the operating system
reads characters from ``$0277`` and takes the count from ``$00C6``. Writing
those two places with ``PUT /v1/machine:writemem`` is the same as typing, as
long as the C64 sits at the READY prompt.

So a disk is started by mounting it and typing ``LOAD"*",8,1`` followed by
RETURN. This module builds the bytes; it needs no Home Assistant, so it can be
tested on its own.
"""

from __future__ import annotations

# Where the KERNAL keeps the pending keystrokes and how many there are.
KEYBOARD_BUFFER = 0x0277
KEYBOARD_LENGTH = 0x00C6
# The buffer holds at most 10 characters on a stock C64.
BUFFER_SIZE = 10
# writemem takes at most 128 bytes per call.
MAX_WRITEMEM = 128

RETURN = 0x0D

# PETSCII codes for the characters that can be typed unshifted. Letters are the
# upper case range, which is what an unshifted key produces.
_PETSCII = {
    **{chr(code): code for code in range(0x41, 0x5B)},  # A-Z
    **{str(digit): 0x30 + digit for digit in range(10)},
    " ": 0x20,
    "!": 0x21,
    '"': 0x22,
    "#": 0x23,
    "$": 0x24,
    "%": 0x25,
    "&": 0x26,
    "'": 0x27,
    "(": 0x28,
    ")": 0x29,
    "*": 0x2A,
    "+": 0x2B,
    ",": 0x2C,
    "-": 0x2D,
    ".": 0x2E,
    "/": 0x2F,
    ":": 0x3A,
    ";": 0x3B,
    "<": 0x3C,
    "=": 0x3D,
    ">": 0x3E,
    "?": 0x3F,
    "@": 0x40,
    "[": 0x5B,
    "]": 0x5D,
}


class KeyboardError(Exception):
    """The text cannot be typed into the buffer."""


def petscii(text: str) -> bytes:
    """Turn text into the PETSCII bytes the keyboard buffer expects."""
    out = bytearray()
    for char in text:
        upper = char.upper()
        code = _PETSCII.get(char)
        if code is None:
            code = _PETSCII.get(upper)
        if code is None:
            raise KeyboardError(f"Cannot type {char!r} on a C64 keyboard")
        out.append(code)
    return bytes(out)


def type_sequence(text: str, enter: bool = True) -> bytes:
    """The bytes to type, RETURN included."""
    data = petscii(text)
    if enter:
        data += bytes([RETURN])
    return data


def chunks(text: str, enter: bool = True) -> list[bytes]:
    """Split the text into pieces the keyboard buffer can hold.

    The buffer takes ten characters; a longer line is typed in several goes,
    exactly like typing by hand, with the KERNAL emptying the buffer in
    between.
    """
    data = type_sequence(text, enter=enter)
    return [data[start : start + BUFFER_SIZE] for start in range(0, len(data), BUFFER_SIZE)]


def load_command(device: int = 8, secondary: int = 1) -> str:
    """The command that loads the first file of a disk and runs it."""
    return f'LOAD"*",{device},{secondary}'


def start_calls(text: str, enter: bool = True) -> list[tuple[int, bytes]]:
    """The writemem calls that type ``text``: buffer first, then the count.

    Two calls per piece, because the KERNAL only looks at the buffer once the
    length at ``$00C6`` is non zero - writing the count last makes the text
    appear at once instead of character by character.
    """
    calls: list[tuple[int, bytes]] = []
    for piece in chunks(text, enter=enter):
        calls.append((KEYBOARD_BUFFER, piece))
        calls.append((KEYBOARD_LENGTH, bytes([len(piece)])))
    return calls
