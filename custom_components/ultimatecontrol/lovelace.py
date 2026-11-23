"""Register the dashboard card as a Lovelace resource.

The card is a JavaScript module. Home Assistant only loads it when its URL is a
resource of the dashboard, and adding that resource is a click the user would
otherwise have to do by hand. This module does it for the user:

* in ``storage`` mode (the usual UI mode) the resource is written into
  ``.storage/lovelace_resources`` and the running Lovelace instance is told to
  pick it up,
* in ``yaml`` mode nothing is written - that config belongs to the user - the
  message is logged instead, with the exact snippet to add.

Everything here is best effort: a dashboard that cannot be updated must never
break the integration.
"""

from __future__ import annotations

import logging

from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_ensure_resource(hass: HomeAssistant, url: str) -> None:
    """Add the card's URL to the Lovelace resources, once."""
    lovelace = hass.data.get(LOVELACE_DOMAIN)
    if lovelace is None:
        _LOGGER.debug("Lovelace is not set up; add the resource %s manually", url)
        return

    resources = getattr(lovelace, "resources", None)
    if resources is None:
        _LOGGER.info(
            "Lovelace runs in YAML mode; add this resource to configuration.yaml:\n"
            "lovelace:\n"
            "  resources:\n"
            "    - url: %s\n"
            "      type: module",
            url,
        )
        return

    hass.async_create_task(
        _async_ensure_resource(hass, resources, url),
        name=f"{DOMAIN} lovelace resource",
    )


async def _async_ensure_resource(
    hass: HomeAssistant, resources: ResourceStorageCollection, url: str
) -> None:
    """Wait for the resource collection, then add the URL if it is missing."""
    # The collection loads lazily; without this the list is empty on a fresh
    # start and the card would be added a second time.
    try:
        await resources.async_get_info()
    except Exception:  # noqa: BLE001 - never break setup over a dashboard
        _LOGGER.debug("Cannot read the Lovelace resources", exc_info=True)

    wanted = url.split("?", 1)[0]
    for item in resources.async_items():
        if str(item.get("url", "")).split("?", 1)[0] == wanted:
            if item.get("url") != url:
                # Same file, older version marker: update it so the browser
                # fetches the new card instead of a cached one.
                await resources.async_update_item(item["id"], {"url": url})
                _LOGGER.debug("Updated the Lovelace resource to %s", url)
            return

    await resources.async_create_item({"res_type": "module", "url": url})
    _LOGGER.info("Added the dashboard card as a Lovelace resource: %s", url)
