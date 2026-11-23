"""Shared runtime data for the UltimateControl integration."""

from __future__ import annotations

from dataclasses import dataclass, field
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

    @property
    def info(self) -> dict:
        """Return the last known ``/v1/info`` payload."""
        return self.coordinator.data or {}


def get_runtime_data(hass: HomeAssistant, entry: ConfigEntry) -> UltimateControlRuntimeData:
    """Return the runtime data of a config entry."""
    return entry.runtime_data
