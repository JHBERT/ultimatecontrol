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
from .csdb import FRONT_URL
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .library import SidLibrary, SidLibraryError
from .runtime_data import UltimateControlRuntimeData
from .songlengths import count_subtunes, ssl_payload_for, start_song

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
    websocket_api.async_register_command(hass, ws_image_play)
    websocket_api.async_register_command(hass, ws_current)
    websocket_api.async_register_command(hass, ws_hvsc_status)
    websocket_api.async_register_command(hass, ws_hvsc_download_songlengths)
    websocket_api.async_register_command(hass, ws_queue_play_folder)
    websocket_api.async_register_command(hass, ws_queue_action)
    websocket_api.async_register_command(hass, ws_queue_status)
    websocket_api.async_register_command(hass, ws_playlists)
    websocket_api.async_register_command(hass, ws_playlist_get)
    websocket_api.async_register_command(hass, ws_playlist_add)
    websocket_api.async_register_command(hass, ws_playlist_edit)
    websocket_api.async_register_command(hass, ws_playlist_play)
    websocket_api.async_register_command(hass, ws_csdb_front)
    websocket_api.async_register_command(hass, ws_csdb_list)
    websocket_api.async_register_command(hass, ws_csdb_release)
    websocket_api.async_register_command(hass, ws_csdb_install)
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
        # true: einen einzelnen Tune melden (für „zur Playlist hinzufügen“),
        # auch wenn er in einem Unterordner liegt.
        vol.Optional("file", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_browse(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List one folder of the library or of the favourites."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    if msg.get("file"):
        try:
            path = await hass.async_add_executor_job(
                library.find, msg["source"], msg["path"]
            )
            info = await hass.async_add_executor_job(library.inspect, path)
        except SidLibraryError as err:
            connection.send_error(msg["id"], "not_found", str(err))
            return
        connection.send_result(
            msg["id"],
            {
                "source": msg["source"],
                "path": msg["path"],
                "file": {
                    "name": info.name,
                    "path": msg["path"],
                    "songs": info.songs,
                    "duration": info.duration,
                },
            },
        )
        return
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
            "start_song": info.start_song,
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
        vol.Required("type"): f"{DOMAIN}/image_play",
        vol.Required("entry_id"): str,
        vol.Required("path"): str,
        vol.Optional("source", default="library"): vol.In(("library", "favorites")),
        vol.Optional("drive", default="a"): vol.In(("a", "b")),
        vol.Optional("mode", default="readonly"): vol.In(
            ("readonly", "readwrite", "unlinked")
        ),
        vol.Optional("autostart", default=False): bool,
        vol.Optional("autostart_method", default="prg"): vol.In(
            ("prg", "keyboard", "none")
        ),
        vol.Optional("load_command"): str,
    }
)
@websocket_api.async_response
async def ws_image_play(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Start a disk image, program or cartridge from the library on the device.

    A disk image is uploaded and mounted (``POST /v1/drives/<drive>:mount``
    takes the image as the request body); PRG and CRT go through the runners,
    which also accept an attachment. Nothing has to be copied to the Ultimate
    beforehand.

    With ``autostart`` the disk is started. ``autostart_method`` picks how:

    ``prg`` (default) pulls the first PRG out of the image and hands it to
    ``run_prg``, which loads and runs it in one go. ``keyboard`` resets the
    machine and types ``LOAD"*",8,1`` plus RETURN into the KERNAL keyboard
    buffer over ``writemem`` - that is the classic way, and it also works for
    an image whose directory cannot be read here. ``none`` only mounts, which
    is what a multi part demo wants: the running demo asks for the next disk
    and the drive just has to carry it.
    """
    from .const import DISK_EXTENSIONS
    from .d64 import D64Error, D64Image
    from .const import KEYBOARD_DELAY
    from .keyboard import load_command

    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        path = await hass.async_add_executor_job(library.find, msg["source"], msg["path"])
    except SidLibraryError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    suffix = path.suffix.lower()
    started: str | None = None
    try:
        data = await hass.async_add_executor_job(path.read_bytes)
    except OSError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    try:
        if suffix in DISK_EXTENSIONS:
            await runtime.api.async_mount_drive(
                drive=msg["drive"],
                image_bytes=data,
                mode=msg["mode"],
                image_type=suffix.lstrip("."),
            )
            action = "mount"
            if (
                msg["autostart"]
                and msg.get("autostart_method", "prg") != "none"
                and suffix in (".d64", ".d71")
            ):
                if msg.get("autostart_method", "prg") == "keyboard":
                    command = msg.get("load_command") or load_command()
                    await runtime.api.async_reset()
                    # Der C64 braucht einen Moment, bis der READY-Prompt steht.
                    await asyncio.sleep(KEYBOARD_DELAY)
                    await runtime.api.async_type_text(command)
                    action = "mount+type"
                    started = command
                else:
                    try:
                        entry, program = D64Image(data).first_prg()
                    except D64Error as err:
                        connection.send_error(msg["id"], "no_autostart", str(err))
                        return
                    await runtime.api.async_run_prg_bytes(program)
                    action = "mount+run"
                    started = entry.name
        elif suffix == ".prg":
            await runtime.api.async_run_prg_bytes(data)
            action = "run_prg"
        elif suffix == ".crt":
            await runtime.api.async_run_crt_bytes(data)
            action = "run_crt"
        else:
            connection.send_error(
                msg["id"],
                "invalid_format",
                f"{path.name} is not a disk image, PRG or CRT",
            )
            return
    except UltimateApiError as err:
        connection.send_error(msg["id"], "device_error", str(err))
        return
    runtime.last_played = {
        "source": msg["source"],
        "path": msg["path"],
        "name": path.name,
        "kind": suffix.lstrip("."),
        "action": action,
    }
    connection.send_result(
        msg["id"],
        {
            "path": msg["path"],
            "name": path.name,
            "kind": suffix.lstrip("."),
            "action": action,
            "started": started,
            "method": msg.get("autostart_method", "prg") if msg["autostart"] else None,
        },
    )


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
            # Without a tune number the SID's own main tune plays, not always
            # the first one.
            start = start_song(data)
            if song is None:
                song = start if start <= songs else 1
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
                "start_song": start,
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


# ----------------------------------------------------------------------
# Folder queue
# ----------------------------------------------------------------------
def queue_for(runtime: UltimateControlRuntimeData) -> Any:
    """Return the queue of a device, creating it when the entry has none."""
    from .queue_player import QueuePlayer

    if getattr(runtime, "queue", None) is not None:
        return runtime.queue

    async def _length_of(item: Any) -> float | None:
        """Look up a tune's length from the library by its file hash."""
        library = _library(runtime)
        try:
            path = await asyncio.get_running_loop().run_in_executor(
                None, library.find, item.source, item.path
            )
            data = await asyncio.get_running_loop().run_in_executor(
                None, path.read_bytes
            )
        except (SidLibraryError, OSError):
            return None
        length = runtime.songlengths.get_length(data, item.song - 1)
        return float(length) if length else None

    async def _start_song_of(item: Any) -> int:
        """Return the sub tune a SID wants played first."""
        library = _library(runtime)
        try:
            path = await asyncio.get_running_loop().run_in_executor(
                None, library.find, item.source, item.path
            )
            data = await asyncio.get_running_loop().run_in_executor(
                None, path.read_bytes
            )
        except (SidLibraryError, OSError):
            return 1
        return start_song(data)

    runtime.queue = QueuePlayer(
        _play_queue_item(runtime),
        length_of=_length_of,
        start_song_of=_start_song_of,
    )
    return runtime.queue


def _play_queue_item(runtime: UltimateControlRuntimeData):
    """Return the callback that sends one queue item to the device."""
    from .songlengths import ssl_payload_for

    async def _play(item: Any) -> None:
        library = _library(runtime)
        api = runtime.api
        path = await asyncio.get_running_loop().run_in_executor(
            None, library.find, item.source, item.path
        )
        data = await asyncio.get_running_loop().run_in_executor(None, path.read_bytes)
        if data[:4] not in SID_MAGIC:
            raise SidLibraryError(f"{path.name} is not a SID file")
        songs = count_subtunes(data)
        song = min(item.song, songs)
        length = runtime.songlengths.get_length(data, song - 1)
        if length:
            item.length = float(length)
        await api.async_upload_and_play_sid(
            data, song, ssl_payload_for(data, runtime.songlengths)
        )
        runtime.last_played = {
            "name": path.name,
            "path": item.path,
            "source": item.source,
            "song": song,
            "songs": songs,
            "length": item.length,
            "song_length": item.length,
            "queue": True,
        }
        notify_queue(runtime)

    return _play


def notify_queue(runtime: UltimateControlRuntimeData) -> None:
    """Tell the dashboard that the queue moved on."""
    for listener in list(getattr(runtime, "queue_listeners", []) or []):
        try:
            listener()
        except Exception:  # noqa: BLE001 - one broken listener must not stop the queue
            _LOGGER.debug("Queue listener failed", exc_info=True)


def folder_queue_items(
    library: SidLibrary, source: str, folder: str, song: int | None
) -> list[Any]:
    """Return every SID of a folder (and its sub folders) as queue items."""
    from .queue_player import QueueItem

    base = library.favorites_dir if source == "favorites" else library.library_dir
    target = base / folder if folder else base
    if not target.is_dir():
        raise SidLibraryError(f"Folder not found: {folder or '(root)'}")
    items: list[QueueItem] = []
    for file in sorted(target.rglob("*"), key=lambda p: str(p).casefold()):
        if not file.is_file() or file.suffix.lower() != ".sid":
            continue
        relative = file.relative_to(base).as_posix()
        try:
            info = library.inspect(file)
        except SidLibraryError:
            continue
        # Ohne ausdrücklichen Wunsch spielt die Warteschlange den Haupttune,
        # den das SID selbst angibt (Header, sonst Tune 1).
        wanted = song or info.start_song
        items.append(
            QueueItem(
                source=source,
                path=relative,
                name=file.name,
                song=min(wanted, info.songs),
                length=info.duration if wanted == 1 else None,
                start_song=info.start_song,
            )
        )
    return items


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/queue_play_folder",
        vol.Required("entry_id"): str,
        vol.Optional("source", default="library"): str,
        vol.Optional("path", default=""): str,
        vol.Optional("song"): vol.All(int, vol.Range(min=1, max=256)),
        vol.Optional("shuffle", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_queue_play_folder(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Play every SID of a folder, one after the other, on a timer."""
    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        items = await hass.async_add_executor_job(
            folder_queue_items,
            library,
            msg.get("source", "library"),
            msg.get("path", ""),
            msg.get("song"),
        )
    except SidLibraryError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    if not items:
        connection.send_error(msg["id"], "empty", "No SID files in this folder")
        return
    if msg.get("shuffle"):
        import random

        random.shuffle(items)

    player = queue_for(runtime)
    player.replace(items, title=msg.get("path", ""))
    try:
        state = await player.start()
    except Exception as err:  # noqa: BLE001 - a device error is the answer
        connection.send_error(msg["id"], "device_error", str(err))
        return
    notify_queue(runtime)
    connection.send_result(msg["id"], state.as_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/queue_action",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In(["next", "previous", "stop", "pause", "resume"]),
    }
)
@websocket_api.async_response
async def ws_queue_action(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Step the queue: next, previous, stop, pause or resume."""
    runtime = _runtime(hass, msg["entry_id"])
    player = queue_for(runtime)
    action = msg["action"]
    try:
        if action == "next":
            state = await player.next()
        elif action == "previous":
            state = await player.previous()
        elif action == "stop":
            state = player.stop()
            await runtime.api.async_reset()
        elif action == "pause":
            await runtime.api.async_pause()
            player.cancel()
            player.state.playing = False
            player.state.remaining = None
            state = player.state
        else:
            await runtime.api.async_resume()
            state = await player.start()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "device_error", str(err))
        return
    notify_queue(runtime)
    connection.send_result(msg["id"], state.as_dict())


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/queue_status", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_queue_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Report the queue: items, position and the time left on the timer."""
    runtime = _runtime(hass, msg["entry_id"])
    connection.send_result(msg["id"], queue_for(runtime).state.as_dict())


# ----------------------------------------------------------------------
# Playlists
# ----------------------------------------------------------------------
def playlist_store(runtime: UltimateControlRuntimeData) -> Any:
    """Return the playlist store of a device."""
    from .playlist import PlaylistStore

    store = getattr(runtime, "playlists", None)
    if store is None:
        store = PlaylistStore(runtime.media_path)
        runtime.playlists = store
    return store


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/playlists", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_playlists(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the saved playlists."""
    runtime = _runtime(hass, msg["entry_id"])
    store = playlist_store(runtime)
    connection.send_result(msg["id"], {"playlists": await hass.async_add_executor_job(store.list)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/playlist_get",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
    }
)
@websocket_api.async_response
async def ws_playlist_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one playlist with all its tunes."""
    from .playlist import PlaylistError

    runtime = _runtime(hass, msg["entry_id"])
    store = playlist_store(runtime)
    try:
        playlist = await hass.async_add_executor_job(store.load, msg["name"])
    except PlaylistError as err:
        connection.send_error(msg["id"], "invalid_name", str(err))
        return
    if playlist is None:
        connection.send_error(msg["id"], "not_found", f"No playlist called {msg['name']}")
        return
    connection.send_result(msg["id"], playlist.as_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/playlist_add",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Optional("path"): str,
        vol.Optional("source", default="library"): str,
        vol.Optional("song", default=1): vol.All(int, vol.Range(min=1, max=256)),
        vol.Optional("items"): list,
    }
)
@websocket_api.async_response
async def ws_playlist_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add one tune (or a list of tunes) to a playlist, creating it if needed."""
    from .playlist import PlaylistError

    runtime = _runtime(hass, msg["entry_id"])
    store = playlist_store(runtime)
    items = msg.get("items")
    if items is None:
        if not msg.get("path"):
            connection.send_error(msg["id"], "invalid", "A tune path is required")
            return
        items = [
            {
                "source": msg.get("source", "library"),
                "path": msg["path"],
                "name": str(msg["path"]).rsplit("/", 1)[-1],
                "song": msg.get("song", 1),
            }
        ]
    try:
        playlist = await hass.async_add_executor_job(store.add, msg["name"], items)
    except PlaylistError as err:
        connection.send_error(msg["id"], "invalid_name", str(err))
        return
    connection.send_result(msg["id"], playlist.as_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/playlist_edit",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Required("action"): vol.In(["remove", "clear", "delete"]),
        vol.Optional("index"): vol.All(int, vol.Range(min=0)),
    }
)
@websocket_api.async_response
async def ws_playlist_edit(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove one tune, empty a playlist or delete it."""
    from .playlist import PlaylistError

    runtime = _runtime(hass, msg["entry_id"])
    store = playlist_store(runtime)
    action = msg["action"]
    try:
        if action == "remove":
            if msg.get("index") is None:
                connection.send_error(msg["id"], "invalid", "An index is required")
                return
            playlist = await hass.async_add_executor_job(
                store.remove_entry, msg["name"], msg["index"]
            )
            connection.send_result(msg["id"], playlist.as_dict())
            return
        if action == "clear":
            playlist = await hass.async_add_executor_job(store.clear, msg["name"])
            connection.send_result(msg["id"], playlist.as_dict())
            return
        removed = await hass.async_add_executor_job(store.delete, msg["name"])
    except PlaylistError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"name": msg["name"], "deleted": removed})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/playlist_play",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Optional("shuffle", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_playlist_play(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Play a playlist: it becomes the device queue, timer included."""
    from .queue_player import QueueItem
    from .playlist import PlaylistError

    runtime = _runtime(hass, msg["entry_id"])
    store = playlist_store(runtime)
    try:
        playlist = await hass.async_add_executor_job(store.load, msg["name"])
    except PlaylistError as err:
        connection.send_error(msg["id"], "invalid_name", str(err))
        return
    if playlist is None:
        connection.send_error(msg["id"], "not_found", f"No playlist called {msg['name']}")
        return
    items = [QueueItem.from_dict(item) for item in playlist.items]
    if not items:
        connection.send_error(msg["id"], "empty", "This playlist has no tunes")
        return
    if msg.get("shuffle"):
        import random

        random.shuffle(items)
    player = queue_for(runtime)
    player.replace(items, title=playlist.name)
    try:
        state = await player.start()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "device_error", str(err))
        return
    notify_queue(runtime)
    connection.send_result(msg["id"], state.as_dict())


# ----------------------------------------------------------------------
# CSDb (csdb.dk)
# ----------------------------------------------------------------------
# The card shows the two tables of the CSDb front page and, behind a click,
# one release. The webservice has no search, so the lists come from the HTML
# pages and a single release from the XML webservice by its id.

_CSDB_CACHE: Any = None


def _csdb_cache() -> Any:
    """One cache for the whole integration, so every card shares the fetches."""
    global _CSDB_CACHE
    if _CSDB_CACHE is None:
        from .csdb import CsdbCache

        _CSDB_CACHE = CsdbCache()
    return _CSDB_CACHE


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/csdb_front",
        # Die Karte schickt entry_id immer mit; ohne diesen Schlüssel lehnt
        # Home Assistants Schema die Nachricht ab ("not a valid option").
        vol.Optional("entry_id"): str,
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_csdb_front(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The latest releases and the top demos of the CSDb front page."""
    from .csdb import CsdbError, async_fetch_text, parse_front

    cache = _csdb_cache()
    cached = None if msg["refresh"] else cache.get("front")
    if cached is not None:
        connection.send_result(msg["id"], {**cached, "cached": True})
        return
    try:
        page = await async_fetch_text(async_get_clientsession(hass), FRONT_URL)
    except CsdbError as err:
        connection.send_error(msg["id"], "csdb_error", str(err))
        return
    tables = parse_front(page)
    result = {
        "latest": [entry.as_dict() for entry in tables["latest"]],
        "top_demos": [entry.as_dict() for entry in tables["top_demos"]],
    }
    cache.put("front", result)
    connection.send_result(msg["id"], {**result, "cached": False})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/csdb_list",
        vol.Optional("entry_id"): str,
        vol.Required("list"): vol.In(("latest", "top_demos")),
        vol.Optional("limit", default=0): int,
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_csdb_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The full list behind a front page table: 25 latest releases or the chart."""
    from .csdb import (
        LATEST_URL,
        TOP_DEMOS_URL,
        CsdbError,
        async_fetch_text,
        parse_latest,
        parse_top,
    )

    cache = _csdb_cache()
    key = f"list:{msg['list']}"
    entries = None if msg["refresh"] else cache.get(key)
    if entries is None:
        url = LATEST_URL if msg["list"] == "latest" else TOP_DEMOS_URL
        try:
            page = await async_fetch_text(async_get_clientsession(hass), url)
        except CsdbError as err:
            connection.send_error(msg["id"], "csdb_error", str(err))
            return
        entries = parse_latest(page) if msg["list"] == "latest" else parse_top(page)
        cache.put(key, entries)
    limit = msg["limit"]
    shown = entries[:limit] if limit and limit > 0 else entries
    connection.send_result(
        msg["id"],
        {
            "list": msg["list"],
            "total": len(entries),
            "entries": [entry.as_dict() for entry in shown],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/csdb_release",
        vol.Optional("entry_id"): str,
        vol.Required("id"): int,
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_csdb_release(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """One release with everything its CSDb page shows."""
    from .csdb import RELEASE_URL, CsdbError, async_fetch_text, parse_release

    cache = _csdb_cache()
    key = f"release:{msg['id']}"
    cached = None if msg["refresh"] else cache.get(key)
    if cached is not None:
        connection.send_result(msg["id"], cached)
        return
    try:
        xml = await async_fetch_text(
            async_get_clientsession(hass), RELEASE_URL.format(release_id=msg["id"])
        )
        release = parse_release(xml)
    except CsdbError as err:
        connection.send_error(msg["id"], "csdb_error", str(err))
        return
    result = release.as_dict()
    cache.put(key, result)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/csdb_install",
        vol.Required("entry_id"): str,
        vol.Required("id"): int,
        vol.Optional("download", default=0): int,
        vol.Optional("subfolder", default=""): str,
        vol.Optional("overwrite", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_csdb_install(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Download a release's archive into the library and unpack its images.

    CSDb hands out ZIP archives with disks, programs and cartridges inside. The
    archive lands in ``<library>/csdb/<release>/``; every image found in it is
    unpacked next to it, so the card can start it like any other library file.
    """
    from .csdb import (
        RELEASE_URL,
        CsdbError,
        async_download_archive,
        async_fetch_text,
        parse_release,
        release_folder,
    )

    runtime = _runtime(hass, msg["entry_id"])
    library = _library(runtime)
    try:
        xml = await async_fetch_text(
            async_get_clientsession(hass), RELEASE_URL.format(release_id=msg["id"])
        )
        release = parse_release(xml)
    except CsdbError as err:
        connection.send_error(msg["id"], "csdb_error", str(err))
        return
    if not release.downloads:
        connection.send_error(msg["id"], "no_download", "This release has no download")
        return
    index = msg["download"]
    if index < 0 or index >= len(release.downloads):
        connection.send_error(msg["id"], "no_download", f"No download {index}")
        return
    # Erst der gewählte Link, dann die übrigen: mancher Fremd-Host antwortet
    # mit einer HTML-Seite statt mit dem Archiv.
    ordered = [release.downloads[index]] + [
        link for i, link in enumerate(release.downloads) if i != index
    ]
    try:
        link, data = await async_download_archive(
            async_get_clientsession(hass), ordered
        )
    except CsdbError as err:
        connection.send_error(msg["id"], "download_failed", str(err))
        return

    def _install() -> dict[str, Any]:
        from .csdb import unpack_images

        # csdb/<Typ>/<Anfangsbuchstabe>/<Gruppe>/<Name> [<Jahr>]
        folder = release_folder(release, msg["subfolder"].strip("/") or "csdb")
        target = library.library_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / link["name"]).write_bytes(data)
        images = unpack_images(data, target, overwrite=msg["overwrite"])
        return {
            "folder": folder,
            "archive": link["name"],
            "images": [f"{folder}/{name}" for name in images],
        }

    try:
        result = await hass.async_add_executor_job(_install)
    except Exception as err:  # noqa: BLE001 - a broken archive, a full disk
        connection.send_error(msg["id"], "unpack_failed", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "release": release.id,
            "name": release.name,
            **result,
        },
    )
