"""Tests for the folder listing that feeds the card's import dialog.

The websocket handler is imported by file path with the Home Assistant pieces
stubbed, and called with a fake connection: what matters is what it lists and
what it refuses.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path, stubs: dict[str, types.ModuleType]):
    for module_name, module in stubs.items():
        sys.modules[module_name] = module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeConnection:
    def __init__(self):
        self.result = None
        self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


class FakeHass:
    def __init__(self, config_dir):
        self.config = types.SimpleNamespace(config_dir=str(config_dir))
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _host_folders_module(tmp_path: Path):
    """Import websocket_api.py with HA and the other modules stubbed."""
    hass_mod = types.ModuleType("homeassistant.core")
    hass_mod.HomeAssistant = object
    hass_mod.callback = lambda f: f
    vol = types.ModuleType("voluptuous")
    for name in ("Required", "Optional", "In", "All", "Coerce", "Range", "Schema"):
        setattr(vol, name, lambda *a, **k: (lambda value=None: value) if name != "Schema" else object)
    vol.Optional = lambda *a, **k: a[0] if a else None
    vol.Required = lambda *a, **k: a[0] if a else None

    ws_mod = types.ModuleType("homeassistant.components.websocket_api")
    ws_mod.websocket_command = lambda *a, **k: (lambda f: f)
    ws_mod.async_response = lambda f: f
    ws_mod.async_register_command = lambda *a, **k: None
    ws_mod.ActiveConnection = object

    const = types.ModuleType("ultimatecontrol.const")
    const.DOMAIN = "ultimatecontrol"
    const.CONF_HOST = "host"
    const.CONF_PASSWORD = "password"
    const.CONF_PORT = "port"
    const.DEFAULT_PORT = 80
    const.SID_CACHE_DIR = "ultimatecontrol"
    api = types.ModuleType("ultimatecontrol.api")
    api.UltimateApi = object
    class UltimateApiError(Exception):
        pass
    class UltimateConnectionError(UltimateApiError):
        pass
    api.UltimateApiError = UltimateApiError
    api.UltimateConnectionError = UltimateConnectionError
    stubs_extra = {"ultimatecontrol.api": api}
    library = types.ModuleType("ultimatecontrol.library")
    library.SidLibrary = object
    class SidLibraryError(Exception):
        pass
    library.SidLibraryError = SidLibraryError

    # "homeassistant.components" must be a package, else the sub module imports
    # inside websocket_api.py cannot resolve.
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    http_mod = types.ModuleType("homeassistant.components.http")
    http_mod.HomeAssistantView = object
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: None
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    ha_root = types.ModuleType("homeassistant")
    ha_root.__path__ = []
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    runtime_data = types.ModuleType("ultimatecontrol.runtime_data")
    runtime_data.UltimateControlRuntimeData = object

    stubs = {
        "homeassistant": ha_root,
        "homeassistant.config_entries": config_entries,
        "ultimatecontrol.runtime_data": runtime_data,
        "homeassistant.core": hass_mod,
        "homeassistant.components": components,
        "homeassistant.components.http": http_mod,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.components.websocket_api": ws_mod,
        "voluptuous": vol,
        "ultimatecontrol.const": const,
        "ultimatecontrol.library": library,
        **stubs_extra,
    }
    pkg = types.ModuleType("ultimatecontrol")
    pkg.__path__ = [str(_PKG)]
    stubs["ultimatecontrol"] = pkg
    # _runtime is not needed for this command; it is called with a dummy entry.
    module = _load("ultimatecontrol.websocket_api", _PKG / "websocket_api.py", stubs)
    module._runtime = lambda hass, entry_id: object()
    return module


def _call(module, hass, path=None):
    connection = FakeConnection()
    msg = {"id": 1, "entry_id": "abc"}
    if path is not None:
        msg["path"] = path
    asyncio.run(module.ws_host_folders(hass, connection, msg))
    return connection


def test_root_lists_the_existing_standard_folders(tmp_path, monkeypatch):
    module = _host_folders_module(tmp_path)
    # The standard roots are absolute; point two of them at the test folder so
    # the test does not depend on the machine it runs on.
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setattr(module, "_IMPORT_ROOTS", (str(tmp_path), str(share)))
    hass = FakeHass(tmp_path)

    connection = _call(module, hass)

    assert connection.error is None
    paths = [entry["path"] for entry in connection.result["entries"]]
    assert str(tmp_path) in paths
    assert str(share) in paths
    assert all(entry["is_dir"] for entry in connection.result["entries"])


def test_a_folder_lists_sub_folders_and_counts_sids(tmp_path):
    module = _host_folders_module(tmp_path)
    folder = tmp_path / "phat"
    (folder / "nested").mkdir(parents=True)
    (folder / "one.sid").write_bytes(b"PSID")
    (folder / "two.SID").write_bytes(b"PSID")
    (folder / "notes.txt").write_text("x")
    hass = FakeHass(tmp_path)

    connection = _call(module, hass, str(folder))

    result = connection.result
    assert result["sid_count"] == 2
    assert [entry["name"] for entry in result["entries"]] == ["nested"]
    assert result["parent"] == str(tmp_path)
    assert result["path"] == str(folder)


def test_a_missing_folder_is_an_error(tmp_path):
    module = _host_folders_module(tmp_path)
    hass = FakeHass(tmp_path)

    connection = _call(module, hass, str(tmp_path / "does-not-exist"))

    assert connection.error is not None
    assert connection.error[0] == "invalid_path"
