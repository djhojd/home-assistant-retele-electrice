"""Regression tests for the clear_statistics service handler.

These tests do not boot HA. They exercise the handler closure directly with
a mocked HomeAssistant and a mocked recorder.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.retele_electrice.const import CONF_POD, DOMAIN
from custom_components.retele_electrice.services import (
    SERVICE_CLEAR_STATISTICS,
    async_register_services,
)


def _make_entry(pod: str) -> MagicMock:
    """Build a minimal fake config entry whose .data carries CONF_POD."""
    entry = MagicMock()
    entry.data = {CONF_POD: pod}
    return entry


def _capture_handler(mock_hass: MagicMock):
    """Run async_register_services(mock_hass) and return the registered handler."""
    async_register_services(mock_hass)
    register_call = mock_hass.services.async_register.call_args
    # Signature: async_register(domain, service, handler, schema=...)
    assert register_call is not None, "async_register was not called"
    return register_call.args[2]


def _make_call(data: dict) -> MagicMock:
    """Fake ServiceCall with the given .data dict."""
    call = MagicMock()
    call.data = data
    return call


async def test_clear_statistics_rejects_confirm_false(mock_hass):
    """confirm=False -> ServiceValidationError, no recorder access."""
    handler = _capture_handler(mock_hass)
    with pytest.raises(ServiceValidationError, match="confirm must be true"):
        await handler(_make_call({"confirm": False}))


async def test_clear_statistics_rejects_unknown_pod(mock_hass):
    """pod=<not-configured> -> ServiceValidationError."""
    mock_hass.config_entries.async_entries.return_value = [_make_entry("RO005E_REAL")]
    handler = _capture_handler(mock_hass)
    with pytest.raises(ServiceValidationError, match="POD RO005E_FAKE"):
        await handler(_make_call({"confirm": True, "pod": "RO005E_FAKE"}))


async def test_clear_statistics_clears_only_specified_pod(mock_hass):
    """confirm=True + pod=POD_A -> only POD_A's stat IDs passed to async_clear_statistics."""
    pod_a = "RO005E_AAA"
    pod_b = "RO005E_BBB"
    mock_hass.config_entries.async_entries.return_value = [
        _make_entry(pod_a),
        _make_entry(pod_b),
    ]

    # Mock the recorder returned by get_instance(hass).
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(
        return_value=[
            {"statistic_id": f"{DOMAIN}:{pod_a.lower()}_import", "source": DOMAIN},
            {"statistic_id": f"{DOMAIN}:{pod_a.lower()}_export", "source": DOMAIN},
            {"statistic_id": f"{DOMAIN}:{pod_b.lower()}_import", "source": DOMAIN},
            # Noise from another integration -- must be ignored.
            {"statistic_id": "sensor.unrelated", "source": "recorder"},
        ]
    )
    mock_recorder.async_clear_statistics = MagicMock()

    with patch(
        "custom_components.retele_electrice.services.get_instance",
        return_value=mock_recorder,
    ):
        handler = _capture_handler(mock_hass)
        await handler(_make_call({"confirm": True, "pod": pod_a}))

    mock_recorder.async_clear_statistics.assert_called_once()
    cleared_ids = mock_recorder.async_clear_statistics.call_args.args[0]
    assert sorted(cleared_ids) == sorted(
        [f"{DOMAIN}:{pod_a.lower()}_import", f"{DOMAIN}:{pod_a.lower()}_export"]
    )


async def test_clear_statistics_clears_all_configured_pods(mock_hass):
    """confirm=True (no pod arg) -> all configured PODs' stat IDs cleared."""
    pod_a = "RO005E_AAA"
    pod_b = "RO005E_BBB"
    mock_hass.config_entries.async_entries.return_value = [
        _make_entry(pod_a),
        _make_entry(pod_b),
    ]

    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(
        return_value=[
            {"statistic_id": f"{DOMAIN}:{pod_a.lower()}_import", "source": DOMAIN},
            {"statistic_id": f"{DOMAIN}:{pod_b.lower()}_export", "source": DOMAIN},
        ]
    )
    mock_recorder.async_clear_statistics = MagicMock()

    with patch(
        "custom_components.retele_electrice.services.get_instance",
        return_value=mock_recorder,
    ):
        handler = _capture_handler(mock_hass)
        await handler(_make_call({"confirm": True}))

    mock_recorder.async_clear_statistics.assert_called_once()
    cleared_ids = mock_recorder.async_clear_statistics.call_args.args[0]
    assert sorted(cleared_ids) == sorted(
        [f"{DOMAIN}:{pod_a.lower()}_import", f"{DOMAIN}:{pod_b.lower()}_export"]
    )
