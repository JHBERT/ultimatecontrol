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
