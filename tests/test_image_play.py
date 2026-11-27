"""Disk images and programs from the library reach the device by upload."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pkg():
    pkg = types.ModuleType("uc_pkg")
    pkg.__path__ = [str(BASE)]
    sys.modules["uc_pkg"] = pkg
    return pkg


@pytest.fixture()
def api_module():
    _pkg()
    _load("uc_pkg.const", BASE / "const.py")
    return _load("uc_pkg.api", BASE / "api.py")


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, method, path, params=None, data=None, content_type=None, **kw):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params or {},
                "data": data,
                "content_type": content_type,
            }
        )
        return {}


def test_a_disk_image_is_uploaded_as_the_body(api_module):
    api = api_module.UltimateApi(None, "127.0.0.1")
    recorder = _Recorder()
    api._request = recorder  # type: ignore[assignment]

    asyncio.run(
        api.async_mount_drive(
            drive="a", image_bytes=b"DISK", mode="readonly", image_type="d64"
        )
    )

    call = recorder.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/v1/drives/a:mount"
    assert call["data"] == b"DISK"
    assert call["params"] == {"mode": "readonly", "type": "d64"}
    assert call["content_type"] == "application/octet-stream"


def test_a_prg_is_uploaded_to_the_runner(api_module):
    api = api_module.UltimateApi(None, "127.0.0.1")
    recorder = _Recorder()
    api._request = recorder  # type: ignore[assignment]

    asyncio.run(api.async_run_prg_bytes(b"\x01\x08PRG"))

    call = recorder.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/v1/runners:run_prg"
    assert call["data"] == b"\x01\x08PRG"


def test_a_crt_is_uploaded_to_the_runner(api_module):
    api = api_module.UltimateApi(None, "127.0.0.1")
    recorder = _Recorder()
    api._request = recorder  # type: ignore[assignment]

    asyncio.run(api.async_run_crt_bytes(b"C64 CARTRIDGE"))

    call = recorder.calls[0]
    assert call["path"] == "/v1/runners:run_crt"
    assert call["data"] == b"C64 CARTRIDGE"


# ----------------------------------------------------------------------
# autostart: the first PRG of a disk goes to run_prg
# ----------------------------------------------------------------------
class FakeConnection:
    def __init__(self) -> None:
        self.result = None
        self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


def _module():
    """Load websocket_api.py with Home Assistant stubbed out."""
    import types

    hass_mod = types.ModuleType("homeassistant.core")
    hass_mod.HomeAssistant = object
    hass_mod.callback = lambda f: f

    vol = types.ModuleType("voluptuous")

    def _identity(*args, **kwargs):
        return args[0] if args else None

    for name in ("Required", "Optional", "In", "All", "Coerce", "Range"):
        setattr(vol, name, _identity)
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
    const.DISK_EXTENSIONS = {".d64", ".d71", ".d81", ".g64", ".g71"}
    const.SID_EXTENSIONS = {".sid"}
    const.PROGRAM_EXTENSIONS = {".prg", ".crt"}

    api = types.ModuleType("ultimatecontrol.api")

    class UltimateApiError(Exception):
        pass

    class UltimateConnectionError(UltimateApiError):
        pass

    api.UltimateApi = object
    api.UltimateApiError = UltimateApiError
    api.UltimateConnectionError = UltimateConnectionError

    library = types.ModuleType("ultimatecontrol.library")

    class SidLibraryError(Exception):
        pass

    library.SidLibrary = object
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

    pkg = types.ModuleType("ultimatecontrol")
    pkg.__path__ = [str(BASE)]

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
    for name, module in stubs.items():
        sys.modules[name] = module

    spec = importlib.util.spec_from_file_location(
        "ultimatecontrol.websocket_api", BASE / "websocket_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.websocket_api"] = module
    spec.loader.exec_module(module)
    return module, library.SidLibraryError

def _d64_with_demo() -> bytes:
    per = {**{t: 21 for t in range(1, 18)}, **{t: 19 for t in range(18, 25)},
           **{t: 18 for t in range(25, 31)}, **{t: 17 for t in range(31, 36)}}

    def offset(track, sector):
        return sum(per[t] for t in range(1, track)) * 256 + sector * 256

    data = bytearray(683 * 256)
    block = bytearray(256)
    block[0], block[1] = 0, 0
    block[2] = 0x82
    block[3], block[4] = 1, 0
    block[5:9] = b"DEMO"
    block[9:21] = b"\xa0" * 12
    block[32] = 1
    data[offset(18, 1) : offset(18, 1) + 256] = block
    payload = b"\x01\x08\x0b\x08\x0a\x00\x9e"
    sector = bytearray(256)
    sector[0], sector[1] = 0, len(payload) + 1
    sector[2 : 2 + len(payload)] = payload
    data[offset(1, 0) : offset(1, 0) + 256] = sector
    return bytes(data)


def test_autostart_runs_the_first_prg_of_a_disk():
    module, _ = _module()
    api = _Api()
    runtime = types.SimpleNamespace(api=api, last_played=None)
    hass = types.SimpleNamespace(
        data={"ultimatecontrol": {"entry": runtime}},
        async_add_executor_job=_executor,
    )
    connection = FakeConnection()
    library = types.SimpleNamespace(
        find=lambda source, path: _temp_d64(),
        library_dir=Path("/tmp"),
        favorites_dir=Path("/tmp"),
    )
    module._runtime = lambda hass, entry_id: runtime
    module._library = lambda runtime: library

    asyncio.run(
        module.ws_image_play(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "e",
                "path": "DEMOS/DEMO.D64",
                "source": "library",
                "drive": "a",
                "mode": "readonly",
                "autostart": True,
            },
        )
    )

    assert connection.error is None
    assert connection.result["action"] == "mount+run"
    assert connection.result["started"] == "DEMO"
    assert [c["path"] for c in api.calls] == [
        "/v1/drives/a:mount",
        "/v1/runners:run_prg",
    ]


def test_without_autostart_the_disk_is_only_mounted():
    module, _ = _module()
    api = _Api()
    runtime = types.SimpleNamespace(api=api, last_played=None)
    hass = types.SimpleNamespace(
        data={"ultimatecontrol": {"entry": runtime}},
        async_add_executor_job=_executor,
    )
    connection = FakeConnection()
    library = types.SimpleNamespace(
        find=lambda source, path: _temp_d64(),
        library_dir=Path("/tmp"),
        favorites_dir=Path("/tmp"),
    )
    module._runtime = lambda hass, entry_id: runtime
    module._library = lambda runtime: library

    asyncio.run(
        module.ws_image_play(
            hass,
            connection,
            {
                "id": 2,
                "entry_id": "e",
                "path": "DEMOS/DEMO.D64",
                "source": "library",
                "drive": "a",
                "mode": "readonly",
                "autostart": False,
            },
        )
    )

    assert connection.result["action"] == "mount"
    assert [c["path"] for c in api.calls] == ["/v1/drives/a:mount"]


class _Api(_Recorder):
    """A recorder that also answers the two runner calls."""

    async def async_mount_drive(self, drive="a", image_bytes=None, mode="readonly", image_type=None):
        await self(
            "POST",
            f"/v1/drives/{drive}:mount",
            params={"mode": mode, "type": image_type},
            data=image_bytes,
            content_type="application/octet-stream",
        )

    async def async_run_prg_bytes(self, data):
        await self("POST", "/v1/runners:run_prg", data=data, content_type="application/octet-stream")


def _temp_d64() -> Path:
    path = Path(__import__("tempfile").gettempdir()) / "uc_demo.d64"
    path.write_bytes(_d64_with_demo())
    return path


async def _executor(func, *args):
    return func(*args)
