import voluptuous as vol

from homeassistant import config_entries

DOMAIN = "ultimatecontrol"


class UltimateControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UltimateControl."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="UltimateControl C64",
                data=user_input,
            )

        data_schema = vol.Schema({
            vol.Required("host"): str,
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)