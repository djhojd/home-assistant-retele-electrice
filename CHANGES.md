# Rețele Electrice — Change Log

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

1. **HA deployment test** — Deploy to HA and verify the Energy Dashboard integration
   (statistics import, cumulative sum continuity across restarts).

2. **Duplicate statistics** — Consider adding a date-range guard so re-runs don't insert
   duplicate hourly rows for days already in the recorder. Note: `async_add_external_statistics`
   is idempotent on the `start` key, so this is safe but wastes API calls.

3. **Historical backfill** — Implement an option to request data for a configurable
   number of past days (e.g. last 90 days) on first setup, rather than the default
   rolling 30-day window.

4. **Session reuse** — The current implementation re-authenticates every update cycle.
   Consider checking if the `sid` cookie is still valid before re-logging in.
