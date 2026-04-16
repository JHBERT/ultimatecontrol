from homeassistant.components.media_player import MediaPlayerEntity

class UltimateMediaPlayer(MediaPlayerEntity):
    def __init__(self):
        self._attr_name = "Ultimate C64 Player"

    def play_media(self, media_type, media_id, **kwargs):
        # Hier kommt später der API Call zum Ultimate II+
        pass