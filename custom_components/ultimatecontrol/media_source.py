"""Media source that browses the file system of the Ultimate device.

The browser shows the folders and files of the cartridge / Ultimate 64 exactly
as they are stored on the device, so an HVSC copy on the Ultimate's USB stick or
SD card shows up as ``/Usb0/C64Music/...`` and can be browsed from any phone,
tablet or the HA UI.

Playable here: SID files (``audio/x-sid``). Disk images and programs are shown
too, so they can be started from the media player; the player accepts the
device path directly.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, unquote

from homeassistant.components.media_player import (
    BrowseError,
    MediaClass,
    MediaType,
)
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .api import UltimateApiError, UltimateConnectionError
from .const import (
    DISK_EXTENSIONS,
    DOMAIN,
    PROGRAM_EXTENSIONS,
    SID_EXTENSIONS,
    SID_MIME_TYPE,
)
from .runtime_data import UltimateControlRuntimeData

_LOGGER = logging.getLogger(__name__)

# Folder names that are noise in a media browser.
HIDDEN_FOLDERS = {"SONGLENGTHS"}

MAX_CHILDREN = 500


async def async_get_media_source(hass: HomeAssistant) -> UltimateMediaSource:
    """Set up the media source."""
    return UltimateMediaSource(hass)


def _entry_to_browse_media(
    domain: str, parent_path: str, entry: dict[str, Any]
) -> BrowseMediaSource | None:
    """Convert one directory entry into a browse media item."""
    name = entry.get("name") or ""
    if not name or name.startswith("."):
        return None

    entry_type = (entry.get("type") or "").lower()
    is_dir = entry_type in ("dir", "directory") or name.endswith("/")
    name = name.rstrip("/")
    identifier = f"{parent_path}/{name}" if parent_path else f"/{name}"

    if is_dir:
        if name.upper() in HIDDEN_FOLDERS:
            return None
        return BrowseMediaSource(
            domain=domain,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=name,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
        )

    suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if suffix in SID_EXTENSIONS:
        return BrowseMediaSource(
            domain=domain,
            identifier=identifier,
            media_class=MediaClass.TRACK,
            media_content_type=SID_MIME_TYPE,
            title=name,
            can_play=True,
            can_expand=False,
        )
    if suffix in DISK_EXTENSIONS or suffix in PROGRAM_EXTENSIONS:
        return BrowseMediaSource(
            domain=domain,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=name,
            can_play=False,
            can_expand=False,
        )
    return None


def _sort_key(item: BrowseMediaSource) -> tuple[int, str]:
    """Sort folders before files, then alphabetically."""
    return (0 if item.can_expand else 1, item.title.casefold())


class UltimateMediaSource(MediaSource):
    """Browse the file system of an Ultimate device."""

    name = "Ultimate C64"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    def _get_runtime(self) -> UltimateControlRuntimeData:
        """Return the runtime data of the (first) configured device."""
        entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise BrowseError("No Ultimate device is configured")
        return entries[0].runtime_data

    async def async_browse_media(
        self, item: MediaSourceItem
    ) -> BrowseMediaSource:
        """Return the contents of one folder on the device."""
        runtime = self._get_runtime()
        path = unquote(item.identifier or "")

        if not path:
            children = await self._async_root_items(runtime)
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MediaClass.APP,
                media_content_type=MediaType.APPS,
                title=self.name,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                children=children,
            )

        try:
            entries = await runtime.api.async_list_directory(path)
        except UltimateConnectionError as err:
            raise BrowseError(f"Device not reachable: {err}") from err
        except UltimateApiError as err:
            raise BrowseError(f"Cannot list {path}: {err}") from err

        children: list[BrowseMediaSource] = []
        for entry in entries or []:
            child = _entry_to_browse_media(DOMAIN, path.rstrip("/"), entry)
            if child is not None:
                children.append(child)
        children.sort(key=_sort_key)

        not_shown = max(len(children) - MAX_CHILDREN, 0)
        children = children[:MAX_CHILDREN]

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=path.rstrip("/").rsplit("/", 1)[-1] or path,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=children,
            not_shown=not_shown,
        )

    async def _async_root_items(
        self, runtime: UltimateControlRuntimeData
    ) -> list[BrowseMediaSource]:
        """Return the top level folders of the device."""
        try:
            entries = await runtime.api.async_list_directory("/")
        except (UltimateConnectionError, UltimateApiError) as err:
            raise BrowseError(f"Cannot list the device root: {err}") from err

        children = [
            child
            for entry in entries or []
            if (child := _entry_to_browse_media(DOMAIN, "", entry)) is not None
        ]
        children.sort(key=_sort_key)
        return children

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Return a playable item for a SID file on the device."""
        path = unquote(item.identifier or "")
        if not path:
            raise Unresolvable("No file selected")
        if not path.lower().endswith(tuple(SID_EXTENSIONS)):
            raise Unresolvable(
                f"{path} is not a SID file; start programs and disks from the "
                "media player entity"
            )
        # SID files are not streamed: the Ultimate plays them itself, so the
        # media player just needs the device path. A relative URL keeps the
        # generic media browser from trying to stream the file.
        return PlayMedia(f"/api/{DOMAIN}/sid{quote(path)}", SID_MIME_TYPE)
