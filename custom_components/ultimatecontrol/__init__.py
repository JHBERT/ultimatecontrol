DOMAIN = "ultimatecontrol"


async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})
    return True