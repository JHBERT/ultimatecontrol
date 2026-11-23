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
from .songlengths import count_subtunes, ssl_payload_for

_LOGGER = logging.getLogger(__name__)

SID_MAGIC = (b"PSID", b"RSID")


def runtime_for(hass: HomeAssistant, entry_id: str) -> UltimateControlRuntimeData:
    """Return the runtime data of one device (raises HomeAssistantError)."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
        from homeassistant.exceptions import HomeAssistantError

        raise HomeAssistantError(f"No UltimateControl device with id {entry_id}")
    return entry.runtime_data


def library_for(runtime: UltimateControlRuntimeData) -> SidLibrary:
    """Return the SID library of a device (same instance as the websocket API)."""
    return _library(runtime)


def _runtime(hass: HomeAssistant, entry_id: str) -> UltimateControlRuntimeData:
    """Return the runtime data of a config entry, or raise a websocket error."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
        raise websocket_api.ConnectionError(
            "unknown_entry",
            "No UltimateControl device with the id "
            f"'{entry_id}'. Configured ids: {', '.join(entry_ids(hass)) or 'none yet'}",
        )
    return entry.runtime_data


def entry_ids(hass: HomeAssistant) -> list[str]:
    """Return the config entry ids of all configured devices."""
    return [entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)]


def _library(runtime: UltimateControlRuntimeData) -> SidLibrary:
    """Return the SID library of a device (created on first use)."""
    library = getattr(runtime, "library", None)
    if library is None:
        library = SidLibrary(runtime.media_path, runtime.songlengths)
        library.ensure_dirs()
        runtime.library = library
    return library


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/devices"})
@websocket_api.async_response
async def ws_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the configured devices: entry id, title and host.

    The card uses this when its ``entry_id`` is missing or wrong, so a dashboard
    keeps working after the entry was re-added (a new id) or when the unique id
    of the device was used instead.
    """
    devices = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = entry.runtime_data
        devices.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "host": entry.data.get(CONF_HOST),
                "unique_id": entry.unique_id,
                "info": (runtime.info if runtime is not None else {}) or {},
            }
        )
    connection.send_result(msg["id"], devices)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket commands once for the whole integration."""
    if hass.data.get(f"{DOMAIN}_ws_registered"):
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    websocket_api.async_register_command(hass, ws_devices)
    websocket_api.async_register_command(hass, ws_browse)
    websocket_api.async_register_command(hass, ws_inspect)
    websocket_api.async_register_command(hass, ws_favorite_add)
    websocket_api.async_register_command(hass, ws_favorite_remove)
    websocket_api.async_register_command(hass, ws_import)
    websocket_api.async_register_command(hass, ws_host_folders)
    websocket_api.async_register_command(hass, ws_play)
    websocket_api.async_register_command(hass, ws_current)
    websocket_api.async_register_command(hass, ws_hvsc_status)
    websocket_api.async_register_command(hass, ws_hvsc_download_songlengths)
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
# importing
# ----------------------------------------------------------------------
# Folders a Home Assistant installation usually has, offered first in the
# import dialog. Only those that exist are returned.
_IMPORT_ROOTS = ("/config", "/share", "/media", "/ssl", "/backup", "/addons", "/local")


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/host_folders",
        vol.Required("entry_id"): str,
        vol.Optional("path"): str,
    }
)
@websocket_api.async_response
async def ws_host_folders(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the folders of the Home Assistant host, for the import dialog.

    Without a path the usual roots are offered; with a path its sub folders,
    so the user picks a folder instead of typing an absolute path.
    """
    _runtime(hass, msg["entry_id"])
    path = (msg.get("path") or "").strip()

    def _list() -> dict[str, Any]:
        if not path:
            roots = [Path(item) for item in _IMPORT_ROOTS]
            # A Home Assistant Core installation keeps /config elsewhere.
            config_dir = Path(hass.config.config_dir)
            if config_dir not in roots:
                roots.insert(0, config_dir)
            existing = [item for item in roots if item.is_dir()]
            return {
                "path": "",
                "parent": None,
                "entries": [
                    {"name": str(item), "path": str(item), "is_dir": True}
                    for item in existing
                ],
                "sid_count": None,
            }

        folder = Path(path).expanduser()
        if not folder.is_dir():
            raise SidLibraryError(f"Not a folder: {folder}")
        entries: list[dict[str, Any]] = []
        sid_count = 0
        try:
            children = sorted(folder.iterdir(), key=lambda item: item.name.lower())
        except OSError as err:
            raise SidLibraryError(str(err)) from err
        for child in children:
            if child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    entries.append(
                        {"name": child.name, "path": str(child), "is_dir": True}
                    )
                elif child.suffix.lower() == ".sid":
                    sid_count += 1
            except OSError:
                continue
        parent = str(folder.parent) if folder.parent != folder else ""
        return {
            "path": str(folder),
            "parent": parent,
            "entries": entries,
            "sid_count": sid_count,
        }

    try:
        result = await hass.async_add_executor_job(_list)
    except SidLibraryError as err:
        connection.send_error(msg["id"], "invalid_path", str(err))
        return
    connection.send_result(msg["id"], result)


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
            # The device's SID player only knows a tune's play time when the
            # length array travels with the upload; without it, it plays five
            # minutes.
            ssl_payload = ssl_payload_for(data, runtime.songlengths)
            await api.async_upload_and_play_sid(data, song, ssl_payload)
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


# ----------------------------------------------------------------------
# HVSC: song lengths and version
# ----------------------------------------------------------------------
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/hvsc_status",
        vol.Required("entry_id"): str,
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_hvsc_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Report the song length database and whether a newer HVSC exists."""
    from . import hvsc_download

    runtime = _runtime(hass, msg["entry_id"])
    documents = runtime.media_path / hvsc_download.DOCUMENTS_PATH
    songlengths_file = await hass.async_add_executor_job(
        hvsc_download.local_songlengths, runtime.media_path
    )
    local = await hass.async_add_executor_job(hvsc_download.local_release, documents)

    remote: int | None = None
    error: str | None = None
    cached = hass.data.get(f"{DOMAIN}_hvsc_remote")
    if msg.get("refresh") or cached is None:
        try:
            session = async_get_clientsession(hass)
            remote = await hvsc_download.async_remote_release(session)
            hass.data[f"{DOMAIN}_hvsc_remote"] = remote
        except Exception as err:  # noqa: BLE001 - offline is not an error state
            error = str(err)
            remote = cached
    else:
        remote = cached

    release = hvsc_download.ReleaseInfo(remote=remote, local=local)
    connection.send_result(
        msg["id"],
        {
            **release.as_dict(),
            "songlengths": len(runtime.songlengths),
            "songlengths_file": str(songlengths_file) if songlengths_file else None,
            "documents_dir": str(documents),
            "error": error,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/hvsc_download_songlengths",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_hvsc_download_songlengths(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Download Songlengths.md5 and load it into the running integration."""
    from . import hvsc_download
    from .songlengths import SongLengthsDatabase

    runtime = _runtime(hass, msg["entry_id"])
    target = runtime.media_path / hvsc_download.SONGLENGTHS_NAME
    try:
        size = await hvsc_download.async_download_songlengths(
            async_get_clientsession(hass), target
        )
    except hvsc_download.HvscDownloadError as err:
        raise websocket_api.ConnectionError("download_failed", str(err)) from err

    database = await hass.async_add_executor_job(SongLengthsDatabase.from_file, target)
    runtime.songlengths = database
    if getattr(runtime, "library", None) is not None:
        runtime.library.songlengths = database
        runtime.library.clear_cache()

    connection.send_result(
        msg["id"], {"bytes": size, "entries": len(database), "path": str(target)}
    )
