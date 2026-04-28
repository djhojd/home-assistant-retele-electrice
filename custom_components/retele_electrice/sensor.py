"""Sensor platform for Rețele Electrice."""
import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_POD
from .coordinator import ReteleElectriceCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    pod = entry.data[CONF_POD]
    async_add_entities([ReteleElectriceSensor(coordinator, pod)])

class ReteleElectriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Rețele Electrice Sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_name = "Last Sync"
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator: ReteleElectriceCoordinator, pod: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pod)},
            name=f"Rețele Electrice {pod}",
            manufacturer="Rețele Electrice",
            model="Energy Meter",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("last_update")
        return None
