"""Service handlers for the Rețele Electrice integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone

import pytz
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from homeassistant.components.recorder.db_schema import (
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.statistics import list_statistic_ids
from homeassistant.components.recorder.tasks import RecorderTask
from homeassistant.components.recorder.util import get_instance, session_scope

from .const import DOMAIN, CONF_POD, stat_id_prefix

_LOGGER = logging.getLogger(__name__)

SERVICE_CLEAR_STATISTICS = "clear_statistics"
ATTR_CONFIRM = "confirm"
ATTR_POD = "pod"
ATTR_FROM = "from"

TZ_BUCHAREST = pytz.timezone("Europe/Bucharest")

CLEAR_STATISTICS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIRM): cv.boolean,
        vol.Optional(ATTR_POD): cv.string,
        vol.Optional(ATTR_FROM): cv.date,
    }
)


@dataclass(slots=True)
class ClearStatisticsRangeTask(RecorderTask):
    """Delete statistics rows from cutoff_ts onward for the given statistic_ids.

    Runs on the recorder thread. Deletes from `Statistics` and
    `StatisticsShortTerm` tables only (NOT `StatisticsMeta`) so the
    metadata survives for the next sync to repopulate from the cutoff.
    """

    statistic_ids: list[str]
    cutoff_ts: float

    def run(self, instance) -> None:
        with session_scope(session=instance.get_session()) as session:
            metadata_ids = [
                row.id
                for row in session.query(StatisticsMeta.id)
                .filter(StatisticsMeta.statistic_id.in_(self.statistic_ids))
                .all()
            ]
            if not metadata_ids:
                return
            for table in (Statistics, StatisticsShortTerm):
                session.query(table).filter(
                    table.metadata_id.in_(metadata_ids),
                    table.start_ts >= self.cutoff_ts,
                ).delete(synchronize_session=False)


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services. Idempotent."""
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_STATISTICS):
        return

    async def _handle_clear_statistics(call: ServiceCall) -> None:
        """Validate input then clear matching statistics."""
        if call.data.get(ATTR_CONFIRM) is not True:
            raise ServiceValidationError(
                "confirm must be true to clear statistics"
            )

        requested_pod = call.data.get(ATTR_POD)
        configured_pods = {
            entry.data[CONF_POD]
            for entry in hass.config_entries.async_entries(DOMAIN)
            if CONF_POD in entry.data
        }

        if requested_pod is not None:
            if requested_pod not in configured_pods:
                raise ServiceValidationError(
                    f"POD {requested_pod} is not configured for this integration"
                )
            target_pods = {requested_pod}
        else:
            target_pods = configured_pods

        if not target_pods:
            _LOGGER.info("No PODs configured — nothing to clear")
            return

        recorder = get_instance(hass)

        # list_statistic_ids is sync; run in executor.
        all_stats = await recorder.async_add_executor_job(
            list_statistic_ids, hass, None, None
        )

        target_prefixes = tuple(stat_id_prefix(p) for p in target_pods)
        targets = [
            entry["statistic_id"]
            for entry in all_stats
            if entry.get("source") == DOMAIN
            and entry["statistic_id"].startswith(target_prefixes)
        ]

        if not targets:
            _LOGGER.info(
                "No matching statistics found for pods=%s — nothing to do",
                target_pods,
            )
            return

        from_date = call.data.get(ATTR_FROM)
        if from_date is None:
            # Recorder.async_clear_statistics is a @callback that queues a task
            # on the recorder thread; it does not return a coroutine.
            recorder.async_clear_statistics(targets)
            for stat_id in targets:
                _LOGGER.info("Cleared %s (queued for deletion)", stat_id)
            return

        cutoff = TZ_BUCHAREST.localize(
            datetime.combine(from_date, time.min)
        ).astimezone(timezone.utc)
        cutoff_ts = cutoff.timestamp()
        recorder.queue_task(
            ClearStatisticsRangeTask(
                statistic_ids=list(targets),
                cutoff_ts=cutoff_ts,
            )
        )
        _LOGGER.info(
            "Range-clearing %d statistic(s) from cutoff %s onwards",
            len(targets),
            cutoff.isoformat(),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_STATISTICS,
        _handle_clear_statistics,
        schema=CLEAR_STATISTICS_SCHEMA,
    )
