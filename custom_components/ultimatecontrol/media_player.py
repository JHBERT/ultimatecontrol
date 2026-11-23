"""Media player entity for the Ultimate II+ / Ultimate 64.

The C64 has no way to report what it is doing, so the entity is state-driven by
what Home Assistant asked for last: a SID that is played stays "playing" until
its HVSC song length has elapsed (or until it is stopped), a PRG / CRT / disk
image leaves the entity "on" because the machine is running something.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_source import (
    MediaSourceItem,
    is_media_source_id,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import (
    UltimateApiError,
    UltimateAuthError,
    UltimateConnectionError,
)
from .const import (
    DISK_EXTENSIONS,
    DOMAIN,
    MANUFACTURER,
    SID_EXTENSIONS,
    SONG_SEPARATOR,
    UPLOAD_DIR,
)
from .runtime_data import UltimateControlConfigEntry, UltimateControlRuntimeData

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

def _split_media_id(media_id: str) -> tuple[str, int | None]:
    """Split "path#2" into ("path", 2). Song numbers are 1-based."""
    if SONG_SEPARATOR not in media_id:
        return media_id, None
    path, _, song = media_id.rpartition(SONG_SEPARATOR)
    try:
        return path, int(song)
    except ValueError:
        return media_id, None


def _suffix(path: str) -> str:
    """Return the lower-case file extension of a device path or URI."""
    return PurePosixPath(path).suffix.lower()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltimateControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player."""
    async_add_entities([UltimateMediaPlayer(entry.runtime_data, entry)])


class UltimateMediaPlayer(MediaPlayerEntity):
    """The C64 behind an Ultimate cartridge."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )
    _attr_source_list = ["SID", "Program", "Disk image"]
    _attr_media_content_type = None

    def __init__(
        self, runtime: UltimateControlRuntimeData, entry: UltimateControlConfigEntry
    ) -> None:
        """Initialise the entity."""
        self._runtime = runtime
        self._entry = entry
        self._attr_name = entry.title
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._attr_state = MediaPlayerState.IDLE
        self._attr_source = "SID"
        self._current_path: str | None = None
        self._current_song: int | None = None
        self._stop_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        """Follow the coordinator and clean up timers on removal."""
        self.async_on_remove(
            self._runtime.coordinator.async_add_listener(self._handle_coordinator)
        )
        self.async_on_remove(self._cancel_stop_timer)
        self._handle_coordinator()

    @callback
    def _handle_coordinator(self) -> None:
        """Mark the entity unavailable when the C64 cannot be reached."""
        self._attr_available = self._runtime.coordinator.last_update_success
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the device registry."""
        info = self._runtime.info
        host = self._entry.data["host"]
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer=MANUFACTURER,
            model=info.get("product") or "Ultimate II+",
            sw_version=info.get("firmware_version"),
            hw_version=info.get("fpga_version"),
            configuration_url=self._runtime.api.base_url,
            serial_number=info.get("unique_id"),
        )

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes about the device and the current media."""
        info = self._runtime.info
        attributes: dict[str, Any] = {
            "host": self._entry.data["host"],
            "current_media": self._current_path,
            "song_number": self._current_song,
        }
        if info.get("hostname"):
            attributes["device_hostname"] = info["hostname"]
        if info.get("core_version"):
            attributes["core_version"] = info["core_version"]
        return attributes

    @property
    def media_title(self) -> str | None:
        """Return the title of the current media."""
        if not self._current_path:
            return None
        return PurePosixPath(self._current_path).name

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    async def async_turn_on(self) -> None:
        """Nothing to power on remotely; reset the machine."""
        await self._async_call(self._runtime.api.async_reset())

    async def async_turn_off(self) -> None:
        """Stop playback and remove any mounted disk."""
        await self.async_media_stop()

    async def async_select_source(self, source: str) -> None:
        """Remember which kind of media the user wants to start."""
        self._attr_source = source
        self.async_write_ha_state()

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Start a SID, PRG, CRT or disk image on the C64."""
        # Media chosen in the HA media browser arrives as a media-source URI;
        # the identifier of the Ultimate media source is the device path.
        if is_media_source_id(media_id):
            try:
                item = MediaSourceItem.from_uri(self.hass, media_id, self.entity_id)
            except ValueError as err:
                raise HomeAssistantError(f"Invalid media id {media_id}") from err
            media_id = unquote(item.identifier or "")
            if not media_id:
                raise HomeAssistantError("No file selected in the media browser")

        path, song = _split_media_id(media_id)
        if not path:
            raise HomeAssistantError("No media id given")

        if path.startswith(("http://", "https://")):
            raise HomeAssistantError(
                "UltimateControl needs a file path on the Ultimate or a "
                "media-source URI, not an http URL"
            )

        suffix = _suffix(path)
        self._cancel_stop_timer()

        if suffix in SID_EXTENSIONS:
            await self._async_play_sid(path, song)
        elif suffix == ".prg":
            await self._async_call(self._runtime.api.async_run_prg(path))
            self._set_state(MediaPlayerState.ON, path)
        elif suffix == ".crt":
            await self._async_call(self._runtime.api.async_run_crt(path))
            self._set_state(MediaPlayerState.ON, path)
        elif suffix in DISK_EXTENSIONS:
            await self._async_call(
                self._runtime.api.async_mount_drive(drive="a", image=path)
            )
            self._set_state(MediaPlayerState.ON, path)
        else:
            raise HomeAssistantError(
                f"Unsupported media type '{suffix or path}'. "
                "Supported: SID, PRG, CRT, D64, D71, D81, G64, G71."
            )

    async def async_media_stop(self) -> None:
        """Stop a running SID by resetting the C64."""
        self._cancel_stop_timer()
        await self._async_call(self._runtime.api.async_reset())
        self._set_state(MediaPlayerState.IDLE, None)

    async def async_media_pause(self) -> None:
        """Pause the machine (freezes the CPU)."""
        await self._async_call(self._runtime.api.async_pause())
        self._set_state(MediaPlayerState.PAUSED, self._current_path)

    async def async_media_play(self) -> None:
        """Resume a paused machine, or replay the last SID."""
        if self._attr_state == MediaPlayerState.PAUSED:
            await self._async_call(self._runtime.api.async_resume())
            self._set_state(MediaPlayerState.PLAYING, self._current_path)
            return
        if self._current_path and _suffix(self._current_path) in SID_EXTENSIONS:
            await self._async_play_sid(self._current_path, self._current_song)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    async def _async_play_sid(self, path: str, song: int | None) -> None:
        """Play a SID, either from the device or by uploading it first."""
        async with self._lock:
            local_file = Path(path)
            if local_file.is_file():
                # A file on the Home Assistant host (HVSC on the HA server):
                # upload it to the device, then play it from there.
                data = await self.hass.async_add_executor_job(local_file.read_bytes)
                remote = f"{UPLOAD_DIR}/{local_file.name}"
                await self._async_call(
                    self._runtime.api.async_upload_and_play_sid(data, song)
                )
                path = remote
            else:
                await self._async_call(
                    self._runtime.api.async_play_sid(path, song)
                )

        self._current_path = path
        self._current_song = song
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_duration = self._lookup_duration(path, song)
        self._set_state(MediaPlayerState.PLAYING, path)
        self._schedule_stop(self._attr_media_duration)

    def _lookup_duration(self, path: str, song: int | None) -> int | None:
        """Return the song length in seconds, if the database knows the file."""
        local_file = Path(path)
        if not local_file.is_file():
            return None
        lengths = self._runtime.songlengths
        if lengths.is_empty:
            return None
        try:
            data = local_file.read_bytes()
        except OSError:
            return None
        length = lengths.get_length(data, (song or 1) - 1)
        return int(length) if length else None

    @callback
    def _schedule_stop(self, duration: int | None) -> None:
        """Return to idle after the song length has elapsed."""
        if not duration:
            return
        delay = max(duration, 1)
        self._stop_task = self.hass.async_create_background_task(
            self._async_stop_later(delay),
            name=f"{DOMAIN} sid stop {self.entity_id}",
        )

    async def _async_stop_later(self, delay: int) -> None:
        """Wait for the song to finish, then mark the entity idle."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        self._attr_state = MediaPlayerState.IDLE
        self._attr_media_position = 0
        self._attr_media_position_updated_at = None
        self.async_write_ha_state()

    @callback
    def _cancel_stop_timer(self) -> None:
        """Cancel a pending stop timer."""
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = None

    @callback
    def _set_state(self, state: MediaPlayerState, path: str | None) -> None:
        """Update the state and write it to Home Assistant."""
        self._attr_state = state
        self._current_path = path
        self._attr_media_position = 0
        self._attr_media_position_updated_at = dt_util.utcnow() if path else None
        self.async_write_ha_state()

    async def _async_call(self, coro: Any) -> None:
        """Run an API call and translate its errors into HA errors."""
        try:
            await coro
        except UltimateAuthError as err:
            raise HomeAssistantError(str(err)) from err
        except UltimateConnectionError as err:
            raise HomeAssistantError(str(err)) from err
        except UltimateApiError as err:
            raise HomeAssistantError(str(err)) from err
