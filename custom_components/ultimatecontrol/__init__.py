"""The UltimateControl integration.

Sets up one Ultimate II+ / Ultimate 64 device per config entry:

* a :class:`UltimateApi` client for the device's REST API,
* a coordinator polling ``/v1/info`` so the entities know when the C64 is gone,
* a media_player entity to start SID / PRG / CRT files and mount disk images,
* a media source that browses the device file system (HVSC, disk images).
"""

from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from pathlib import Path

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UltimateApi, UltimateApiError, UltimateConnectionError
from .const import (
    CONF_FAVORITES_FOLDER,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SID_CACHE_DIR,
)
from . import lovelace, websocket_api
from .library import SidLibrary, SidLibraryError
from .runtime_data import UltimateControlConfigEntry, UltimateControlRuntimeData
from .songlengths import SongLengthsDatabase

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

SERVICE_IMPORT = "import_folder"
ATTR_ENTRY_ID = "entry_id"
CONF_FOLDER = "folder"
CONF_SUBFOLDER = "subfolder"

# The dashboard card; served as a module so a dashboard needs no file copy.
PANEL_URL = "/ultimatecontrol_panel/ultimatecontrol-panel.js?version=1.7.4"

# Optional file name of the HVSC song length database inside the cache folder.
# The raw ``Songlengths.md5`` is parsed, the JSON file (built with
# ``tools/build_songlengths.py``) loads much faster on big installations.
SONGLENGTHS_FILES = ("Songlengths.json", "Songlengths.md5")


async def async_setup_entry(
    hass: HomeAssistant, entry: UltimateControlConfigEntry
) -> bool:
    """Set up UltimateControl from a config entry."""
    session = async_get_clientsession(hass)
    api = UltimateApi(
        session,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        password=entry.data.get(CONF_PASSWORD),
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    async def _async_update_data() -> dict:
        """Poll /v1/info; raises UpdateFailed when the device is unreachable."""
        try:
            return await api.async_get_info()
        except UltimateConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except UltimateApiError as err:
            raise UpdateFailed(str(err)) from err

    coordinator: DataUpdateCoordinator[dict] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN} {entry.data[CONF_HOST]}",
        update_interval=timedelta(seconds=scan_interval),
        update_method=_async_update_data,
        config_entry=entry,
    )

    # First refresh: a device that is off at setup must not break the entry,
    # the entities simply start as unavailable.
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        _LOGGER.warning(
            "Ultimate at %s is not reachable yet: %s",
            entry.data[CONF_HOST],
            coordinator.last_exception,
        )

    media_path = Path(hass.config.path(SID_CACHE_DIR))
    songlengths = await _async_load_songlengths(hass, media_path)
    library = SidLibrary(media_path, songlengths)
    await hass.async_add_executor_job(library.ensure_dirs)
    favorites_folder = entry.options.get(CONF_FAVORITES_FOLDER) or ""
    if favorites_folder:
        await _async_seed_favorites(hass, library, favorites_folder)

    entry.runtime_data = UltimateControlRuntimeData(
        api=api,
        coordinator=coordinator,
        media_path=media_path,
        songlengths=songlengths,
        library=library,
    )
    # The folder queue: its timer must be a Home Assistant background task, so
    # it is stopped with the entry instead of outliving it.
    queue = websocket_api.queue_for(entry.runtime_data)
    queue._factory = lambda coro: hass.async_create_background_task(  # noqa: SLF001
        coro, name=f"{DOMAIN} queue"
    )

    @callback
    def _queue_moved() -> None:
        """Fire an event so the dashboard can follow the queue."""
        hass.bus.async_fire(
            f"{DOMAIN}_queue_changed",
            {**entry.runtime_data.queue.state.as_dict(), "entry_id": entry.entry_id},
        )

    entry.runtime_data.queue_listeners.append(_queue_moved)

    websocket_api.async_register(hass)
    _async_serve_panel(hass)
    _async_register_services(hass)
    lovelace.async_ensure_resource(hass, PANEL_URL)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: UltimateControlConfigEntry
) -> bool:
    """Unload a config entry."""
    runtime = entry.runtime_data
    if runtime is not None and runtime.queue is not None:
        runtime.queue.cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class PanelView(HomeAssistantView):
    """Serve the UltimateControl dashboard card as a JS module.

    Home Assistant loads dashboard resources with a ``<script type="module">
``, which a login-protected URL cannot satisfy - the browser's module loader
    sends no auth header and the 401 makes the module fail silently. The card
    therefore needs no auth: it is code, not data (every API call it makes is
    authenticated, and it refuses to work without a real websocket connection).
    """

    url = "/ultimatecontrol_panel/ultimatecontrol-panel.js"
    name = f"api:{DOMAIN}:panel"
    requires_auth = False

    async def get(self, request):  # noqa: ANN001
        """Return the card."""
        from aiohttp import web

        return web.Response(
            body=async_serve_panel_source(),
            content_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )


def async_serve_panel_source() -> bytes:
    """Return the card's source (read on demand from the integration folder)."""
    return (Path(__file__).parent / "frontend" / "ultimatecontrol-panel.js").read_bytes()


async def _async_handle_import(hass: HomeAssistant, call: ServiceCall) -> None:
    """Copy all SID files of a folder on the host into the library."""
    runtime = websocket_api.runtime_for(hass, call.data[ATTR_ENTRY_ID])
    library = websocket_api.library_for(runtime)
    folder = Path(call.data[CONF_FOLDER]).expanduser()
    subfolder = (call.data.get(CONF_SUBFOLDER) or "").strip("/")
    if not folder.is_dir():
        raise HomeAssistantError(f"Not a folder: {folder}")

    def _copy() -> tuple[int, list[str]]:
        imported = 0
        skipped: list[str] = []
        for file in sorted(folder.rglob("*")):
            if not file.is_file() or file.suffix.lower() != ".sid":
                continue
            relative = file.relative_to(folder).as_posix()
            if subfolder:
                relative = f"{subfolder}/{relative}"
            try:
                library.import_file(file, relative)
                imported += 1
            except SidLibraryError as err:
                skipped.append(f"{relative}: {err}")
        return imported, skipped

    imported, skipped = await hass.async_add_executor_job(_copy)
    _LOGGER.info(
        "Imported %s SID file(s) from %s, %s skipped", imported, folder, len(skipped)
    )


SERVICE_RESTORE_QUEUE = "restore_queue"


async def _async_restore_queue(hass: HomeAssistant, call: ServiceCall) -> None:
    """Start the queue again after a Home Assistant restart.

    The timer of a running queue does not survive a restart: the C64 keeps
    playing, but nothing would send the next tune. This service puts the queue
    back together from the SIDs in a folder, so a restart in the middle of a
    folder does not end the evening. It is meant for an automation that runs
    ``ultimatecontrol.restore_queue`` at Home Assistant start.
    """
    runtime = websocket_api.runtime_for(hass, call.data[ATTR_ENTRY_ID])
    source = call.data.get("source", "library")
    folder = (call.data.get(CONF_FOLDER) or "").strip("/")
    shuffle = bool(call.data.get("shuffle", False))
    library = websocket_api.library_for(runtime)
    try:
        items = await hass.async_add_executor_job(
            websocket_api.folder_queue_items, library, source, folder, None
        )
    except SidLibraryError as err:
        raise HomeAssistantError(str(err)) from err
    if not items:
        raise HomeAssistantError(f"No SID files in {folder or 'the library'}")
    if shuffle:
        import random

        random.shuffle(items)
    player = websocket_api.queue_for(runtime)
    player.replace(items, title=folder)
    await player.start()
    websocket_api.notify_queue(runtime)
    _LOGGER.info("Queue restored: %s tune(s) from %s", len(items), folder or source)


IMPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(CONF_FOLDER): cv.string,
        vol.Optional(CONF_SUBFOLDER): cv.string,
    }
)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's services once."""
    if hass.services.has_service(DOMAIN, SERVICE_IMPORT):
        return

    async def _import(call: ServiceCall) -> None:
        await _async_handle_import(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT, _import, schema=IMPORT_SCHEMA
    )

    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_QUEUE):

        async def _restore(call: ServiceCall) -> None:
            await _async_restore_queue(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_QUEUE,
            _restore,
            schema=vol.Schema(
                {
                    vol.Required(ATTR_ENTRY_ID): cv.string,
                    vol.Optional("source", default="library"): cv.string,
                    vol.Optional(CONF_FOLDER, default=""): cv.string,
                    vol.Optional("shuffle", default=False): cv.boolean,
                }
            ),
        )


@callback
def _async_serve_panel(hass: HomeAssistant) -> None:
    """Register the card view (idempotent: several entries share one view)."""
    if not hass.data.get(f"{DOMAIN}_panel_served"):
        hass.http.register_view(PanelView())
        hass.data[f"{DOMAIN}_panel_served"] = True


async def _async_seed_favorites(
    hass: HomeAssistant, library: SidLibrary, folder: str
) -> None:
    """Copy the SIDs of a folder on the host into the favourites (once)."""
    source = Path(folder).expanduser()
    if not await hass.async_add_executor_job(source.is_dir):
        _LOGGER.warning("Favourites folder %s is not a directory", source)
        return

    def _copy() -> int:
        copied = 0
        for file in sorted(source.rglob("*")):
            if not file.is_file() or file.suffix.lower() != ".sid":
                continue
            target = library.favorites_dir / file.relative_to(source).as_posix()
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
            copied += 1
        return copied

    copied = await hass.async_add_executor_job(_copy)
    _LOGGER.info("Added %s SID file(s) from %s to the favourites", copied, source)


async def _async_update_listener(
    hass: HomeAssistant, entry: UltimateControlConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_load_songlengths(
    hass: HomeAssistant, media_path: Path
) -> SongLengthsDatabase:
    """Load the HVSC song length database if the user placed one in the cache."""
    for filename in SONGLENGTHS_FILES:
        path = media_path / filename
        if not await hass.async_add_executor_job(path.is_file):
            continue
        if path.suffix == ".json":
            return await hass.async_add_executor_job(
                SongLengthsDatabase.from_json_file, path
            )
        return await hass.async_add_executor_job(SongLengthsDatabase.from_file, path)

    _LOGGER.debug(
        "No song length database in %s; song lengths are unknown and SIDs play "
        "until they are stopped",
        media_path,
    )
    return SongLengthsDatabase()
