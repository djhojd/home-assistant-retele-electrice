"""The Rețele Electrice integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_POD, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .api import ReteleElectriceApi
from .coordinator import ReteleElectriceCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rețele Electrice from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    pod = entry.data[CONF_POD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    api = ReteleElectriceApi(email, password)
    
    coordinator = ReteleElectriceCoordinator(hass, api, pod, update_interval)
    coordinator.config_entry = entry

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # First-install hook: fetch POD info if we don't have it yet. Non-blocking —
    # integration setup completes immediately even if the fetch is slow or fails.
    if "pod_info" not in entry.data:
        _LOGGER.debug("POD info absent for %s, scheduling initial fetch", pod)

        async def _initial_pod_info_fetch():
            try:
                await coordinator.async_refresh_pod_info()
                new_info = entry.data.get("pod_info") or {}
                _LOGGER.info(
                    "Initial POD info fetched for %s (%d fields)",
                    pod, len(new_info),
                )
            except Exception as err:
                _LOGGER.warning(
                    "Initial POD info fetch failed for %s: %s; integration "
                    "loaded without metadata. Press the Refresh POD Info button "
                    "to retry.",
                    pod, err,
                )

        hass.async_create_task(_initial_pod_info_fetch())
    else:
        _LOGGER.debug(
            "Loaded persisted POD info for %s (refreshed_at=%s)",
            pod, entry.data.get("pod_info_refreshed_at"),
        )

    async_register_services(hass)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()

    return unload_ok
