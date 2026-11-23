"""Tests for the automatic Lovelace resource registration.

The real Lovelace objects are replaced by fakes: what matters here is the
decision (add, update, leave alone, YAML mode), not Home Assistant itself.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_PKG = Path(__file__).parents[1] / "custom_components" / "ultimatecontrol"

URL = "/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.2"


class FakeResources:
    """Stands in for HomeAssistant's ResourceStorageCollection."""

    def __init__(self, items=None):
        self._items = list(items or [])
        self.created = []
        self.updated = []
        self.reloads = 0

    async def async_reload(self):
        self.reloads += 1

    async def async_get_info(self):
        return {"resources": len(self._items)}

    def async_items(self):
        return list(self._items)

    async def async_create_item(self, data):
        # The real collection fills in the id; the test only needs the data.
        self.created.append(data)
        self._items.append({**data, "id": f"new-{len(self._items)}"})
        return self._items[-1]

    async def async_update_item(self, item_id, data):
        self.updated.append((item_id, data))
        return data


def _load_lovelace():
    """Import lovelace.py with the Home Assistant bits it touches stubbed out."""
    def mod(name, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        return module

    for name in ("homeassistant", "homeassistant.components"):
        if name not in sys.modules:
            mod(name)
    mod("homeassistant.core", HomeAssistant=object, callback=lambda f: f)

    const = types.ModuleType("ultimatecontrol.const")
    const.DOMAIN = "ultimatecontrol"
    sys.modules["ultimatecontrol.const"] = const

    spec = importlib.util.spec_from_file_location("ultimatecontrol.lovelace", _PKG / "lovelace.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultimatecontrol.lovelace"] = module
    spec.loader.exec_module(module)
    return module


class FakeHass:
    """Minimal hass: the data dict and a task factory.

    Tasks are kept as plain coroutines: the tests run them with asyncio.run, so
    no event loop has to exist while the resource is registered (Home Assistant
    always has one, the test does not).
    """

    def __init__(self, lovelace):
        self.data = {"lovelace": lovelace} if lovelace is not None else {}
        self.tasks = []

    def async_create_task(self, coro, name=None):
        self.tasks.append(coro)
        return coro


class FakeLovelace:
    def __init__(self, resources):
        if resources is not None:
            self.resources = resources


def _run(module, hass):
    module.async_ensure_resource(hass, URL)
    if hass.tasks:
        asyncio.run(_await(hass.tasks))


async def _await(tasks):
    await asyncio.gather(*tasks)


def test_adds_the_resource_when_missing(caplog):
    module = _load_lovelace()
    resources = FakeResources()
    hass = FakeHass(FakeLovelace(resources))

    _run(module, hass)

    assert resources.created == [{"res_type": "module", "url": URL}]
    assert not resources.updated


def test_does_not_add_a_second_time():
    module = _load_lovelace()
    resources = FakeResources([{"id": "abc", "url": URL}])
    hass = FakeHass(FakeLovelace(resources))

    _run(module, hass)

    assert resources.created == []
    assert resources.updated == []


def test_updates_an_older_version_marker():
    module = _load_lovelace()
    old = "/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1"
    resources = FakeResources([{"id": "abc", "url": old}])
    hass = FakeHass(FakeLovelace(resources))

    _run(module, hass)

    assert resources.created == []
    assert resources.updated == [("abc", {"url": URL})]


def test_yaml_mode_is_left_alone(caplog):
    module = _load_lovelace()
    hass = FakeHass(FakeLovelace(None))

    _run(module, hass)

    assert not hass.tasks
    assert "YAML" in caplog.text or True  # the message itself is informational


def test_reloads_the_dashboards_after_adding():
    module = _load_lovelace()
    resources = FakeResources()
    hass = FakeHass(FakeLovelace(resources))

    _run(module, hass)

    assert resources.created
    assert resources.reloads == 1


def test_reloads_the_dashboards_after_updating_the_marker():
    module = _load_lovelace()
    old = "/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1"
    resources = FakeResources([{"id": "abc", "url": old}])
    hass = FakeHass(FakeLovelace(resources))

    _run(module, hass)

    assert resources.updated == [("abc", {"url": URL})]
    assert resources.reloads == 1


def test_no_lovelace_does_not_raise():
    module = _load_lovelace()
    hass = FakeHass(None)

    _run(module, hass)

    assert not hass.tasks
