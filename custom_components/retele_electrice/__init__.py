"""The Rețele Electrice integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_POD, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .api import ReteleElectriceApi
from .coordinator import ReteleElectriceCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)


async def _has_existing_stats(hass: HomeAssistant, pod: str) -> bool:
    """Return True iff the recorder has any retele_electrice:<pod>_* row.

    Mirrors the discovery pattern used by services.py: list all stat IDs
    once, filter by our DOMAIN source and the POD's prefix.
    """
    from homeassistant.components.recorder.statistics import list_statistic_ids
    from homeassistant.components.recorder.util import get_instance
    from .const import stat_id_prefix

    recorder = get_instance(hass)
    all_stats = await recorder.async_add_executor_job(
        list_statistic_ids, hass, None, None
    )
    prefix = stat_id_prefix(pod)
    return any(
        e.get("source") == DOMAIN and e["statistic_id"].startswith(prefix)
        for e in all_stats
    )


PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rețele Electrice from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    pod = entry.data[CONF_POD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    api = ReteleElectriceApi(email, password)
    
    coordinator = ReteleElectriceCoordinator(hass, api, pod, update_interval)
    coordinator.config_entry = entry

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # First-install hook: fetch POD info if we don't have it yet. Non-blocking —
    # integration setup completes immediately even if the fetch is slow or fails.
    if "pod_info" not in entry.data:
        _LOGGER.debug("POD info absent for %s, scheduling initial fetch", pod)

        async def _initial_pod_info_fetch():
            try:
                await coordinator.async_refresh_pod_info()
                new_info = entry.data.get("pod_info") or {}
                _LOGGER.info(
                    "Initial POD info fetched for %s (%d fields)",
                    pod, len(new_info),
                )
            except Exception as err:
                _LOGGER.warning(
                    "Initial POD info fetch failed for %s: %s; integration "
                    "loaded without metadata. Press the Refresh POD Info button "
                    "to retry.",
                    pod, err,
                )

        hass.async_create_task(_initial_pod_info_fetch())
    else:
        _LOGGER.debug(
            "Loaded persisted POD info for %s (refreshed_at=%s)",
            pod, entry.data.get("pod_info_refreshed_at"),
        )

    # First-install hook (part 2): auto-backfill the full meter history if
    #  - the POD has no existing stats, AND
    #  - pod_info has the install date (either already, or once it lands).
    # Non-blocking — integration setup completes immediately even if the
    # backfill is slow or fails.
    async def _maybe_initial_backfill():
        # Wait for pod_info if not yet on entry.data.
        if "pod_info" not in entry.data:
            from homeassistant.helpers.dispatcher import async_dispatcher_connect
            import asyncio
            ready = asyncio.Event()
            signal = f"retele_electrice_pod_info_updated_{entry.entry_id}"
            unsub = async_dispatcher_connect(hass, signal, lambda *_: ready.set())
            try:
                await asyncio.wait_for(ready.wait(), timeout=60)
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "Backfill: pod_info_updated signal never fired for %s; "
                    "skipping auto-backfill", pod,
                )
                return
            finally:
                unsub()

        pod_info = entry.data.get("pod_info") or {}
        install_date_str = pod_info.get("meter_data_montare")
        if not install_date_str:
            _LOGGER.debug(
                "Backfill: no meter_data_montare for %s; skipping auto-backfill",
                pod,
            )
            return

        # Smart-meter check: PODs with telecitit != "D" don't support
        # remote-read load curves. Backfill would loop pointlessly,
        # generating QN04 errors against the portal for every month.
        if pod_info.get("telecitit") != "D":
            _LOGGER.info(
                "Backfill: POD %s is non-smart (telecitit=%r); skipping "
                "auto-backfill. Load curves are not available for this POD.",
                pod, pod_info.get("telecitit"),
            )
            return

        if await _has_existing_stats(hass, pod):
            _LOGGER.debug(
                "Backfill: POD %s already has stats; skipping auto-backfill",
                pod,
            )
            return

        from datetime import date
        try:
            await coordinator.async_backfill_history(
                date.fromisoformat(install_date_str)
            )
        except Exception as err:
            _LOGGER.warning(
                "Backfill: auto-trigger failed for %s: %s. Run "
                "retele_electrice.backfill_history manually to retry.",
                pod, err, exc_info=True,
            )

    hass.async_create_task(_maybe_initial_backfill())

    async_register_services(hass)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()

    return unload_ok
