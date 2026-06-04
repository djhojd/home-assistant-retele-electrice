"""Tests for the per-field POD info diagnostic sensors."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from custom_components.retele_electrice.sensor import (
    _MAX_STATE_LEN,
    _POD_FIELD_DESCRIPTORS,
    PodFieldSensor,
    _build_pod_field_sensors,
)
from homeassistant.components.sensor import SensorDeviceClass


POD = "RO005EXXXXXXXXX"


def _entry_with(pod_info: dict | None) -> MagicMock:
    """Build a fake ConfigEntry whose `.data` carries `pod_info` (or None)."""
    entry = MagicMock()
    entry.data = {"pod": POD}
    if pod_info is not None:
        entry.data["pod_info"] = pod_info
    entry.entry_id = "test_entry_id"
    return entry


def _descriptor(key: str):
    """Find the descriptor for `key` in the production list."""
    for d in _POD_FIELD_DESCRIPTORS:
        if d.key == key:
            return d
    raise KeyError(f"No descriptor for key={key!r}")


# ---------------------------------------------------------------------------
# Descriptor-list invariants
# ---------------------------------------------------------------------------


def test_descriptor_suffixes_are_unique():
    """Two descriptors with the same suffix would collide on unique_id."""
    suffixes = [d.suffix for d in _POD_FIELD_DESCRIPTORS]
    assert len(suffixes) == len(set(suffixes)), f"duplicate suffixes: {suffixes}"


def test_descriptor_keys_are_unique():
    """Two descriptors for the same pod_info key would double-render the same value."""
    keys = [d.key for d in _POD_FIELD_DESCRIPTORS]
    assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"


def test_no_sensitive_fields_promoted():
    """Privacy boundary: sensitive fields must never be promoted to sensors.

    They stay attribute-only on the existing PodInfoSensor.
    """
    forbidden = {"cui", "adresa_client", "nr_cadastral", "carte_funciara"}
    promoted = {d.key for d in _POD_FIELD_DESCRIPTORS}
    leaked = forbidden & promoted
    assert not leaked, f"sensitive keys leaked into sensor descriptors: {leaked}"


# ---------------------------------------------------------------------------
# PodFieldSensor.native_value
# ---------------------------------------------------------------------------


def test_native_value_returns_str_for_populated_string_field():
    entry = _entry_with({"nume_client": "EXAMPLE CUSTOMER"})
    sensor = PodFieldSensor(entry, POD, _descriptor("nume_client"))
    assert sensor.native_value == "EXAMPLE CUSTOMER"


def test_native_value_returns_none_when_key_missing():
    entry = _entry_with({})  # pod_info present but field absent
    sensor = PodFieldSensor(entry, POD, _descriptor("nume_client"))
    assert sensor.native_value is None


def test_native_value_returns_none_when_pod_info_missing():
    entry = _entry_with(None)  # no pod_info at all (pre-first-refresh)
    sensor = PodFieldSensor(entry, POD, _descriptor("nume_client"))
    assert sensor.native_value is None


def test_native_value_parses_date_field():
    entry = _entry_with({"atr_date": "2020-01-15"})
    sensor = PodFieldSensor(entry, POD, _descriptor("atr_date"))
    assert sensor.native_value == date(2020, 1, 15)


def test_native_value_returns_none_for_malformed_date():
    entry = _entry_with({"atr_date": "not-a-date"})
    sensor = PodFieldSensor(entry, POD, _descriptor("atr_date"))
    assert sensor.native_value is None


def test_native_value_returns_float_for_power_field():
    entry = _entry_with({"kw_aprobata": 6.0})
    sensor = PodFieldSensor(entry, POD, _descriptor("kw_aprobata"))
    assert sensor.native_value == 6.0


def test_native_value_truncates_long_string():
    long = "La bornele de iesire din contorul de energie electrica si altele"
    assert len(long) > _MAX_STATE_LEN
    entry = _entry_with({"delimitare": long})
    sensor = PodFieldSensor(entry, POD, _descriptor("delimitare"))
    value = sensor.native_value
    assert value.endswith("…")
    # Truncated chunk fits within _MAX_STATE_LEN; ellipsis adds 1 char.
    assert len(value) <= _MAX_STATE_LEN + 1
    assert long.startswith(value.rstrip("…").rstrip())


def test_extra_state_attributes_has_full_value_only_for_truncated_strings():
    long = "La bornele de iesire din contorul de energie electrica si altele"
    entry = _entry_with({"delimitare": long, "nume_client": "SHORT"})
    long_sensor = PodFieldSensor(entry, POD, _descriptor("delimitare"))
    short_sensor = PodFieldSensor(entry, POD, _descriptor("nume_client"))
    assert long_sensor.extra_state_attributes == {"full_value": long}
    assert short_sensor.extra_state_attributes is None


# ---------------------------------------------------------------------------
# Dynamic registration (_build_pod_field_sensors)
# ---------------------------------------------------------------------------


def test_build_skips_descriptors_with_null_values():
    """Only descriptors whose pod_info value is populated produce a sensor."""
    entry = _entry_with({
        "nume_client": "EXAMPLE CUSTOMER",
        "kw_aprobata": 6.0,
        "kw_evacuata": None,         # null -> skip
        "furnizor": "",              # empty -> skip
        # all other keys absent -> skip
    })
    new = _build_pod_field_sensors(entry, POD, already_added=set())
    keys = {s._descriptor.key for s in new}
    assert keys == {"nume_client", "kw_aprobata"}


def test_build_skips_already_added_descriptors():
    """Refreshes don't double-register sensors that already exist."""
    entry = _entry_with({
        "nume_client": "EXAMPLE CUSTOMER",
        "kw_aprobata": 6.0,
    })
    new = _build_pod_field_sensors(entry, POD, already_added={"nume_client"})
    keys = {s._descriptor.key for s in new}
    assert keys == {"kw_aprobata"}, "only the new key should produce a sensor"


def test_build_returns_empty_when_pod_info_missing():
    """Pre-first-refresh state: no pod_info -> no sensors."""
    entry = _entry_with(None)
    new = _build_pod_field_sensors(entry, POD, already_added=set())
    assert new == []


def test_build_returns_new_sensor_when_field_appears_after_refresh():
    """Simulate kw_evacuata flipping from None -> 5.0 between refreshes."""
    # First refresh: kw_evacuata null, only kw_aprobata populated.
    entry = _entry_with({"kw_aprobata": 6.0, "kw_evacuata": None})
    initial = _build_pod_field_sensors(entry, POD, already_added=set())
    already = {s._descriptor.key for s in initial}
    assert already == {"kw_aprobata"}

    # Second refresh: kw_evacuata now populated -> exactly one new sensor.
    entry.data["pod_info"]["kw_evacuata"] = 5.0
    new = _build_pod_field_sensors(entry, POD, already_added=already)
    keys = {s._descriptor.key for s in new}
    assert keys == {"kw_evacuata"}


# ---------------------------------------------------------------------------
# Descriptor metadata sanity
# ---------------------------------------------------------------------------


def test_kw_descriptors_have_power_device_class():
    """Sanity: kW fields should be rendered as POWER in HA's UI/templates."""
    for key in ("kw_aprobata", "kw_evacuata"):
        d = _descriptor(key)
        assert d.device_class is SensorDeviceClass.POWER
        assert d.unit == "kW"


def test_date_descriptors_have_date_device_class():
    """Sanity: *_date fields should be rendered as DATE."""
    for key in ("atr_date", "cer_date", "activ_furnizor_la", "activ_consumator_la"):
        d = _descriptor(key)
        assert d.device_class is SensorDeviceClass.DATE
