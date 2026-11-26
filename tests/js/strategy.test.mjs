// Tests for the dashboard strategy's pure functions: node --test "tests/js/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildViews,
  discoverPods,
} from "../../custom_components/retele_electrice/frontend/retele-electrice-strategy.js";

const DOMAIN = "retele_electrice";

function fakeHass(pods) {
  const devices = {};
  const entities = {};
  for (const { pod, keys = [], nameByUser = null } of pods) {
    const id = `dev_${pod}`;
    devices[id] = { id, identifiers: [[DOMAIN, pod]], name_by_user: nameByUser };
    for (const key of keys) {
      const entityId = `sensor.renamed_${pod.toLowerCase()}_${key}`;
      entities[entityId] = {
        entity_id: entityId, device_id: id, platform: DOMAIN, translation_key: key,
      };
    }
  }
  devices.other = { id: "other", identifiers: [["hue", "x"]] };
  return { devices, entities };
}

const stat = (pod, kind, source = DOMAIN) => ({
  statistic_id: `${DOMAIN}:${pod.toLowerCase()}_${kind}`, source,
});

const KEYS = ["last_sync", "sync_data", "refresh_pod_info", "pod_info",
  "contracted_power", "smart_metered", "supplier", "meter_install_date"];
const PROSUMER = "RO005EXXXXXXXXX";
const NON_SMART = "RO005E000000000";

/** Every string value anywhere in the config, for "is X referenced" checks. */
function strings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => strings(v, out));
  return out;
}

test("discoverPods maps devices, translation keys and statistics", () => {
  const hass = fakeHass([{ pod: PROSUMER, keys: KEYS, nameByUser: "Home" }]);
  const pods = discoverPods(hass, [
    stat(PROSUMER, "import"), stat(PROSUMER, "export"),
    stat(PROSUMER, "import_cost", "recorder"), // foreign source is ignored
  ]);

  assert.equal(pods.length, 1);
  assert.equal(pods[0].pod, PROSUMER);
  assert.equal(pods[0].title, "Home");
  assert.equal(pods[0].entities.sync_data, `sensor.renamed_${PROSUMER.toLowerCase()}_sync_data`);
  assert.deepEqual(Object.keys(pods[0].stats), ["import", "export"]);
});

test("prosumer with prices gets energy, money and meter cards in all views", () => {
  const hass = fakeHass([{ pod: PROSUMER, keys: KEYS }]);
  const kinds = ["import", "export", "import_cost", "export_compensation"];
  const views = buildViews(discoverPods(hass, kinds.map((k) => stat(PROSUMER, k))));

  assert.deepEqual(views.map((v) => v.path), ["overview", "explorer", "year-over-year"]);
  const overview = strings(views[0]);
  for (const kind of kinds) assert.ok(overview.includes(`${DOMAIN}:${PROSUMER.toLowerCase()}_${kind}`));
  assert.ok(overview.includes("Cost & compensation"));
  assert.ok(overview.includes(`sensor.renamed_${PROSUMER.toLowerCase()}_refresh_pod_info`));
});

test("import-only POD has no export or money cards", () => {
  const hass = fakeHass([{ pod: PROSUMER, keys: KEYS }]);
  const views = buildViews(discoverPods(hass, [stat(PROSUMER, "import")]));
  const all = strings(views);

  assert.ok(!all.some((s) => s.endsWith("_export")));
  assert.ok(!all.includes("Cost & compensation"));
  assert.ok(all.includes("Import"));
});

test("POD without statistics shows only status and meter, no data views", () => {
  const hass = fakeHass([{ pod: NON_SMART, keys: KEYS }]);
  const views = buildViews(discoverPods(hass, []));

  assert.deepEqual(views.map((v) => v.path), ["overview"]);
  const cards = views[0].sections.flatMap((s) => s.cards);
  assert.ok(cards.some((c) => c.type === "markdown" && c.content.includes("no hourly data")));
  assert.ok(!cards.some((c) => c.type === "statistic" || c.type === "statistics-graph"));
});

test("two PODs: data views list only the POD with statistics", () => {
  const hass = fakeHass([{ pod: PROSUMER, keys: KEYS }, { pod: NON_SMART, keys: KEYS }]);
  const views = buildViews(discoverPods(hass, [stat(PROSUMER, "import"), stat(PROSUMER, "export")]));

  const overview = strings(views[0]);
  assert.ok(overview.includes(`Meter ${PROSUMER}`));
  assert.ok(overview.includes(`Meter ${NON_SMART}`));
  for (const v of views.slice(1)) assert.ok(!strings(v).includes(NON_SMART));
});

test("missing entities are skipped, not rendered as broken tiles", () => {
  const hass = fakeHass([{ pod: PROSUMER, keys: ["last_sync"] }]);
  const views = buildViews(discoverPods(hass, [stat(PROSUMER, "import")]));
  const tiles = views[0].sections.flatMap((s) => s.cards).filter((c) => c.type === "tile");

  assert.deepEqual(tiles.map((t) => t.name), ["Last sync"]);
});

test("no PODs: a single view pointing at Add integration", () => {
  const views = buildViews(discoverPods({ devices: {}, entities: {} }, []));

  assert.equal(views.length, 1);
  assert.ok(strings(views).some((s) => s.includes("Add integration")));
});
