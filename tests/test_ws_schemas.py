"""Every websocket command must accept the ``entry_id`` the card always sends.

The card's ``_ws`` helper puts ``entry_id`` into every message, and Home
Assistant validates a command against its schema with extra keys forbidden. A
command whose schema does not mention ``entry_id`` therefore fails before its
handler runs, with ``not a valid option at 'entry_id'`` - which is exactly what
happened to the CSDb commands in 1.7.0. This test reads the schemas straight
from the source, so it needs no Home Assistant stubs.
"""

from __future__ import annotations

import ast
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "ultimatecontrol"
SOURCE = BASE / "websocket_api.py"


def _schemas() -> list[tuple[str, set[str]]]:
    """Return (command, keys) for every websocket_command decorator."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    found: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is None:
                continue
            name = getattr(call.func, "attr", getattr(call.func, "id", ""))
            if name != "websocket_command" or not call.args:
                continue
            schema = call.args[0]
            if not isinstance(schema, ast.Dict):
                continue
            keys: set[str] = set()
            for key in schema.keys:
                if isinstance(key, ast.Call) and getattr(key.func, "attr", "") in (
                    "Required",
                    "Optional",
                ):
                    if key.args and isinstance(key.args[0], ast.Constant):
                        keys.add(str(key.args[0].value))
                elif isinstance(key, ast.Constant):
                    keys.add(str(key.value))
            found.append((node.name, keys))
    return found


def test_the_schemas_are_found_at_all():
    schemas = _schemas()
    assert len(schemas) >= 20
    names = [name for name, _ in schemas]
    assert "ws_csdb_front" in names
    assert "ws_devices" in names


def test_every_command_accepts_entry_id():
    """A command that does not mention entry_id rejects the card's message."""
    missing = [
        name
        for name, keys in _schemas()
        if name != "ws_devices" and "entry_id" not in keys
    ]
    assert missing == [], f"ohne entry_id im Schema: {missing}"


def test_devices_is_the_only_command_without_entry_id():
    """``devices`` lists the entries, so it cannot take one."""
    schemas = dict(_schemas())
    assert schemas["ws_devices"] == {"type"}
    assert "entry_id" in schemas["ws_csdb_front"]
    assert "entry_id" in schemas["ws_csdb_list"]
    assert "entry_id" in schemas["ws_csdb_release"]
    assert "entry_id" in schemas["ws_csdb_install"]
