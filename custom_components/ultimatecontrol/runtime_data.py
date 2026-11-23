"""Shared runtime data for the UltimateControl integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import UltimateApi
from .songlengths import SongLengthsDatabase

type UltimateControlConfigEntry = ConfigEntry[UltimateControlRuntimeData]


@dataclass(slots=True)
class UltimateControlRuntimeData:
    """Objects shared by the platforms of one config entry."""

    api: UltimateApi
    coordinator: DataUpdateCoordinator[dict]
    media_path: Path
    songlengths: SongLengthsDatabase = field(default_factory=SongLengthsDatabase)
    # The local SID library (see library.py); created on first use so a device
    # without a library never touches the disk.
    library: Any = None
    # What the dashboard started last: name, tune, song length.
    last_played: dict[str, Any] = field(default_factory=dict)
    # The folder queue of this device (queue_player.py); created at setup.
    queue: Any = None
    # Callbacks that fire when the queue moves on, so the dashboard follows.
    queue_listeners: list[Any] = field(default_factory=list)
    # Saved playlists (playlist.py); created on first use.
    playlists: Any = None

    @property
    def info(self) -> dict:
        """Return the last known ``/v1/info`` payload."""
        return self.coordinator.data or {}


def get_runtime_data(hass: HomeAssistant, entry: ConfigEntry) -> UltimateControlRuntimeData:
    """Return the runtime data of a config entry."""
    return entry.runtime_data
