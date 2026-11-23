"""Download the HVSC song length database and check for HVSC updates.

The High Voltage SID Collection publishes its documents one by one, so a Home
Assistant installation does not need the 80 MB collection to get correct song
lengths:

* ``DOCUMENTS/Songlengths.md5`` - one length per sub tune, keyed by file MD5
* ``DOCUMENTS/HVSC.txt``        - the collection's release ("Release 85")

Both files sit in the collection's *uncompressed* part, which is why they can be
fetched without an unpacker. The full archive is a 7z with the BCJ2 filter,
which neither Python's :mod:`lzma` nor Home Assistant can decode - that is what
``hvsc.py`` will do once the collection itself is imported.

This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Mirrors of the collection. The first one that answers wins; the official page
# links them, and a mirror that is down must not stop a download.
HVSC_MIRRORS = (
    "https://hvsc.brona.dk/HVSC",
    "https://hvsc.c64.org/download",
)

DOCUMENTS_PATH = "C64Music/DOCUMENTS"
SONGLENGTHS_NAME = "Songlengths.md5"
HVSC_TXT_NAME = "HVSC.txt"

# The song length file is ~5 MB; give a slow installation time to fetch it.
DOWNLOAD_TIMEOUT = 120
# The version file is tiny.
VERSION_TIMEOUT = 30
CHUNK_SIZE = 64 * 1024

_RELEASE_RE = re.compile(r"^\s*Release\s+(\d+)\s*$", re.MULTILINE)


class HvscDownloadError(Exception):
    """Neither mirror could deliver a file."""


@dataclass(slots=True)
class ReleaseInfo:
    """The release a mirror offers and what the local installation has."""

    remote: int | None
    local: int | None

    @property
    def update_available(self) -> bool:
        """Return True when the mirror has a newer release than the local one."""
        if self.remote is None or self.local is None:
            return False
        return self.remote > self.local

    @property
    def updates_missing(self) -> list[int]:
        """Return the update numbers between the local and the remote release."""
        if not self.update_available:
            return []
        return list(range(self.local + 1, self.remote + 1))

    def as_dict(self) -> dict[str, object]:
        """Return the payload for the websocket API."""
        return {
            "remote": self.remote,
            "local": self.local,
            "update_available": self.update_available,
            "updates_missing": self.updates_missing,
        }


def parse_release(text: str) -> int | None:
    """Return the release number of an ``HVSC.txt``."""
    match = _RELEASE_RE.search(text)
    return int(match.group(1)) if match else None


async def async_fetch_text(
    session,  # aiohttp.ClientSession
    name: str,
    *,
    timeout: int = VERSION_TIMEOUT,
) -> str:
    """Fetch one document of the collection from the first mirror that has it."""
    path = f"{DOCUMENTS_PATH}/{name}"
    errors: list[str] = []
    for mirror in HVSC_MIRRORS:
        url = f"{mirror}/{path}"
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    errors.append(f"{url}: HTTP {response.status}")
                    continue
                return await response.text(errors="replace")
        except Exception as err:  # noqa: BLE001 - a dead mirror must not stop us
            errors.append(f"{url}: {err}")
    raise HvscDownloadError("; ".join(errors) or f"Could not fetch {name}")


async def async_remote_release(session) -> int | None:
    """Return the release number the mirrors currently offer."""
    text = await async_fetch_text(session, HVSC_TXT_NAME)
    return parse_release(text)


def local_release(documents_dir: Path) -> int | None:
    """Return the release of the collection installed on the host, if any."""
    path = documents_dir / HVSC_TXT_NAME
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_release(text)


def local_songlengths(data_dir: Path) -> Path | None:
    """Return the installed song length file, if there is one.

    The integration keeps its own copy directly in its data folder; an imported
    collection keeps it below ``C64Music/DOCUMENTS``.
    """
    for candidate in (
        data_dir / SONGLENGTHS_NAME,
        data_dir / DOCUMENTS_PATH / SONGLENGTHS_NAME,
    ):
        if candidate.is_file():
            return candidate
    return None


async def async_download_songlengths(
    session, target: Path, *, timeout: int = DOWNLOAD_TIMEOUT
) -> int:
    """Download ``Songlengths.md5`` to ``target``; returns the file size.

    The file is written to a temporary name and moved into place only when the
    download finished, so a dropped connection never leaves a half file that the
    integration would then parse.
    """
    path = f"{DOCUMENTS_PATH}/{SONGLENGTHS_NAME}"
    errors: list[str] = []
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    for mirror in HVSC_MIRRORS:
        url = f"{mirror}/{path}"
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    errors.append(f"{url}: HTTP {response.status}")
                    continue
                written = 0
                with temporary.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        handle.write(chunk)
                        written += len(chunk)
            if written == 0:
                errors.append(f"{url}: empty file")
                continue
            temporary.replace(target)
            _LOGGER.info("Downloaded %s song lengths (%s bytes) to %s", written, written, target)
            return written
        except Exception as err:  # noqa: BLE001
            errors.append(f"{url}: {err}")
            temporary.unlink(missing_ok=True)
    raise HvscDownloadError("; ".join(errors) or "No mirror delivered the file")
