"""Tests for the playlist websocket commands.

The card adds the running tune to a playlist, lists the playlists and plays
one. Home Assistant is stubbed; the store and the queue are the real ones.
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
    def __init__(self):
        self.uploads = []

    async def async_upload_and_play_sid(self, data, song, ssl=None):
        self.uploads.append(song)

    async def async_reset(self):
        pass


class FakeHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _module():
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

    class ConnectionError(Exception):  # noqa: N818
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
    return module


class Lengths:
    def get_length(self, data, index=0):
        return 90.0

    def get_lengths(self, md5):
        return [90.0]

    def get_all_lengths(self, data):
        return [90.0]

    def __len__(self):
        return 1


def _library(tmp_path, lengths):
    spec = importlib.util.spec_from_file_location(
        "ultimatecontrol.library", _PKG / "library.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.library"] = module
    spec.loader.exec_module(module)
    library = module.SidLibrary(tmp_path, lengths)
    library.ensure_dirs()
    folder = library.library_dir / "MUSICIANS" / "H"
    folder.mkdir(parents=True)
    (folder / "A.sid").write_bytes(_sid(2))
    (folder / "B.sid").write_bytes(_sid(1))
    return library


def _setup(tmp_path):
    module = _module()
    lengths = Lengths()
    library = _library(tmp_path, lengths)
    runtime = types.SimpleNamespace(
        api=FakeApi(),
        media_path=tmp_path,
        songlengths=lengths,
        library=library,
        last_played={},
        queue=None,
        queue_listeners=[],
        playlists=None,
    )
    module._runtime = lambda hass, entry_id: runtime
    return module, runtime, FakeHass()


def test_adding_the_running_tune_creates_the_playlist(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "e",
                "name": "Lieblinge",
                "path": "MUSICIANS/H/A.sid",
                "song": 2,
            },
        )
    )
    assert connection.error is None
    assert connection.result["name"] == "Lieblinge"
    assert connection.result["count"] == 1
    assert connection.result["items"][0]["song"] == 2


def test_a_second_tune_is_appended_and_the_first_not_duplicated(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    base = {"id": 1, "entry_id": "e", "name": "p"}
    asyncio.run(
        module.ws_playlist_add(hass, connection, {**base, "path": "MUSICIANS/H/A.sid"})
    )
    asyncio.run(
        module.ws_playlist_add(hass, connection, {**base, "path": "MUSICIANS/H/B.sid"})
    )
    assert connection.result["count"] == 2
    asyncio.run(
        module.ws_playlist_add(hass, connection, {**base, "path": "MUSICIANS/H/A.sid"})
    )
    assert connection.result["count"] == 2


def test_a_list_of_tunes_can_be_added_at_once(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "e",
                "name": "ganz",
                "items": [{"path": "MUSICIANS/H/A.sid"}, {"path": "MUSICIANS/H/B.sid"}],
            },
        )
    )
    assert connection.result["count"] == 2


def test_the_list_shows_the_saved_playlists(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass, connection, {"id": 1, "entry_id": "e", "name": "p", "path": "MUSICIANS/H/A.sid"}
        )
    )
    asyncio.run(module.ws_playlists(hass, connection, {"id": 2, "entry_id": "e"}))
    assert connection.result["playlists"] == [{"name": "p", "count": 1}]


def test_one_playlist_can_be_read_with_all_its_tunes(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass, connection, {"id": 1, "entry_id": "e", "name": "p", "path": "MUSICIANS/H/A.sid"}
        )
    )
    asyncio.run(module.ws_playlist_get(hass, connection, {"id": 2, "entry_id": "e", "name": "p"}))
    assert connection.result["items"][0]["name"] == "A.sid"


def test_an_unknown_playlist_is_reported(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_get(hass, connection, {"id": 1, "entry_id": "e", "name": "gibtsnicht"})
    )
    assert connection.error[0] == "not_found"


def test_playing_a_playlist_fills_the_queue(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "e",
                "name": "p",
                "items": [{"path": "MUSICIANS/H/A.sid", "song": 2}, {"path": "MUSICIANS/H/B.sid"}],
            },
        )
    )
    asyncio.run(module.ws_playlist_play(hass, connection, {"id": 2, "entry_id": "e", "name": "p"}))
    assert connection.error is None
    assert connection.result["count"] == 2
    assert connection.result["playing"] is True
    assert connection.result["title"] == "p"
    # Tune 2 of A.sid was asked for and sent.
    assert runtime.api.uploads == [2]
    runtime.queue.cancel()


def test_playing_an_empty_playlist_is_an_error(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    # An empty playlist is created by clearing an existing one.
    asyncio.run(
        module.ws_playlist_add(
            hass, connection, {"id": 1, "entry_id": "e", "name": "leer", "path": "MUSICIANS/H/A.sid"}
        )
    )
    asyncio.run(
        module.ws_playlist_edit(
            hass, connection, {"id": 2, "entry_id": "e", "name": "leer", "action": "clear"}
        )
    )
    asyncio.run(
        module.ws_playlist_play(hass, connection, {"id": 3, "entry_id": "e", "name": "leer"})
    )
    assert connection.error[0] == "empty"


def test_an_entry_can_be_removed_and_the_playlist_deleted(tmp_path):
    module, runtime, hass = _setup(tmp_path)
    connection = FakeConnection()
    asyncio.run(
        module.ws_playlist_add(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "e",
                "name": "p",
                "items": [{"path": "MUSICIANS/H/A.sid"}, {"path": "MUSICIANS/H/B.sid"}],
            },
        )
    )
    asyncio.run(
        module.ws_playlist_edit(
            hass, connection, {"id": 2, "entry_id": "e", "name": "p", "action": "remove", "index": 0}
        )
    )
    assert connection.result["count"] == 1
    assert connection.result["items"][0]["name"] == "B.sid"
    asyncio.run(
        module.ws_playlist_edit(
            hass, connection, {"id": 3, "entry_id": "e", "name": "p", "action": "delete"}
        )
    )
    assert connection.result["deleted"] is True
