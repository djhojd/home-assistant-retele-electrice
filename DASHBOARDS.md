<!-- updated: 2026-11-26 -->

# Recommended dashboards for Retele Electrice

Ready-to-paste Lovelace YAML for the integration: one full dashboard per POD type, plus optional add-ons. Each dashboard has three views:

- **Overview**: sync status, period totals (this/last month, this/last year), charts at three scales (7 days hourly, 30 days daily, 12 months monthly), and the meter details.
- **Explorer**: a date picker driving range totals and a chart.
- **Year over year**: this month vs the same month last year, the last 12 months vs the 12 before, and 24-month charts.

Everything uses Home Assistant's built-in cards (`tile`, `statistic`, `statistics-graph`, `energy-date-selection`, `heading`, `sections` views). Charts use the same colours throughout: blue (`#488fc2`) for import and purple (`#8353d1`) for export.

---

## How to know your POD type

- **Prosumer**: your meter records both consumption (import) and production (export). Use the prosumer dashboard.
- **Non-prosumer**: consumption only. Use the non-prosumer dashboard.

To check: if the statistic `retele_electrice:<your-pod>_export` exists (**Developer Tools** → **Statistics**, search `retele_electrice`), you're a prosumer.

A POD on a non-smart meter (sensor `..._smart_metered` is `N`) gets no hourly data from the portal. Use only the [meter details add-on](#meter-details-for-another-pod) for it.

---

## Prosumer dashboard

Replace `RO005EXXXXXXXXX` (uppercase, in headings) and `ro005exxxxxxxxx` (lowercase, in entity IDs) with your POD.

```yaml
views:
  - type: sections
    title: Overview
    path: overview
    icon: mdi:flash
    sections:
      - type: grid
        cards:
          - type: heading
            heading: RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:transmission-tower
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_last_sync
            name: Last sync
            icon: mdi:sync
            grid_options: {columns: 6}
          - type: tile
            entity: button.retele_electrice_ro005exxxxxxxxx_sync_data
            name: Sync now
            icon: mdi:cloud-sync
            grid_options: {columns: 6}
          - type: heading
            heading: Period totals
            heading_style: subtitle
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · last month
            stat_type: change
            period: {calendar: {period: month, offset: -1}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · last month
            stat_type: change
            period: {calendar: {period: month, offset: -1}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · this year
            stat_type: change
            period: {calendar: {period: year}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · this year
            stat_type: change
            period: {calendar: {period: year}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · last year
            stat_type: change
            period: {calendar: {period: year, offset: -1}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · last year
            stat_type: change
            period: {calendar: {period: year, offset: -1}}
            grid_options: {columns: 6}
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: Import vs Export
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Last 7 days (hourly)
            entities: &import_export
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
              - entity: retele_electrice:ro005exxxxxxxxx_export
                name: Export
                color: "#8353d1"
            stat_types: [change]
            period: hour
            days_to_show: 7
            chart_type: bar
            grid_options: {columns: full}
          - type: statistics-graph
            title: Last 30 days (daily)
            entities: *import_export
            stat_types: [change]
            period: day
            days_to_show: 30
            chart_type: bar
            grid_options: {columns: full}
          - type: statistics-graph
            title: Last 12 months (monthly)
            entities: *import_export
            stat_types: [change]
            period: month
            days_to_show: 365
            chart_type: bar
            grid_options: {columns: full}
      - type: grid
        cards:
          - type: heading
            heading: Meter RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:meter-electric
            badges:
              - type: button
                icon: mdi:refresh
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target:
                    entity_id: button.retele_electrice_ro005exxxxxxxxx_refresh_pod_info
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_contracted_power
            name: Contracted power
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_smart_metered
            name: Smart-metered
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_supplier
            name: Supplier
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_meter_install_date
            name: Meter installed
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_pod_info
            name: Info updated
            grid_options: {columns: 6}

  - type: sections
    title: Explorer
    path: explorer
    icon: mdi:calendar-search
    sections:
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:calendar-search
          - type: energy-date-selection
            disable_compare: true
            grid_options: {columns: full}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import
            stat_type: change
            period: energy_date_selection
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export
            stat_type: change
            period: energy_date_selection
            grid_options: {columns: 6}
          - type: statistics-graph
            title: Import vs Export
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
              - entity: retele_electrice:ro005exxxxxxxxx_export
                name: Export
                color: "#8353d1"
            stat_types: [change]
            chart_type: bar
            energy_date_selection: true
            grid_options: {columns: full}

  - type: sections
    title: Year over year
    path: year-over-year
    icon: mdi:calendar-sync
    sections:
      - type: grid
        cards:
          - type: heading
            heading: This month vs a year ago
            heading_style: title
            icon: mdi:calendar-month
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · same month last year
            stat_type: change
            period: {calendar: {period: month, offset: -12}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · same month last year
            stat_type: change
            period: {calendar: {period: month, offset: -12}}
            grid_options: {columns: 6}
      - type: grid
        cards:
          - type: heading
            heading: Last 12 months vs the 12 before
            heading_style: title
            icon: mdi:calendar-range
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · last 12 months
            stat_type: change
            period: {rolling_window: {duration: {days: 365}}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import · 12 months before
            stat_type: change
            period: {rolling_window: {duration: {days: 365}, offset: {days: -365}}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · last 12 months
            stat_type: change
            period: {rolling_window: {duration: {days: 365}}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export
            name: Export · 12 months before
            stat_type: change
            period: {rolling_window: {duration: {days: 365}, offset: {days: -365}}}
            grid_options: {columns: 6}
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: Last 24 months (monthly)
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Import
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
            stat_types: [change]
            period: month
            days_to_show: 730
            chart_type: bar
            grid_options: {columns: full}
          - type: statistics-graph
            title: Export
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_export
                name: Export
                color: "#8353d1"
            stat_types: [change]
            period: month
            days_to_show: 730
            chart_type: bar
            grid_options: {columns: full}
```

---

## Non-prosumer dashboard

The same three views without the export cards and series.

Replace `RO005EXXXXXXXXX` / `ro005exxxxxxxxx` with your POD.

```yaml
views:
  - type: sections
    title: Overview
    path: overview
    icon: mdi:flash
    sections:
      - type: grid
        cards:
          - type: heading
            heading: RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:transmission-tower
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_last_sync
            name: Last sync
            icon: mdi:sync
            grid_options: {columns: 6}
          - type: tile
            entity: button.retele_electrice_ro005exxxxxxxxx_sync_data
            name: Sync now
            icon: mdi:cloud-sync
            grid_options: {columns: 6}
          - type: heading
            heading: Period totals
            heading_style: subtitle
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: This month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Last month
            stat_type: change
            period: {calendar: {period: month, offset: -1}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: This year
            stat_type: change
            period: {calendar: {period: year}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Last year
            stat_type: change
            period: {calendar: {period: year, offset: -1}}
            grid_options: {columns: 6}
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: Import
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Last 7 days (hourly)
            entities: &import
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
            stat_types: [change]
            period: hour
            days_to_show: 7
            chart_type: bar
            grid_options: {columns: full}
          - type: statistics-graph
            title: Last 30 days (daily)
            entities: *import
            stat_types: [change]
            period: day
            days_to_show: 30
            chart_type: bar
            grid_options: {columns: full}
          - type: statistics-graph
            title: Last 12 months (monthly)
            entities: *import
            stat_types: [change]
            period: month
            days_to_show: 365
            chart_type: bar
            grid_options: {columns: full}
      - type: grid
        cards:
          - type: heading
            heading: Meter RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:meter-electric
            badges:
              - type: button
                icon: mdi:refresh
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target:
                    entity_id: button.retele_electrice_ro005exxxxxxxxx_refresh_pod_info
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_contracted_power
            name: Contracted power
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_smart_metered
            name: Smart-metered
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_supplier
            name: Supplier
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_meter_install_date
            name: Meter installed
            grid_options: {columns: 6}
          - type: tile
            entity: sensor.retele_electrice_ro005exxxxxxxxx_pod_info
            name: Info updated
            grid_options: {columns: 6}

  - type: sections
    title: Explorer
    path: explorer
    icon: mdi:calendar-search
    sections:
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: RO005EXXXXXXXXX
            heading_style: title
            icon: mdi:calendar-search
          - type: energy-date-selection
            disable_compare: true
            grid_options: {columns: full}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Import
            stat_type: change
            period: energy_date_selection
            grid_options: {columns: 6}
          - type: statistics-graph
            title: Import
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
            stat_types: [change]
            chart_type: bar
            energy_date_selection: true
            grid_options: {columns: full}

  - type: sections
    title: Year over year
    path: year-over-year
    icon: mdi:calendar-sync
    sections:
      - type: grid
        cards:
          - type: heading
            heading: Compared with a year before
            heading_style: title
            icon: mdi:calendar-month
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: This month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Same month last year
            stat_type: change
            period: {calendar: {period: month, offset: -12}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: Last 12 months
            stat_type: change
            period: {rolling_window: {duration: {days: 365}}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import
            name: 12 months before
            stat_type: change
            period: {rolling_window: {duration: {days: 365}, offset: {days: -365}}}
            grid_options: {columns: 6}
      - type: grid
        column_span: 2
        cards:
          - type: heading
            heading: Last 24 months (monthly)
            heading_style: title
            icon: mdi:chart-bar
          - type: statistics-graph
            title: Import
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_import
                name: Import
                color: "#488fc2"
            stat_types: [change]
            period: month
            days_to_show: 730
            chart_type: bar
            grid_options: {columns: full}
```

---

## Add-ons

### Cost and compensation

With an import and/or export price set under **Configure** (see [Prices](README.md#prices-optional)), the integration writes `retele_electrice:<pod>_import_cost` and `retele_electrice:<pod>_export_compensation` in your Home Assistant currency. Add this section to the Overview view's `sections:` list, and drop the lines for a price you didn't set.

```yaml
      - type: grid
        cards:
          - type: heading
            heading: Cost & compensation
            heading_style: title
            icon: mdi:cash
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import_cost
            name: Cost · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export_compensation
            name: Compensation · this month
            stat_type: change
            period: {calendar: {period: month}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_import_cost
            name: Cost · last month
            stat_type: change
            period: {calendar: {period: month, offset: -1}}
            grid_options: {columns: 6}
          - type: statistic
            entity: retele_electrice:ro005exxxxxxxxx_export_compensation
            name: Compensation · last month
            stat_type: change
            period: {calendar: {period: month, offset: -1}}
            grid_options: {columns: 6}
          - type: statistics-graph
            title: Last 12 months (monthly)
            entities:
              - entity: retele_electrice:ro005exxxxxxxxx_import_cost
                name: Cost
                color: "#488fc2"
              - entity: retele_electrice:ro005exxxxxxxxx_export_compensation
                name: Compensation
                color: "#8353d1"
            stat_types: [change]
            period: month
            days_to_show: 365
            chart_type: bar
```

Home Assistant can't subtract one statistic from another, so there's no net figure. The chart shows both side by side.

### Meter details for another POD

For a second POD, or a non-smart one with no hourly data, add the meter section on its own: copy the `Meter RO005EXXXXXXXXX` grid from either dashboard into the Overview's `sections:` list and substitute that POD.

---

## How to install a dashboard YAML

### As a brand-new dashboard

1. **Settings** → **Dashboards** → **Add Dashboard**
2. Pick **New dashboard from scratch**, give it a name, then **Create**.
3. Open the new dashboard, click ⋮ (top-right) → **Edit dashboard** → **Take control** if prompted.
4. Click ⋮ again → **Raw configuration editor**.
5. Replace the contents with the snippet you picked, after substituting your POD.
6. **Save**.

### As extra views on an existing dashboard

1. Open the existing dashboard, click ⋮ → **Edit dashboard** → ⋮ → **Raw configuration editor**.
2. Append the snippet's view entries to the top-level `views:` list (drop the leading `views:` line, keep each `- type: sections …` block).
3. **Save**.

---

## Tips

- **POD ID substitution.** The placeholder `RO005EXXXXXXXXX` (uppercase, in headings) and `ro005exxxxxxxxx` (lowercase, in entity IDs) appears throughout. Find/replace both forms with your own POD.
- **Multi-POD setups.** Duplicate the Overview's sections per POD; the heading with the POD ID makes a clean separator.
- **Explorer opens on today, which is always empty.** The portal publishes a few days late, and the date picker has no default-period setting. Pick **Last 30 days** once from its preset menu: Home Assistant remembers that choice per browser. The arrow buttons aren't remembered.
- **Year-over-year cards start empty.** They fill in once you have more than a year of statistics. Run the `backfill_history` service to import history back to the meter's install date.
- **`&import_export` / `*import_export`** are YAML anchors that reuse the same entity list across charts. Home Assistant expands them when you save. Keep them, or paste the list out in full.
- **Bar vs line.** Bars suit energy totals. Set `chart_type: line` if you prefer lines.
