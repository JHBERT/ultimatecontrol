"""Tests for the queue websocket commands the card calls.

``queue_play_folder`` builds the queue from a folder, starts the first tune and
arms the timer; ``queue_action`` steps it; ``queue_status`` reports it. Home
Assistant is stubbed, so the device is a recorder and the library a real one on
a temporary folder.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


def _sid(songs: int = 1) -> bytes:
    header = bytearray(124)
    header[0:4] = b"PSID"
    header[4:6] = (2).to_bytes(2, "big")
    header[14:16] = songs.to_bytes(2, "big")
    return bytes(header) + b"\x00" * 32


class FakeConnection:
    def __init__(self):
        self.result = None
        self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


class FakeApi:
    """Records what the queue sends to the device."""

    def __init__(self):
        self.uploads = []
        self.calls = []

    async def async_upload_and_play_sid(self, data, song, ssl=None):
        self.uploads.append((data[:4], song, ssl))

    async def async_reset(self):
        self.calls.append("reset")

    async def async_pause(self):
        self.calls.append("pause")

    async def async_resume(self):
        self.calls.append("resume")


def _module():
    """Load websocket_api.py with Home Assistant stubbed out."""
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
    for name, module in stubs.items():
        sys.modules[name] = module

    spec = importlib.util.spec_from_file_location(
        "ultimatecontrol.websocket_api", _PKG / "websocket_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.websocket_api"] = module
    spec.loader.exec_module(module)
    return module, library.SidLibraryError


class FakeHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _library(tmp_path, songlengths):
    """A real SidLibrary with a small HVSC-style folder tree."""
    import importlib.util as iu

    spec = iu.spec_from_file_location("ultimatecontrol.library", _PKG / "library.py")
    module = iu.module_from_spec(spec)
    sys.modules["ultimatecontrol.library"] = module
    spec.loader.exec_module(module)

    library = module.SidLibrary(tmp_path, songlengths)
    library.ensure_dirs()
    folder = library.library_dir / "MUSICIANS" / "H" / "Hubbard"
    folder.mkdir(parents=True)
    (folder / "Commando.sid").write_bytes(_sid(1))
    (folder / "Monty.sid").write_bytes(_sid(1))
    (folder / "readme.txt").write_text("kein SID", encoding="utf-8")
    return library


class Lengths:
    """A tiny song length database: every file 90 seconds, hash ignored."""

    def __init__(self, seconds=90.0):
        self.seconds = seconds

    def get_length(self, data, index=0):
        return self.seconds

    def get_lengths(self, md5):
        return [self.seconds]

    def get_all_lengths(self, data):
        return [self.seconds]

    def __len__(self):
        return 1


def _setup(tmp_path, seconds=90.0):
    module, _ = _module()
    lengths = Lengths(seconds)
    library = _library(tmp_path, lengths)
    api = FakeApi()
    runtime = types.SimpleNamespace(
        api=api,
        media_path=tmp_path,
        songlengths=lengths,
        library=library,
        last_played={},
        queue=None,
        queue_listeners=[],
    )
    module._runtime = lambda hass, entry_id: runtime
    return module, runtime, api, FakeHass()


def test_play_folder_queues_every_sid_and_starts_the_first(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass,
            connection,
            {"id": 1, "entry_id": "e", "source": "library", "path": "MUSICIANS"},
        )
    )
    assert connection.error is None
    result = connection.result
    # Only SID files are queued, folders are walked through.
    assert result["count"] == 2
    assert [item["name"] for item in result["items"]] == ["Commando.sid", "Monty.sid"]
    assert result["index"] == 0
    assert result["playing"] is True
    assert len(api.uploads) == 1
    runtime.queue.cancel()


def test_the_first_tune_is_uploaded_with_its_length_array(tmp_path):
    module, runtime, api, hass = _setup(tmp_path, seconds=317.0)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    magic, song, ssl = api.uploads[0]
    assert magic == b"PSID"
    assert song == 1
    # 5:17 as packed BCD.
    assert ssl == bytes([0x05, 0x17])
    runtime.queue.cancel()


def test_the_timer_runs_with_the_song_length(tmp_path):
    module, runtime, api, hass = _setup(tmp_path, seconds=90.0)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    # The reported time left is the tune's length plus the small grace.
    assert runtime.queue.state.remaining == 90.5
    runtime.queue.cancel()


def test_an_empty_folder_is_an_error(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    empty = runtime.library.library_dir / "leer"
    empty.mkdir()
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "leer"}
        )
    )
    assert connection.error[0] == "empty"


def test_a_missing_folder_is_reported(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "gibtsnicht"}
        )
    )
    assert connection.error[0] == "not_found"


def test_next_and_previous_step_through_the_folder(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    asyncio.run(
        module.ws_queue_action(hass, connection, {"id": 2, "entry_id": "e", "action": "next"})
    )
    assert connection.result["index"] == 1
    assert len(api.uploads) == 2
    asyncio.run(
        module.ws_queue_action(
            hass, connection, {"id": 3, "entry_id": "e", "action": "previous"}
        )
    )
    assert connection.result["index"] == 0
    runtime.queue.cancel()


def test_stop_resets_the_c64_and_ends_the_queue(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    asyncio.run(
        module.ws_queue_action(hass, connection, {"id": 2, "entry_id": "e", "action": "stop"})
    )
    assert connection.result["playing"] is False
    assert "reset" in api.calls


def test_pause_cancels_the_timer_and_resume_restarts_it(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    asyncio.run(
        module.ws_queue_action(hass, connection, {"id": 2, "entry_id": "e", "action": "pause"})
    )
    assert connection.result["playing"] is False
    assert runtime.queue.state.task is None
    assert "pause" in api.calls

    asyncio.run(
        module.ws_queue_action(hass, connection, {"id": 3, "entry_id": "e", "action": "resume"})
    )
    assert connection.result["playing"] is True
    assert runtime.queue.state.task is not None
    assert "resume" in api.calls
    runtime.queue.cancel()


def test_status_reports_an_empty_queue(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(module.ws_queue_status(hass, connection, {"id": 1, "entry_id": "e"}))
    assert connection.result["count"] == 0
    assert connection.result["playing"] is False


def _sid_with_main(songs: int, start: int) -> bytes:
    header = bytearray(124)
    header[0:4] = b"PSID"
    header[4:6] = (2).to_bytes(2, "big")
    header[14:16] = songs.to_bytes(2, "big")
    header[16:18] = start.to_bytes(2, "big")
    return bytes(header) + b"\x00" * 32


def test_a_folder_plays_each_tunes_main_tune(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    folder = runtime.library.library_dir / "MUSICIANS" / "H" / "Hubbard"
    (folder / "Commando.sid").write_bytes(_sid_with_main(3, 2))
    (folder / "Monty.sid").write_bytes(_sid_with_main(4, 0))
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    songs = [item["song"] for item in connection.result["items"]]
    # Commando asks for tune 2, Monty for its first.
    assert songs == [2, 1]
    # And the first tune the device got is that main tune.
    assert api.uploads[0][1] == 2
    runtime.queue.cancel()


def test_the_queue_status_carries_the_end_time(tmp_path):
    module, runtime, api, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_queue_play_folder(
            hass, connection, {"id": 1, "entry_id": "e", "path": "MUSICIANS"}
        )
    )
    asyncio.run(module.ws_queue_status(hass, connection, {"id": 2, "entry_id": "e"}))
    # A dashboard that is opened later knows what runs and how long it runs.
    assert connection.result["playing"] is True
    assert connection.result["ends_at"] is not None
    assert connection.result["items"][connection.result["index"]]["name"] == "Commando.sid"
    runtime.queue.cancel()
