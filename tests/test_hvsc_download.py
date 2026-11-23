"""Tests for the HVSC song length download and the release check.

Two layers are covered: the pure helpers of ``hvsc_download.py`` (release
parsing, local detection, the update chain) and the websocket handlers, which
are imported by file path with the Home Assistant pieces stubbed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"

HVSC_TXT = """\
-----------------------------------------------------------------------------
                        T H E   H I G H   V O L T A G E
                          S I D   C O L L E C T I O N

                                  Release 85

                                June 28, 2026
"""

SONGLENGTHS = """\
[Database]
; /DEMOS/0-9/10_Orbyte.sid
5f08a730b280e54fd1e75a7046b93fdc=1:17
; /DEMOS/0-9/5th_Demo.sid
020ea2a086d380e7a0108e4cff01399f=5:17 1:00 0:42
"""


def _load(name: str, path: Path, stubs: dict[str, types.ModuleType]):
    for module_name, module in stubs.items():
        sys.modules[module_name] = module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pure_module():
    """Import hvsc_download.py without any Home Assistant stub."""
    spec = importlib.util.spec_from_file_location(
        "ultimatecontrol.hvsc_download", _PKG / "hvsc_download.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.hvsc_download"] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------
# release detection
# ----------------------------------------------------------------------
def test_release_is_read_from_hvsc_txt():
    module = _pure_module()
    assert module.parse_release(HVSC_TXT) == 85


def test_a_file_without_a_release_line_yields_none():
    module = _pure_module()
    assert module.parse_release("nothing here") is None


def test_local_release_is_none_without_a_collection(tmp_path):
    module = _pure_module()
    assert module.local_release(tmp_path / "DOCUMENTS") is None


def test_local_release_is_read_from_the_documents_folder(tmp_path):
    module = _pure_module()
    documents = tmp_path / "C64Music" / "DOCUMENTS"
    documents.mkdir(parents=True)
    (documents / "HVSC.txt").write_text(HVSC_TXT, encoding="utf-8")
    assert module.local_release(documents) == 85


def test_an_old_collection_lists_every_missing_update():
    module = _pure_module()
    release = module.ReleaseInfo(remote=85, local=83)
    assert release.update_available is True
    assert release.updates_missing == [84, 85]


def test_an_up_to_date_collection_has_nothing_to_do():
    module = _pure_module()
    release = module.ReleaseInfo(remote=85, local=85)
    assert release.update_available is False
    assert release.updates_missing == []


def test_an_unknown_local_version_is_not_reported_as_outdated():
    module = _pure_module()
    assert module.ReleaseInfo(remote=85, local=None).update_available is False


# ----------------------------------------------------------------------
# local song length file
# ----------------------------------------------------------------------
def test_installed_songlengths_are_found_in_documents(tmp_path):
    module = _pure_module()
    documents = tmp_path / "C64Music" / "DOCUMENTS"
    documents.mkdir(parents=True)
    target = documents / "Songlengths.md5"
    target.write_text(SONGLENGTHS, encoding="utf-8")
    assert module.local_songlengths(tmp_path) == target


def test_installed_songlengths_are_found_in_the_data_folder(tmp_path):
    module = _pure_module()
    target = tmp_path / "Songlengths.md5"
    target.write_text(SONGLENGTHS, encoding="utf-8")
    assert module.local_songlengths(tmp_path) == target


def test_no_songlengths_file_is_reported_as_missing(tmp_path):
    module = _pure_module()
    assert module.local_songlengths(tmp_path) is None


# ----------------------------------------------------------------------
# download
# ----------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self, errors="strict"):
        return self._body.decode("utf-8", errors)

    @property
    def content(self):
        return FakeContent(self._body)


class FakeContent:
    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, size: int):
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


class FakeSession:
    """A session that answers from a dict of URL suffix -> (status, body)."""

    def __init__(self, routes: dict[str, tuple[int, bytes]]):
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        for suffix, (status, body) in self.routes.items():
            if url.endswith(suffix):
                return FakeResponse(status, body)
        return FakeResponse(404, b"")


def test_songlengths_are_written_when_a_mirror_answers(tmp_path):
    module = _pure_module()
    session = FakeSession(
        {"/C64Music/DOCUMENTS/Songlengths.md5": (200, SONGLENGTHS.encode())}
    )
    target = tmp_path / "Songlengths.md5"

    written = asyncio.run(module.async_download_songlengths(session, target))

    assert written == len(SONGLENGTHS.encode())
    assert target.read_text(encoding="utf-8") == SONGLENGTHS
    assert not (tmp_path / "Songlengths.md5.part").exists()


def test_a_broken_first_mirror_falls_through_to_the_next(tmp_path):
    module = _pure_module()
    module.HVSC_MIRRORS = ("https://broken.invalid", "https://working.invalid")
    session = FakeSession(
        {
            "broken.invalid/C64Music/DOCUMENTS/Songlengths.md5": (500, b""),
            "working.invalid/C64Music/DOCUMENTS/Songlengths.md5": (200, b"x=1:00"),
        }
    )
    target = tmp_path / "Songlengths.md5"

    asyncio.run(module.async_download_songlengths(session, target))

    assert target.read_text() == "x=1:00"
    assert len(session.requested) == 2


def test_no_mirror_leaves_no_half_file_behind(tmp_path):
    module = _pure_module()
    module.HVSC_MIRRORS = ("https://one.invalid",)
    session = FakeSession({"one.invalid/C64Music/DOCUMENTS/Songlengths.md5": (404, b"")})
    target = tmp_path / "Songlengths.md5"

    with pytest.raises(module.HvscDownloadError):
        asyncio.run(module.async_download_songlengths(session, target))

    assert not target.exists()
    assert not (tmp_path / "Songlengths.md5.part").exists()


def test_remote_release_is_read_over_http():
    module = _pure_module()
    session = FakeSession(
        {"/C64Music/DOCUMENTS/HVSC.txt": (200, HVSC_TXT.encode())}
    )
    assert asyncio.run(module.async_remote_release(session)) == 85
