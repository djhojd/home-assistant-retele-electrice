// Retele Electrice dashboard strategy. Use with:
//   strategy:
//     type: custom:retele-electrice
// The views are rebuilt from this integration's devices, entities and
// statistics each time the dashboard opens. DASHBOARDS.md is the reference
// layout; keep the two in step.

const DOMAIN = "retele_electrice";
const IMPORT_COLOR = "#488fc2";
const EXPORT_COLOR = "#8353d1";
const STAT_KINDS = ["import", "export", "import_cost", "export_compensation"];

const HALF = { grid_options: { columns: 6 } };
const FULL = { grid_options: { columns: "full" } };

const THIS_MONTH = { calendar: { period: "month" } };
const LAST_MONTH = { calendar: { period: "month", offset: -1 } };
const THIS_YEAR = { calendar: { period: "year" } };
const LAST_YEAR = { calendar: { period: "year", offset: -1 } };
const SAME_MONTH_LAST_YEAR = { calendar: { period: "month", offset: -12 } };
const LAST_12_MONTHS = { rolling_window: { duration: { days: 365 } } };
const PREVIOUS_12_MONTHS = {
  rolling_window: { duration: { days: 365 }, offset: { days: -365 } },
};

const ENERGY = [
  { kind: "import", label: "Import", color: IMPORT_COLOR },
  { kind: "export", label: "Export", color: EXPORT_COLOR },
];
const MONEY = [
  { kind: "import_cost", label: "Cost", color: IMPORT_COLOR },
  { kind: "export_compensation", label: "Compensation", color: EXPORT_COLOR },
];

/**
 * One entry per POD device: {pod, title, entities, stats}.
 * entities maps translation_key -> entity_id (survives entity-ID renames);
 * stats maps kind ("import", "export_compensation", ...) -> statistic_id.
 */
export function discoverPods(hass, statisticIds) {
  const known = new Set(
    statisticIds.filter((s) => s.source === DOMAIN).map((s) => s.statistic_id),
  );
  const entities = Object.values(hass.entities || {});
  const pods = [];
  for (const device of Object.values(hass.devices || {})) {
    const identifier = (device.identifiers || []).find(([d]) => d === DOMAIN);
    if (!identifier) continue;
    const pod = identifier[1];
    const byKey = {};
    for (const e of entities) {
      if (e.device_id === device.id && e.platform === DOMAIN && e.translation_key) {
        byKey[e.translation_key] = e.entity_id;
      }
    }
    const stats = {};
    for (const kind of STAT_KINDS) {
      const id = `${DOMAIN}:${pod.toLowerCase()}_${kind}`;
      if (known.has(id)) stats[kind] = id;
    }
    pods.push({ pod, title: device.name_by_user || pod, entities: byKey, stats });
  }
  return pods.sort((a, b) => a.pod.localeCompare(b.pod));
}

const heading = (text, icon, extra = {}) => ({
  type: "heading", heading: text, heading_style: "title", icon, ...extra,
});
const subtitle = (text) => ({ type: "heading", heading: text, heading_style: "subtitle" });
const tile = (entity, name, extra = {}) =>
  entity ? { type: "tile", entity, name, ...extra } : null;
const total = (entity, name, period) => ({
  type: "statistic", entity, name, stat_type: "change", period, ...HALF,
});
const graph = (title, series, period, days) => ({
  type: "statistics-graph", title, entities: series, stat_types: ["change"],
  period, days_to_show: days, chart_type: "bar", ...FULL,
});
const grid = (cards, extra = {}) => ({ type: "grid", ...extra, cards: cards.filter(Boolean) });
const view = (title, path, icon, sections) => ({ type: "sections", title, path, icon, sections });

const present = (pod, group) => group.filter((g) => pod.stats[g.kind]);
const series = (pod, group) =>
  present(pod, group).map((g) => ({ entity: pod.stats[g.kind], name: g.label, color: g.color }));
const totals = (pod, group, periods) =>
  periods.flatMap(([suffix, period]) =>
    present(pod, group).map((g) => total(pod.stats[g.kind], `${g.label} · ${suffix}`, period)),
  );
const hasEnergy = (pod) => present(pod, ENERGY).length > 0;
const chartTitle = (pod) => present(pod, ENERGY).map((g) => g.label).join(" vs ");

function meterSection(pod) {
  const refresh = pod.entities.refresh_pod_info;
  const badges = refresh
    ? [{
        type: "button",
        icon: "mdi:refresh",
        tap_action: {
          action: "perform-action",
          perform_action: "button.press",
          target: { entity_id: refresh },
        },
      }]
    : [];
  return grid([
    heading(`Meter ${pod.title}`, "mdi:meter-electric", { badges }),
    tile(pod.entities.contracted_power, "Contracted power", HALF),
    tile(pod.entities.smart_metered, "Smart-metered", HALF),
    tile(pod.entities.supplier, "Supplier"),
    tile(pod.entities.meter_install_date, "Meter installed", HALF),
    tile(pod.entities.pod_info, "Info updated", HALF),
  ]);
}

function overviewSections(pod) {
  const status = [
    heading(pod.title, "mdi:transmission-tower"),
    tile(pod.entities.last_sync, "Last sync", { icon: "mdi:sync", ...HALF }),
    tile(pod.entities.sync_data, "Sync now", { icon: "mdi:cloud-sync", ...HALF }),
  ];
  if (!hasEnergy(pod)) {
    return [
      grid([
        ...status,
        {
          type: "markdown",
          content:
            "The portal has no hourly data for this POD (it isn't on a smart meter), " +
            "so only the meter details are shown.",
        },
      ]),
      meterSection(pod),
    ];
  }
  const sections = [
    grid([
      ...status,
      subtitle("Period totals"),
      ...totals(pod, ENERGY, [
        ["this month", THIS_MONTH], ["last month", LAST_MONTH],
        ["this year", THIS_YEAR], ["last year", LAST_YEAR],
      ]),
    ]),
    grid([
      heading(chartTitle(pod), "mdi:chart-bar"),
      graph("Last 7 days (hourly)", series(pod, ENERGY), "hour", 7),
      graph("Last 30 days (daily)", series(pod, ENERGY), "day", 30),
      graph("Last 12 months (monthly)", series(pod, ENERGY), "month", 365),
    ], { column_span: 2 }),
  ];
  if (present(pod, MONEY).length) {
    sections.push(grid([
      heading("Cost & compensation", "mdi:cash"),
      ...totals(pod, MONEY, [["this month", THIS_MONTH], ["last month", LAST_MONTH]]),
      graph("Last 12 months (monthly)", series(pod, MONEY), "month", 365),
    ]));
  }
  sections.push(meterSection(pod));
  return sections;
}

function explorerSections(pods) {
  return [
    grid([
      heading("Pick a range", "mdi:calendar-search"),
      { type: "energy-date-selection", disable_compare: true, ...FULL },
      subtitle(
        "The portal publishes a few days late, so today is empty. " +
          "Pick Last 30 days once from the date menu and it's remembered in this browser.",
      ),
    ], { column_span: 2 }),
    ...pods.map((pod) => grid([
      heading(pod.title, "mdi:transmission-tower"),
      ...[...present(pod, ENERGY), ...present(pod, MONEY)].map((g) =>
        total(pod.stats[g.kind], g.label, "energy_date_selection")),
      {
        type: "statistics-graph",
        title: chartTitle(pod),
        entities: series(pod, ENERGY),
        stat_types: ["change"],
        chart_type: "bar",
        energy_date_selection: true,
        ...FULL,
      },
    ], { column_span: 2 })),
  ];
}

function yearOverYearSections(pod) {
  return [
    grid([
      heading(pod.title, "mdi:calendar-sync"),
      subtitle("This month vs a year ago"),
      ...totals(pod, ENERGY, [["this month", THIS_MONTH], ["same month last year", SAME_MONTH_LAST_YEAR]]),
      subtitle("Last 12 months vs the 12 before"),
      ...totals(pod, ENERGY, [["last 12 months", LAST_12_MONTHS], ["12 months before", PREVIOUS_12_MONTHS]]),
    ]),
    grid([
      heading(`${pod.title} · last 24 months`, "mdi:chart-bar"),
      ...present(pod, ENERGY).map((g) =>
        graph(g.label, [{ entity: pod.stats[g.kind], name: g.label, color: g.color }], "month", 730)),
    ], { column_span: 2 }),
  ];
}

export function buildViews(pods) {
  if (!pods.length) {
    return [view("Overview", "overview", "mdi:flash", [grid([{
      type: "markdown",
      content:
        "No Retele Electrice POD found. Add one under **Settings → Devices & services → " +
        "Add integration → Retele Electrice**.",
    }])])];
  }
  const views = [view("Overview", "overview", "mdi:flash", pods.flatMap(overviewSections))];
  const withData = pods.filter(hasEnergy);
  if (withData.length) {
    views.push(view("Explorer", "explorer", "mdi:calendar-search", explorerSections(withData)));
    views.push(view("Year over year", "year-over-year", "mdi:calendar-sync",
      withData.flatMap(yearOverYearSections)));
  }
  return views;
}

async function fetchStatisticIds(hass) {
  try {
    return await hass.callWS({ type: "recorder/list_statistic_ids", statistic_type: "sum" });
  } catch (err) {
    // Without statistics the dashboard still shows sync status and meter details.
    console.warn("retele-electrice strategy: could not list statistics", err);
    return [];
  }
}

const TAG = "ll-strategy-dashboard-retele-electrice";
if (typeof customElements !== "undefined" && !customElements.get(TAG)) {
  customElements.define(TAG, class extends HTMLElement {
    static noEditor = true;

    static async generate(_config, hass) {
      const pods = discoverPods(hass, await fetchStatisticIds(hass));
      return { title: "Retele Electrice", views: buildViews(pods) };
    }
  });
  window.customStrategies = window.customStrategies || [];
  window.customStrategies.push({
    type: "retele-electrice",
    strategyType: "dashboard",
    name: "Retele Electrice",
    description: "Energy, cost and meter details for every Retele Electrice POD.",
    documentationURL: "https://github.com/djhojd/home-assistant-retele-electrice#dashboard",
  });
}
