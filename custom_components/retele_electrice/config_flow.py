"""Config flow for Retele Electrice integration."""
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_POD,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_UPDATE_INTERVAL_HOURS,
    current_update_interval_hours,
)
from .api import ReteleElectriceApi, ReteleElectriceAuthError

_LOGGER = logging.getLogger(__name__)


def _update_interval_field():
    """Return the schema value for the polling-interval field.

    Shared by STEP_USER_DATA_SCHEMA (install-time) and OptionsFlowHandler
    (post-install). `vol.Coerce(int)` keeps the on-disk type stable —
    NumberSelector returns float by default; we want int in entry.data.
    """
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=MIN_UPDATE_INTERVAL_HOURS,
                max=MAX_UPDATE_INTERVAL_HOURS,
                step=1,
                unit_of_measurement="hours",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Coerce(int),
    )


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_POD): str,
        vol.Required(
            CONF_UPDATE_INTERVAL_HOURS,
            default=DEFAULT_UPDATE_INTERVAL_HOURS,
        ): _update_interval_field(),
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = ReteleElectriceApi(data[CONF_EMAIL], data[CONF_PASSWORD])
    pod = data[CONF_POD]

    try:
        await api.login(pod)
    except ReteleElectriceAuthError as e:
        raise InvalidAuth from e
    except Exception as e:
        _LOGGER.error("Error connecting to Retele Electrice: %s", e)
        raise CannotConnect from e
    finally:
        await api.close()

    return {"title": f"Retele Electrice {pod}"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Retele Electrice."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth (e.g. an expired portal password) with a confirm form."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password and validate it before saving."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = {**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await validate_input(self.hass, new_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=new_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={CONF_EMAIL: reauth_entry.data[CONF_EMAIL]},
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow for Retele Electrice."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the config entry for later reads.

        Recent Home Assistant defines `OptionsFlow.config_entry` as a
        read-only property that derives the entry from `self.hass` and
        `self.handler` (both assigned by the framework when the flow
        starts). Assigning `self.config_entry = ...` therefore raises
        `AttributeError`. We keep an explicit reference so the handler
        is usable both from HA's flow machinery and from unit tests that
        construct it directly without a running HA.
        """
        self._config_entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry this options flow belongs to."""
        return self._config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = current_update_interval_hours(self.config_entry)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS, default=current
                ): _update_interval_field(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
