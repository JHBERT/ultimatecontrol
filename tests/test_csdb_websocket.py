"""The CSDb websocket commands must read the release the card meant.

Home Assistant's websocket client (``sendMessagePromise``) puts the running
command number into ``message.id`` right before sending, so a body key called
``id`` is overwritten by it. ``csdb_release`` therefore opened the release whose
number happened to equal the command counter - the card showed a different demo
than the one clicked. The key is ``release`` now, and this test drives the
handler to prove it uses that and not ``id``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
import types
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


class FakeConnection:
    def __init__(self):
        self.result = None
        self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


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
    ws_mod.ConnectionError = type("ConnectionError", (Exception,), {})

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

    const = types.ModuleType("ultimatecontrol.const")
    const.DOMAIN = "ultimatecontrol"
    const.CONF_HOST = "host"
    const.CONF_PASSWORD = "password"
    const.CONF_PORT = "port"
    const.DEFAULT_PORT = 80

    api = types.ModuleType("ultimatecontrol.api")
    api.UltimateApi = object
    api.UltimateApiError = type("UltimateApiError", (Exception,), {})
    api.UltimateConnectionError = type("UltimateConnectionError", (Exception,), {})

    library = types.ModuleType("ultimatecontrol.library")
    library.SidLibrary = object
    library.SidLibraryError = type("SidLibraryError", (Exception,), {})

    runtime_mod = types.ModuleType("ultimatecontrol.runtime_data")
    runtime_mod.UltimateControlRuntimeData = object

    pkg = types.ModuleType("ultimatecontrol")
    pkg.__path__ = [str(_PKG)]

    for name, module in {
        "homeassistant": ha_root,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": hass_mod,
        "homeassistant.components": components,
        "homeassistant.components.http": http_mod,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.components.websocket_api": ws_mod,
        "voluptuous": vol,
        "ultimatecontrol": pkg,
        "ultimatecontrol.const": const,
        "ultimatecontrol.api": api,
        "ultimatecontrol.library": library,
        "ultimatecontrol.runtime_data": runtime_mod,
    }.items():
        sys.modules[name] = module

    spec = importlib.util.spec_from_file_location(
        "ultimatecontrol.websocket_api", _PKG / "websocket_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.websocket_api"] = module
    spec.loader.exec_module(module)
    module._csdb_cache().clear()
    return module


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


XML = """<?xml version="1.0"?>
<CSDb>
  <Release>
    <ID>{id}</ID>
    <Name>{name}</Name>
    <Type>C64 Demo</Type>
    <ReleaseYear>1989</ReleaseYear>
    <ReleasedBy><Group><Name>Megastyle</Name></Group></ReleasedBy>
    <DownloadLinks/>
    <Credits/>
    <Comments/>
  </Release>
</CSDb>"""


def _patch_fetch(module, seen):
    """Answer the release webservice with the id that was actually asked for."""
    import ultimatecontrol.csdb as csdb

    async def fetch(session, url):
        seen.append(url)
        release_id = int(re.search(r"[?&]id=(\d+)", url).group(1))
        return XML.format(id=release_id, name=f"Release {release_id}")

    csdb.async_fetch_text = fetch
    return csdb


def test_the_handler_opens_the_release_it_was_given():
    module = _module()
    seen = []
    _patch_fetch(module, seen)
    connection = FakeConnection()
    # "id" trägt die Befehlsnummer, "release" die gemeinte Demo.
    asyncio.run(
        module.ws_csdb_release(
            FakeHass(), connection, {"id": 7, "release": 232976, "refresh": True}
        )
    )
    assert connection.error is None
    assert connection.result["id"] == 232976
    assert connection.result["name"] == "Release 232976"
    assert "id=232976" in seen[0]


def test_the_command_number_alone_does_not_decide_the_release():
    module = _module()
    seen = []
    _patch_fetch(module, seen)
    connection = FakeConnection()
    asyncio.run(
        module.ws_csdb_release(
            FakeHass(), connection, {"id": 265370, "release": 82, "refresh": True}
        )
    )
    assert connection.result["id"] == 82
    assert "id=82" in seen[0]


def test_the_cache_is_keyed_by_the_release():
    module = _module()
    seen = []
    _patch_fetch(module, seen)
    for release in (82, 232976):
        connection = FakeConnection()
        asyncio.run(
            module.ws_csdb_release(FakeHass(), connection, {"id": 1, "release": release, "refresh": False})
        )
        assert connection.result["id"] == release
    assert len(seen) == 2
