"""Shared DeviceInfo composition for all entities of one POD."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_POD_INFO_URL = (
    "https://contulmeu.reteleelectrice.ro/s/new-pod-info-client?pod={pod}"
)


def build_device_info(pod: str, entry_data: dict[str, Any]) -> DeviceInfo:
    """Compose DeviceInfo for `pod` from the persisted entry data.

    Standard DeviceInfo slots come from the meter section of pod_info; the
    rest of pod_info ends up on the diagnostic POD info sensor as attributes.
    Falls back to minimal static values if pod_info is absent (e.g. before
    the first refresh has succeeded).
    """
    pod_info: dict[str, Any] = entry_data.get("pod_info") or {}

    info = DeviceInfo(
        identifiers={(DOMAIN, pod)},
        name=f"Rețele Electrice {pod}",
        manufacturer="Rețele Electrice",
        configuration_url=_POD_INFO_URL.format(pod=pod),
    )

    # meter_marca is the brand+model identifier (e.g. "ACE2000 : 5/60A, 230 V").
    info["model"] = pod_info.get("meter_marca") or "Energy Meter"

    if serial := pod_info.get("meter_seria"):
        info["serial_number"] = serial
    if install_date := pod_info.get("meter_data_montare"):
        info["hw_version"] = install_date

    return info
