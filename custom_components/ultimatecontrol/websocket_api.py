"""Websocket API and HTTP views for the UltimateControl dashboard.

The dashboard needs three things Home Assistant's media browser cannot give it:

* the sub tune count and the HVSC song length of every SID, so a card can offer
  "Tune 5 of 19 - 3:12" without loading anything onto the C64 first,
* a favourites folder that a plain button can add the current tune to,
* an import from one folder on the Home Assistant host.

Everything here is small and speaks JSON over the existing websocket connection
(or a plain GET for the cover), so a dashboard card needs no extra package.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UltimateApiError, UltimateConnectionError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .library import SidLibrary, SidLibraryError
from .runtime_data import UltimateControlRuntimeData
from .songlengths import count_subtunes

_LOGGER = logging.getLogger(__name__)

SID_MAGIC = (b"PSID", b"RSID")


def _runtime(hass: HomeAssistant, entry_id: str) -> UltimateControlRuntimeData:
    """Return the runtime data of a config entry, or raise a websocket error."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
        raise websocket_api.ConnectionError(
            "unknown_entry", f"No UltimateControl device with id {entry_id}"
        )
    return entry.runtime_data


def _library(runtime: UltimateControlRuntimeData) -> SidLibrary:
    """Return the SID library of a device (created on first use)."""
    library = getattr(runtime, "library", None)
    if library is None:
        library = SidLibrary(runtime.media_path, runtime.songlengths)
        library.ensure_dirs()
        runtime.library = library
    return library


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket commands once for the whole integration."""
    if hass.data.get(f"{DOMAIN}_ws_registered"):
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    websocket_api.async_register_command(hass, ws_browse)
    websocket_api.async_register_command(hass, ws_inspect)
    websocket_api.async_register_command(hass, ws_favorite_add)
    websocket_api.async_register_command(hass, ws_favorite_remove)
    websocket_api.async_register_command(hass, ws_import)
    websocket_api.async_register_command(hass, ws_play)
    websocket_api.async_register_command(hass, ws_current)
    hass.http.register_view(UltimateSidView(hass))


# ----------------------------------------------------------------------
# browsing
# ----------------------------------------------------------------------
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/browse",
        vol.Required("entry_id"): str,
        vol.Optional("source", default="library"): vol.In(("library", "favorites")),
        vol.Optional("path", default=""): str,
    }
)
@websocket_api.async_response
async def ws_browse(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List one folder of the library or of the favourites."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        entries = await hass.async_add_executor_job(
            library.list_dir, msg["source"], msg["path"]
        )
    except SidLibraryError as err:
        connection.send_error(msg["id"], "invalid_path", str(err))
        return
    connection.send_result(
        msg["id"], {"source": msg["source"], "path": msg["path"], "entries": entries}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/inspect",
        vol.Required("entry_id"): str,
        vol.Optional("source", default="library"): vol.In(("library", "favorites")),
        vol.Required("path"): str,
    }
)
@websocket_api.async_response
async def ws_inspect(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a SID's tune count and the HVSC song lengths of every tune."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        path = await hass.async_add_executor_job(library.find, msg["source"], msg["path"])
        info = await hass.async_add_executor_job(library.inspect, path)
    except SidLibraryError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "name": info.name,
            "path": msg["path"],
            "songs": info.songs,
            "lengths": info.lengths,
            "duration": info.duration,
            "md5": info.md5,
            "size": info.size,
        },
    )


# ----------------------------------------------------------------------
# favourites and imports
# ----------------------------------------------------------------------
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/favorite_add",
        vol.Required("entry_id"): str,
        vol.Required("path"): str,
    }
)
@websocket_api.async_response
async def ws_favorite_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Copy a library file into the favourites folder."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        target = await hass.async_add_executor_job(library.add_favorite, msg["path"])
    except SidLibraryError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"path": str(target.relative_to(library.favorites_dir))})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/favorite_remove",
        vol.Required("entry_id"): str,
        vol.Required("path"): str,
    }
)
@websocket_api.async_response
async def ws_favorite_remove(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove one favourite."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    removed = await hass.async_add_executor_job(library.remove_favorite, msg["path"])
    connection.send_result(msg["id"], {"removed": removed})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/import",
        vol.Required("entry_id"): str,
        vol.Required("folder"): str,
        vol.Optional("subfolder", default=""): str,
        vol.Optional("overwrite", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_import(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Copy all SID files of a folder on the Home Assistant host into the library."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    source = Path(msg["folder"]).expanduser()
    if not source.is_absolute():
        connection.send_error(msg["id"], "invalid_path", "Folder must be absolute")
        return
    if not await hass.async_add_executor_job(source.is_dir):
        connection.send_error(msg["id"], "not_found", f"Not a folder: {source}")
        return

    def _copy() -> tuple[list[str], list[str]]:
        imported: list[str] = []
        skipped: list[str] = []
        for file in sorted(source.rglob("*")):
            if not file.is_file() or file.suffix.lower() != ".sid":
                continue
            relative = (
                f"{msg['subfolder'].strip('/')}/{file.relative_to(source).as_posix()}"
                if msg["subfolder"]
                else file.relative_to(source).as_posix()
            )
            try:
                library.import_file(file, relative, overwrite=msg["overwrite"])
                imported.append(relative)
            except SidLibraryError as err:
                skipped.append(f"{relative}: {err}")
        return imported, skipped

    imported, skipped = await hass.async_add_executor_job(_copy)
    connection.send_result(
        msg["id"],
        {"imported": len(imported), "skipped": skipped[:50], "files": imported[:50]},
    )


# ----------------------------------------------------------------------
# playing
# ----------------------------------------------------------------------
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/play",
        vol.Required("entry_id"): str,
        vol.Optional("source", default="library"): vol.In(("library", "favorites")),
        vol.Required("path"): str,
        vol.Optional("song"): vol.All(vol.Coerce(int), vol.Range(min=1, max=256)),
        vol.Optional("device_path"): str,
    }
)
@websocket_api.async_response
async def ws_play(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Play one tune: stream it to the device, or start a file already there.

    ``device_path`` names a SID on the Ultimate itself (the media browser
    knows those); ``path`` names a file in the library or the favourites. The
    library wins when both are given, because its tune count and song length are
    known.
    """
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    api = runtime.api
    song = msg.get("song")

    local_path: Path | None = None
    if msg.get("device_path"):
        device_path = msg["device_path"]
    else:
        try:
            local_path = await hass.async_add_executor_job(
                library.find, msg["source"], msg["path"]
            )
        except SidLibraryError as err:
            connection.send_error(msg["id"], "not_found", str(err))
            return
        device_path = msg["path"]

    try:
        if local_path is not None:
            data = await hass.async_add_executor_job(local_path.read_bytes)
            if data[:4] not in SID_MAGIC:
                connection.send_error(
                    msg["id"], "invalid_format", f"{local_path.name} is not a SID file"
                )
                return
            songs = count_subtunes(data)
            if song is not None and song > songs:
                connection.send_error(
                    msg["id"],
                    "invalid_song",
                    f"{local_path.name} has {songs} tune(s), not {song}",
                )
                return
            # The song length is taken from the HVSC database by the file's
            # hash and goes to the dashboard with the answer.
            md5 = library.inspect(local_path).md5
            length = runtime.songlengths.length_of(md5, (song or 1) - 1)
            await api.async_upload_and_play_sid(data, song)
            runtime.last_played = {
                "name": local_path.name,
                "path": msg["path"],
                "source": msg["source"],
                "song": song or 1,
                "songs": songs,
                "length": length,
            }
        else:
            if song is not None:
                await api.async_play_sid(device_path, song)
            else:
                await api.async_play_sid(device_path)
            length = None
            runtime.last_played = {
                "name": device_path.rsplit("/", 1)[-1],
                "path": device_path,
                "source": "device",
                "song": song or 1,
                "songs": None,
                "length": length,
            }
    except (UltimateApiError, UltimateConnectionError) as err:
        connection.send_error(msg["id"], "device_error", str(err))
        return

    runtime.last_played["song_length"] = length
    connection.send_result(msg["id"], runtime.last_played)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/current", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_current(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return what is playing, so a card can show it and offer "add favourite"."""
    runtime = _runtime(hass, msg["entry_id"])
    connection.send_result(msg["id"], getattr(runtime, "last_played", None) or {})


# ----------------------------------------------------------------------
# the SID file itself (for the file name shown in a card)
# ----------------------------------------------------------------------
class UltimateSidView(HomeAssistantView):
    """Serve a library SID file (used for size/length lookups by a card)."""

    url = f"/api/{DOMAIN}/file/{{entry_id}}/{{path:.+}}"
    name = f"api:{DOMAIN}:file"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Keep the Home Assistant instance."""
        self.hass = hass

    async def get(self, request, entry_id: str, path: str):  # noqa: ANN001
        """Return the raw SID file or its metadata."""
        from aiohttp import web

        runtime = _runtime(self.hass, entry_id)
        library = _library(runtime)
        try:
            file = await self.hass.async_add_executor_job(library.library_file, path)
        except SidLibraryError:
            file = None
        if file is None:
            return web.Response(status=404, text="Not in the library")
        data = await self.hass.async_add_executor_job(file.read_bytes)
        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{file.name}"'},
        )
