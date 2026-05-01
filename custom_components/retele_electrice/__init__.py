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

    async_register_services(hass)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()

    return unload_ok
