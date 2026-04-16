from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.const import STATE_IDLE

DOMAIN = "ultimatecontrol"


async def async_setup_entry(hass, config_entry, async_add_entities):
    host = config_entry.data["host"]

    async_add_entities([
        UltimateMediaPlayer(host)
    ])


class UltimateMediaPlayer(MediaPlayerEntity):
    def __init__(self, host):
        self._host = host
        self._attr_name = "Ultimate C64 Player"
        self._attr_state = STATE_IDLE

    async def async_play_media(self, media_type, media_id, **kwargs):
        # später: API Call zum Ultimate II+
        pass