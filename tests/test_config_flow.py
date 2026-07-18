"""Tests for the Retele Electrice options and reauth flows."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from custom_components.retele_electrice import config_flow
from custom_components.retele_electrice.config_flow import (
    CannotConnect,
    ConfigFlow,
    InvalidAuth,
    OptionsFlowHandler,
)
from custom_components.retele_electrice.const import (
    CONF_POD,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
)


def _make_entry(*, data: dict | None = None, options: dict | None = None) -> MagicMock:
    """Build a fake ConfigEntry with the given data and options dicts."""
    entry = MagicMock()
    entry.data = data or {}
    entry.options = options or {}
    return entry


def _make_reauth_flow(entry_data: dict) -> tuple[ConfigFlow, MagicMock]:
    """Build a ConfigFlow wired for a reauth flow against a fake entry.

    Bypasses HA's flow manager (no real hass boot, matching this suite's
    mock-only style) — sets just enough (`hass`, `context`) for
    `_get_reauth_entry()` / `async_show_form()` to resolve.
    """
    entry = MagicMock()
    entry.data = entry_data
    entry.entry_id = "test_entry_id"
    entry.title = "Retele Electrice ROD1"

    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}
    return flow, entry


def _entry_data(**overrides) -> dict:
    base = {
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "old-password",
        CONF_POD: "ROD1",
    }
    base.update(overrides)
    return base


async def test_reauth_confirm_shows_form_with_email_placeholder():
    """No user_input yet -> show the password-only form with the account's
    email surfaced so the user knows which credential they're rotating."""
    flow, _entry = _make_reauth_flow(_entry_data())

    result = await flow.async_step_reauth_confirm(user_input=None)

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    placeholders = result["description_placeholders"]
    assert placeholders is not None
    assert placeholders[CONF_EMAIL] == "user@example.com"


async def test_reauth_confirm_success_updates_password_and_reloads():
    """A valid new password replaces just CONF_PASSWORD in entry.data and
    reloads the entry — pod_info and other persisted fields are preserved."""
    flow, entry = _make_reauth_flow(_entry_data(pod_info={"meter_marca": "X"}))
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reauth_successful"}
    )

    with patch.object(
        config_flow, "validate_input", AsyncMock(return_value={"title": "x"})
    ):
        result = await flow.async_step_reauth_confirm(
            user_input={CONF_PASSWORD: "new-password"}
        )

    flow.async_update_reload_and_abort.assert_called_once()
    call_args, call_kwargs = flow.async_update_reload_and_abort.call_args
    assert call_args[0] is entry
    assert call_kwargs["data"][CONF_PASSWORD] == "new-password"
    assert call_kwargs["data"][CONF_EMAIL] == "user@example.com"
    assert call_kwargs["data"]["pod_info"] == {"meter_marca": "X"}
    assert result["reason"] == "reauth_successful"


async def test_reauth_confirm_invalid_auth_shows_error():
    """A still-wrong password re-shows the form with invalid_auth, not a crash."""
    flow, _entry = _make_reauth_flow(_entry_data())

    with patch.object(
        config_flow, "validate_input", AsyncMock(side_effect=InvalidAuth())
    ):
        result = await flow.async_step_reauth_confirm(
            user_input={CONF_PASSWORD: "still-wrong"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_confirm_cannot_connect_shows_error():
    """A network failure during validation surfaces cannot_connect."""
    flow, _entry = _make_reauth_flow(_entry_data())

    with patch.object(
        config_flow, "validate_input", AsyncMock(side_effect=CannotConnect())
    ):
        result = await flow.async_step_reauth_confirm(
            user_input={CONF_PASSWORD: "new-password"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_async_step_reauth_forwards_to_confirm():
    """The framework's entry point just hands off to the confirm form."""
    flow, entry = _make_reauth_flow(_entry_data())

    result = await flow.async_step_reauth(entry.data)

    assert result["step_id"] == "reauth_confirm"


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
