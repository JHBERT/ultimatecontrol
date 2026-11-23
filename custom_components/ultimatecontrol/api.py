"""Small async client for the Ultimate II+ / Ultimate 64 REST API.

Only the subset needed by this integration is implemented:

* ``GET  /v1/info``                       -> :meth:`UltimateApi.async_get_info`
* ``GET  /v1/drives``                     -> :meth:`UltimateApi.async_get_drives`
* ``PUT  /v1/runners:sidplay``            -> :meth:`UltimateApi.async_play_sid`
* ``PUT  /v1/runners:run_prg``            -> :meth:`UltimateApi.async_run_prg`
* ``PUT  /v1/runners:run_crt``            -> :meth:`UltimateApi.async_run_crt`
* ``POST /v1/runners:sidplay`` (upload)   -> :meth:`UltimateApi.async_upload_and_play_sid`
* ``PUT  /v1/drives/<drive>:mount``       -> :meth:`UltimateApi.async_mount_drive`
* ``PUT  /v1/drives/<drive>:remove``      -> :meth:`UltimateApi.async_unmount_drive`
* ``PUT  /v1/machine:reset``              -> :meth:`UltimateApi.async_reset`

API reference: https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html
Every response carries an ``errors`` array; a non-empty array is treated as a
failure, as is any HTTP status outside 2xx.

The client takes a ``ClientSession`` from Home Assistant (``async_get_clientsession``)
so it never has to open its own connection pool.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT, RUNNER_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class UltimateApiError(Exception):
    """Base error for the Ultimate API."""


class UltimateConnectionError(UltimateApiError):
    """The device could not be reached."""


class UltimateAuthError(UltimateApiError):
    """The network password was missing or wrong (HTTP 403)."""


class UltimateCommandError(UltimateApiError):
    """The device answered, but reported one or more errors."""


def _quote_path(path: str) -> str:
    """URL-quote a device file path, keeping the slashes intact."""
    return quote(path, safe="/")


class UltimateApi:
    """Thin wrapper around the Ultimate REST API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
        password: str | None = None,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self.host = host
        self.port = port
        self._password = password or None
        self._base = f"http://{host}:{port}"

    @property
    def base_url(self) -> str:
        """Return the base URL of the device."""
        return self._base

    # ------------------------------------------------------------------
    # low level plumbing
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        """Return the headers every request needs."""
        if self._password:
            # Firmware >= 3.12 accepts (and ignores) the header when no
            # network password is set.
            return {"X-Password": self._password}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Perform one API call and return the decoded JSON body."""
        url = f"{self._base}{path}"
        headers = self._headers()
        if content_type:
            headers["Content-Type"] = content_type

        try:
            async with asyncio.timeout(timeout):
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=ClientTimeout(total=timeout),
                ) as resp:
                    return await self._handle_response(resp, url)
        except TimeoutError as err:
            raise UltimateConnectionError(
                f"Timeout talking to the Ultimate at {self.host}"
            ) from err
        except ClientError as err:
            raise UltimateConnectionError(
                f"Cannot reach the Ultimate at {self.host}: {err}"
            ) from err

    async def _handle_response(
        self, resp: ClientResponse, url: str
    ) -> dict[str, Any]:
        """Validate the HTTP status and the ``errors`` array."""
        if resp.status == 403:
            raise UltimateAuthError(
                "The Ultimate refused the request (HTTP 403). "
                "Check the network password."
            )
        if resp.status >= 400:
            text = await resp.text()
            raise UltimateApiError(
                f"{url} returned HTTP {resp.status}: {text.strip()[:200]}"
            )

        try:
            payload = await resp.json(content_type=None)
        except ValueError:
            # Some commands (machine:reset, poweroff) may answer without a body.
            return {}

        if not isinstance(payload, dict):
            return {}

        errors = payload.get("errors") or []
        if errors:
            raise UltimateCommandError("; ".join(str(err) for err in errors))
        return payload

    # ------------------------------------------------------------------
    # device information
    # ------------------------------------------------------------------
    async def async_get_info(self) -> dict[str, Any]:
        """Return ``/v1/info`` (product, firmware version, hostname, ...)."""
        return await self._request("GET", "/v1/info")

    async def async_get_drives(self) -> dict[str, Any]:
        """Return the state of the emulated floppy drives."""
        return await self._request("GET", "/v1/drives")

    async def async_list_directory(self, path: str) -> list[dict[str, Any]]:
        """Return the entries of one folder on the device.

        Uses ``GET /v1/files/<path>``. Firmware releases answer this route in
        slightly different shapes, so the parsing below accepts a list of
        entries as well as a dict with a list under a common key, and entries
        given either as ``{"name": ..., "type": ...}`` or as plain names.
        """
        clean = "/" + path.strip("/")
        if clean == "/":
            payload = await self._request("GET", "/v1/files/")
        else:
            payload = await self._request("GET", f"/v1/files{_quote_path(clean)}/")
        return self._extract_entries(payload)

    @staticmethod
    def _extract_entries(payload: Any) -> list[dict[str, Any]]:
        """Normalise a /v1/files answer into a list of entry dicts."""
        if isinstance(payload, list):
            raw_entries = payload
        elif isinstance(payload, dict):
            raw_entries = []
            for key in ("files", "entries", "items", "children"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw_entries = value
                    break
            else:
                # A dict keyed by name: {"Games": {"type": "dir"}, ...}
                raw_entries = [
                    {"name": name, **(meta if isinstance(meta, dict) else {})}
                    for name, meta in payload.items()
                    if name not in ("errors", "path", "current") and isinstance(meta, (dict, str))
                ]
        else:
            return []

        entries: list[dict[str, Any]] = []
        for raw in raw_entries:
            if isinstance(raw, str):
                entries.append(
                    {
                        "name": raw.rstrip("/"),
                        "type": "dir" if raw.endswith("/") else "file",
                    }
                )
            elif isinstance(raw, dict):
                name = raw.get("name") or raw.get("filename") or raw.get("path")
                if not name:
                    continue
                entry = dict(raw)
                entry["name"] = str(name).rstrip("/")
                if "type" not in entry:
                    entry["type"] = "dir" if raw.get("is_dir") or str(name).endswith("/") else "file"
                entries.append(entry)
        return entries

    # ------------------------------------------------------------------
    # runners
    # ------------------------------------------------------------------
    async def async_play_sid(self, file_path: str, song_nr: int | None = None) -> None:
        """Play a SID file that already exists on the device."""
        params: dict[str, Any] = {"file": file_path}
        if song_nr is not None:
            params["songnr"] = song_nr
        await self._request(
            "PUT", "/v1/runners:sidplay", params=params, timeout=RUNNER_TIMEOUT
        )

    async def async_upload_and_play_sid(
        self, sid_bytes: bytes, song_nr: int | None = None
    ) -> None:
        """Upload SID bytes to the device and play them in one POST."""
        params: dict[str, Any] = {}
        if song_nr is not None:
            params["songnr"] = song_nr
        await self._request(
            "POST",
            "/v1/runners:sidplay",
            params=params,
            data=sid_bytes,
            content_type="application/octet-stream",
            timeout=RUNNER_TIMEOUT,
        )

    async def async_run_prg(self, file_path: str) -> None:
        """Reset the C64 and run a PRG that exists on the device."""
        await self._request(
            "PUT",
            "/v1/runners:run_prg",
            params={"file": file_path},
            timeout=RUNNER_TIMEOUT,
        )

    async def async_run_crt(self, file_path: str) -> None:
        """Reset the C64 with a CRT cartridge that exists on the device."""
        await self._request(
            "PUT",
            "/v1/runners:run_crt",
            params={"file": file_path},
            timeout=RUNNER_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # drives
    # ------------------------------------------------------------------
    async def async_mount_drive(
        self,
        drive: str = "a",
        image: str | None = None,
        image_bytes: bytes | None = None,
        mode: str = "readonly",
        image_type: str | None = None,
    ) -> None:
        """Mount a disk image, either from the device or uploaded from HA."""
        params: dict[str, Any] = {"mode": mode}
        if image_type:
            params["type"] = image_type

        if image_bytes is not None:
            await self._request(
                "POST",
                f"/v1/drives/{drive}:mount",
                params=params,
                data=image_bytes,
                content_type="application/octet-stream",
                timeout=RUNNER_TIMEOUT,
            )
            return

        if image is None:
            raise ValueError("Either image or image_bytes is required")
        params["image"] = image
        await self._request(
            "PUT", f"/v1/drives/{drive}:mount", params=params, timeout=RUNNER_TIMEOUT
        )

    async def async_unmount_drive(self, drive: str = "a") -> None:
        """Remove the disk image from a drive."""
        await self._request("PUT", f"/v1/drives/{drive}:remove")

    # ------------------------------------------------------------------
    # machine
    # ------------------------------------------------------------------
    async def async_reset(self) -> None:
        """Send a reset to the machine."""
        await self._request("PUT", "/v1/machine:reset")

    async def async_pause(self) -> None:
        """Pause the machine (freezes the CPU)."""
        await self._request("PUT", "/v1/machine:pause")

    async def async_resume(self) -> None:
        """Resume a paused machine."""
        await self._request("PUT", "/v1/machine:resume")

    async def async_test_connection(self) -> dict[str, Any]:
        """Fetch /v1/info and make sure it looks like an Ultimate device."""
        info = await self.async_get_info()
        if "product" not in info and "firmware_version" not in info:
            raise UltimateApiError(
                "The host answered, but not like an Ultimate device "
                "(no product or firmware version in /v1/info)."
            )
        return info
