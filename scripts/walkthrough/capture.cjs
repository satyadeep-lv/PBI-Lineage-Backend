#!/usr/bin/env node
/**
 * Captures the screens for the Home page "how to use" walkthrough.
 *
 *   node scripts/walkthrough/capture.cjs [--base http://localhost:5173] [--theme light|dark]
 *   python scripts/walkthrough/compose.py
 *
 * Needs the dev server running (`npm run dev`); every backend call is served by
 * the fictional mock in mock-backend.cjs, so no real backend or account is used.
 * For each theme it drives a 1280x760 viewport through the storyboard below and
 * writes, to scripts/walkthrough/.frames/<theme>/:
 *   - one PNG per screen, plus a PNG taken while hovering each click target, and
 *   - manifest.json: per screen its route, caption, cursor start/end points
 *     (the centre of the element clicked next) and whether the move is a click.
 * compose.py turns those into public/how-to-use-<theme>.gif and the still posters.
 * Re-run both whenever the UI changes so the Home page never shows a stale screen.
 */
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const { fixture, mockBackend } = require("./mock-backend.cjs");

const VIEWPORT = { width: 1280, height: 760 };
const TOTAL_STEPS = 9;
const OUT_ROOT = path.join(__dirname, ".frames");
const HEADER_HEIGHT = 64;
/** compose.py draws the step caption over the bottom-left corner; keep graph content above it. */
const CAPTION_CLEARANCE = 64;

function parseArgs(argv) {
  const args = { base: "http://localhost:5173", themes: ["light", "dark"] };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--base") args.base = argv[++index].replace(/\/$/, "");
    else if (argv[index] === "--theme") args.themes = [argv[++index]];
  }
  return args;
}

// ---------------------------------------------------------------------------
// Page helpers
// ---------------------------------------------------------------------------

const sidebarItem = (page, label) =>
  page.getByRole("navigation", { name: "Workspace navigation" }).getByRole("button", { name: new RegExp(`^${label}`) }).first();
const documentsTrigger = (page) =>
  page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Documents" });

// Table impact's single search: a "Tables" trigger opening one input over two result columns.
const TABLE_QUERY = "sales";
const tablesTrigger = (page) => page.getByRole("button", { name: "Tables", exact: true });
const tablesInput = (page) => page.getByPlaceholder("Search semantic tables or database tables...");
const searchGroup = (page, heading) =>
  page.locator("[cmdk-group]").filter({ has: page.locator("[cmdk-group-heading]", { hasText: heading }) });
const searchOption = (page, heading, primary) =>
  searchGroup(page, heading).getByRole("option").filter({ has: page.getByText(primary, { exact: true }) });

// Measure impact's measure picker: a "Measure" trigger opening a searchable list.
const MEASURE_QUERY = "total sales";
// Entries show the measure name first ("Total Sales"), then "Sales · Finance Model · Finance".
const MEASURE_NAME = "Total Sales";
const measureTrigger = (page) => page.getByRole("button", { name: "Measure", exact: true });
const measureInput = (page) => page.getByPlaceholder("Search a measure by name...");
const measureOption = (page) =>
  page.getByRole("option").filter({ has: page.getByText(MEASURE_NAME, { exact: true }) }).filter({ hasText: "Finance Model" });

// Impact pages: the summary tiles row, the graph card, and a report node's +N visuals badge.
const summaryTiles = (page) =>
  page.getByText("Visuals", { exact: true }).first().locator("xpath=ancestor::div[contains(@class,'grid')][1]");
const graphCard = (page) => page.locator(".react-flow").first().locator("xpath=ancestor::div[contains(@class,'rounded-md')][1]");
const graphNode = (page, label) =>
  page.locator(".react-flow__node").filter({ has: page.getByText(label, { exact: true }) });

// The report opened in Explorer earlier in the storyboard; Measure impact expands it into its visuals.
const EXPANDED_REPORT = "Profit and Loss";
const SALES_MODEL_ID = fixture.MODELS.find((item) => item.name === "Sales Model").id;

/*
 * What frameGraph frames in an impact graph. `fit` picks the nodes to fit (and
 * `center`, when given, the ones to centre on); a node is picked when any rule
 * matches: `all`, `focal` (the ringed node), a `labels` entry equal to its label,
 * or an `ids` fragment inside its React Flow id (object ids are namespaced per model).
 */
// Table impact: the chain behind the picked database table SALESDB.MART.FACT_ORDERS (the Sales Model block).
const TABLE_GRAPH = {
  fit: {
    ids: ["db|SALESDB.", SALES_MODEL_ID],
    labels: ["Regional Sales", "Account Health", "Quota Attainment"],
  },
};
// Measure impact before expanding: every rank from the database table down to the reports, centred on
// the measure (the row of reports and impacted measures is wider than the canvas and runs off both sides).
const MEASURE_GRAPH = { fit: { all: true }, axis: "height", center: { focal: true } };
// Measure impact after expanding: the measure's chain from its database table, the report, and its visuals.
const MEASURE_VISUALS_GRAPH = {
  fit: { focal: true, ids: ["visual|"], labels: [EXPANDED_REPORT, "Sales", "Sales[Amount]", "ANALYTICS.FINANCE.FACT_SALES"] },
};

async function centerOf(locator) {
  await locator.waitFor({ state: "visible" });
  const box = await locator.boundingBox();
  if (!box) throw new Error(`No bounding box for ${locator}`);
  return { x: Math.round(box.x + box.width / 2), y: Math.round(box.y + box.height / 2) };
}

/** Real content only: no spinners, skeletons, layout passes or loading banners anywhere on screen. */
async function waitForQuiet(page) {
  await page.waitForFunction(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const busy = [...document.querySelectorAll(".animate-spin, .animate-pulse, [aria-busy='true'], [data-slot='skeleton']")].some(visible);
    const text = document.body.innerText;
    const loadingText = /Loading backend API catalog|Building (the )?(table|measure) inventory|Finding calculation links|Checking the visuals in|Checking reports\.\.\.|Finding the reports connected/i.test(text);
    return !busy && !loadingText;
  }, null, { timeout: 60_000 });
  // Two frames for React to commit, then a beat for hover/entrance transitions.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForTimeout(350);
}

/** The Overview totals roll up with requestAnimationFrame; wait until each shows its settled value. */
async function waitForCountUps(page) {
  await page.waitForFunction(() => {
    const counters = [...document.querySelectorAll("span > span[aria-hidden='true'] + span.sr-only")];
    return counters.length >= 3 && counters.every((settled) => settled.previousElementSibling.textContent === settled.textContent);
  }, null, { timeout: 15_000 });
}

/** Scrolls the window so `locator`'s top sits `gap` px below the sticky header. */
async function scrollToTop(page, locator, gap = 12) {
  await locator.waitFor({ state: "visible" });
  await locator.evaluate((element, offset) => {
    const top = element.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top: Math.max(0, top), behavior: "instant" });
  }, HEADER_HEIGHT + gap);
  await page.waitForTimeout(250);
}

/**
 * The impact graph has finished its layout pass ("Arranging lineage graph" is gone), its
 * fit-view animation has stopped, and the canvas is no longer resizing (the page margin
 * animates while the Power AI panel opens or closes).
 */
async function graphSettled(page) {
  await page.locator(".react-flow__node").first().waitFor();
  await page.getByRole("status", { name: "Arranging lineage graph" }).waitFor({ state: "detached", timeout: 30_000 });
  let last = "";
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const now = await page.locator(".react-flow").first().evaluate((canvas) => {
      const rect = canvas.getBoundingClientRect();
      return `${rect.width}|${canvas.querySelector(".react-flow__viewport")?.style.transform}`;
    });
    if (now === last) return;
    last = now;
    await page.waitForTimeout(120);
  }
}

/** The on-screen part of the graph canvas, the current zoom, and the bounding boxes of the picked nodes. */
function measureGraph(page, spec) {
  return page.evaluate(({ spec, header, clearance }) => {
    const pick = (rule) => (node) => {
      if (!rule) return false;
      const id = node.getAttribute("data-id") ?? "";
      const label = node.querySelector(".font-semibold")?.textContent?.trim() ?? "";
      return Boolean(rule.all
        || (rule.focal && node.querySelector(".ring-2"))
        || rule.ids?.some((fragment) => id.includes(fragment))
        || rule.labels?.includes(label));
    };
    const bounds = (rule) => {
      const rects = [...document.querySelectorAll(".react-flow__node")].filter(pick(rule)).map((node) => node.getBoundingClientRect());
      if (!rects.length) return null;
      return {
        left: Math.min(...rects.map((rect) => rect.left)),
        // The collapse badge overhangs each node's top-right corner.
        top: Math.min(...rects.map((rect) => rect.top)) - 10,
        right: Math.max(...rects.map((rect) => rect.right)) + 10,
        bottom: Math.max(...rects.map((rect) => rect.bottom)),
        count: rects.length,
      };
    };
    const canvas = document.querySelector(".react-flow").getBoundingClientRect();
    const transform = document.querySelector(".react-flow__viewport")?.style.transform ?? "";
    const pad = 12;
    return {
      zoom: Number(/scale\(([^)]+)\)/.exec(transform)?.[1] ?? 1),
      area: {
        left: canvas.left + pad,
        right: canvas.right - pad,
        top: Math.max(canvas.top, header) + pad,
        bottom: Math.min(canvas.bottom, window.innerHeight - clearance) - pad,
      },
      fit: bounds(spec.fit),
      center: bounds(spec.center ?? spec.fit),
    };
  }, { spec, header: HEADER_HEIGHT, clearance: CAPTION_CLEARANCE });
}

/** A point on empty canvas (not a node, edge or control) inside `area`, to start a pan from. */
function emptyCanvasPoint(page, area) {
  return page.evaluate((area) => {
    for (let y = area.top + 8; y < area.bottom - 8; y += 12) {
      for (let x = area.left + 8; x < area.right - 8; x += 12) {
        if (document.elementFromPoint(x, y)?.classList.contains("react-flow__pane")) return { x, y };
      }
    }
    return null;
  }, area);
}

/**
 * Frames part of an impact graph the way a viewer would: a mouse-wheel zoom over
 * the canvas, then a drag on empty canvas, until the picked nodes fill the part of
 * the canvas that is on screen. The graph opens fitted to its whole canvas, which
 * is taller than the window and far too small to read in the walkthrough.
 * `axis: "height"` fits the picked nodes' height only and lets a wide row run off
 * the sides, centred on the `center` nodes. Leaves the pointer at `restoreMouse`.
 */
async function frameGraph(page, spec, restoreMouse) {
  const maxZoom = spec.maxZoom ?? 1;
  await graphSettled(page);
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const { zoom, area, fit, center } = await measureGraph(page, spec);
    if (!fit || !center) throw new Error(`frameGraph: no graph node matches ${JSON.stringify(spec)}`);
    const areaWidth = area.right - area.left;
    const areaHeight = area.bottom - area.top;
    if (areaWidth < 200 || areaHeight < 160) throw new Error(`frameGraph: only ${Math.round(areaWidth)}x${Math.round(areaHeight)} px of the graph canvas is on screen`);
    const fitHeight = areaHeight / ((fit.bottom - fit.top) / zoom);
    const fitWidth = areaWidth / ((fit.right - fit.left) / zoom);
    const target = Math.min(maxZoom, spec.axis === "height" ? fitHeight : Math.min(fitHeight, fitWidth));
    const middle = { x: (area.left + area.right) / 2, y: (area.top + area.bottom) / 2 };
    if (Math.abs(target / zoom - 1) > 0.01) {
      // d3-zoom scales by 2^(-deltaY * 0.002) per pixel-mode wheel event, around the pointer.
      await page.mouse.move(middle.x, middle.y);
      await page.mouse.wheel(0, -500 * Math.log2(target / zoom));
      await page.waitForTimeout(260);
      continue;
    }
    const dx = middle.x - (center.left + center.right) / 2;
    const dy = middle.y - (fit.top + fit.bottom) / 2;
    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) break;
    const from = await emptyCanvasPoint(page, area);
    if (!from) throw new Error("frameGraph: no empty canvas to pan from");
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + dx, from.y + dy, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(200);
  }
  if (restoreMouse) await page.mouse.move(restoreMouse.x, restoreMouse.y);
}

async function assertNoErrorScreens(page, label) {
  const text = await page.locator("body").innerText();
  const bad = [/authentication is required/i, /could not be loaded/i, /unavailable for this identity/i, /Failed to resolve/i, /Unexpected Application Error/i];
  const hit = bad.find((pattern) => pattern.test(text));
  if (hit) throw new Error(`${label}: error state on screen (${hit})`);
  if (await page.locator("vite-error-overlay").count()) throw new Error(`${label}: Vite error overlay is showing`);
}

// ---------------------------------------------------------------------------
// Storyboard
// ---------------------------------------------------------------------------

/**
 * Each screen: `ready` brings it on screen and waits for real content (and may
 * return `{ mouse }` when it moved the pointer, e.g. to follow a control the
 * page scrolled); `moves` are the cursor's trips on that screen, ending in the
 * click that leads to the next screen (a move with `click: false` only hovers).
 * `before` runs at the start of a move and is captured as `baseFile`, so the
 * cursor sets off from the state the previous click produced.
 */
function storyboard(base) {
  return [
    {
      id: "01-power-bi",
      step: 1,
      caption: "Connect Power BI & Fabric",
      hold: 1600,
      async ready(page) {
        await page.goto(`${base}/workspace/power-bi`);
        await page.getByRole("heading", { name: "Connect Power BI and Fabric" }).waitFor({ timeout: 90_000 });
        await page.locator("header").getByText(/online/).first().waitFor();
        // Fictional placeholder IDs, never submitted.
        await page.getByLabel("Microsoft tenant ID").fill("7c1e4f0a-2b3d-4e5f-8a9b-0c1d2e3f4a5b");
        await page.getByLabel("Application client ID").fill("3f9d2c71-6a4b-4c8e-9d0f-1a2b3c4d5e6f");
        await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
      },
      moves: [
        { target: (page) => page.getByRole("button", { name: "Start Microsoft sign-in" }), click: false, holdAfter: 1000 },
        { target: (page) => sidebarItem(page, "Database"), click: true },
      ],
    },
    {
      id: "02-database",
      step: 2,
      caption: "Connect your database (optional)",
      async ready(page) {
        await page.getByRole("heading", { level: 1 }).filter({ hasText: /database/i }).waitFor();
      },
      moves: [{ target: (page) => sidebarItem(page, "Overview"), click: true }],
    },
    {
      id: "03-overview",
      step: 3,
      caption: "See everything your account can access",
      async ready(page) {
        await page.getByRole("heading", { name: "Overview", exact: true }).waitFor();
        await page.getByRole("region", { name: "Reports" }).getByRole("link").first().waitFor();
        await page.getByRole("region", { name: "Semantic models" }).getByRole("link").first().waitFor();
        await waitForCountUps(page);
      },
      moves: [{ target: (page) => page.getByRole("region", { name: "Reports" }).getByRole("link", { name: "Profit and Loss, in Finance" }), click: true }],
    },
    {
      id: "04-explorer",
      step: 4,
      caption: "Open any report in Explorer",
      async ready(page) {
        await page.getByRole("heading", { name: "Explorer", exact: true }).waitFor();
        await page.getByRole("tab", { name: "Report details", exact: true, selected: true }).waitFor();
        await page.getByText("Number of pages", { exact: true }).waitFor();
        await page.locator("main .ag-row").first().waitFor();
        // Open on the selected report and its evidence rather than the page intro.
        await scrollToTop(page, page.getByRole("tablist", { name: "Explorer sections" }), 8);
      },
      moves: [{ target: (page) => sidebarItem(page, "Report lineage"), click: true }],
    },
    {
      id: "05a-report-lineage",
      step: 5,
      caption: "Trace report lineage end to end",
      hold: 1300,
      async ready(page) {
        await page.getByRole("heading", { name: "Report lineage", exact: true }).waitFor();
        await page.getByText("Report ID:").waitFor();
        await page.locator("main .ag-row").first().waitFor();
      },
      moves: [{ target: (page) => page.getByRole("tab", { name: "Visual fields", exact: true }), click: true }],
    },
    {
      id: "05b-report-visuals",
      step: 5,
      caption: "Trace report lineage end to end",
      async ready(page) {
        await page.getByRole("heading", { name: "Visual fields traced to the database" }).waitFor();
        await page.getByText(/^Semantic model: /).waitFor();
        await page.getByText("Fields in visuals", { exact: true }).waitFor();
        await page.locator("main .ag-row").first().waitFor();
        await scrollToTop(page, page.getByRole("tablist", { name: "Report sections" }), 8);
      },
      moves: [{ target: (page) => sidebarItem(page, "Table impact"), click: true }],
    },
    {
      id: "06a-table-search",
      step: 6,
      caption: "Check which reports, models, and measures use a table",
      hold: 1300,
      async ready(page) {
        await page.getByRole("heading", { name: "Table impact", exact: true }).waitFor();
        await page.getByText(/indexed across \d+ workspaces?/).waitFor({ timeout: 60_000 });
        await page.getByText("No tables selected", { exact: true }).waitFor();
      },
      moves: [{ target: (page) => tablesTrigger(page), click: true }],
    },
    {
      id: "06b-table-pick",
      step: 6,
      caption: "Check which reports, models, and measures use a table",
      hold: 1700,
      async ready(page) {
        await tablesInput(page).fill(TABLE_QUERY);
        await searchGroup(page, /^Semantic tables \(\d+\)/).getByRole("option").first().waitFor();
        await searchGroup(page, /^Database tables \(\d+\)/).getByRole("option").first().waitFor();
        // The open list runs past the fold; bring the whole dropdown into view (inventory line on top)
        // and keep the pointer on the trigger it just clicked, the way the page moves under a real hand.
        await scrollToTop(page, page.getByText(/indexed across \d+ workspaces?/).locator(".."), 0);
        const mouse = await centerOf(tablesTrigger(page));
        await page.mouse.move(mouse.x, mouse.y);
        return { mouse };
      },
      moves: [
        { target: (page) => searchOption(page, /^Semantic tables/, "Sales"), click: true },
        {
          async before(page) {
            await searchOption(page, /^Semantic tables/, "Sales").and(page.locator("[data-checked='true']")).waitFor();
          },
          target: (page) => searchOption(page, /^Database tables/, "SALESDB.MART.FACT_ORDERS"),
          click: true,
        },
        {
          async before(page) {
            await page.getByRole("list", { name: "Selected tables" }).getByRole("listitem").nth(1).waitFor();
          },
          target: (page) => page.getByRole("button", { name: "Done", exact: true }),
          click: true,
        },
      ],
    },
    {
      id: "06c-table-results",
      step: 6,
      caption: "Check which reports, models, and measures use a table",
      hold: 3400,
      async ready(page, { mouse }) {
        await tablesInput(page).waitFor({ state: "detached" });
        await page.getByText(/calculation links? found in 2 semantic models/).waitFor();
        await page.getByText(/Checked the visuals in \d+ connected reports?\./).waitFor();
        await page.getByText("With a visual that uses the tables", { exact: true }).waitFor();
        await page.getByRole("heading", { name: /^Impact of \d+ semantic tables$/ }).waitFor();
        await page.locator("main .ag-row").first().waitFor();
        await waitForQuiet(page);
        // The summary tiles on top, the impact graph beneath: the picked database table's chain
        // down to the reports that use it.
        await scrollToTop(page, summaryTiles(page), 8);
        await frameGraph(page, TABLE_GRAPH, mouse);
      },
      moves: [{ target: (page) => sidebarItem(page, "Measure impact"), click: true }],
    },
    {
      id: "07a-measure-search",
      step: 7,
      caption: "Follow a measure to every visual",
      hold: 1400,
      async ready(page) {
        await page.getByRole("heading", { name: "Measure impact", exact: true }).waitFor();
        await page.getByText(/measures indexed across/).waitFor();
        await page.getByText(/Checked the visuals in \d+ connected reports?\./).waitFor();
        await graphSettled(page);
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
      },
      moves: [{ target: (page) => measureTrigger(page), click: true }],
    },
    {
      id: "07b-measure-pick",
      step: 7,
      caption: "Follow a measure to every visual",
      hold: 1400,
      async ready(page) {
        await measureInput(page).fill(MEASURE_QUERY);
        await measureOption(page).waitFor();
      },
      moves: [{ target: (page) => measureOption(page), click: true }],
    },
    {
      id: "07c-measure-results",
      step: 7,
      caption: "Follow a measure to every visual",
      hold: 2600,
      async ready(page, { mouse }) {
        await measureInput(page).waitFor({ state: "detached" });
        await page.getByRole("heading", { name: `${MEASURE_NAME} impact` }).waitFor();
        await page.locator("main .ag-row").first().waitFor();
        await waitForQuiet(page);
        // The summary tiles on top, the graph beneath from the database table down to the reports.
        await scrollToTop(page, summaryTiles(page), 8);
        await frameGraph(page, MEASURE_GRAPH, mouse);
      },
      // Reports open collapsed; the +N badge opens one into the visuals that show the measure.
      moves: [{ target: (page) => graphNode(page, EXPANDED_REPORT).getByRole("button", { name: "Expand descendants" }), click: true }],
    },
    {
      id: "07d-measure-visuals",
      step: 7,
      caption: "Follow a measure to every visual",
      hold: 3000,
      async ready(page, { mouse }) {
        await graphNode(page, EXPANDED_REPORT).getByRole("button", { name: "Collapse descendants" }).waitFor();
        await page.locator(".react-flow__node[data-id^='visual|']").first().waitFor();
        await scrollToTop(page, graphCard(page), 10);
        await frameGraph(page, MEASURE_VISUALS_GRAPH, mouse);
      },
      moves: [{ target: (page) => page.getByRole("button", { name: "Open Power AI" }), click: true }],
    },
    {
      id: "08-power-ai",
      step: 8,
      caption: "Ask Power AI about anything you can see",
      async ready(page) {
        const panel = page.getByRole("complementary", { name: "Power AI" });
        await panel.waitFor();
        await panel.getByText("Suggested questions").waitFor();
        // The docked panel narrows the page; the graph keeps its zoom and simply shows less of itself.
        await graphSettled(page);
      },
      moves: [{
        async before(page) {
          await page.keyboard.press("Escape");
          await page.getByRole("button", { name: "Open Power AI" }).waitFor();
          await graphSettled(page);
        },
        target: (page) => documentsTrigger(page),
        click: true,
      }],
    },
    {
      id: "09-documents",
      step: 9,
      caption: "Setup guide and API reference live under Documents",
      async ready(page) {
        await page.getByRole("menuitem", { name: "Setup guide" }).waitFor();
        await page.getByRole("menuitem", { name: "API reference" }).waitFor();
      },
      moves: [],
    },
  ];
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

async function captureTheme(browser, base, theme) {
  const outDir = path.join(OUT_ROOT, theme);
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });

  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: "reduce" });
  await context.addInitScript((value) => {
    try { window.localStorage.setItem("themePreference", value); } catch { /* storage unavailable */ }
  }, theme);
  // Answer the dev server's HMR socket locally and say nothing, so a file saved elsewhere in the
  // repo (docs, tests) cannot full-reload the page halfway through the storyboard.
  const devHost = new URL(base).host;
  await context.routeWebSocket((url) => url.host === devHost, () => {});
  const page = await context.newPage();

  const problems = [];
  const unhandled = new Set();
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text()}`);
  });
  await mockBackend(page, { onUnhandled: (request) => unhandled.add(request) });

  const shoot = async (file) => {
    await page.screenshot({ path: path.join(outDir, file), animations: "disabled", caret: "hide" });
    return file;
  };

  const shots = [];
  let mouse = null;
  for (const screen of storyboard(base)) {
    const readied = await screen.ready(page, { mouse });
    if (readied?.mouse) mouse = readied.mouse;
    if (!mouse) {
      // The loop ends on the Documents menu, so the first screen's cursor rests there.
      mouse = await centerOf(documentsTrigger(page));
      await page.mouse.move(mouse.x, mouse.y);
    }
    await waitForQuiet(page);
    await assertNoErrorScreens(page, screen.id);

    const pathname = new URL(page.url()).pathname;
    const file = await shoot(`${screen.id}.png`);
    const shot = { id: screen.id, step: screen.step, totalSteps: TOTAL_STEPS, caption: screen.caption, path: pathname, file, hold: screen.hold ?? 2200, cursor: mouse, moves: [] };

    for (const [index, move] of screen.moves.entries()) {
      const record = { from: mouse, to: null, baseFile: null, hoverFile: null, click: move.click, holdAfter: move.holdAfter ?? 0 };
      if (move.before) {
        await move.before(page, { mouse });
        await waitForQuiet(page);
        record.baseFile = await shoot(`${screen.id}-before-${index + 1}.png`);
      }
      const target = move.target(page);
      const to = await centerOf(target);
      await page.mouse.move(to.x, to.y, { steps: 6 });
      await page.waitForTimeout(300); // let hover transitions finish
      record.to = to;
      record.hoverFile = await shoot(`${screen.id}-hover-${index + 1}.png`);
      if (move.click) await page.mouse.click(to.x, to.y);
      mouse = to;
      shot.moves.push(record);
    }
    shots.push(shot);
    console.log(`  [${theme}] ${screen.id} ${pathname}`);
  }

  const manifest = { theme, viewport: VIEWPORT, totalSteps: TOTAL_STEPS, capturedAt: new Date().toISOString(), shots };
  fs.writeFileSync(path.join(outDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await context.close();

  if (unhandled.size) console.log(`  [${theme}] unmocked calls (answered with {}):\n    ${[...unhandled].join("\n    ")}`);
  if (problems.length) {
    console.log(`  [${theme}] browser problems:\n    ${problems.join("\n    ")}`);
    if (problems.some((problem) => problem.startsWith("pageerror"))) throw new Error(`${theme}: uncaught page errors during capture`);
  }
  return manifest;
}

async function main() {
  const { base, themes } = parseArgs(process.argv.slice(2));
  const health = await fetch(base).then((response) => response.ok).catch(() => false);
  if (!health) throw new Error(`Nothing is serving ${base}. Start the dev server with \`npm run dev\` first.`);

  const browser = await chromium.launch();
  try {
    for (const theme of themes) {
      console.log(`Capturing ${theme} theme from ${base}`);
      await captureTheme(browser, base, theme);
    }
  } finally {
    await browser.close();
  }
  console.log(`Frames written to ${path.relative(process.cwd(), OUT_ROOT)}. Next: python scripts/walkthrough/compose.py`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
