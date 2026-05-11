# Retele Electrice - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/djhojd/home-assistant-retele-electrice?include_prereleases&sort=semver)](https://github.com/djhojd/home-assistant-retele-electrice/releases)
[![Tests](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/test.yml/badge.svg)](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/test.yml)
[![Hassfest](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/hassfest.yml/badge.svg)](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/hassfest.yml)
[![HACS Action](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/hacs.yml/badge.svg)](https://github.com/djhojd/home-assistant-retele-electrice/actions/workflows/hacs.yml)
[![Home Assistant: 2026.1+](https://img.shields.io/badge/Home%20Assistant-2026.1+-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Custom component for [Home Assistant](https://www.home-assistant.io/) that imports hourly energy consumption and export data from the [Retele Electrice](https://contulmeu.reteleelectrice.ro) portal (formerly Distributie Energie Electrica Romania) as external statistics that you can add to the HA Energy Dashboard.

> ⚠️ **Work in progress.** Tested with just one prosumer POD.
>
> Help wanted: if you have a different POD on Retele Electrice (non-prosumer, different meter, etc.), please install it and report any problems by [opening an issue](https://github.com/djhojd/home-assistant-retele-electrice/issues/new).

## Features

- **Hourly electricity consumption and production in Home Assistant** — kWh import + export, refreshed automatically every 12 hours
- **Full meter history on first install** — backfills everything the meter has recorded, going back to its installation date
- **Energy Dashboard ready** — drop the import / export statistics straight into Home Assistant's built-in Energy Dashboard
- **Per-POD device card** with last-sync timestamp, one-click manual refresh, and full contract / meter details (customer, address, contracted kW, supplier, meter brand and serial)
- **Pre-built dashboards** — copy-paste Lovelace YAML for prosumer or non-prosumer setups, see [DASHBOARDS.md](DASHBOARDS.md)

## Requirements

- A registered account on [contulmeu.reteleelectrice.ro](https://contulmeu.reteleelectrice.ro)
- Your **POD** (Point of Delivery) identifier (format: `RO005Exxxxxxxxx`)
- Home Assistant 2026.1.0 or newer

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=djhojd&repository=home-assistant-retele-electrice&category=integration)

Click the badge above to register the custom repository → click **Download** in HACS → restart Home Assistant when prompted.

<details>
<summary>Manual install (without the badge)</summary>

1. Open HACS in Home Assistant
2. Go to **Integrations** > three-dot menu > **Custom repositories**
3. Add `https://github.com/djhojd/home-assistant-retele-electrice` as an **Integration**
4. Search for "Retele Electrice" and install it
5. Restart Home Assistant

</details>

### Manual

1. Copy `custom_components/retele_electrice/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=retele_electrice)

Click the badge above to open the setup dialog filtered to this integration, then enter your credentials (see [Privacy](#privacy) for how they're stored and used):

- **Email** - your portal login email
- **Password** - your portal password
- **POD** - your Point of Delivery ID (e.g. `RO005EXXXXXXXXX`)
- **Update interval** - how often to fetch data, in minutes (default: 720 = 12 hours)

<details>
<summary>Manual navigation (without the badge)</summary>

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Retele Electrice"
3. Enter the credentials listed above

</details>

## Energy Dashboard setup

The integration imports data as **external statistics** with the metadata Home Assistant's Energy Dashboard expects, so it shows up in the picker — but you still need to point the dashboard at it.

1. Open **Settings** > **Dashboards** > **Energy** (or click the **Energy** icon in the sidebar).
2. If first time, click **Configure Energy**. Otherwise click the gear icon.
3. Under **Electricity grid**:

   | Field | Pick |
   |---|---|
   | **Grid consumption** -> Add Source -> *Use an existing tracked entity* | `retele_electrice:<your-pod>_import` |
   | **Return to grid** *(prosumers only)* -> Add Source | `retele_electrice:<your-pod>_export` |

4. **Save**. Charts populate immediately for the date range covered by imported statistics.

What you don't get yet:
- **Cost tracking** - The integration doesn't fetch tariffs. Set a fixed `RON / kWh` price in the Energy config's "Use a static price" option if you want cost.
- **Live data** - The portal publishes with a 1-2 day delay, so today's bar stays empty until the portal catches up.
- **Solar production** - Add your inverter's integration as **Solar production** independently.

### Recommended dashboards

For richer per-POD dashboards (last sync, manual sync button, period totals, multi-range charts), see [`DASHBOARDS.md`](DASHBOARDS.md) for ready-to-paste Lovelace YAML. Two variants per POD type (prosumer / non-prosumer): a recommended **Starter** and an optional **Explorer**. All snippets use only Home Assistant's built-in cards - no HACS dependencies.

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.retele_electrice_<pod>_last_sync` | Sensor (timestamp) | Last successful data sync time |
| `sensor.retele_electrice_<pod>_pod_info` | Sensor (diagnostic, timestamp) | POD metadata; state = last refresh time, attributes carry the contract and meter details |
| `button.retele_electrice_<pod>_sync_button` | Button | Triggers a manual data refresh |
| `button.retele_electrice_<pod>_refresh_pod_info` | Button (diagnostic) | Manually re-fetch POD info from the portal |

## Services

### `retele_electrice.clear_statistics`

Permanently deletes the integration's imported energy statistics from the HA recorder. Use this to recover from corrupted cumulative sums or to force a clean re-import. After clearing, the next coordinator update (or a press of the **Sync Data** button) will re-fetch and re-populate.

```yaml
service: retele_electrice.clear_statistics
data:
  confirm: true              # required, must literally be true
  pod: RO005EXXXXXXXXX       # optional; defaults to all configured PODs
  from: 2026-04-29           # optional; only delete rows on/after this date
```

The service refuses to run unless `confirm: true` is passed, and rejects unknown PODs.

If `from:` is provided, only rows where the timestamp is at or after midnight Bucharest local time of that date are deleted. Older rows survive. Useful for recovering a specific gap without losing months of history. The cumulative `sum` chain is rebuilt from the cutoff onward by the next sync.

### `retele_electrice.backfill_history`

Wipes the POD's statistics and re-imports the full chain from a starting date (defaults to the meter install date from POD info) to today. Useful on existing installs where you want to backfill data older than the integration's normal sync window.

```yaml
service: retele_electrice.backfill_history
data:
  confirm: true              # required, must literally be true
  pod: RO005EXXXXXXXXX       # optional; defaults to all configured PODs
  from: 2025-10-01           # optional; defaults to pod_info.meter_data_montare
```

Triggered automatically on first install if (a) no statistics exist for the POD, and (b) `pod_info` has the meter install date. Otherwise must be invoked manually.

The service is synchronous and takes about 10 seconds for ~7 months of history (one portal request per month).

## Troubleshooting

### "Authentication failed"

- Verify your email and password work on [contulmeu.reteleelectrice.ro](https://contulmeu.reteleelectrice.ro)
- The portal uses Salesforce login - if the portal changes its login form structure, the integration may need updating

### "VF page ViewState not found"

- The session may have expired. The integration re-authenticates on each update cycle, but if this persists, restart HA.

### No data in Energy Dashboard

- Data appears as **external statistics**, not as entity state. Check **Developer Tools** > **Statistics** to verify the data is being imported.
- The integration fetches data for the current month by default. Historical data before the integration was installed is not available unless backfilled.

### Debug logging

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.retele_electrice: debug
```

## Privacy

The Retele Electrice portal has no public API or OAuth — username + password is the only way to authenticate, so the integration replicates the browser login flow from your Home Assistant instance.

- **Credentials are stored locally** in Home Assistant's encrypted config storage and never leave your HA.
- **All requests go directly to `contulmeu.reteleelectrice.ro`** — no third-party services, no telemetry.
- **Open source** — auth and data-fetching code is in [`api.py`](custom_components/retele_electrice/api.py).

## License

MIT
