"""Tests for the Retele Electrice options flow."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.retele_electrice.config_flow import OptionsFlowHandler
from custom_components.retele_electrice.const import (
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
)


def _make_entry(*, data: dict | None = None, options: dict | None = None) -> MagicMock:
    """Build a fake ConfigEntry with the given data and options dicts."""
    entry = MagicMock()
    entry.data = data or {}
    entry.options = options or {}
    return entry


async def test_options_flow_init_step_shows_value_from_options():
    """When options has a value, the form pre-fills with it."""
    entry = _make_entry(options={CONF_UPDATE_INTERVAL_HOURS: 12})
    handler = OptionsFlowHandler(entry)
    result = await handler.async_step_init(user_input=None)

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    default = next(
        key.default() for key in schema
        if str(key) == CONF_UPDATE_INTERVAL_HOURS
    )
    assert default == 12


async def test_options_flow_falls_back_to_entry_data():
    """When options is empty but entry.data has a value, the form uses entry.data."""
    entry = _make_entry(data={CONF_UPDATE_INTERVAL_HOURS: 6}, options={})
    handler = OptionsFlowHandler(entry)
    result = await handler.async_step_init(user_input=None)

    schema = result["data_schema"].schema
    default = next(
        key.default() for key in schema
        if str(key) == CONF_UPDATE_INTERVAL_HOURS
    )
    assert default == 6


async def test_options_flow_falls_back_to_default_when_neither_set():
    """No options, no entry.data → use the default."""
    entry = _make_entry(data={}, options={})
    handler = OptionsFlowHandler(entry)
    result = await handler.async_step_init(user_input=None)

    schema = result["data_schema"].schema
    default = next(
        key.default() for key in schema
        if str(key) == CONF_UPDATE_INTERVAL_HOURS
    )
    assert default == DEFAULT_UPDATE_INTERVAL_HOURS


async def test_options_flow_saves_new_interval():
    """Submitting user_input returns a create_entry result with the new value."""
    entry = _make_entry()
    handler = OptionsFlowHandler(entry)
    result = await handler.async_step_init(
        user_input={CONF_UPDATE_INTERVAL_HOURS: 48}
    )

    assert result["type"] == "create_entry"
    assert result["data"] == {CONF_UPDATE_INTERVAL_HOURS: 48}
