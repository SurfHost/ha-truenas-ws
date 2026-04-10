"""Config flow for TrueNAS integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TrueNASWebSocketClient
from .const import CONF_API_KEY, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import TrueNASConfigEntry
from .errors import TrueNASAuthenticationError, TrueNASConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)


class TrueNASConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TrueNAS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(
                self.hass,
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
            )
            client = TrueNASWebSocketClient(
                host=user_input[CONF_HOST],
                api_key=user_input[CONF_API_KEY],
                session=session,
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
            )

            try:
                await client.connect()
                system_info = await client.get_system_info()
                await client.disconnect()
            except TrueNASConnectionError:
                errors["base"] = "cannot_connect"
            except TrueNASAuthenticationError:
                errors["base"] = "invalid_auth"
            except (TimeoutError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(system_info.hostname)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=system_info.hostname,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            session = async_get_clientsession(
                self.hass,
                verify_ssl=reauth_entry.data.get(CONF_VERIFY_SSL, False),
            )
            client = TrueNASWebSocketClient(
                host=reauth_entry.data[CONF_HOST],
                api_key=user_input[CONF_API_KEY],
                session=session,
                verify_ssl=reauth_entry.data.get(CONF_VERIFY_SSL, False),
            )

            try:
                await client.connect()
                await client.get_system_info()
                await client.disconnect()
            except TrueNASAuthenticationError:
                errors["base"] = "invalid_auth"
            except TrueNASConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: TrueNASConfigEntry,
    ) -> TrueNASOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TrueNASOptionsFlowHandler()


class TrueNASOptionsFlowHandler(OptionsFlow):
    """Handle TrueNAS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
        )
