# Retele Electrice - Home Assistant Integration

Custom component for [Home Assistant](https://www.home-assistant.io/) that imports hourly energy consumption and export data from the [Retele Electrice](https://contulmeu.reteleelectrice.ro) portal (formerly Distributie Energie Electrica Romania) into the HA Energy Dashboard.

## What it does

- Logs in to `contulmeu.reteleelectrice.ro` with your credentials
- Fetches **hourly kWh data** for both grid import (consumption) and grid export (production)
- Injects the data as **external statistics** into the HA recorder, making it available in the **Energy Dashboard**
- Provides a **"Last Sync" sensor** showing when data was last fetched
- Provides a **"Sync Data" button** to trigger a manual refresh

## Requirements

- A registered account on [contulmeu.reteleelectrice.ro](https://contulmeu.reteleelectrice.ro)
- Your **POD** (Point of Delivery) identifier (format: `RO005Exxxxxxxxx`)
- Home Assistant 2024.4.0 or newer

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > three-dot menu > **Custom repositories**
3. Add `https://github.com/djhojd/home-assistant-retele-electrice` as an **Integration**
4. Search for "Retele Electrice" and install it
5. Restart Home Assistant

### Manual

1. Copy `custom_components/retele_electrice/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Retele Electrice"
3. Enter your credentials:
   - **Email** - your portal login email
   - **Password** - your portal password
   - **POD** - your Point of Delivery ID (e.g. `RO005E513888412`)
   - **Update interval** - how often to fetch data, in minutes (default: 720 = 12 hours)

## How it works

The integration scrapes data from the Retele Electrice Salesforce-based portal:

1. **Authentication** - POSTs credentials to the Visualforce login form with Salesforce ViewState tokens, then follows the `frontdoor.jsp` redirect to establish a session cookie.
2. **Data retrieval** - Makes Ajax4JSF (a4j) postbacks to the `PED_ProxyCallWSAsync_Curve_VF` Visualforce page with `methodN=ValoriDiEnergia`, which triggers a server-side web service callout.
3. **Statistics import** - Parses the hourly kWh values and injects them into HA's recorder as external statistics with cumulative sums, compatible with the Energy Dashboard.

### Data format

Each daily record contains 24 semicolon-separated hourly values in comma-decimal format:

```
sampleDate:   "01/04/2026 00:00"
sampleValues: "0,384000;0,277000;0,241000;..."  (24 values, one per hour)
energyType:   "WI" (import) or "WE" (export)
```

### Statistics IDs

The integration creates two external statistics per POD:

| Statistic ID | Description |
|---|---|
| `retele_electrice:<pod>_import` | Grid import (consumption) in kWh |
| `retele_electrice:<pod>_export` | Grid export (production) in kWh |

These appear automatically in the Energy Dashboard configuration.

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.retele_electrice_<pod>_last_sync` | Sensor (timestamp) | Last successful data sync time |
| `button.retele_electrice_<pod>_sync_button` | Button | Triggers a manual data refresh |

## Services

### `retele_electrice.clear_statistics`

Permanently deletes the integration's imported energy statistics from the HA recorder. Use this to recover from corrupted cumulative sums or to force a clean re-import. After clearing, the next coordinator update (or a press of the **Sync Data** button) will re-fetch the current month and re-populate from scratch.

```yaml
service: retele_electrice.clear_statistics
data:
  confirm: true              # required, must literally be true
  pod: RO005E513888412       # optional; defaults to all configured PODs
```

The service refuses to run unless `confirm: true` is passed, and rejects unknown PODs.

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

## Development

Local-only scripts, fixtures, demo CSVs, and credentials live in `dev/` (gitignored). Clone this repo and create the folder yourself; nothing in `dev/` is shipped.

### Running tests locally

```bash
# Install uv (if not already installed) — https://docs.astral.sh/uv/

# From the repository root:
cd dev
uv run test_api.py
```

Requires `dev/credentials.json`:

```json
{
  "email": "your@email.com",
  "password": "your-password"
}
```

## License

MIT
