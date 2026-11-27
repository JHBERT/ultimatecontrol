"""Parse the CSDb pages: front page, the two lists and one release.

The fixtures are cut-down copies of the real markup (CSDb's own tables use
``<font>`` and ``bgcolor`` and no classes), so the parsers are tested against
the shape they will actually see.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def csdb():
    return _load("uc_csdb", BASE / "csdb.py")


FRONT = """
<table bgcolor="#000000" cellspacing="1" cellpadding="1" border="0" width="99%">
<tr><td colspan=4><b><a href="latestreleases.php"><font color="#ffffff">Latest Releases</font></a></b></td></tr>
<tr>
<td bgcolor="#444444"><font size=1 color="#bebebe"><b>Name</b></font></td>
</tr><tr><td bgcolor="#222222" nowrap><font size=1><a href="release/?id=266233">Certificate of Authenticity</a></font></td><td bgcolor="#222222" nowrap><font size=1><a href="browse.php?type=releases&amp;releasetype_id=9&amp;browsesub=Browse">C64 Graphics</a></font></td>
<td bgcolor="#222222" nowrap><font size=1><a href="scener/?id=30459">Worrior1</a></font></td><td bgcolor="#222222" nowrap><font size=1 color="#bebebe">(2026-11-27)</font></td></tr>
<tr><td bgcolor="#333333" nowrap><font size=1><a href="release/?id=266229" title="Maniac Mansion and Zak McKracken V3 [1351 mouse] [german]">Maniac Mansion and Zak McKracken..</a></font></td><td bgcolor="#333333" nowrap><font size=1><a href="browse.php?type=releases&amp;releasetype_id=46&amp;browsesub=Browse">EasyFlash Release</a></font></td>
<td bgcolor="#333333" nowrap><font size=1><a href="group/?id=6491">Binary Legends</a></font></td><td bgcolor="#333333" nowrap><font size=1 color="#bebebe">(2026-11-26)</font></td></tr>
</table>
<tr bgcolor="#7474fc"><td align=center><b><a href="/toplist.php?type=release&amp;subtype=%281%29"><font color="#ffffff">Top Demos</font></a></b></td></tr><tr bgcolor="#100098"><td align=left><table cellpadding=4><tr><td nowrap>1 <a href="/release/?id=232976">Next Level</a>&nbsp;&nbsp;<font size=1>(9.7)</font><br>
2 <a href="/release/?id=262146">The Lab</a>&nbsp;&nbsp;<font size=1>(9.7)</font><br>
3 <a href="/release/?id=265512">Breadbin of Horror</a>&nbsp;&nbsp;<font size=1>(9.7)</font><br>
</td></tr></table></td></tr>
</table>
"""

LATEST = """
<table width="100%">
<tr><td bgcolor="#444444"><font size=1 color="#bebebe"><b>Name</b></font></td></tr>
<tr><td bgcolor="#222222" align="center"><a href="/release/download.php?id=327903"><img src="/gfx/icon-dllink.gif"></a></td><td bgcolor="#222222" nowrap><font size=1><a href="release/?id=266230">Fabu Writer V1.1</a></font></td><td bgcolor="#222222" nowrap><font size=1><a href="browse.php?type=releases&releasetype_id=15&browsesub=Browse">C64 Tool</a></font></td>
<td bgcolor="#222222" nowrap><font size=1><a href="/scener/?id=4867">Fabu</a></font></td><td bgcolor="#222222" nowrap><font size=1 color=#bebebe>2026-11-27</font></td></tr>
</table>
"""

TOP = """
<table cellspacing=2 cellpadding=1>
<tr><td><b>Place</b></td><td><b>Release Name</b></td><td><b>Weighted Average</b></td></tr>
<tr><td align=right>1</td><td><a href="/release/?id=232976">Next Level</a> by <a href="/group/?id=8937">Performers</a></td><td align=center><font size=1>9.72</font></td><td></td><td align=center>196</td></tr>
<tr><td align=right>3</td><td><a href="/release/?id=265512">Breadbin of Horror</a> by <a href="/group/?id=240">Atlantis</a>, <a href="/group/?id=631">Bonzai</a></td><td align=center><font size=1>9.71</font></td><td></td><td align=center>78</td></tr>
</table>
"""

RELEASE = """<?xml version="1.0" encoding="UTF-8"?>
<CSDbData><Release><ID>232976</ID>
<Name>Next Level</Name>
<Type>C64 Demo</Type>
<ReleaseDay>3</ReleaseDay>
<ReleaseMonth>6</ReleaseMonth>
<ReleaseYear>2023</ReleaseYear>
<ReleasedAt><Event><ID>3187</ID><Name>X'2023</Name></Event></ReleasedAt>
<Achievement><Compo>C64 Demo</Compo><Place>1</Place></Achievement>
<Rating>9.72</Rating>
<ScreenShot>https://csdb.dk/gfx/releases/232000/232976.png</ScreenShot>
<ReleasedBy><Group><ID>8937</ID><Name>Performers</Name></Group></ReleasedBy>
<Credits><Credit><CreditType>Graphics</CreditType><Handle><ID>16567</ID><Handle>Prowler</Handle><Scener><ID>14800</ID></Scener></Handle></Credit>
<Credit><CreditType>Music</CreditType><Handle><ID>1</ID><Handle>Linus</Handle></Handle></Credit></Credits>
<UsedSIDs><SID><ID>61932</ID><HVSCPath>/MUSICIANS/L/Linus/Next_Level_Side_3.sid</HVSCPath>
<Name>Next Level Side 3</Name><Author>Sascha Zeidler (Linus)</Author><NOSongs>1</NOSongs><DefaultSong>1</DefaultSong></SID></UsedSIDs>
<DownloadLinks><DownloadLink><Link>https://csdb.dk/getinternalfile.php/246065/next_level_performers.zip</Link>
<CounterLink>https://csdb.dk/release/download.php?id=286205</CounterLink><Downloads>11029</Downloads><Status>Ok</Status></DownloadLink></DownloadLinks>
<Comments><Goof><CSDbUser><Login>BroBryce64</Login></CSDbUser><Date>27.05.2026</Date><Text>Nice one.</Text></Goof></Comments>
</Release></CSDbData>
"""


def test_front_page_has_both_tables(csdb):
    tables = csdb.parse_front(FRONT)
    latest = tables["latest"]
    assert [entry.id for entry in latest] == [266233, 266229]
    assert latest[0].type == "C64 Graphics"
    assert latest[0].group == "Worrior1"
    assert latest[0].date == "2026-11-27"
    # The long name comes from the title attribute, not the shortened text.
    assert latest[1].name.startswith("Maniac Mansion")
    assert latest[1].name.endswith("[german]")
    top = tables["top_demos"]
    assert [entry.place for entry in top] == [1, 2, 3]
    assert top[0].name == "Next Level"
    assert top[0].rating == "9.7"
    assert top[0].as_dict()["url"].endswith("/release/?id=232976")


def test_latest_list_carries_the_download_id(csdb):
    entries = csdb.parse_latest(LATEST)
    assert len(entries) == 1
    assert entries[0].id == 266230
    assert entries[0].download_id == 327903
    assert entries[0].type == "C64 Tool"
    assert entries[0].date == "2026-11-27"


def test_top_list_has_groups_rating_and_votes(csdb):
    entries = csdb.parse_top(TOP)
    assert [entry.place for entry in entries] == [1, 3]
    assert entries[0].group == "Performers"
    assert entries[0].rating == "9.72"
    assert entries[0].votes == 196
    assert entries[1].group == "Atlantis, Bonzai"
    assert entries[1].votes == 78


def test_release_has_everything_its_page_shows(csdb):
    release = csdb.parse_release(RELEASE)
    assert release.id == 232976
    assert release.name == "Next Level"
    assert release.type == "C64 Demo"
    assert release.date == "2023-06-03"
    assert release.rating == "9.72"
    assert release.place == 1
    assert release.compo == "C64 Demo"
    assert release.event == "X'2023"
    assert release.groups == ["Performers"]
    assert release.credits == [
        {"role": "Graphics", "handle": "Prowler", "scener": "14800"},
        {"role": "Music", "handle": "Linus", "scener": ""},
    ]
    assert release.downloads[0]["name"] == "next_level_performers.zip"
    assert release.downloads[0]["downloads"] == 11029
    assert release.sids[0]["path"] == "/MUSICIANS/L/Linus/Next_Level_Side_3.sid"
    assert release.sids[0]["songs"] == 1
    assert release.comments[0]["user"] == "BroBryce64"
    assert release.comments[0]["text"] == "Nice one."


def test_release_without_xml_is_an_error(csdb):
    with pytest.raises(csdb.CsdbError):
        csdb.parse_release("<html>not xml at all")


def test_cache_expires(csdb):
    now = [0.0]
    cache = csdb.CsdbCache(seconds=10, clock=lambda: now[0])
    cache.put("front", {"latest": []})
    assert cache.get("front") == {"latest": []}
    now[0] = 5
    assert cache.get("front") is not None
    now[0] = 11
    assert cache.get("front") is None


def test_entries_serialise_with_a_csdb_url(csdb):
    entry = csdb.CsdbEntry(id=1, name="Demo", place=2, rating="9.5")
    data = entry.as_dict()
    assert data["url"] == "https://csdb.dk/release/?id=1"
    assert data["place"] == 2
    assert data["rating"] == "9.5"


def test_unpack_images_keeps_only_images_and_flat_names(csdb, tmp_path):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo/next_level.d64", b"disk")
        archive.writestr("demo/readme.txt", b"text")
        archive.writestr("../../escape.prg", b"prg")
        archive.writestr("demo/sub/extra.crt", b"crt")
    written = csdb.unpack_images(buffer.getvalue(), tmp_path / "csdb" / "1")
    assert sorted(written) == ["escape.prg", "extra.crt", "next_level.d64"]
    target = tmp_path / "csdb" / "1"
    assert (target / "next_level.d64").read_bytes() == b"disk"
    # Nothing was written outside the folder.
    assert not (tmp_path / "escape.prg").exists()
    assert not (tmp_path.parent / "escape.prg").exists()


def test_unpack_images_keeps_existing_files_without_overwrite(csdb, tmp_path):
    import io
    import zipfile

    target = tmp_path / "x"
    target.mkdir()
    (target / "a.d64").write_bytes(b"old")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.d64", b"new")
    assert csdb.unpack_images(buffer.getvalue(), target) == ["a.d64"]
    assert (target / "a.d64").read_bytes() == b"old"
    csdb.unpack_images(buffer.getvalue(), target, overwrite=True)
    assert (target / "a.d64").read_bytes() == b"new"


def test_a_page_instead_of_an_archive_is_recognised(csdb):
    assert csdb.looks_like_zip(b"PK\x03\x04rest") is True
    assert csdb.looks_like_zip(b"<!DOCTYPE html><html></html>") is False
    assert csdb.looks_like_zip(b"") is False
    described = csdb._describe(b"<html>blocked</html>", "text/html")
    assert described.startswith("HTML instead of a ZIP")
    assert "text/html" in described


def test_the_second_link_is_used_when_the_first_answers_with_html(csdb):
    import asyncio

    links = [
        {"url": "https://www.c64.com/demos/download.php?id=1368", "name": "download.php?id=1368"},
        {"url": "https://csdb.dk/getinternalfile.php/16959/Piece of Cake.zip", "name": "Piece of Cake.zip"},
    ]

    async def fetch(session, url):
        if "c64.com" in url:
            return b"<!DOCTYPE html><html>blocked</html>", "text/html", ""
        return b"PK\x03\x04zipdata", "application/octet-stream", ""

    link, data = asyncio.run(csdb.async_download_archive(None, links, fetch=fetch))
    assert link["name"] == "Piece of Cake.zip"
    assert data.startswith(b"PK")


def test_the_file_name_comes_from_the_content_disposition(csdb):
    import asyncio

    async def fetch(session, url):
        return b"PK\x03\x04x", "application/octet-stream", "piece_of_cake_1.zip"

    links = [{"url": "https://www.c64.com/x", "name": "download.php?id=1368"}]
    link, _ = asyncio.run(csdb.async_download_archive(None, links, fetch=fetch))
    assert link["name"] == "piece_of_cake_1.zip"


def test_a_failure_says_what_came_back_instead(csdb):
    import asyncio

    async def fetch(session, url):
        return b"<html>nope</html>", "text/html", ""

    links = [{"url": "https://a/x", "name": "a.zip"}, {"url": "https://b/y", "name": "b.zip"}]
    with pytest.raises(csdb.CsdbError) as err:
        asyncio.run(csdb.async_download_archive(None, links, fetch=fetch))
    message = str(err.value)
    assert "No download answered with a ZIP archive" in message
    assert "a.zip" in message and "b.zip" in message
    assert "HTML instead of a ZIP" in message
