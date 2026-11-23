"""Tests for saved playlists.

A playlist is a small JSON file of tune references; these tests pin the file
handling, the duplicate rule and the editing operations.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


playlist_mod = _load("ultimatecontrol.playlist", _PKG / "playlist.py")
PlaylistStore = playlist_mod.PlaylistStore
PlaylistError = playlist_mod.PlaylistError


def _store(tmp_path: Path) -> PlaylistStore:
    store = PlaylistStore(tmp_path)
    store.ensure_dir()
    return store


def test_a_new_playlist_is_written_as_json(tmp_path):
    store = _store(tmp_path)
    store.add("Meine Favoriten", [{"path": "A/B.sid", "song": 2}])
    file = tmp_path / "playlists" / "Meine Favoriten.json"
    assert file.is_file()
    data = json.loads(file.read_text(encoding="utf-8"))
    assert data["items"][0]["path"] == "A/B.sid"
    assert data["items"][0]["song"] == 2
    assert data["items"][0]["name"] == "B.sid"


def test_an_entry_needs_no_copy_of_the_sid(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "MUSICIANS/H/Hubbard/Commando.sid"}])
    raw = (tmp_path / "playlists" / "p.json").read_text(encoding="utf-8")
    assert "PSID" not in raw
    assert len(raw) < 400


def test_a_tune_is_only_once_in_a_playlist(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "A.sid", "song": 1}])
    store.add("p", [{"path": "A.sid", "song": 1}, {"path": "A.sid", "song": 2}])
    loaded = store.load("p")
    assert loaded is not None
    # Same file, different tune: that is a second entry.
    assert [item["song"] for item in loaded.items] == [1, 2]


def test_adding_to_a_missing_playlist_creates_it(tmp_path):
    store = _store(tmp_path)
    assert store.load("neu") is None
    store.add("neu", [{"path": "x.sid"}])
    assert store.load("neu").count == 1


def test_entries_can_be_removed_by_position(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "a.sid"}, {"path": "b.sid"}, {"path": "c.sid"}])
    store.remove_entry("p", 1)
    assert [item["path"] for item in store.load("p").items] == ["a.sid", "c.sid"]


def test_removing_an_entry_that_does_not_exist_is_an_error(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "a.sid"}])
    try:
        store.remove_entry("p", 5)
    except PlaylistError as err:
        assert "entry" in str(err)
    else:
        raise AssertionError("expected PlaylistError")


def test_clearing_keeps_the_playlist(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "a.sid"}])
    store.clear("p")
    assert store.load("p") is not None
    assert store.load("p").count == 0


def test_the_list_shows_names_and_counts_sorted(tmp_path):
    store = _store(tmp_path)
    store.add("Zweite", [{"path": "a.sid"}])
    store.add("erste", [{"path": "b.sid"}, {"path": "c.sid"}])
    assert store.list() == [
        {"name": "erste", "count": 2},
        {"name": "Zweite", "count": 1},
    ]


def test_a_playlist_can_be_deleted(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": "a.sid"}])
    assert store.delete("p") is True
    assert store.load("p") is None
    assert store.delete("p") is False


def test_a_name_that_would_leave_the_folder_is_refused(tmp_path):
    store = _store(tmp_path)
    try:
        store.add("../../etc/passwd", [{"path": "a.sid"}])
    except PlaylistError:
        pass
    # The name is sanitised, so nothing is written outside the folder.
    assert not (tmp_path.parent / "etc").exists()
    assert [item["name"] for item in store.list()] == ["etcpasswd"]


def test_an_empty_name_is_refused(tmp_path):
    store = _store(tmp_path)
    try:
        store.add("   ", [{"path": "a.sid"}])
    except PlaylistError:
        return
    raise AssertionError("expected PlaylistError")


def test_an_unreadable_file_does_not_break_the_list(tmp_path):
    store = _store(tmp_path)
    store.add("gut", [{"path": "a.sid"}])
    (tmp_path / "playlists" / "kaputt.json").write_text("{nicht json", encoding="utf-8")
    assert [item["name"] for item in store.list()] == ["gut"]


def test_an_entry_without_a_path_is_ignored(tmp_path):
    store = _store(tmp_path)
    store.add("p", [{"path": ""}, {"path": "a.sid"}])
    assert store.load("p").count == 1
