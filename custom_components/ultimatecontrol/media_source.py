"""Media source that browses the file system of the Ultimate device.

Firmware 3.x has no directory listing over REST: ``GET /v1/files/<dir>`` is
404, and the only way to learn a folder's contents is the wildcard stat
``GET /v1/files/<dir>/*:info``, which answers with the first match only. The
browser therefore grows the listing pattern by pattern (``*``, then ``A*``,
``B*`` ...) and repeats with ``*<name>*`` until no new name appears. That finds
every folder and file of a directory - including folders that only contain
folders - with a bounded number of small requests per folder.

Playable here: SID files (``audio/x-sid``). Disk images and programs are shown
too, so they can be started from the media player; the player accepts the
device path directly.
"""

from __future__ import annotations

import logging
import string
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

from .api import UltimateApi, UltimateApiError, UltimateConnectionError
from .ftp import FtpError, async_list_dir
from .const import (
    DOMAIN,
    RUNNABLE_EXTENSIONS,
    SID_EXTENSIONS,
    SID_MIME_TYPE,
)
from .runtime_data import UltimateControlRuntimeData

_LOGGER = logging.getLogger(__name__)

# Folder names that are noise in a media browser.
HIDDEN_FOLDERS = {"SONGLENGTHS"}

MAX_CHILDREN = 500
# Upper bound of wildcard requests per folder, so a huge folder cannot hang
# the media browser.
MAX_REQUESTS_PER_FOLDER = 400

FIRST_CHARS = string.ascii_uppercase + string.digits + "_-."


async def async_get_media_source(hass: HomeAssistant) -> UltimateMediaSource:
    """Set up the media source."""
    return UltimateMediaSource(hass)


async def async_list_folder(
    runtime: UltimateControlRuntimeData, folder: str
) -> list[dict[str, Any]]:
    """Return all entries of one folder.

    FTP lists names (``NLST``), the REST API says whether a name is a folder
    (``/v1/files/<path>:info`` without an extension). FTP is far more reliable
    than the wildcard stat, whose ``*`` matches only part of a folder.

    An entry is ``{"name": ..., "type": "dir"|"file"}``.
    """
    api = runtime.api
    path = "/" + folder.strip("/") if folder.strip("/") else "/"

    try:
        names = await async_list_dir(api.host, path, api.password)
    except FtpError as err:
        _LOGGER.debug("FTP listing of %s failed: %s", path, err)
        names = []

    if not names:
        return await _async_list_folder_via_api(api, path)

    entries: list[dict[str, Any]] = []
    for entry in names:
        name = entry.name
        if not name or name.startswith("."):
            continue
        child = f"{path.rstrip('/')}/{name}"
        if _suffix_of(name) or not await api.async_is_dir(child):
            entries.append({"name": name, "type": "file"})
        else:
            entries.append({"name": name, "type": "dir"})
    return entries


def _suffix_of(name: str) -> str:
    """Return the lower-case extension of a file name, "" for none."""
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


async def _async_list_folder_via_api(api: UltimateApi, path: str) -> list[dict[str, Any]]:
    """Fallback when FTP is off: grow the folder's contents from the wildcard.

    ``GET /v1/files/<folder>/<pattern>:info`` answers with the first match only,
    so the listing is built pattern by pattern.
    """
    found: dict[str, str] = {}
    requests = 0

    async def probe(pattern: str) -> dict[str, Any] | None:
        nonlocal requests
        if requests >= MAX_REQUESTS_PER_FOLDER:
            return None
        requests += 1
        return await api.async_list_entry(path, pattern)

    async def add(entry: dict[str, Any] | None) -> str | None:
        if not entry:
            return None
        name = entry["name"]
        if name and name not in found:
            found[name] = entry.get("type", "file")
            return name
        return None

    async def sweep(pattern: str, rounds: int) -> None:
        for _ in range(rounds):
            if await add(await probe(pattern)) is None:
                return

    try:
        await add(await probe("*"))
        for char in FIRST_CHARS:
            await sweep(f"{char}*", rounds=8)
        for name in list(found):
            await sweep(f"*{name}*", rounds=4)
            if requests >= MAX_REQUESTS_PER_FOLDER:
                break
    except UltimateConnectionError as err:
        raise BrowseError(f"Device not reachable: {err}") from err
    except UltimateApiError as err:
        raise BrowseError(f"Cannot list {path}: {err}") from err

    entries = [{"name": name, "type": kind} for name, kind in found.items()]
    for entry in entries:
        name = entry["name"]
        if name == path.strip("/"):
            entry["type"] = "dir"
            continue
        child = f"{path.rstrip('/')}/{name}"
        entry["type"] = "dir" if await api.async_is_dir(child) else "file"
    return entries


def _entry_to_browse_media(
    domain: str,
    parent_path: str,
    entry: dict[str, Any],
    hide_other: bool = True,
) -> BrowseMediaSource | None:
    """Convert one directory entry into a browse media item.

    With ``hide_other`` only files the device can start (SID, PRG, CRT, disk
    images) and folders are kept; firmware and text files are left out.
    """
    name = entry.get("name") or ""
    if not name or name.startswith("."):
        return None

    is_dir = (entry.get("type") or "").lower() in ("dir", "directory")
    name = name.rstrip("/")
    identifier = f"{parent_path}/{name}" if parent_path else f"/{name}"
    identifier = identifier.replace("//", "/")

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

    suffix = _suffix_of(name)
    if hide_other and suffix not in RUNNABLE_EXTENSIONS:
        # Firmware, text and image files cannot be started; the browser shows
        # what the device can actually play.
        return None
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
    return BrowseMediaSource(
        domain=domain,
        identifier=identifier,
        media_class=MediaClass.TRACK,
        media_content_type="",
        title=name,
        can_play=True,
        can_expand=False,
    )


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

    def _get_runtimes(self) -> dict[str, tuple[str, UltimateControlRuntimeData]]:
        """Return the configured devices as {entry_id: (name, runtime)}."""
        return {
            entry.entry_id: (entry.title, entry.runtime_data)
            for entry in self.hass.config_entries.async_loaded_entries(DOMAIN)
        }

    def _select_runtime(
        self, identifier: str
    ) -> tuple[str, str, UltimateControlRuntimeData]:
        """Split "<entry_id>/<path>" into the device and the path.

        With a single configured device the identifier may also be a plain
        path, so media links without a device keep working.
        """
        runtimes = self._get_runtimes()
        if not runtimes:
            raise BrowseError("No Ultimate device is configured")

        entry_id, separator, rest = identifier.partition("/")
        if entry_id in runtimes:
            _name, runtime = runtimes[entry_id]
            return entry_id, (rest if separator else ""), runtime

        if len(runtimes) == 1:
            only_id = next(iter(runtimes))
            return only_id, identifier, runtimes[only_id][1]

        raise Unresolvable(
            "This media id does not name a configured device: " + identifier
        )

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return the contents of one folder on the device."""
        identifier = unquote(item.identifier or "").lstrip("/")
        runtimes = self._get_runtimes()
        if not runtimes:
            raise BrowseError("No Ultimate device is configured")

        if not identifier:
            if len(runtimes) > 1:
                return BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=None,
                    media_class=MediaClass.APP,
                    media_content_type=MediaType.APPS,
                    title=self.name,
                    can_play=False,
                    can_expand=True,
                    children_media_class=MediaClass.APP,
                    children=[
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=f"dev-{entry_id}/",
                            media_class=MediaClass.APP,
                            media_content_type=MediaType.APP,
                            title=name,
                            can_play=False,
                            can_expand=True,
                        )
                        for entry_id, (name, _runtime) in runtimes.items()
                    ],
                )
            entry_id = next(iter(runtimes))
            prefix, path = f"dev-{entry_id}/", ""
        else:
            try:
                entry_id, path, runtime = self._select_runtime(
                    identifier.removeprefix("dev-")
                )
            except Unresolvable as err:
                raise BrowseError(str(err)) from err
            prefix = f"dev-{entry_id}/"

        device_name, runtime = runtimes[entry_id]
        parent = "/" + path.strip("/") if path.strip("/") else "/"
        try:
            entries = await async_list_folder(runtime, parent)
        except BrowseError:
            raise
        except (UltimateConnectionError, UltimateApiError) as err:
            raise BrowseError(f"Cannot list {parent}: {err}") from err

        # The device plays SID files itself; programs and disk images are
        # started from the media player entity, so the browser hides them.
        # Unless that would leave a folder empty - then everything playable
        # is shown, so a folder is never a dead end.
        children: list[BrowseMediaSource] = []
        for hide_other in (True, False):
            built: list[BrowseMediaSource] = []
            for entry in entries:
                child = _entry_to_browse_media(
                    DOMAIN,
                    prefix + parent.rstrip("/"),
                    entry,
                    hide_other=hide_other,
                )
                if child is not None:
                    built.append(child)
            children = built
            if children or hide_other is False:
                break
        children.sort(key=_sort_key)

        not_shown = max(len(children) - MAX_CHILDREN, 0)
        children = children[:MAX_CHILDREN]

        if path.strip("/"):
            title = path.rstrip("/").rsplit("/", 1)[-1]
        else:
            title = device_name

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=prefix + parent,
            media_class=MediaClass.APP if not path.strip("/") else MediaClass.DIRECTORY,
            media_content_type=MediaType.APPS if not path.strip("/") else MediaType.MUSIC,
            title=title,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=children,
            not_shown=not_shown,
        )

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Return a playable item for a SID file on the device."""
        identifier = unquote(item.identifier or "")
        if not identifier:
            raise Unresolvable("No file selected")
        try:
            _entry_id, path, _runtime = self._select_runtime(
                identifier.lstrip("/").removeprefix("dev-")
            )
        except Unresolvable as err:
            raise Unresolvable(str(err)) from err
        if not path.strip("/"):
            raise Unresolvable("No file selected")
        if not path.lower().endswith(tuple(SID_EXTENSIONS)):
            raise Unresolvable(
                f"{path} is not a SID file; start programs and disks from the "
                "media player entity"
            )
        # SID files are not streamed: the Ultimate plays them itself, so the
        # media player only needs the device path. A relative URL keeps the
        # generic media browser from trying to stream the file.
        return PlayMedia(f"/api/{DOMAIN}/sid{quote(path)}", SID_MIME_TYPE)
