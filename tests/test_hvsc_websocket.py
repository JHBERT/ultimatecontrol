"""Tests for the HVSC websocket commands the card calls.

``hvsc_status`` reports what the installation has and whether a mirror offers a
newer release; ``hvsc_download_songlengths`` fetches the file, loads it and
replaces the running database. Both are imported by file path with Home
Assistant stubbed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"

SONGLENGTHS = """\
[Database]
; /DEMOS/0-9/10_Orbyte.sid
5f08a730b280e54fd1e75a7046b93fdc=1:17
"""


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


def _websocket_module(tmp_path: Path, runtime):
    hass_mod = types.ModuleType("homeassistant.core")
    hass_mod.HomeAssistant = object
    hass_mod.callback = lambda f: f
    vol = types.ModuleType("voluptuous")
    for name in ("Required", "Optional", "In", "All", "Coerce", "Range"):
        setattr(vol, name, lambda *a, **k: a[0] if a else None)
    vol.Schema = object

    ws_mod = types.ModuleType("homeassistant.components.websocket_api")
    ws_mod.websocket_command = lambda *a, **k: (lambda f: f)
    ws_mod.async_response = lambda f: f
    ws_mod.async_register_command = lambda *a, **k: None
    ws_mod.ActiveConnection = object

    class ConnectionError(Exception):  # noqa: N818 - mirrors HA's own class
        def __init__(self, code, message):
            super().__init__(message)
            self.code = code

    ws_mod.ConnectionError = ConnectionError

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

    library = types.ModuleType("ultimatecontrol.library")
    library.SidLibrary = object

    class SidLibraryError(Exception):
        pass

    library.SidLibraryError = SidLibraryError

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
    runtime_mod = types.ModuleType("ultimatecontrol.runtime_data")
    runtime_mod.UltimateControlRuntimeData = object

    songlengths = _load(
        "ultimatecontrol.songlengths", _PKG / "songlengths.py", {}
    )

    pkg = types.ModuleType("ultimatecontrol")
    pkg.__path__ = [str(_PKG)]

    stubs = {
        "homeassistant": ha_root,
        "homeassistant.config_entries": config_entries,
        "ultimatecontrol.runtime_data": runtime_mod,
        "homeassistant.core": hass_mod,
        "homeassistant.components": components,
        "homeassistant.components.http": http_mod,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.components.websocket_api": ws_mod,
        "voluptuous": vol,
        "ultimatecontrol.const": const,
        "ultimatecontrol.library": library,
        "ultimatecontrol.api": api,
        "ultimatecontrol": pkg,
    }
    module = _load("ultimatecontrol.websocket_api", _PKG / "websocket_api.py", stubs)
    module._runtime = lambda hass, entry_id: runtime
    return module, songlengths


class EmptyDatabase:
    """Stands in for a SongLengthsDatabase with no entries."""

    def __len__(self):
        return 0


def _runtime(tmp_path: Path):
    return types.SimpleNamespace(
        media_path=tmp_path,
        songlengths=EmptyDatabase(),
        library=None,
    )


def test_status_reports_missing_songlengths_and_the_local_release(tmp_path):
    runtime = _runtime(tmp_path)
    documents = tmp_path / "C64Music" / "DOCUMENTS"
    documents.mkdir(parents=True)
    (documents / "HVSC.txt").write_text("Release 83\n", encoding="utf-8")
    module, _ = _websocket_module(tmp_path, runtime)
    hass = FakeHass(tmp_path)

    class Session:
        pass

    import ultimatecontrol.hvsc_download as download

    async def fake_release(session):
        return 85

    download.async_remote_release = fake_release
    connection = FakeConnection()
    asyncio.run(module.ws_hvsc_status(hass, connection, {"id": 1, "entry_id": "abc"}))

    result = connection.result
    assert result["local"] == 83
    assert result["remote"] == 85
    assert result["update_available"] is True
    assert result["updates_missing"] == [84, 85]
    assert result["songlengths_file"] is None


def test_status_survives_an_offline_mirror(tmp_path):
    runtime = _runtime(tmp_path)
    module, _ = _websocket_module(tmp_path, runtime)
    hass = FakeHass(tmp_path)

    import ultimatecontrol.hvsc_download as download

    async def broken(session):
        raise download.HvscDownloadError("offline")

    download.async_remote_release = broken
    connection = FakeConnection()
    asyncio.run(module.ws_hvsc_status(hass, connection, {"id": 1, "entry_id": "abc"}))

    assert connection.result["remote"] is None
    assert connection.result["error"] == "offline"
    assert connection.result["update_available"] is False


def test_download_loads_the_database_into_the_runtime(tmp_path):
    runtime = _runtime(tmp_path)
    module, _ = _websocket_module(tmp_path, runtime)
    hass = FakeHass(tmp_path)

    import ultimatecontrol.hvsc_download as download

    async def fake_download(session, target, timeout=0):
        target.write_text(SONGLENGTHS, encoding="utf-8")
        return len(SONGLENGTHS)

    download.async_download_songlengths = fake_download
    connection = FakeConnection()
    asyncio.run(
        module.ws_hvsc_download_songlengths(hass, connection, {"id": 1, "entry_id": "abc"})
    )

    assert connection.result["entries"] == 1
    assert connection.result["bytes"] == len(SONGLENGTHS)
    assert len(runtime.songlengths) == 1


def test_a_failed_download_raises_a_websocket_error(tmp_path):
    runtime = _runtime(tmp_path)
    module, _ = _websocket_module(tmp_path, runtime)
    hass = FakeHass(tmp_path)

    import ultimatecontrol.hvsc_download as download

    async def broken(session, target, timeout=0):
        raise download.HvscDownloadError("no mirror")

    download.async_download_songlengths = broken
    connection = FakeConnection()
    try:
        asyncio.run(
            module.ws_hvsc_download_songlengths(
                hass, connection, {"id": 1, "entry_id": "abc"}
            )
        )
    except Exception as err:  # noqa: BLE001 - the stub connection error
        assert "no mirror" in str(err)
    else:  # pragma: no cover - the handler must not swallow the error
        raise AssertionError("the handler should have raised")
