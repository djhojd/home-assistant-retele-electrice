# Rețele Electrice — Change Log

## Session: 2026-05-01 — POD info feature

### New: per-POD metadata fetched from `/s/new-pod-info-client`

Static contract and meter metadata (~20 fields: customer name, addresses, contracted kW, supplier, meter serial / model / install date, status, etc.) is now fetched on integration first install and on demand via a new "Refresh POD Info" button per POD. Persisted in the config entry across restarts.

### New entities (per POD)

| Entity | Type | Notes |
|---|---|---|
| `sensor.retele_electrice_<pod>_pod_info` | Diagnostic timestamp sensor | State = last refresh time. Attributes = the 20 metadata fields. Hidden from default dashboards, visible on the device detail page. |
| `button.retele_electrice_<pod>_refresh_pod_info` | Diagnostic button | On press: re-fetches POD info from the portal. |

### Updated `DeviceInfo`

The per-POD device now carries the meter model (Romanian `marca`), serial (`seria`), and install date (`data_montare`) — sourced from POD info — plus a `configuration_url` link to the portal page. Falls back to minimal static values until the first POD-info fetch lands.

The device fields are pushed via `device_registry.async_update_device()` from the coordinator after each refresh. Mutating `Entity._attr_device_info` after entity registration is a no-op — the device registry is HA's source of truth for the device row and only reads `DeviceInfo` once at entity creation.

### Logging

All POD-info paths log at appropriate levels (DEBUG / INFO / WARNING) per `docs/plans/2026-05-01-pod-info-design.md` § Logging. Enable via `logger: { logs: { custom_components.retele_electrice: debug } }` for full trace.

### Files changed

| File | Change |
|---|---|
| `api.py` | New `_parse_pod_info_response()` and `get_pod_info()` |
| `coordinator.py` | New `async_refresh_pod_info()` — persists `entry.data["pod_info"]` + `entry.data["pod_info_refreshed_at"]`, dispatches a signal |
| `_device.py` | New: `build_device_info()` shared helper |
| `__init__.py` | Non-blocking first-install POD info fetch |
| `sensor.py` | New `PodInfoSensor` (diagnostic, dispatcher-driven) |
| `button.py` | New `RefreshPodInfoButton` |
| `coordinator.py` | New `_update_device_registry()` — pushes meter fields onto the HA device row |
| `tests/test_api.py` | New file — parser regression test |
| `tests/test_coordinator.py` | +5 tests (3 for `async_refresh_pod_info`, 2 for the device-registry update) |
| `tests/fixtures/pod_info_RO005E510252818.json` | Captured API fixture |

---

## Session: 2026-04-30 — Statistics fix + recovery service

### Critical bug fix

`coordinator._import_statistics` was reading its own previous-run last `sum` as
the baseline and then re-writing the entire current month on top of it. Because
`async_add_external_statistics` overwrites by `start`, every cycle bumped every
previously-recorded hour upward by ~1 month's consumption. After ~6 cycles the
April 1 import row was showing `change=119.874 kWh` (real value: ~2.831).

Fix: the method is now **append-only**. Each cycle reads the latest recorded
`(start, sum)` and only inserts hours strictly newer than `last_ts`, with
cumulative sums continuing from `last_sum`. Re-running on already-imported
data is now a no-op.

### New: `retele_electrice.clear_statistics` recovery service

Permanently deletes the integration's external statistics so the user can
recover from corrupted data and let the new logic re-import cleanly.

```yaml
service: retele_electrice.clear_statistics
data:
  confirm: true              # required, must literally be true
  pod: RO005E513888412       # optional; defaults to all configured PODs
```

Discovers all `retele_electrice:<pod_lower>_*` statistic IDs under our DOMAIN
source and clears them via the recorder's `async_clear_statistics` instance
method.

### Other changes

| File | Change |
|---|---|
| `coordinator.py` | Append-only `_import_statistics` rewrite (the bug fix) |
| `coordinator.py` | Added `unit_class="energy"` to silence HA 2026.11 deprecation |
| `coordinator.py` | Recorder `start` is now a Unix-timestamp float in current HA — converted to tz-aware UTC datetime before comparison |
| `services.py` | New module: `clear_statistics` service handler |
| `services.yaml` | New file: service description for Developer Tools UI |
| `__init__.py` | Idempotent registration of the service across config entries |
| `const.py` | New helper `stat_id_prefix(pod)` shared between coordinator and service |

### Verified working

End-to-end recovery path tested against the live HA instance:

1. Pre-fix April 1 import showed `change=119.874 kWh` (corrupt).
2. Called `retele_electrice.clear_statistics` with `confirm: true` → both stat
   IDs wiped, `total_count=0`.
3. Pressed Sync Data button → coordinator re-fetched and re-imported.
4. Post-fix April 1 import shows `change=2.831 kWh` ✓ (matches portal).
5. Pressed Sync Data again → idempotent (no new rows, identical history).

### Lessons captured for the design docs

Two HA-API assumptions in the original design turned out to be wrong and
required hot-fix commits during the verification step:

- `async_clear_statistics` is **not** a free function in
  `homeassistant.components.recorder.statistics`. It's a `@callback`
  instance method on the `Recorder` class:
  `get_instance(hass).async_clear_statistics(stat_ids)`.
- `get_last_statistics` returns `start` as a **Unix-timestamp float** in
  current HA, not as a `datetime`. Must be converted with
  `datetime.fromtimestamp(value, tz=timezone.utc)` before comparing to a
  tz-aware datetime.

Both would have been caught by an automated test harness — adding one is
recorded as future work below.

---

## Session: 2026-04-28 (evening)

### API Rewrite — Working Authentication & Data Retrieval

| File | Change |
|---|---|
| `api.py` | Complete rewrite. Replaced broken Aura-based flow with working VF page a4j postback approach |
| `api.py` | Login: POST credentials with Salesforce ViewState + jsfcljs dynamic field, follow `frontdoor.jsp` to establish `sid` cookie |
| `api.py` | Data: GET `/PED_ProxyCallWSAsync_Curve_VF` for ViewState, POST a4j with `methodN=ValoriDiEnergia` and date/POD params |
| `api.py` | Removed unused `_extract_aura_token`, `_update_aura_context`, and Aura context/token machinery |
| `api.py` | Fetches both import (WI) and export (WE) data in a single `get_consumption_data` call |
| `api.py` | Removed debug file write (`failed_auth_page.html`) — logs HTML at DEBUG level instead |
| `hacs.json` | Created for HACS distribution |
| `coordinator.py` | Updated comment (cosmetic) |

### Verified Working

- Login flow tested against live portal
- 54 records returned: 27 days import + 27 days export with 24 hourly values each
- Date range: full current month (1st to today)

---

## Session: 2026-04-28 (earlier)

### Critical Bug Fixes

| File | Issue | Fix |
|---|---|---|
| `coordinator.py` | `_import_statistics` was called via `async_add_executor_job`, but `async_add_external_statistics` is not thread-safe | Made the method `async` and call it directly from the event loop |
| `coordinator.py` | Cumulative `sum` was reset to `0.0` on every update cycle, corrupting Energy Dashboard totals | Now fetches last known sum from recorder via `get_last_statistics` before building rows |
| `coordinator.py` | `get_last_statistics` result accessed with wrong indexing (`[0][0]`) | Fixed to access by `statistic_id` key as per the API: `result[statistic_id][0]` |
| `coordinator.py` | Floating-point drift in cumulative sum | Sum is now `round(..., 6)` on every step |
| `config_flow.py` | `api.login()` called without required `pod` argument | Passes `pod` to `login(pod)` |
| `config_flow.py` | Missing `ReteleElectriceAuthError` import; no `CannotConnect` error class | Added import, class, and handler in `async_step_user` |
| `manifest.json` | `aiohttp` (HA built-in) listed as requirement; `pytz` missing; no `recorder` dependency | Fixed to `beautifulsoup4`, `pytz`, and added `"recorder"` as integration dependency |

### Improvements

- **`sensor.py` / `button.py`**: Plain `dict` for `device_info` replaced with typed `DeviceInfo`
  dataclass — avoids silent HA validation warnings and is the correct HA pattern.
- **`strings.json` + `translations/en.json`**: Created with all config-flow error codes
  (`cannot_connect`, `invalid_auth`, `unknown`) — required for the UI to render
  human-readable error messages instead of raw error keys.

---

## Pending / Next Steps

1. **Test harness** — Add `pytest-homeassistant-custom-component` so the validation
   logic in `services.py` and the timestamp/baseline logic in `coordinator.py` can be
   unit-tested. Both regressions of the 2026-04-30 hot-fixes (free-function vs
   instance method, datetime vs float) would have been caught at CI time.

2. **Reactive energy import** — Same `ValoriDiEnergia` method, two unused energy
   types in the dropdown (inductive + capacitive). Adds power-factor monitoring data.

3. **Meter readings fallback** — Use `/s/new-reading-archive-client` for non-smart
   PODs (currently surfaces only the QN04 warning). See
   `docs/investigations/2026-04-30-portal-data-sources.md`.

4. **Historical backfill** — Configurable number of past months to fetch on first
   install, rather than just the current month.

5. **Session reuse** — Currently re-authenticates every update cycle. Could check
   `sid` cookie validity first.

6. **Late-correction handling** — Optionally re-fetch the last N days on each cycle
   to pick up portal-side corrections to already-recorded values.
