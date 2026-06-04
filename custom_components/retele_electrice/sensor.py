"""Sensor platform for Retele Electrice."""
import logging
from dataclasses import dataclass
from datetime import date, datetime

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

# Strings longer than this are truncated for the sensor's state (with an
# ellipsis suffix); the untruncated value is exposed via the `full_value`
# attribute so templates remain lossless.
_MAX_STATE_LEN = 50


@dataclass(frozen=True)
class _PodFieldDescriptor:
    """Static metadata for one POD-info field promoted to its own sensor."""

    key: str                                # pod_info dict key (raw API name)
    name: str                               # English label shown in the UI
    suffix: str                             # unique_id / entity_id suffix
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    icon: str | None = None


# Order here drives the order entities are registered (and therefore the order
# they typically appear in the UI). Group: useful → contractual → technical.
_POD_FIELD_DESCRIPTORS: tuple[_PodFieldDescriptor, ...] = (
    # --- Useful ---
    _PodFieldDescriptor("nume_client", "Customer", "customer",
                        icon="mdi:account"),
    _PodFieldDescriptor("adresa_locons", "Consumption address",
                        "consumption_address", icon="mdi:map-marker"),
    _PodFieldDescriptor("furnizor", "Supplier", "supplier",
                        icon="mdi:office-building"),
    _PodFieldDescriptor("kw_aprobata", "Contracted power", "contracted_power",
                        device_class=SensorDeviceClass.POWER, unit="kW"),
    _PodFieldDescriptor("kw_evacuata", "Export power", "export_power",
                        device_class=SensorDeviceClass.POWER, unit="kW"),
    # --- Contractual / regulatory ---
    _PodFieldDescriptor("atr_number", "ATR number", "atr_number",
                        icon="mdi:file-document"),
    _PodFieldDescriptor("atr_date", "ATR date", "atr_date",
                        device_class=SensorDeviceClass.DATE),
    _PodFieldDescriptor("cer_version", "Consumer registry version",
                        "cer_version", icon="mdi:tag"),
    _PodFieldDescriptor("cer_date", "Consumer registry date", "cer_date",
                        device_class=SensorDeviceClass.DATE),
    _PodFieldDescriptor("activ", "Active flag", "active_flag",
                        icon="mdi:check-circle"),
    _PodFieldDescriptor("activ_furnizor_la", "Supplier active since",
                        "supplier_active_since",
                        device_class=SensorDeviceClass.DATE),
    _PodFieldDescriptor("activ_consumator_la", "Consumer active since",
                        "consumer_active_since",
                        device_class=SensorDeviceClass.DATE),
    _PodFieldDescriptor("furnizor_pre", "Previous supplier", "previous_supplier",
                        icon="mdi:office-building-outline"),
    # --- Technical / niche ---
    _PodFieldDescriptor("telecitit", "Smart-metered", "smart_metered",
                        icon="mdi:meter-electric"),
    _PodFieldDescriptor("delimitare", "Delimitation point", "delimitation_point",
                        icon="mdi:transit-connection-variant"),
    _PodFieldDescriptor("u_delimitare", "Delimitation voltage",
                        "delimitation_voltage", icon="mdi:flash"),
    _PodFieldDescriptor("meter_det_tip", "Meter type code", "meter_type_code",
                        icon="mdi:identifier"),
    _PodFieldDescriptor("meter_tipmontaj_cod", "Meter install type",
                        "meter_install_type", icon="mdi:wrench"),
    _PodFieldDescriptor("meter_constanta", "Meter constant", "meter_constant",
                        icon="mdi:function-variant"),
    _PodFieldDescriptor("meter_precizie", "Meter precision class",
                        "meter_precision_class", icon="mdi:bullseye-arrow"),
    _PodFieldDescriptor("meter_data_montare", "Meter install date",
                        "meter_install_date",
                        device_class=SensorDeviceClass.DATE),
)


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

    # Dynamic per-field diagnostic sensors. Only registered for fields whose
    # value is populated; new fields appearing after a POD-info refresh add
    # new sensors via the dispatcher subscription below.
    already_added: set[str] = set()

    def _register_field_sensors() -> None:
        new = _build_pod_field_sensors(entry, pod, already_added)
        if new:
            async_add_entities(new)
            already_added.update(s._descriptor.key for s in new)

    _register_field_sensors()

    signal = f"retele_electrice_pod_info_updated_{entry.entry_id}"
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal, _register_field_sensors)
    )


def _build_pod_field_sensors(
    entry: ConfigEntry, pod: str, already_added: set[str],
) -> list["PodFieldSensor"]:
    """Return one `PodFieldSensor` per descriptor that should be added now.

    Skips descriptors whose key is in `already_added` and descriptors whose
    `pod_info[key]` is missing, None, or empty. Returning a list rather than
    side-effecting `async_add_entities` keeps this unit-testable without HA.
    """
    info = entry.data.get("pod_info") or {}
    return [
        PodFieldSensor(entry, pod, d)
        for d in _POD_FIELD_DESCRIPTORS
        if d.key not in already_added and info.get(d.key) not in (None, "")
    ]


class ReteleElectriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Retele Electrice Sensor."""

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
    _attr_name = "POD Info Last Sync"
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    # Romanian field names returned by the API; these populate DeviceInfo
    # in build_device_info() so they're excluded from the attribute dict.
    _DEVICE_INFO_KEYS = frozenset({
        "meter_marca",
        "meter_seria",
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


class PodFieldSensor(SensorEntity):
    """Diagnostic sensor exposing one pod_info field as its own entity.

    Reads `entry.data["pod_info"][descriptor.key]` on every state read so
    it always reflects the latest persisted value. Re-renders in response
    to the `retele_electrice_pod_info_updated_<entry_id>` dispatcher signal.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, pod: str,
                 descriptor: _PodFieldDescriptor) -> None:
        self._entry = entry
        self._descriptor = descriptor
        self._attr_unique_id = f"retele_electrice_{pod}_{descriptor.suffix}"
        self._attr_name = descriptor.name
        self._attr_icon = descriptor.icon
        self._attr_device_class = descriptor.device_class
        self._attr_native_unit_of_measurement = descriptor.unit
        self._attr_device_info = build_device_info(pod, entry.data)

    @property
    def native_value(self):
        info = self._entry.data.get("pod_info") or {}
        value = info.get(self._descriptor.key)
        if value is None:
            return None
        if self._descriptor.device_class is SensorDeviceClass.DATE:
            try:
                return date.fromisoformat(value)
            except (TypeError, ValueError):
                return None
        if isinstance(value, str) and len(value) > _MAX_STATE_LEN:
            return value[:_MAX_STATE_LEN].rstrip() + "…"
        return value

    @property
    def extra_state_attributes(self):
        info = self._entry.data.get("pod_info") or {}
        value = info.get(self._descriptor.key)
        if isinstance(value, str) and len(value) > _MAX_STATE_LEN:
            return {"full_value": value}
        return None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        signal = f"retele_electrice_pod_info_updated_{self._entry.entry_id}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_updated)
        )

    @callback
    def _on_updated(self):
        self.async_write_ha_state()
