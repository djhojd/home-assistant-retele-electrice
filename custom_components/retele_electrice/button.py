"""Button platform for Rețele Electrice."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_POD
from .coordinator import ReteleElectriceCoordinator
from ._device import build_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    pod = entry.data[CONF_POD]
    async_add_entities([
        ReteleElectriceSyncButton(coordinator, pod, entry.data),
        RefreshPodInfoButton(coordinator, pod, entry.data),
    ])

class ReteleElectriceSyncButton(ButtonEntity):
    """Button to trigger a manual sync."""

    _attr_has_entity_name = True
    _attr_name = "Sync Data"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator: ReteleElectriceCoordinator, pod: str, entry_data: dict) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_sync_button"
        self._attr_device_info = build_device_info(pod, entry_data)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual sync triggered for POD %s", self.pod)
        await self.coordinator.async_request_refresh()


class RefreshPodInfoButton(ButtonEntity):
    """Button to fetch fresh POD info from the portal."""

    _attr_has_entity_name = True
    _attr_name = "Refresh POD Info"
    _attr_icon = "mdi:database-refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, pod, entry_data):
        self.coordinator = coordinator
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_refresh_pod_info"
        self._attr_device_info = build_device_info(pod, entry_data)

    async def async_press(self) -> None:
        _LOGGER.debug("POD info refresh button pressed for %s", self.pod)
        try:
            await self.coordinator.async_refresh_pod_info()
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to refresh POD info for {self.pod}: {err}"
            ) from err
