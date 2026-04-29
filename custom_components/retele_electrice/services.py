"""Service handlers for the Rețele Electrice integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_POD

_LOGGER = logging.getLogger(__name__)

SERVICE_CLEAR_STATISTICS = "clear_statistics"
ATTR_CONFIRM = "confirm"
ATTR_POD = "pod"

CLEAR_STATISTICS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIRM): cv.boolean,
        vol.Optional(ATTR_POD): cv.string,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services. Idempotent."""
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_STATISTICS):
        return

    async def _handle_clear_statistics(call: ServiceCall) -> None:
        """Stub — full implementation lands in a later task."""
        _LOGGER.warning(
            "clear_statistics called with %s — handler not yet implemented",
            dict(call.data),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_STATISTICS,
        _handle_clear_statistics,
        schema=CLEAR_STATISTICS_SCHEMA,
    )
