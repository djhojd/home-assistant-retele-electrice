"""DataUpdateCoordinator for Rețele Electrice.

Data format returned by the Aura API (based on network captures):
  [
    {
      "sampleDate":   "01/04/2026 00:00",  # DD/MM/YYYY HH:MM  (start of the day)
      "sampleValues": "0,384000;0,277000;...;0,112000",  # 24 semicolon-separated hourly kWh values
      "energyType":   "WI"  # "WI" = withdraw (import), "WE" = export
    },
    ...
  ]

Each day has exactly 24 hourly sample values. Values are comma-decimal floats.
"""
import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytz

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.components.recorder.util import get_instance

from .api import ReteleElectriceApi, ReteleElectriceAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TZ_BUCHAREST = pytz.timezone("Europe/Bucharest")
ENERGY_TYPE_IMPORT = "WI"
ENERGY_TYPE_EXPORT = "WE"


def _iter_months(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Yield (month_start, month_end) tuples covering [start, end].

    The first tuple's month_start is `start` itself (may be mid-month).
    The last tuple's month_end is `end` (may be mid-month).
    All intermediate months go from the 1st to the last day of that month.
    """
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            next_month_first = cursor.replace(year=cursor.year + 1, month=1, day=1)
        else:
            next_month_first = cursor.replace(month=cursor.month + 1, day=1)
        last_of_month = next_month_first - timedelta(days=1)
        chunk_end = min(last_of_month, end)
        yield (cursor, chunk_end)
        cursor = next_month_first


class ReteleElectriceCoordinator(DataUpdateCoordinator):
    """Coordinate data fetching from the Rețele Electrice API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ReteleElectriceApi,
        pod: str,
        update_interval_mins: int,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.pod = pod

        super().__init__(
            hass,
            _LOGGER,
            name="Rețele Electrice",
            update_interval=timedelta(minutes=update_interval_mins),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API and import it into HA statistics."""
        try:
            # Re-authenticate on every cycle; session may expire between updates
            await self.api.login(self.pod)

            records = await self.api.get_consumption_data(self.pod)

            if records:
                await self._import_statistics(records)
                _LOGGER.info(
                    "Imported %d daily records for POD %s", len(records), self.pod
                )
            else:
                _LOGGER.warning("No consumption records returned for POD %s", self.pod)

            return {
                "last_update": datetime.now(tz=timezone.utc),
                "records_count": len(records),
                "pod": self.pod,
            }

        except ReteleElectriceAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def async_refresh_pod_info(self) -> None:
        """Fetch POD info, persist to the config entry, dispatch a signal.

        On failure: existing pod_info (if any) is preserved in entry.data;
        the exception propagates so the caller (button handler / first-install
        hook) can decide how to surface it.
        """
        _LOGGER.info("Refreshing POD info for %s", self.pod)
        try:
            new_info = await self.api.get_pod_info(self.pod)
        except Exception:
            _LOGGER.warning(
                "POD info refresh failed for %s", self.pod, exc_info=True
            )
            raise

        entry = getattr(self, "config_entry", None)
        if entry is None:
            _LOGGER.error(
                "Coordinator has no config_entry; cannot persist POD info"
            )
            return

        old_info = entry.data.get("pod_info") or {}
        diff = sorted(
            k
            for k in set(old_info) | set(new_info)
            if old_info.get(k) != new_info.get(k)
        )
        if old_info and diff:
            _LOGGER.debug("POD info diff for %s: %s", self.pod, diff)

        new_data = {
            **entry.data,
            "pod_info": new_info,
            "pod_info_refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self.hass.config_entries.async_update_entry(entry, data=new_data)

        # HA's device registry is the source of truth for device fields; mutating
        # entity._attr_device_info after registration is a no-op. Push meter
        # fields here so the device card reflects fresh data.
        self._update_device_registry(new_info)

        signal = f"retele_electrice_pod_info_updated_{entry.entry_id}"
        async_dispatcher_send(self.hass, signal)

        _LOGGER.info(
            "POD info refreshed for %s (%d fields)", self.pod, len(new_info)
        )

    async def async_backfill_history(self, from_date: date) -> None:
        """Wipe POD stats and re-import the full chain from from_date to today.

        Uses month-by-month chunks via the existing api.get_consumption_data.
        After the wipe, the existing _import_statistics rebuilds the cumulative
        sum chain chronologically from zero — no special-case logic needed.
        """
        _LOGGER.info(
            "Backfill: starting for %s from %s to today",
            self.pod, from_date.isoformat(),
        )

        targets = [
            f"{DOMAIN}:{self.pod.lower()}_import",
            f"{DOMAIN}:{self.pod.lower()}_export",
        ]
        recorder = get_instance(self.hass)
        # Recorder.async_clear_statistics is a @callback that queues the wipe on
        # the recorder thread; the subsequent _import_statistics will queue its
        # writes after, so FIFO ordering guarantees wipe happens-before import.
        recorder.async_clear_statistics(targets)

        today = date.today()
        all_records: list[dict[str, Any]] = []
        for month_start, month_end in _iter_months(from_date, today):
            try:
                records = await self.api.get_consumption_data(
                    self.pod, month_start, month_end
                )
            except Exception:
                _LOGGER.warning(
                    "Backfill: failed for %s window %s..%s; partial data kept",
                    self.pod, month_start, month_end, exc_info=True,
                )
                break
            _LOGGER.debug(
                "Backfill: %s..%s → %d records",
                month_start, month_end, len(records),
            )
            all_records.extend(records)

        if all_records:
            await self._import_statistics(all_records)
            _LOGGER.info(
                "Backfill complete for %s: %d daily records",
                self.pod, len(all_records),
            )
        else:
            _LOGGER.info(
                "Backfill: no records found for %s; nothing to import", self.pod
            )

    def _update_device_registry(self, pod_info: dict[str, Any]) -> None:
        """Push meter fields from pod_info onto the device registry row."""
        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get_device(identifiers={(DOMAIN, self.pod)})
        if device is None:
            _LOGGER.debug(
                "Device for %s not in registry yet; skipping update", self.pod
            )
            return

        updates: dict[str, str] = {}
        if model := pod_info.get("meter_marca"):
            updates["model"] = model
        if serial := pod_info.get("meter_seria"):
            updates["serial_number"] = serial
        if hw := pod_info.get("meter_data_montare"):
            updates["hw_version"] = hw

        if updates:
            device_reg.async_update_device(device.id, **updates)
            _LOGGER.debug(
                "Device registry updated for %s: %s",
                self.pod, sorted(updates.keys()),
            )

    # ------------------------------------------------------------------
    # Statistics injection
    # ------------------------------------------------------------------

    async def _import_statistics(self, records: list[dict[str, Any]]) -> None:
        """Parse API records and inject into HA Energy Dashboard.

        Append-only: existing recorder rows are never overwritten. Each cycle
        only inserts hours strictly newer than the latest already-recorded
        `start`, with cumulative sums continuing from the last recorded `sum`.
        """
        import_id = f"{DOMAIN}:{self.pod.lower()}_import"
        export_id = f"{DOMAIN}:{self.pod.lower()}_export"

        # Per-stat baseline (last_ts, last_sum). `last_ts` is timezone-aware UTC.
        # In recent HA versions, `start` is a Unix timestamp (float); older
        # versions returned a datetime. Normalise to a tz-aware datetime so
        # later comparisons against `start_aware` work in both cases.
        async def _baseline(stat_id: str) -> tuple[datetime | None, float]:
            result = await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, {"sum"}
            )
            if not result or stat_id not in result or not result[stat_id]:
                return None, 0.0
            row = result[stat_id][0]
            raw_start = row.get("start")
            if isinstance(raw_start, (int, float)):
                last_ts = datetime.fromtimestamp(raw_start, tz=timezone.utc)
            else:
                last_ts = raw_start
            last_sum = row.get("sum") or 0.0
            return last_ts, float(last_sum)

        import_last_ts, import_sum = await _baseline(import_id)
        export_last_ts, export_sum = await _baseline(export_id)

        import_stats: list[StatisticData] = []
        export_stats: list[StatisticData] = []

        for record in records:
            energy_type = record.get("energyType", "")
            date_str = record.get("sampleDate", "")
            values_str = record.get("sampleValues", "")

            if not date_str or not values_str:
                _LOGGER.debug("Skipping incomplete record: %s", record)
                continue

            try:
                day_start = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            except ValueError:
                try:
                    day_start = datetime.strptime(date_str, "%d/%m/%Y")
                except ValueError:
                    _LOGGER.warning("Could not parse date: %s", date_str)
                    continue

            raw_values = values_str.split(";")
            hourly_values: list[float] = []
            for raw in raw_values:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    hourly_values.append(float(raw.replace(",", ".")))
                except ValueError:
                    _LOGGER.warning("Could not parse value: %r", raw)
                    hourly_values.append(0.0)

            if not hourly_values:
                continue

            for hour_idx, value in enumerate(hourly_values):
                start_naive = day_start + timedelta(hours=hour_idx)
                try:
                    start_aware = TZ_BUCHAREST.localize(start_naive, is_dst=None)
                except pytz.exceptions.AmbiguousTimeError:
                    start_aware = TZ_BUCHAREST.localize(start_naive, is_dst=True)
                except pytz.exceptions.NonExistentTimeError:
                    continue

                if energy_type == ENERGY_TYPE_IMPORT:
                    if import_last_ts is not None and start_aware <= import_last_ts:
                        continue
                    import_sum = round(import_sum + value, 6)
                    import_stats.append(
                        StatisticData(
                            start=start_aware,
                            state=value,
                            sum=import_sum,
                        )
                    )
                elif energy_type == ENERGY_TYPE_EXPORT:
                    if export_last_ts is not None and start_aware <= export_last_ts:
                        continue
                    export_sum = round(export_sum + value, 6)
                    export_stats.append(
                        StatisticData(
                            start=start_aware,
                            state=value,
                            sum=export_sum,
                        )
                    )
                else:
                    _LOGGER.debug("Unknown energyType %r — skipping", energy_type)

        if import_stats:
            self._push_statistics(
                statistic_id=import_id,
                name=f"Rețele Electrice {self.pod} Import",
                stats=import_stats,
            )
        if export_stats:
            self._push_statistics(
                statistic_id=export_id,
                name=f"Rețele Electrice {self.pod} Export",
                stats=export_stats,
            )

    def _push_statistics(
        self,
        statistic_id: str,
        name: str,
        stats: list[StatisticData],
    ) -> None:
        """Register metadata and push statistics into HA recorder."""
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class="energy",
            unit_of_measurement="kWh",
        )
        _LOGGER.debug(
            "Pushing %d hourly records for statistic '%s'", len(stats), statistic_id
        )
        async_add_external_statistics(self.hass, metadata, stats)
