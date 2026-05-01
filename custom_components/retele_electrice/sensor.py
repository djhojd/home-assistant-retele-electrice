"""Sensor platform for Rețele Electrice."""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_POD
from .coordinator import ReteleElectriceCoordinator
from ._device import build_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    pod = entry.data[CONF_POD]
    async_add_entities([
        ReteleElectriceSensor(coordinator, pod, entry.data),
        PodInfoSensor(hass, entry, pod),
    ])

class ReteleElectriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Rețele Electrice Sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_name = "Last Sync"
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator: ReteleElectriceCoordinator, pod: str, entry_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_last_sync"
        self._attr_device_info = build_device_info(pod, entry_data)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("last_update")
        return None


class PodInfoSensor(SensorEntity):
    """Diagnostic sensor carrying the POD's static metadata as attributes."""

    _attr_has_entity_name = True
    _attr_name = "POD Info"
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    # Romanian field names returned by the API; these populate DeviceInfo
    # in build_device_info() so they're excluded from the attribute dict.
    _DEVICE_INFO_KEYS = frozenset({
        "meter_marca",
        "meter_seria",
        "meter_data_montare",
    })

    def __init__(self, hass, entry, pod):
        self.hass = hass
        self._entry = entry
        self.pod = pod
        self._attr_unique_id = f"retele_electrice_{pod}_pod_info"
        self._attr_device_info = build_device_info(pod, entry.data)

    @property
    def native_value(self):
        ts = self._entry.data.get("pod_info_refreshed_at")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        info = self._entry.data.get("pod_info") or {}
        return {k: v for k, v in info.items() if k not in self._DEVICE_INFO_KEYS}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        signal = f"retele_electrice_pod_info_updated_{self._entry.entry_id}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_updated)
        )

    @callback
    def _on_updated(self):
        self.async_write_ha_state()
