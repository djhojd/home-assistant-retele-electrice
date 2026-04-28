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
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)

from .api import ReteleElectriceApi, ReteleElectriceAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TZ_BUCHAREST = pytz.timezone("Europe/Bucharest")
ENERGY_TYPE_IMPORT = "WI"
ENERGY_TYPE_EXPORT = "WE"


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

    # ------------------------------------------------------------------
    # Statistics injection
    # ------------------------------------------------------------------

    async def _import_statistics(self, records: list[dict[str, Any]]) -> None:
        """Parse API records and inject into HA Energy Dashboard.

        Each record contains 24 hourly consumption values for one day.
        We insert one StatisticData row per hour.

        Args:
            records: List of dicts from the Aura API, each with keys
                     sampleDate, sampleValues, energyType.
        """
        # Separate import (WI) and export (WE) records
        import_stats: list[StatisticData] = []
        export_stats: list[StatisticData] = []

        # Get existing sums to maintain continuity across update cycles.
        # get_last_statistics returns {statistic_id: [row_dict, ...]} or {}.
        import_id = f"{DOMAIN}:{self.pod.lower()}_import"
        export_id = f"{DOMAIN}:{self.pod.lower()}_export"

        last_import = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, import_id, True, {"sum"}
        )
        last_export = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, export_id, True, {"sum"}
        )

        import_sum: float = (
            last_import[import_id][0].get("sum") or 0.0
            if import_id in last_import
            else 0.0
        )
        export_sum: float = (
            last_export[export_id][0].get("sum") or 0.0
            if export_id in last_export
            else 0.0
        )

        for record in records:
            energy_type = record.get("energyType", "")
            date_str = record.get("sampleDate", "")
            values_str = record.get("sampleValues", "")

            if not date_str or not values_str:
                _LOGGER.debug("Skipping incomplete record: %s", record)
                continue

            # Parse the day start from "DD/MM/YYYY HH:MM"
            try:
                day_start = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            except ValueError:
                # Try without time component
                try:
                    day_start = datetime.strptime(date_str, "%d/%m/%Y")
                except ValueError:
                    _LOGGER.warning("Could not parse date: %s", date_str)
                    continue

            # Parse semicolon-delimited hourly values ("0,384000;0,277000;...")
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

            # Build one StatisticData per hour
            for hour_idx, value in enumerate(hourly_values):
                start_naive = day_start + timedelta(hours=hour_idx)
                # Localise to Bucharest, handling DST correctly
                try:
                    start_aware = TZ_BUCHAREST.localize(start_naive, is_dst=None)
                except pytz.exceptions.AmbiguousTimeError:
                    start_aware = TZ_BUCHAREST.localize(start_naive, is_dst=True)
                except pytz.exceptions.NonExistentTimeError:
                    # Skip the hour that doesn't exist (spring-forward DST gap)
                    continue

                if energy_type == ENERGY_TYPE_IMPORT:
                    import_sum = round(import_sum + value, 6)
                    import_stats.append(
                        StatisticData(
                            start=start_aware,
                            state=value,
                            sum=import_sum,
                        )
                    )
                elif energy_type == ENERGY_TYPE_EXPORT:
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

        # Inject import statistics
        if import_stats:
            self._push_statistics(
                statistic_id=f"{DOMAIN}:{self.pod.lower()}_import",
                name=f"Rețele Electrice {self.pod} Import",
                stats=import_stats,
            )

        # Inject export statistics (if any)
        if export_stats:
            self._push_statistics(
                statistic_id=f"{DOMAIN}:{self.pod.lower()}_export",
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
            unit_of_measurement="kWh",
        )
        _LOGGER.debug(
            "Pushing %d hourly records for statistic '%s'", len(stats), statistic_id
        )
        async_add_external_statistics(self.hass, metadata, stats)
