"""Button platform for Rețele Electrice."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_POD
from .coordinator import ReteleElectriceCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    pod = entry.data[CONF_POD]
    async_add_entities([ReteleElectriceSyncButton(coordinator, pod)])

class ReteleElectriceSyncButton(ButtonEntity):
    """Button to trigger a manual sync."""

    _attr_has_entity_name = True
    _attr_name = "Sync Data"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator: ReteleElectriceCoordinator, pod: str) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_sync_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pod)},
            name=f"Rețele Electrice {pod}",
            manufacturer="Rețele Electrice",
            model="Energy Meter",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual sync triggered for POD %s", self.pod)
        await self.coordinator.async_request_refresh()
