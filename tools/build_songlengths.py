"""Parse the HVSC Songlengths.md5 file into the JSON map the integration uses.

Usage:
    python tools/build_songlengths.py Songlengths.md5 [out.json]

The result is a plain ``{"<md5>": [seconds, seconds, ...]}`` map. Copy it to the
Home Assistant config folder as ``ultimatecontrol/Songlengths.json``. The
integration then knows how long each sub tune is and can end a song on its own
instead of leaving the C64 playing forever.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LENGTH_ATTRS = "(GMZB)"


def parse_length(token: str) -> float | None:
    """Parse '3:57' / '1:02.5' / '0:06(G)' into seconds."""
    token = token.strip()
    while token.endswith(")") and "(" in token:
        token = token[: token.rindex("(")]
    if ":" not in token:
        return None
    minutes, _, seconds = token.partition(":")
    try:
        value = int(minutes) * 60 + float(seconds)
    except ValueError:
        return None
    return round(value, 3)


def main(argv: list[str]) -> int:
    """Convert the file given on the command line."""
    if len(argv) < 2:
        print(__doc__)
        return 1
    source = Path(argv[1])
    target = Path(argv[2]) if len(argv) > 2 else source.with_name("Songlengths.json")

    lengths: dict[str, list[float]] = {}
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith((";", "[")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed = [length for token in value.split() if (length := parse_length(token))]
        if key.strip() and parsed:
            lengths[key.strip().lower()] = parsed

    target.write_text(json.dumps(lengths, separators=(",", ":")), encoding="utf-8")
    print(f"{len(lengths)} entries written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
