"""Service handlers for the Rețele Electrice integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from homeassistant.components.recorder.statistics import (
    async_clear_statistics,
    list_statistic_ids,
)
from homeassistant.components.recorder.util import get_instance

from .const import DOMAIN, CONF_POD, stat_id_prefix

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
        """Validate input then clear matching statistics."""
        if call.data.get(ATTR_CONFIRM) is not True:
            raise ServiceValidationError(
                "confirm must be true to clear statistics"
            )

        requested_pod = call.data.get(ATTR_POD)
        configured_pods = {
            entry.data[CONF_POD]
            for entry in hass.config_entries.async_entries(DOMAIN)
            if CONF_POD in entry.data
        }

        if requested_pod is not None:
            if requested_pod not in configured_pods:
                raise ServiceValidationError(
                    f"POD {requested_pod} is not configured for this integration"
                )
            target_pods = {requested_pod}
        else:
            target_pods = configured_pods

        if not target_pods:
            _LOGGER.info("No PODs configured — nothing to clear")
            return

        recorder = get_instance(hass)

        # list_statistic_ids is sync; run in executor.
        all_stats = await recorder.async_add_executor_job(
            list_statistic_ids, hass, None, None
        )

        target_prefixes = tuple(stat_id_prefix(p) for p in target_pods)
        targets = [
            entry["statistic_id"]
            for entry in all_stats
            if entry.get("source") == DOMAIN
            and entry["statistic_id"].startswith(target_prefixes)
        ]

        if not targets:
            _LOGGER.info(
                "No matching statistics found for pods=%s — nothing to do",
                target_pods,
            )
            return

        await recorder.async_add_executor_job(
            async_clear_statistics, hass, targets
        )

        for stat_id in targets:
            _LOGGER.info("Cleared %s", stat_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_STATISTICS,
        _handle_clear_statistics,
        schema=CLEAR_STATISTICS_SCHEMA,
    )
