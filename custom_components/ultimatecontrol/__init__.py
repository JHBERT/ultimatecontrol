"""The UltimateControl integration.

Sets up one Ultimate II+ / Ultimate 64 device per config entry:

* a :class:`UltimateApi` client for the device's REST API,
* a coordinator polling ``/v1/info`` so the entities know when the C64 is gone,
* a media_player entity to start SID / PRG / CRT files and mount disk images,
* a media source that browses the device file system (HVSC, disk images).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UltimateApi, UltimateApiError, UltimateConnectionError
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SID_CACHE_DIR,
)
from .runtime_data import UltimateControlConfigEntry, UltimateControlRuntimeData
from .songlengths import SongLengthsDatabase

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

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

    entry.runtime_data = UltimateControlRuntimeData(
        api=api,
        coordinator=coordinator,
        media_path=media_path,
        songlengths=songlengths,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: UltimateControlConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


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
