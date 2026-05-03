<!-- updated: 2026-05-03 -->

# Recommended dashboards for Rețele Electrice

Ready-to-paste Lovelace YAML for the integration. Two variants per POD type:

- **Starter ("Energie")** — 6–8 cards, the everyday view. Recommended.
- **Explorer** — period totals + multi-range charts. Optional.

All snippets use only Home Assistant's built-in cards (`tile`, `statistic`, `statistics-graph`, `heading`, `grid` sections). No HACS dependencies.

---

## How to know your POD type

Two POD types are supported:

- **Prosumer** — your meter records both consumption (import) and production (export). Use the prosumer snippets.
- **Non-prosumer** — consumption only. Use the non-prosumer snippets.

To check which one you have:

1. Open **Developer Tools** → **States** in Home Assistant.
2. Filter by `sensor.retele_electrice_<your-pod>_pod_info`.
3. Look at the `kw_evacuata` attribute.
   - Numeric value (e.g. `5.0`) → **prosumer**.
   - Empty / null / missing → **non-prosumer**.

---

## For prosumer PODs

### 1 — Starter ("Energie") dashboard *(recommended)*

Prosumer POD with both consumption (import) and production (export). Shows last sync, a manual sync button, this-month import/export totals, and three 30-day daily bar charts.

Replace `RO005E513888412` (uppercase, in titles) and `ro005e513888412` (lowercase, in entity IDs) with your POD.

```yaml
views:
  - type: sections
    title: Energie
    path: energie
    icon: mdi:flash
    sections:
      - type: grid
        title: RO005E513888412
        cards:
          - type: heading
            heading: Consum & Export
            heading_style: title
            icon: mdi:transmission-tower
          - type: tile
            entity: sensor.retele_electrice_ro005e513888412_last_sync
            name: Ultima sincronizare
            icon: mdi:sync
          - type: tile
            entity: button.retele_electrice_ro005e513888412_sync_data
            name: Sincronizare manuala
            icon: mdi:cloud-sync
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            name: Import luna curenta
            stat_type: change
            period:
              calendar:
                period: month
          - type: statistic
            entity: retele_electrice:ro005e513888412_export
            name: Export luna curenta
            stat_type: change
            period:
              calendar:
                period: month
          - type: statistics-graph
            title: Import zilnic (kWh)
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
          - type: statistics-graph
            title: Export zilnic (kWh)
            entities:
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
          - type: statistics-graph
            title: Import vs Export (30 zile)
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
```

### 2 — Explorer dashboard *(optional, deeper analysis)*

Two sections: period totals as statistic cards (this/last month, this/last year — both import and export), then four multi-range bar charts (last 7 days hourly, last 30 days daily, last 90 days daily, this year monthly).

Replace `RO005E513888412` / `ro005e513888412` with your POD.

```yaml
views:
  - type: sections
    title: Explorer
    path: explorer
    icon: mdi:chart-bar
    sections:
      - type: grid
        title: RO005E513888412 — Period totals
        cards:
          - type: heading
            heading: Period totals (statistic cards)
            heading_style: title
            icon: mdi:counter
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: month
            name: Import — This month
          - type: statistic
            entity: retele_electrice:ro005e513888412_export
            stat_type: change
            period:
              calendar:
                period: month
            name: Export — This month
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: month
                offset: -1
            name: Import — Last month
          - type: statistic
            entity: retele_electrice:ro005e513888412_export
            stat_type: change
            period:
              calendar:
                period: month
                offset: -1
            name: Export — Last month
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: year
            name: Import — This year
          - type: statistic
            entity: retele_electrice:ro005e513888412_export
            stat_type: change
            period:
              calendar:
                period: year
            name: Export — This year
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: year
                offset: -1
            name: Import — Last year
          - type: statistic
            entity: retele_electrice:ro005e513888412_export
            stat_type: change
            period:
              calendar:
                period: year
                offset: -1
            name: Export — Last year
      - type: grid
        title: RO005E513888412 — Charts
        cards:
          - type: heading
            heading: Charts (statistics-graph)
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Last 7 days (hourly) — Import vs Export
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: hour
            days_to_show: 7
            chart_type: bar
          - type: statistics-graph
            title: Last 30 days (daily) — Import vs Export
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
          - type: statistics-graph
            title: Last 90 days (daily) — Import vs Export
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: day
            days_to_show: 90
            chart_type: bar
          - type: statistics-graph
            title: This year (monthly) — Import vs Export
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
              - entity: retele_electrice:ro005e513888412_export
                name: Export
            stat_types:
              - change
            period: month
            days_to_show: 365
            chart_type: bar
```

---

## For non-prosumer PODs

### 3 — Starter ("Energie") dashboard *(recommended)*

Non-prosumer POD with consumption only. Same shape as the prosumer Starter, with export-related cards removed.

Replace `RO005E513888412` / `ro005e513888412` with your POD.

```yaml
views:
  - type: sections
    title: Energie
    path: energie
    icon: mdi:flash
    sections:
      - type: grid
        title: RO005E513888412
        cards:
          - type: heading
            heading: Consum
            heading_style: title
            icon: mdi:transmission-tower
          - type: tile
            entity: sensor.retele_electrice_ro005e513888412_last_sync
            name: Ultima sincronizare
            icon: mdi:sync
          - type: tile
            entity: button.retele_electrice_ro005e513888412_sync_data
            name: Sincronizare manuala
            icon: mdi:cloud-sync
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            name: Import luna curenta
            stat_type: change
            period:
              calendar:
                period: month
          - type: statistics-graph
            title: Import zilnic (kWh)
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
```

### 4 — Explorer dashboard *(optional, deeper analysis)*

Non-prosumer Explorer. Same two-section layout as prosumer Explorer, but only import statistic cards (4 instead of 8) and import-only series in the multi-range charts.

Replace `RO005E513888412` / `ro005e513888412` with your POD.

```yaml
views:
  - type: sections
    title: Explorer
    path: explorer
    icon: mdi:chart-bar
    sections:
      - type: grid
        title: RO005E513888412 — Period totals
        cards:
          - type: heading
            heading: Period totals (statistic cards)
            heading_style: title
            icon: mdi:counter
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: month
            name: Import — This month
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: month
                offset: -1
            name: Import — Last month
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: year
            name: Import — This year
          - type: statistic
            entity: retele_electrice:ro005e513888412_import
            stat_type: change
            period:
              calendar:
                period: year
                offset: -1
            name: Import — Last year
      - type: grid
        title: RO005E513888412 — Charts
        cards:
          - type: heading
            heading: Charts (statistics-graph)
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Last 7 days (hourly) — Import
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: hour
            days_to_show: 7
            chart_type: bar
          - type: statistics-graph
            title: Last 30 days (daily) — Import
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: day
            days_to_show: 30
            chart_type: bar
          - type: statistics-graph
            title: Last 90 days (daily) — Import
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: day
            days_to_show: 90
            chart_type: bar
          - type: statistics-graph
            title: This year (monthly) — Import
            entities:
              - entity: retele_electrice:ro005e513888412_import
                name: Import
            stat_types:
              - change
            period: month
            days_to_show: 365
            chart_type: bar
```

---

## How to install a dashboard YAML

### As a brand-new dashboard

1. **Settings** → **Dashboards** → **Add Dashboard**
2. Pick **New dashboard from scratch**, give it a name, then **Create**.
3. Open the new dashboard, click ⋮ (top-right) → **Edit dashboard** → **Take control** if prompted.
4. Click ⋮ again → **Raw configuration editor**.
5. Replace the contents with the snippet you picked, after substituting your POD.
6. **Save**.

### As an extra view on an existing dashboard

1. Open the existing dashboard, click ⋮ → **Edit dashboard** → ⋮ → **Raw configuration editor**.
2. Find the top-level `views:` list and append the snippet's `views:` entry to it (drop the leading `views:` line; keep just the `- type: sections …` block).
3. **Save**.

---

## Customization tips

- **POD ID substitution.** The placeholder `RO005E513888412` (uppercase, in titles) and `ro005e513888412` (lowercase, in entity IDs) appears throughout each snippet. Find/replace both forms with your own POD.
- **Multi-POD setups.** Duplicate the `- type: grid` section per POD; each section's `title:` makes a clean separator.
- **Chart length.** `days_to_show` on each `statistics-graph` controls history. Bump to `90` or `365` if you want a longer view.
- **Bar vs line.** Daily bars work well for energy. If you prefer lines, set `chart_type: line` (or remove the line — `bar` is the default).
- **Romanian vs English labels.** Snippets ship with Romanian labels (`Import luna curenta`, `Sincronizare manuala`). Translate the `name:` and `title:` fields freely; they don't affect the data.
- **Diacritics.** Snippets deliberately avoid `ă` / `â` / `î` / `ș` / `ț` for editor portability. Add them back in the `name:` / `title:` fields if your editor handles UTF-8 cleanly.
