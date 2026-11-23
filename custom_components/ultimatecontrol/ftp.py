"""FTP helper for the Ultimate device (root listing only).

The REST API of firmware 3.x can stat a path and can match a wildcard, but it
cannot enumerate a folder - and on the Ultimate II+ the plain wildcard does not
even see the top-level folders. FTP can: ``NLST /`` returns the root entries.

Home Assistant's global ``filesystem`` pip package is not suitable (it is a local
path helper from 2015), so this module speaks just enough FTP for a listing:
USER/PASS, TYPE A, PASV and NLST. Reads only; nothing is uploaded or removed.
An optional network password is sent as the FTP password.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

FTP_PORT = 21
_PASV_RE = re.compile(r"(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")


class FtpError(Exception):
    """The FTP listing failed."""


@dataclass(slots=True)
class FtpEntry:
    """One entry returned by NLST."""

    name: str
    is_dir: bool


async def _read_reply(
    reader: asyncio.StreamReader, expect: str | None = None
) -> str:
    """Read one (possibly multi-line) FTP reply, optionally checking its code."""
    lines: list[str] = []
    while True:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
        except TimeoutError as err:
            raise FtpError("Timeout waiting for the device's FTP server") from err
        if not raw:
            raise FtpError("The FTP connection closed unexpectedly")
        text = raw.decode(errors="replace").strip()
        lines.append(text)
        # "123-" continues, "123 " ends the reply.
        if len(text) >= 4 and text[3] == "-":
            continue
        break
    reply = "\n".join(lines)
    if expect and not reply.startswith(expect):
        raise FtpError(f"FTP server answered '{reply}' instead of {expect}")
    return reply


async def _send(writer: asyncio.StreamWriter, command: str) -> None:
    """Send one FTP command."""
    writer.write((command + "\r\n").encode())
    await writer.drain()


async def async_list_dir(
    host: str, path: str = "/", password: str | None = None, port: int = FTP_PORT
) -> list[FtpEntry]:
    """Return the entries of one folder over FTP.

    ``NLST`` gives names only, so ``is_dir`` is False for every entry; the
    caller asks the REST API for the type when a folder matters.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10
        )
    except (OSError, TimeoutError) as err:
        raise FtpError(f"Cannot reach the FTP server on {host}: {err}") from err

    try:
        await _read_reply(reader, "220")
        await _send(writer, "USER anonymous")
        await _read_reply(reader, "331")
        await _send(writer, f"PASS {password or 'anonymous'}")
        await _read_reply(reader, "230")
        await _send(writer, "TYPE A")
        await _read_reply(reader, "200")

        await _send(writer, "PASV")
        reply = await _read_reply(reader, "227")
        match = _PASV_RE.search(reply)
        if not match:
            raise FtpError(f"Cannot read the passive address from '{reply}'")
        numbers = [int(part) for part in match.groups()]
        data_host = ".".join(str(part) for part in numbers[:4])
        data_port = numbers[4] * 256 + numbers[5]

        try:
            data_reader, data_writer = await asyncio.wait_for(
                asyncio.open_connection(data_host, data_port), timeout=10
            )
        except (OSError, TimeoutError) as err:
            raise FtpError(f"Cannot open the FTP data connection: {err}") from err

        await _send(writer, f"NLST {path or '/'}")
        await _read_reply(reader, "1")
        try:
            payload = await asyncio.wait_for(data_reader.read(), timeout=15)
        finally:
            data_writer.close()
        await _read_reply(reader, "2")

        entries: list[FtpEntry] = []
        for line in payload.decode(errors="replace").splitlines():
            name = line.strip().lstrip("/")
            if not name or name in (".", ".."):
                continue
            # NLST gives names only; a trailing slash marks a folder on the
            # devices that report it, otherwise the name is used as-is.
            entries.append(
                FtpEntry(name=name.rstrip("/"), is_dir=name.endswith("/"))
            )
        return entries
    finally:
        try:
            await _send(writer, "QUIT")
        except (OSError, FtpError):
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
