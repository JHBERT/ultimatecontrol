"""CSDb (csdb.dk) as a small, read-only source for C64 demos.

The dashboard wants the two tables of the CSDb front page - the latest releases
and the top demos - and, behind a click, the page of one demo. CSDb has no
search in its webservice, but it does have two things that make this easy and
polite:

* the front page and the two list pages are plain HTML tables, small enough to
  fetch and parse with a handful of regular expressions,
* ``/webservice/?type=release&id=<id>&depth=2`` returns one release as XML with
  everything its page shows: type, date, group, event and placing, rating,
  credits, used SIDs, download links and comments.

Nothing here writes to CSDb and nothing is cached on disk; a short in-memory
cache keeps the front page from being fetched once per dashboard refresh.
"""

from __future__ import annotations

import asyncio
import html as html_module
import re
import time
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

CSDB_BASE = "https://csdb.dk"
FRONT_URL = f"{CSDB_BASE}/"
LATEST_URL = f"{CSDB_BASE}/latestreleases.php"
TOP_DEMOS_URL = f"{CSDB_BASE}/toplist.php?type=release&subtype=%281%29"
RELEASE_URL = f"{CSDB_BASE}/webservice/?type=release&id={{release_id}}&depth=2"

# CSDb asks nothing of a client, but a browser user agent is what its pages
# expect, and a timeout keeps a slow site from holding a dashboard request.
USER_AGENT = "Mozilla/5.0 (compatible; UltimateControl)"
TIMEOUT = 15
# The front page changes when a release is added, so a few minutes are enough.
CACHE_SECONDS = 300


class CsdbError(Exception):
    """CSDb could not be reached or answered with something unexpected."""


@dataclass
class CsdbEntry:
    """One row of a CSDb list: enough to show it and to open its page."""

    id: int
    name: str
    type: str = ""
    group: str = ""
    date: str = ""
    rating: str = ""
    votes: int = 0
    place: int = 0
    download_id: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "group": self.group,
            "date": self.date,
            "rating": self.rating,
            "votes": self.votes,
            "place": self.place,
            "download_id": self.download_id,
            "url": f"{CSDB_BASE}/release/?id={self.id}",
        }


@dataclass
class CsdbRelease:
    """One release as its CSDb page shows it."""

    id: int
    name: str
    type: str = ""
    date: str = ""
    rating: str = ""
    place: int = 0
    compo: str = ""
    event: str = ""
    website: str = ""
    screenshot: str = ""
    groups: list[str] = field(default_factory=list)
    credits: list[dict[str, str]] = field(default_factory=list)
    downloads: list[dict[str, Any]] = field(default_factory=list)
    sids: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "date": self.date,
            "rating": self.rating,
            "place": self.place,
            "compo": self.compo,
            "event": self.event,
            "website": self.website,
            "screenshot": self.screenshot,
            "groups": self.groups,
            "credits": self.credits,
            "downloads": self.downloads,
            "sids": self.sids,
            "comments": self.comments,
            "url": f"{CSDB_BASE}/release/?id={self.id}",
        }


# --------------------------------------------------------------------------- #
# HTML helpers
# --------------------------------------------------------------------------- #

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\n]+")


def _text(raw: str) -> str:
    """Strip tags and entities from a fragment of CSDb HTML."""
    return _WS.sub(" ", html_module.unescape(_TAG.sub(" ", raw))).strip()


# --------------------------------------------------------------------------- #
# Front page and list pages
# --------------------------------------------------------------------------- #

# Rows are split first and matched one by one: one regular expression over a
# whole table backtracks catastrophically on CSDb's markup.
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_RELEASE_LINK = re.compile(r'<a href="/?release/\?id=(\d+)"(?: title="([^"]*)")?[^>]*>(.*?)</a>', re.S)
_DOWNLOAD_LINK = re.compile(r'release/download\.php\?id=(\d+)')
_BROWSE_LINK = re.compile(r'browse\.php\?[^"]*">(.*?)</a>', re.S)
_GROUP_LINK = re.compile(r'(?:scener|group)/\?id=\d+">(.*?)</a>', re.S)
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_TOP_ITEM = re.compile(r'(\d+)\s*<a href="/?release/\?id=(\d+)">(.*?)</a>', re.S)
_RATING = re.compile(r"\(([\d.]+)\)")
_TOP_PLACE = re.compile(r"<td align=right>(\d+)</td>")
_TOP_VOTES = re.compile(r"<td align=center>(\d+)</td>")
_TOP_RATING = re.compile(r"<td align=center><font size=1>([\d.]+)</font></td>")


def _section(page: str, marker: str) -> str:
    """Return the table that follows ``marker`` up to its closing tag."""
    start = page.find(marker)
    if start < 0:
        return ""
    end = page.find("</table>", start)
    return page[start : end if end > 0 else len(page)]


def _rows(section: str) -> list[str]:
    return _ROW.findall(section)


def parse_front(page: str) -> dict[str, list[CsdbEntry]]:
    """Parse the two tables of the front page: latest releases and top demos."""
    latest: list[CsdbEntry] = []
    for row in _rows(_section(page, 'href="latestreleases.php"')):
        link = _RELEASE_LINK.search(row)
        if not link:
            continue
        date = _DATE.search(row)
        kind = _BROWSE_LINK.search(row)
        group = _GROUP_LINK.search(row)
        release_id, title, name = link.groups()
        latest.append(
            CsdbEntry(
                id=int(release_id),
                name=_text(title or "") or _text(name),
                type=_text(kind.group(1)) if kind else "",
                group=_text(group.group(1)) if group else "",
                date=date.group(1) if date else "",
            )
        )

    top: list[CsdbEntry] = []
    section = _section(page, "Top Demos")
    for item in _TOP_ITEM.finditer(section):
        place, release_id, name = item.groups()
        rating = _RATING.search(section, item.end())
        top.append(
            CsdbEntry(
                id=int(release_id),
                name=_text(name),
                place=int(place),
                rating=rating.group(1) if rating else "",
            )
        )
    return {"latest": latest, "top_demos": top}


def parse_latest(page: str) -> list[CsdbEntry]:
    """Parse ``latestreleases.php``: 25 releases with their download link."""
    entries: list[CsdbEntry] = []
    for row in _rows(page):
        link = _RELEASE_LINK.search(row)
        if not link:
            continue
        release_id, title, name = link.groups()
        download = _DOWNLOAD_LINK.search(row)
        date = _DATE.search(row)
        kind = _BROWSE_LINK.search(row)
        group = _GROUP_LINK.search(row)
        entries.append(
            CsdbEntry(
                id=int(release_id),
                name=_text(title or "") or _text(name),
                type=_text(kind.group(1)) if kind else "",
                group=_text(group.group(1)) if group else "",
                date=date.group(1) if date else "",
                download_id=int(download.group(1)) if download else 0,
            )
        )
    return entries


def parse_top(page: str) -> list[CsdbEntry]:
    """Parse the demo chart: place, name, groups, rating and vote count."""
    entries: list[CsdbEntry] = []
    # Nur die Chart-Tabelle, nicht die Listen daneben (Gruppen, Scener, ...).
    start = page.find("Release Name")
    section = page[start : page.find("</table>", start)] if start > 0 else page
    for row in _rows(section):
        place = _TOP_PLACE.search(row)
        link = _RELEASE_LINK.search(row)
        if not place or not link:
            continue
        release_id, title, name = link.groups()
        rating = _TOP_RATING.search(row) or _RATING.search(row)
        votes = _TOP_VOTES.findall(row)
        entries.append(
            CsdbEntry(
                id=int(release_id),
                name=_text(title or "") or _text(name),
                group=", ".join(_text(g) for g in _GROUP_LINK.findall(row)),
                rating=rating.group(1) if rating else "",
                votes=int(votes[-1]) if votes else 0,
                place=int(place.group(1)),
            )
        )
    return entries


# --------------------------------------------------------------------------- #
# One release
# --------------------------------------------------------------------------- #


def _child_text(node: ElementTree.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _date(node: ElementTree.Element | None, prefix: str = "") -> str:
    day = _child_text(node, f"{prefix}Day")
    month = _child_text(node, f"{prefix}Month")
    year = _child_text(node, f"{prefix}Year")
    if not year:
        return ""
    if day and month:
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return year


def parse_release(xml: str) -> CsdbRelease:
    """Parse the webservice XML of one release (depth 2)."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as err:
        raise CsdbError(f"CSDb answered with invalid XML: {err}") from err
    node = root.find("Release")
    if node is None:
        raise CsdbError("CSDb answered without a release")

    release_id = int(_child_text(node, "ID") or 0)
    if not release_id:
        raise CsdbError("CSDb answered without a release id")

    groups = [
        _child_text(group, "Name")
        for group in node.findall("ReleasedBy/Group")
        if _child_text(group, "Name")
    ]

    credits: list[dict[str, str]] = []
    for credit in node.findall("Credits/Credit"):
        handle = credit.find("Handle")
        name = _child_text(handle, "Handle")
        if not name:
            continue
        credits.append(
            {
                "role": _child_text(credit, "CreditType"),
                "handle": name,
                "scener": _child_text(handle, "Scener/ID"),
            }
        )

    downloads: list[dict[str, Any]] = []
    for link in node.findall("DownloadLinks/DownloadLink"):
        url = _child_text(link, "Link")
        if not url:
            continue
        downloads.append(
            {
                "url": url,
                "name": url.rstrip("/").split("/")[-1],
                "downloads": int(_child_text(link, "Downloads") or 0),
                "status": _child_text(link, "Status"),
            }
        )

    sids: list[dict[str, Any]] = []
    for sid in node.findall("UsedSIDs/SID"):
        sid_id = _child_text(sid, "ID")
        if not sid_id:
            continue
        sids.append(
            {
                "id": int(sid_id),
                "name": _child_text(sid, "Name"),
                "author": _child_text(sid, "Author"),
                "path": _child_text(sid, "HVSCPath"),
                "songs": int(_child_text(sid, "NOSongs") or 0),
                "default_song": int(_child_text(sid, "DefaultSong") or 0),
            }
        )

    comments: list[dict[str, str]] = []
    for comment in node.findall("Comments/Goof") + node.findall("Comments/HiddenPart"):
        text = _child_text(comment, "Text")
        if not text:
            continue
        comments.append(
            {
                "user": _child_text(comment, "CSDbUser/Login"),
                "date": _child_text(comment, "Date"),
                "text": text,
            }
        )

    event = node.find("ReleasedAt/Event")
    return CsdbRelease(
        id=release_id,
        name=_child_text(node, "Name"),
        type=_child_text(node, "Type"),
        date=_date(node, "Release"),
        rating=_child_text(node, "Rating"),
        place=int(_child_text(node, "Achievement/Place") or 0),
        compo=_child_text(node, "Achievement/Compo"),
        event=_child_text(event, "Name"),
        website=_child_text(node, "Website"),
        screenshot=_child_text(node, "ScreenShot"),
        groups=groups,
        credits=credits,
        downloads=downloads,
        sids=sids,
        comments=comments,
    )


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #


async def async_fetch_text(session: Any, url: str) -> str:
    """Fetch one CSDb page as text."""
    try:
        async with asyncio.timeout(TIMEOUT):
            async with session.get(url, headers={"User-Agent": USER_AGENT}) as resp:
                if resp.status != 200:
                    raise CsdbError(f"CSDb answered with HTTP {resp.status} for {url}")
                return await resp.text()
    except CsdbError:
        raise
    except (TimeoutError, asyncio.TimeoutError) as err:
        raise CsdbError(f"CSDb did not answer in time: {url}") from err
    except Exception as err:  # aiohttp errors, DNS, TLS
        raise CsdbError(f"CSDb could not be reached: {err}") from err


IMAGE_SUFFIXES = {".sid", ".d64", ".d71", ".d81", ".g64", ".g71", ".prg", ".crt"}


def unpack_images(data: bytes, target: Any, overwrite: bool = False) -> list[str]:
    """Write every image of a release archive into ``target``.

    CSDb hands out ZIP archives with disks, programs and cartridges inside,
    often in sub folders. Only the file name is kept, so nothing can climb out
    of the library. Returns the names written, in archive order.
    """
    import io
    import zipfile
    from pathlib import Path

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name or Path(name).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            out = target / name
            if not out.exists() or overwrite:
                out.write_bytes(archive.read(info))
            written.append(name)
    return written


class CsdbCache:
    """A tiny in-memory cache, so a dashboard refresh does not hit CSDb."""

    def __init__(self, seconds: int = CACHE_SECONDS, clock: Any = None) -> None:
        self.seconds = seconds
        self._clock = clock or time.monotonic
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        hit = self._entries.get(key)
        if hit is None:
            return None
        stamp, value = hit
        if self._clock() - stamp > self.seconds:
            self._entries.pop(key, None)
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._entries[key] = (self._clock(), value)

    def clear(self) -> None:
        self._entries.clear()
