"""Regression tests for the clear_statistics service handler.

These tests do not boot HA. They exercise the handler closure directly with
a mocked HomeAssistant and a mocked recorder.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz
from homeassistant.exceptions import ServiceValidationError

from custom_components.retele_electrice.const import CONF_POD, DOMAIN
from custom_components.retele_electrice.services import (
    SERVICE_BACKFILL_HISTORY,
    SERVICE_CLEAR_STATISTICS,
    async_register_services,
)


def _make_entry(pod: str) -> MagicMock:
    """Build a minimal fake config entry whose .data carries CONF_POD."""
    entry = MagicMock()
    entry.data = {CONF_POD: pod}
    return entry


def _capture_handler(mock_hass: MagicMock):
    """Run async_register_services(mock_hass) and return the clear_statistics handler."""
    return _capture_handler_for(mock_hass, SERVICE_CLEAR_STATISTICS)


def _capture_handler_for(mock_hass: MagicMock, service_name: str):
    """Run async_register_services(mock_hass), find handler for service_name."""
    async_register_services(mock_hass)
    for register_call in mock_hass.services.async_register.call_args_list:
        # Signature: async_register(domain, service, handler, schema=...)
        if register_call.args[1] == service_name:
            return register_call.args[2]
    raise AssertionError(f"service {service_name} was not registered")


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


async def test_clear_statistics_with_from_date_queues_range_task(mock_hass):
    """confirm=True + pod=POD_A + from=2026-04-29 -> queue_task called with
    ClearStatisticsRangeTask carrying the expected stat_ids and cutoff_ts.

    cutoff = midnight Bucharest of 2026-04-29 -> 2026-04-28T21:00:00+00:00 (DST).
    """
    pod = "RO005E_AAA"
    mock_hass.config_entries.async_entries.return_value = [_make_entry(pod)]

    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(
        return_value=[
            {"statistic_id": f"{DOMAIN}:{pod.lower()}_import", "source": DOMAIN},
            {"statistic_id": f"{DOMAIN}:{pod.lower()}_export", "source": DOMAIN},
        ]
    )
    mock_recorder.async_clear_statistics = MagicMock()
    mock_recorder.queue_task = MagicMock()

    with patch(
        "custom_components.retele_electrice.services.get_instance",
        return_value=mock_recorder,
    ):
        handler = _capture_handler(mock_hass)
        await handler(_make_call({
            "confirm": True,
            "pod": pod,
            "from": date(2026, 4, 29),
        }))

    mock_recorder.async_clear_statistics.assert_not_called()
    mock_recorder.queue_task.assert_called_once()
    queued = mock_recorder.queue_task.call_args.args[0]
    assert sorted(queued.statistic_ids) == sorted(
        [f"{DOMAIN}:{pod.lower()}_import", f"{DOMAIN}:{pod.lower()}_export"]
    )
    expected_cutoff = pytz.timezone("Europe/Bucharest").localize(
        datetime.combine(date(2026, 4, 29), time.min)
    ).astimezone(timezone.utc).timestamp()
    assert queued.cutoff_ts == expected_cutoff


async def test_clear_statistics_without_from_uses_wipe_all_path(mock_hass):
    """Regression: no `from` arg -> existing async_clear_statistics path is taken.

    queue_task must NOT be called.
    """
    pod = "RO005E_AAA"
    mock_hass.config_entries.async_entries.return_value = [_make_entry(pod)]

    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(
        return_value=[{"statistic_id": f"{DOMAIN}:{pod.lower()}_import", "source": DOMAIN}]
    )
    mock_recorder.async_clear_statistics = MagicMock()
    mock_recorder.queue_task = MagicMock()

    with patch(
        "custom_components.retele_electrice.services.get_instance",
        return_value=mock_recorder,
    ):
        handler = _capture_handler(mock_hass)
        await handler(_make_call({"confirm": True, "pod": pod}))

    mock_recorder.async_clear_statistics.assert_called_once()
    mock_recorder.queue_task.assert_not_called()


async def test_backfill_history_defaults_from_to_install_date(mock_hass):
    """confirm=True + pod=POD (no from) -> coordinator.async_backfill_history
    called with from_date = pod_info.meter_data_montare."""
    from datetime import date

    pod = "RO005E_AAA"
    entry = _make_entry(pod)
    entry.data = {
        CONF_POD: pod,
        "pod_info": {"meter_data_montare": "2025-10-01"},
    }
    entry.entry_id = "test_entry_id"
    mock_hass.config_entries.async_entries.return_value = [entry]

    fake_coordinator = MagicMock()
    fake_coordinator.async_backfill_history = AsyncMock()
    mock_hass.data = {DOMAIN: {entry.entry_id: fake_coordinator}}

    handler = _capture_handler_for(mock_hass, SERVICE_BACKFILL_HISTORY)
    await handler(_make_call({"confirm": True, "pod": pod}))

    fake_coordinator.async_backfill_history.assert_called_once_with(date(2025, 10, 1))


async def test_backfill_history_explicit_from_overrides_install_date(mock_hass):
    """from arg explicitly provided -> that date wins, install_date ignored."""
    from datetime import date

    pod = "RO005E_AAA"
    entry = _make_entry(pod)
    entry.data = {
        CONF_POD: pod,
        "pod_info": {"meter_data_montare": "2025-10-01"},  # ignored
    }
    entry.entry_id = "test_entry_id"
    mock_hass.config_entries.async_entries.return_value = [entry]

    fake_coordinator = MagicMock()
    fake_coordinator.async_backfill_history = AsyncMock()
    mock_hass.data = {DOMAIN: {entry.entry_id: fake_coordinator}}

    handler = _capture_handler_for(mock_hass, SERVICE_BACKFILL_HISTORY)
    await handler(_make_call({"confirm": True, "pod": pod, "from": date(2026, 1, 1)}))

    fake_coordinator.async_backfill_history.assert_called_once_with(date(2026, 1, 1))
