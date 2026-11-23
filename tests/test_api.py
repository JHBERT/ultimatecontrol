"""Tests for the Ultimate REST API client.

These tests run without Home Assistant: they start a small aiohttp test server
that answers like an Ultimate II+ and check the request the client builds and
how it reacts to the device's answers.

Run with:  pytest tests -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

# Load the modules by file path: the package __init__ imports Home Assistant,
# which the API client itself does not need.
_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"
_spec = importlib.util.spec_from_file_location(
    "uc_const", _PKG / "const.py"
)
uc_const = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uc_const)
sys.modules["ultimatecontrol"] = type(sys)("ultimatecontrol")
sys.modules["ultimatecontrol.const"] = uc_const
_spec = importlib.util.spec_from_file_location("ultimatecontrol.api", _PKG / "api.py")
api_module = importlib.util.module_from_spec(_spec)
sys.modules["ultimatecontrol.api"] = api_module
_spec.loader.exec_module(api_module)

from ultimatecontrol.api import (  # noqa: E402
    UltimateApi,
    UltimateAuthError,
    UltimateCommandError,
    UltimateConnectionError,
)

class FakeUltimate:
    """Records requests and answers like an Ultimate II+."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.errors: list[str] = []
        self.require_password: str | None = None

    async def handler(self, request: web.Request) -> web.Response:
        if self.require_password is not None:
            if request.headers.get("X-Password") != self.require_password:
                return web.json_response(
                    {"errors": ["Forbidden"]}, status=403
                )
        body = await request.read()
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "body_len": len(body),
                "content_type": request.headers.get("Content-Type"),
                "password": request.headers.get("X-Password"),
            }
        )
        if request.path == "/v1/info":
            return web.json_response(
                {
                    "product": "Ultimate II+",
                    "firmware_version": "3.12",
                    "hostname": "Terakura",
                    "unique_id": "8D927F",
                    "errors": [],
                }
            )
        return web.json_response({"errors": self.errors})


@pytest.fixture
async def device():
    fake = FakeUltimate()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handler)
    server = TestServer(app)
    await server.start_server()
    yield fake, str(server.host), server.port
    await server.close()


@pytest.fixture
async def client(device):
    import aiohttp

    fake, host, port = device
    async with aiohttp.ClientSession() as session:
        yield UltimateApi(session, host, port), fake


async def test_info(client):
    api, fake = client
    info = await api.async_test_connection()
    assert info["product"] == "Ultimate II+"
    assert fake.requests[0]["path"] == "/v1/info"
    assert fake.requests[0]["method"] == "GET"


async def test_sidplay_builds_put_with_file_and_songnr(client):
    api, fake = client
    await api.async_play_sid("/Usb0/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid", 2)
    request = fake.requests[-1]
    assert request["method"] == "PUT"
    assert request["path"] == "/v1/runners:sidplay"
    assert request["query"] == {
        "file": "/Usb0/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid",
        "songnr": "2",
    }


async def test_run_prg_and_crt(client):
    api, fake = client
    await api.async_run_prg("/Usb0/Games/Bubble Bobble.prg")
    assert fake.requests[-1]["path"] == "/v1/runners:run_prg"
    assert fake.requests[-1]["query"] == {"file": "/Usb0/Games/Bubble Bobble.prg"}

    await api.async_run_crt("/Usb0/Carts/Action.crt")
    assert fake.requests[-1]["path"] == "/v1/runners:run_crt"
    assert fake.requests[-1]["query"] == {"file": "/Usb0/Carts/Action.crt"}


async def test_upload_and_play_sid_posts_bytes(client):
    api, fake = client
    await api.async_upload_and_play_sid(b"\x50\x53\x49\x44" + b"\x00" * 20, 1)
    request = fake.requests[-1]
    assert request["method"] == "POST"
    assert request["path"] == "/v1/runners:sidplay"
    assert request["body_len"] == 24
    assert request["content_type"] == "application/octet-stream"


async def test_mount_drive(client):
    api, fake = client
    await api.async_mount_drive("a", image="/Usb0/D64/Giana Sisters.d64")
    request = fake.requests[-1]
    assert request["path"] == "/v1/drives/a:mount"
    assert request["query"] == {
        "mode": "readonly",
        "image": "/Usb0/D64/Giana Sisters.d64",
    }


async def test_password_header_is_sent(client):
    api, fake = client
    api._password = "geheim"  # noqa: SLF001
    await api.async_get_info()
    assert fake.requests[-1]["password"] == "geheim"


async def test_auth_error(client):
    api, fake = client
    fake.require_password = "geheim"
    with pytest.raises(UltimateAuthError):
        await api.async_get_info()


async def test_device_errors_raise(client):
    api, fake = client
    fake.errors = ["Error in command"]
    with pytest.raises(UltimateCommandError):
        await api.async_play_sid("/Usb0/test.sid")


async def test_connection_error():
    import aiohttp

    async with aiohttp.ClientSession() as session:
        api = UltimateApi(session, "127.0.0.1", 1, None)  # nothing listens here
        with pytest.raises(UltimateConnectionError):
            await api.async_get_info()


async def test_list_directory_normalises_shapes(client):
    api, fake = client
    # entries as dicts
    fake.handler = None
    entries = UltimateApi._extract_entries(
        {"files": [{"name": "Games", "type": "dir"}, {"name": "x.sid", "type": "file"}]}
    )
    assert [e["name"] for e in entries] == ["Games", "x.sid"]
    # entries as names, folder marked by trailing slash
    entries = UltimateApi._extract_entries({"files": ["Games/", "x.sid"]})
    assert entries[0] == {"name": "Games", "type": "dir"}
    assert entries[1] == {"name": "x.sid", "type": "file"}
    # entries keyed by name
    entries = UltimateApi._extract_entries(
        {"errors": [], "Games": {"type": "dir"}, "D64": {"type": "dir"}}
    )
    assert [e["name"] for e in entries] == ["Games", "D64"]


async def test_sidplay_upload_sends_the_song_lengths_as_a_second_part(client):
    api, fake = client
    ssl = bytes([0x05, 0x17, 0x01, 0x00])
    await api.async_upload_and_play_sid(b"PSID" + b"\x00" * 60, 2, ssl)
    request = fake.requests[-1]
    assert request["method"] == "POST"
    assert request["path"] == "/v1/runners:sidplay"
    assert request["query"] == {"songnr": "2"}
    assert request["content_type"].startswith("multipart/form-data")
    # Both parts are counted in the body: the SID and the length array.
    assert request["body_len"] > len(ssl) + 64


async def test_sidplay_upload_without_lengths_is_a_plain_body(client):
    api, fake = client
    await api.async_upload_and_play_sid(b"PSID" + b"\x00" * 60)
    request = fake.requests[-1]
    assert request["content_type"] == "application/octet-stream"
    assert request["body_len"] == 64


async def test_an_oversized_length_array_is_refused_before_sending(client):
    api, fake = client
    before = len(fake.requests)
    with pytest.raises(api_module.UltimateApiError):
        await api.async_upload_and_play_sid(b"PSID", None, b"\x00" * 513)
    assert len(fake.requests) == before
