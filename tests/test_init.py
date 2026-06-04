"""Tests for integration setup and migration."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.retele_electrice import async_migrate_entry
from custom_components.retele_electrice.const import (
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_UPDATE_INTERVAL_HOURS,
)


def _make_v1_entry(data: dict) -> MagicMock:
    """Build a fake ConfigEntry pretending to be schema version 1."""
    entry = MagicMock()
    entry.version = 1
    entry.data = data
    return entry


async def test_migrate_v1_converts_minutes_to_hours():
    """v1 entry with update_interval=720 minutes -> v2 entry with update_interval_hours=12."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    entry = _make_v1_entry({
        "email": "e@example.com",
        "password": "p",
        "pod": "RO005EXXXXXXXXX",
        "update_interval": 720,
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_called_once()
    kwargs = hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["version"] == 2
    assert kwargs["data"][CONF_UPDATE_INTERVAL_HOURS] == 12
    assert "update_interval" not in kwargs["data"]
    # Other keys preserved
    assert kwargs["data"]["email"] == "e@example.com"
    assert kwargs["data"]["pod"] == "RO005EXXXXXXXXX"


async def test_migrate_v1_missing_field_uses_default():
    """v1 entry with no update_interval -> v2 entry with the default."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    entry = _make_v1_entry({
        "email": "e@example.com",
        "password": "p",
        "pod": "RO005EXXXXXXXXX",
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    kwargs = hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"][CONF_UPDATE_INTERVAL_HOURS] == DEFAULT_UPDATE_INTERVAL_HOURS


async def test_migrate_v1_clamps_to_bounds():
    """v1 entry with extreme update_interval gets clamped into [MIN, MAX]."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    # 60000 minutes = 1000 hours -> clamped to MAX_UPDATE_INTERVAL_HOURS (168)
    entry = _make_v1_entry({"update_interval": 60000})
    await async_migrate_entry(hass, entry)
    assert (
        hass.config_entries.async_update_entry.call_args.kwargs["data"][CONF_UPDATE_INTERVAL_HOURS]
        == MAX_UPDATE_INTERVAL_HOURS
    )

    # 0 minutes -> clamped to MIN_UPDATE_INTERVAL_HOURS (1)
    hass.config_entries.async_update_entry.reset_mock()
    entry = _make_v1_entry({"update_interval": 0})
    await async_migrate_entry(hass, entry)
    assert (
        hass.config_entries.async_update_entry.call_args.kwargs["data"][CONF_UPDATE_INTERVAL_HOURS]
        == MIN_UPDATE_INTERVAL_HOURS
    )


async def test_migrate_v2_is_noop():
    """v2 entries skip migration entirely and return True without touching the entry."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    entry = MagicMock()
    entry.version = 2
    entry.data = {CONF_UPDATE_INTERVAL_HOURS: 12}

    result = await async_migrate_entry(hass, entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


async def test_options_update_listener_mutates_coordinator_interval():
    """When options change, the listener updates coordinator.update_interval."""
    from custom_components.retele_electrice import async_update_options

    sentinel_data = {"records_count": 3, "pod": "RO005EXXXXXXXXX"}
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(hours=24)
    coordinator.data = sentinel_data
    hass.data = {DOMAIN: {"test_entry_id": coordinator}}

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.options = {CONF_UPDATE_INTERVAL_HOURS: 6}
    entry.data = {}

    await async_update_options(hass, entry)

    assert coordinator.update_interval == timedelta(hours=6)
    # Ensure the pending refresh timer is re-armed using the new interval.
    # Using a sentinel value (not a MagicMock self-equality) ensures the
    # assertion catches code that calls async_set_updated_data with the
    # wrong argument.
    coordinator.async_set_updated_data.assert_called_once_with(sentinel_data)


async def test_options_update_listener_falls_back_to_default():
    """When options is empty and entry.data is empty, the listener uses the default."""
    from custom_components.retele_electrice import async_update_options

    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(hours=12)
    hass.data = {DOMAIN: {"test_entry_id": coordinator}}

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.options = {}
    entry.data = {}

    await async_update_options(hass, entry)

    assert coordinator.update_interval == timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS)
