"""Config flow for UltimateControl."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    UltimateApi,
    UltimateApiError,
    UltimateAuthError,
    UltimateConnectionError,
)
from .const import (
    DEFAULT_FAVORITES_FOLDER,
    CONF_FAVORITES_FOLDER,
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
        vol.Optional(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_FAVORITES_FOLDER): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
    }
)


def _schema_with_defaults(schema: vol.Schema, defaults: dict[str, Any]) -> vol.Schema:
    """Return a schema with the given default values applied."""
    return schema.extend(defaults) if defaults else schema


class UltimateControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UltimateControl."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the device address and verify the device answers."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = UltimateApi(
                async_get_clientsession(self.hass),
                host=user_input[CONF_HOST].strip(),
                port=user_input.get(CONF_PORT, DEFAULT_PORT),
                password=user_input.get(CONF_PASSWORD) or None,
            )
            try:
                info = await api.async_test_connection()
            except UltimateAuthError:
                errors["base"] = "invalid_auth"
            except UltimateConnectionError:
                errors["base"] = "cannot_connect"
            except UltimateApiError:
                errors["base"] = "not_an_ultimate"
            else:
                await self.async_set_unique_id(
                    info.get("unique_id") or user_input[CONF_HOST],
                    raise_on_progress=False,
                )
                self._abort_if_unique_id_configured()

                name = user_input.get(CONF_NAME) or info.get("hostname") or DEFAULT_NAME
                data = {
                    CONF_HOST: user_input[CONF_HOST].strip(),
                    CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
                }
                return self.async_create_entry(title=name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema_with_defaults(
                STEP_USER_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start re-authentication when the network password is wrong."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new network password."""
        entry: ConfigEntry | None = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None and entry is not None:
            api = UltimateApi(
                async_get_clientsession(self.hass),
                host=entry.data[CONF_HOST],
                port=entry.data.get(CONF_PORT, DEFAULT_PORT),
                password=user_input.get(CONF_PASSWORD) or None,
            )
            try:
                await api.async_test_connection()
            except UltimateAuthError:
                errors["base"] = "invalid_auth"
            except UltimateConnectionError:
                errors["base"] = "cannot_connect"
            except UltimateApiError:
                errors["base"] = "not_an_ultimate"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> UltimateControlOptionsFlow:
        """Return the options flow."""
        return UltimateControlOptionsFlow()


class UltimateControlOptionsFlow(OptionsFlow):
    """Options: poll interval and network password."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_password = user_input.get(CONF_PASSWORD)
            entry = self.config_entry
            api = UltimateApi(
                async_get_clientsession(self.hass),
                host=entry.data[CONF_HOST],
                port=entry.data.get(CONF_PORT, DEFAULT_PORT),
                password=new_password or None,
            )
            try:
                await api.async_get_info()
            except UltimateAuthError:
                errors["base"] = "invalid_auth"
            except (UltimateConnectionError, UltimateApiError):
                errors["base"] = "cannot_connect"
            else:
                if new_password is not None:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_PASSWORD: new_password or None},
                    )
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_FAVORITES_FOLDER: (
                            user_input.get(CONF_FAVORITES_FOLDER) or ""
                        ).strip(),
                    }
                )

        current = {
            CONF_SCAN_INTERVAL: self.config_entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
        }
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    description={"suggested_value": current[CONF_SCAN_INTERVAL]},
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_FAVORITES_FOLDER,
                    default=self.config_entry.options.get(CONF_FAVORITES_FOLDER, ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
