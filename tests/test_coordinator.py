"""Regression tests for ReteleElectriceCoordinator._import_statistics.

Mock-only: no HA boot, no real recorder. We verify the append-only baseline
logic from commits 819fdb7 (cumulative-sum corruption fix) and 3e9fad7
(float-vs-datetime fix) by mocking `hass.async_add_executor_job` and the
coordinator's `_push_statistics` helper.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.retele_electrice.const import DOMAIN
from custom_components.retele_electrice.coordinator import ReteleElectriceCoordinator


POD = "RO005E_TEST"
IMPORT_ID = f"{DOMAIN}:{POD.lower()}_import"
EXPORT_ID = f"{DOMAIN}:{POD.lower()}_export"


@pytest.fixture
def coordinator(mock_hass, fake_api):
    """Coordinator under test, wired to mocked hass + fake api.

    Bypasses `DataUpdateCoordinator.__init__` (which calls `frame.report_usage`
    and requires a real HA ContextVar). `_import_statistics` only reads
    `self.hass` and `self.pod`, so we set those directly.
    """
    coord = ReteleElectriceCoordinator.__new__(ReteleElectriceCoordinator)
    coord.hass = mock_hass
    coord.api = fake_api
    coord.pod = POD
    return coord


def _baseline_returner(per_stat_result: dict[str, list[dict]]):
    """Build an AsyncMock side_effect that returns a per-stat result dict.

    Usage: mock_hass.async_add_executor_job = AsyncMock(side_effect=_baseline_returner({
        IMPORT_ID: [{"start": <ts>, "sum": <sum>}],
        EXPORT_ID: [],   # empty
    }))

    The coordinator calls `async_add_executor_job(get_last_statistics, hass, 1, stat_id, True, {"sum"})`.
    The function arg sits at index 0, hass at 1, then n=1 at 2, then stat_id at 3.
    """

    async def _side_effect(*args, **kwargs):
        # Args: (get_last_statistics, hass, 1, stat_id, True, {"sum"})
        stat_id = args[3]
        rows = per_stat_result.get(stat_id, [])
        if rows:
            return {stat_id: rows}
        return {}

    return _side_effect


async def test_import_statistics_with_empty_recorder_inserts_records(
    coordinator, mock_hass, make_records
):
    """Empty recorder -> import branch fires with all 24 records, sums build from 0.0."""
    mock_hass.async_add_executor_job = AsyncMock(
        side_effect=_baseline_returner({IMPORT_ID: [], EXPORT_ID: []})
    )
    coordinator._push_statistics = MagicMock()

    records = make_records(date_str="01/04/2026 00:00", energy_type="WI")
    await coordinator._import_statistics(records)

    coordinator._push_statistics.assert_called_once()
    kwargs = coordinator._push_statistics.call_args.kwargs
    assert kwargs["statistic_id"] == IMPORT_ID
    assert len(kwargs["stats"]) == 24
    # First hour value is 0.1 -> first cumulative sum is 0.1.
    # `StatisticData` is a TypedDict, not a dataclass, so use dict access.
    assert kwargs["stats"][0]["sum"] == pytest.approx(0.1)


async def test_import_statistics_skips_already_recorded_hours(
    coordinator, mock_hass, make_records
):
    """last_ts at hour 11 Bucharest (08:00 UTC on April 1) -> only hours 12-23 land."""
    last_ts = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
    mock_hass.async_add_executor_job = AsyncMock(
        side_effect=_baseline_returner(
            {
                IMPORT_ID: [{"start": last_ts, "sum": 1.5}],
                EXPORT_ID: [],
            }
        )
    )
    coordinator._push_statistics = MagicMock()

    records = make_records(date_str="01/04/2026 00:00", energy_type="WI")
    await coordinator._import_statistics(records)

    coordinator._push_statistics.assert_called_once()
    stats = coordinator._push_statistics.call_args.kwargs["stats"]
    # 24 - 12 already-recorded hours = 12 new hours.
    assert len(stats) == 12
    # First new hour's cumulative sum builds from baseline 1.5 + value 1.3 (hour 12 = 0.1*13).
    # `StatisticData` is a TypedDict, not a dataclass, so use dict access.
    assert stats[0]["sum"] == pytest.approx(1.5 + 1.3, abs=1e-6)


async def test_import_statistics_handles_float_start_from_recorder(
    coordinator, mock_hass, make_records
):
    """Recorder returns `start` as a Unix-timestamp float (current HA) -- must not raise."""
    last_ts_float = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc).timestamp()
    mock_hass.async_add_executor_job = AsyncMock(
        side_effect=_baseline_returner(
            {
                IMPORT_ID: [{"start": last_ts_float, "sum": 1.5}],
                EXPORT_ID: [],
            }
        )
    )
    coordinator._push_statistics = MagicMock()

    records = make_records(date_str="01/04/2026 00:00", energy_type="WI")

    # Pre-3e9fad7 this raised TypeError comparing datetime to float.
    await coordinator._import_statistics(records)

    coordinator._push_statistics.assert_called_once()
    stats = coordinator._push_statistics.call_args.kwargs["stats"]
    assert len(stats) == 12  # same 12 hours filtered as in the datetime case


async def test_import_statistics_no_push_when_all_records_already_recorded(
    coordinator, mock_hass, make_records
):
    """last_ts beyond every record's timestamp -> coordinator pushes nothing.

    This is the regression test for the cumulative-sum corruption bug. Pre-fix,
    the coordinator would re-write the whole month with sums shifted up by the
    previous run's last sum; post-fix, every record fails the strict-newer
    filter and no push happens at all.
    """
    last_ts = datetime(2030, 1, 1, tzinfo=timezone.utc)
    mock_hass.async_add_executor_job = AsyncMock(
        side_effect=_baseline_returner(
            {
                IMPORT_ID: [{"start": last_ts, "sum": 100.0}],
                EXPORT_ID: [{"start": last_ts, "sum": 100.0}],
            }
        )
    )
    coordinator._push_statistics = MagicMock()

    records = (
        make_records(date_str="01/04/2026 00:00", energy_type="WI")
        + make_records(date_str="01/04/2026 00:00", energy_type="WE")
    )
    await coordinator._import_statistics(records)

    coordinator._push_statistics.assert_not_called()


async def test_refresh_pod_info_persists_to_config_entry(
    coordinator, mock_hass, fake_api
):
    """Successful fetch updates entry.data with pod_info + timestamp."""
    pod_info = {
        "nume_client": "TEST USER",
        "kw_aprobata": 6.0,
        "meter_seria": "001",
    }
    fake_api.get_pod_info = AsyncMock(return_value=pod_info)

    fake_entry = MagicMock()
    fake_entry.data = {"pod": coordinator.pod}
    fake_entry.entry_id = "test_entry_id"
    coordinator.config_entry = fake_entry

    await coordinator.async_refresh_pod_info()

    update_call = mock_hass.config_entries.async_update_entry.call_args
    assert update_call is not None, "async_update_entry was not called"
    new_data = update_call.kwargs["data"]
    assert new_data["pod_info"] == pod_info
    assert "pod_info_refreshed_at" in new_data
    # ISO-8601 with timezone
    assert "T" in new_data["pod_info_refreshed_at"]


async def test_refresh_pod_info_dispatches_signal(
    coordinator, mock_hass, fake_api, monkeypatch
):
    """Successful fetch fires the per-entry pod_info_updated signal."""
    fake_api.get_pod_info = AsyncMock(return_value={"meter_seria": "X"})

    fake_entry = MagicMock()
    fake_entry.data = {"pod": coordinator.pod}
    fake_entry.entry_id = "test_entry_id"
    coordinator.config_entry = fake_entry

    sent = []
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.async_dispatcher_send",
        lambda hass, signal, *args: sent.append((signal, args)),
    )

    await coordinator.async_refresh_pod_info()

    assert any(
        signal == "retele_electrice_pod_info_updated_test_entry_id"
        for signal, _ in sent
    ), f"expected pod_info_updated signal not in {sent}"


async def test_refresh_pod_info_failure_preserves_existing_data(
    coordinator, mock_hass, fake_api
):
    """If api raises, existing entry.data['pod_info'] is left untouched."""
    fake_api.get_pod_info = AsyncMock(side_effect=RuntimeError("portal down"))

    fake_entry = MagicMock()
    fake_entry.data = {
        "pod": coordinator.pod,
        "pod_info": {"nume_client": "OLD"},
    }
    fake_entry.entry_id = "test_entry_id"
    coordinator.config_entry = fake_entry

    with pytest.raises(RuntimeError, match="portal down"):
        await coordinator.async_refresh_pod_info()

    mock_hass.config_entries.async_update_entry.assert_not_called()


async def test_refresh_pod_info_updates_device_registry(
    coordinator, mock_hass, fake_api, monkeypatch
):
    """Meter fields from pod_info are pushed onto the HA device registry row."""
    fake_api.get_pod_info = AsyncMock(return_value={
        "nume_client": "TEST",
        "meter_marca": "ACE2000 : 5/60A, 230 V",
        "meter_seria": "004000860528410",
        "meter_data_montare": "2010-08-27",
    })

    fake_entry = MagicMock()
    fake_entry.data = {"pod": coordinator.pod}
    fake_entry.entry_id = "test_entry_id"
    coordinator.config_entry = fake_entry

    fake_device = MagicMock()
    fake_device.id = "fake_device_id"
    fake_registry = MagicMock()
    fake_registry.async_get_device = MagicMock(return_value=fake_device)
    fake_registry.async_update_device = MagicMock()
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.dr.async_get",
        lambda hass: fake_registry,
    )

    await coordinator.async_refresh_pod_info()

    fake_registry.async_update_device.assert_called_once_with(
        "fake_device_id",
        model="ACE2000 : 5/60A, 230 V",
        serial_number="004000860528410",
        hw_version="2010-08-27",
    )


async def test_refresh_pod_info_skips_device_update_when_device_missing(
    coordinator, mock_hass, fake_api, monkeypatch
):
    """If the device isn't in the registry yet, the registry call is skipped."""
    fake_api.get_pod_info = AsyncMock(return_value={"meter_marca": "X"})

    fake_entry = MagicMock()
    fake_entry.data = {"pod": coordinator.pod}
    fake_entry.entry_id = "test_entry_id"
    coordinator.config_entry = fake_entry

    fake_registry = MagicMock()
    fake_registry.async_get_device = MagicMock(return_value=None)
    fake_registry.async_update_device = MagicMock()
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.dr.async_get",
        lambda hass: fake_registry,
    )

    await coordinator.async_refresh_pod_info()

    fake_registry.async_update_device.assert_not_called()


async def test_backfill_history_wipes_then_imports_in_order(
    coordinator, mock_hass, fake_api, monkeypatch
):
    """Backfill calls async_clear_statistics, then _import_statistics with
    chronologically-ordered records covering install date → today."""
    from datetime import date as _date

    # Mock today() to return a fixed date so _iter_months is deterministic.
    class _FakeDate(_date):
        @classmethod
        def today(cls):
            return _date(2026, 5, 3)
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.date", _FakeDate
    )

    # Per-month: api returns one identifying record so we can assert ordering.
    fake_api.get_consumption_data = AsyncMock(side_effect=[
        [{"sampleDate": "01/03/2026 00:00", "sampleValues": "0,1", "energyType": "WI"}],
        [{"sampleDate": "01/04/2026 00:00", "sampleValues": "0,2", "energyType": "WI"}],
        [{"sampleDate": "01/05/2026 00:00", "sampleValues": "0,3", "energyType": "WI"}],
    ])

    fake_recorder = MagicMock()
    fake_recorder.async_clear_statistics = MagicMock()
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.get_instance",
        lambda hass: fake_recorder,
    )

    coordinator._import_statistics = AsyncMock()

    # Track call order
    calls = []
    fake_recorder.async_clear_statistics.side_effect = (
        lambda ids: calls.append(("wipe", tuple(sorted(ids))))
    )
    coordinator._import_statistics.side_effect = (
        lambda recs: calls.append(("import", len(recs)))
    )

    await coordinator.async_backfill_history(_date(2026, 3, 1))

    # Wipe must run before import.
    assert calls[0][0] == "wipe", "wipe must run before import"
    assert calls[0][1] == (EXPORT_ID, IMPORT_ID), \
        "wipe should target both stat IDs (sorted)"
    assert calls[1] == ("import", 3), "all 3 monthly records imported in one call"

    # API called once per month, in chronological order.
    assert fake_api.get_consumption_data.call_count == 3
    api_calls = fake_api.get_consumption_data.call_args_list
    assert api_calls[0].args[1] == _date(2026, 3, 1)
    assert api_calls[1].args[1] == _date(2026, 4, 1)
    assert api_calls[2].args[1] == _date(2026, 5, 1)


async def test_backfill_history_partial_failure_keeps_collected_records(
    coordinator, mock_hass, fake_api, monkeypatch, caplog
):
    """If api raises mid-loop, accumulated records are still imported and
    a WARNING is logged."""
    from datetime import date as _date
    import logging

    class _FakeDate(_date):
        @classmethod
        def today(cls):
            return _date(2026, 5, 3)
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.date", _FakeDate
    )

    fake_api.get_consumption_data = AsyncMock(side_effect=[
        [{"sampleDate": "01/03/2026 00:00", "sampleValues": "0,1", "energyType": "WI"}],
        RuntimeError("portal hiccup"),
    ])

    fake_recorder = MagicMock()
    fake_recorder.async_clear_statistics = MagicMock()
    monkeypatch.setattr(
        "custom_components.retele_electrice.coordinator.get_instance",
        lambda hass: fake_recorder,
    )

    coordinator._import_statistics = AsyncMock()

    with caplog.at_level(logging.WARNING):
        await coordinator.async_backfill_history(_date(2026, 3, 1))

    coordinator._import_statistics.assert_called_once()
    imported_records = coordinator._import_statistics.call_args.args[0]
    assert len(imported_records) == 1, "only month-1 records preserved"
    assert "Backfill: failed" in caplog.text


from datetime import date as _real_date

from custom_components.retele_electrice.coordinator import _iter_months


@pytest.mark.parametrize("start, end, expected", [
    # Year boundary: Dec 15 2025 -> Jan 10 2026
    (
        _real_date(2025, 12, 15), _real_date(2026, 1, 10),
        [
            (_real_date(2025, 12, 15), _real_date(2025, 12, 31)),
            (_real_date(2026, 1, 1), _real_date(2026, 1, 10)),
        ],
    ),
    # Single-day range
    (
        _real_date(2026, 5, 3), _real_date(2026, 5, 3),
        [(_real_date(2026, 5, 3), _real_date(2026, 5, 3))],
    ),
    # start AFTER end -> empty
    (
        _real_date(2026, 5, 10), _real_date(2026, 5, 3),
        [],
    ),
    # Single full month aligned to month boundaries
    (
        _real_date(2026, 3, 1), _real_date(2026, 3, 31),
        [(_real_date(2026, 3, 1), _real_date(2026, 3, 31))],
    ),
])
def test_iter_months(start, end, expected):
    """_iter_months handles year-boundary, single-day, empty, and aligned cases."""
    assert list(_iter_months(start, end)) == expected
