import { expect, test, type Page } from "@playwright/test";

/*
 * A fictional four-workspace estate:
 * - Finance: three reports, two semantic models (two reports share Finance Model).
 * - Marketing: one report bound to its one model.
 * - Operations: one report bound to a model in Shared Data, and no models of its own.
 * - Shared Data: one model and no reports.
 * Totals: 4 workspaces, 5 reports, 4 semantic models.
 */
const finance = { id: "10000000-0000-4000-8000-000000000001", name: "Finance" };
const marketing = { id: "10000000-0000-4000-8000-000000000002", name: "Marketing" };
const operations = { id: "10000000-0000-4000-8000-000000000003", name: "Operations" };
const shared = { id: "10000000-0000-4000-8000-000000000004", name: "Shared Data" };

const financeModel = { id: "30000000-0000-4000-8000-000000000001", name: "Finance Model", target_storage_mode: "Import", is_refreshable: true };
const forecastModel = { id: "30000000-0000-4000-8000-000000000002", name: "Forecast Model", target_storage_mode: "Import", is_refreshable: true };
const campaignModel = { id: "30000000-0000-4000-8000-000000000003", name: "Campaign Model", target_storage_mode: "DirectQuery", is_refreshable: false };
const referenceModel = { id: "30000000-0000-4000-8000-000000000004", name: "Reference Model", target_storage_mode: "Import", is_refreshable: true };

const report = (id: number, name: string, model: { id: string }, extra: Record<string, unknown> = {}) => ({
  id: `20000000-0000-4000-8000-00000000000${id}`,
  name,
  dataset_id: model.id,
  report_type: "PowerBIReport",
  format: "PBIR",
  is_owned_by_me: true,
  ...extra,
});
const budgetTracker = report(1, "Budget Tracker", financeModel);
const revenueSummary = report(2, "Revenue Summary", financeModel);
const varianceAnalysis = report(3, "Variance Analysis", forecastModel);
const campaignResults = report(4, "Campaign Results", campaignModel);
const fleetStatus = report(5, "Fleet Status", referenceModel, { dataset_workspace_id: shared.id });

type FixtureReport = ReturnType<typeof report>;
type FixtureModel = typeof financeModel;

/** Per-workspace inventory, in the order the backend returns it. */
const inventory = new Map<string, { reports: FixtureReport[]; semanticModels: FixtureModel[] }>([
  [finance.id, { reports: [budgetTracker, revenueSummary, varianceAnalysis], semanticModels: [financeModel, forecastModel] }],
  [marketing.id, { reports: [campaignResults], semanticModels: [campaignModel] }],
  [operations.id, { reports: [fleetStatus], semanticModels: [] }],
  [shared.id, { reports: [], semanticModels: [referenceModel] }],
]);
const allReports = [...inventory.values()].flatMap((entry) => entry.reports);
const workspaceName = new Map([finance, marketing, operations, shared].map((workspace) => [workspace.id, workspace.name]));

/** Deliberately unsorted: the page orders workspaces and their items by name. */
const workspaceList = { workspaces: [shared, finance, operations, marketing] };

const estateResponse = {
  workspaces: [operations, shared, marketing, finance].map((workspace) => {
    const { reports, semanticModels } = inventory.get(workspace.id)!;
    return {
      workspace,
      reports,
      semantic_models: semanticModels,
      report_bindings: reports.map((item) => ({ report_id: item.id, semantic_model_id: item.dataset_id, status: "matched" })),
    };
  }),
  graph: { nodes: [], edges: [] },
  warnings: [],
  workspace_count: 4,
  report_count: 5,
  semantic_model_count: 4,
};

const reportPages = { pages: [{ name: "summary", display_name: "Summary", order: 0 }, { name: "detail", display_name: "Detail", order: 1 }] };

type MockOptions = { estateStatus?: number; workspaceListStatus?: number };

/**
 * One handler for every backend read Overview and Explorer make, so no request
 * reaches a real backend. Anything it does not recognise is recorded in
 * `unhandled` (and answered with `{}`) so a test can prove it mocked everything.
 */
async function mockBackend(page: Page, options: MockOptions = {}) {
  const requests: string[] = [];
  const unhandled: string[] = [];
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/**", (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const path = pathname.slice(pathname.indexOf("/api/v1"));
    requests.push(`${request.method()} ${path}`);

    if (path === "/api/v1/health") return route.fulfill({ json: { status: "ok" } });
    if (path === "/api/v1/ai/status") return route.fulfill({ json: { enabled: true, configured: true, streaming_enabled: true } });
    if (path === "/api/v1/workspaces") {
      return options.workspaceListStatus
        ? route.fulfill({ status: options.workspaceListStatus, json: { detail: "Not authenticated" } })
        : route.fulfill({ json: workspaceList });
    }
    if (path === "/api/v1/lineage/estate/discover") {
      return options.estateStatus
        ? route.fulfill({ status: options.estateStatus, json: { detail: "Estate discovery is not permitted for this account." } })
        : route.fulfill({ json: estateResponse });
    }
    if (path === "/api/v1/explorer/semantic-model-objects") {
      const selection = request.postDataJSON()?.reports?.[0] ?? {};
      const selected = allReports.find((item) => item.id === selection.report_id);
      const context = {
        workspace_id: selection.workspace_id,
        workspace_name: workspaceName.get(selection.workspace_id),
        report_id: selected?.id,
        report_name: selected?.name,
        semantic_model_id: selected?.dataset_id,
      };
      const rows = [
        { ...context, semantic_table: "Ledger", semantic_object_type: "column", semantic_object_name: "Amount", semantic_data_type: "decimal", semantic_source_column: "AMOUNT", semantic_dax_expression: null },
        { ...context, semantic_table: "Ledger", semantic_object_type: "measure", semantic_object_name: "Total Amount", semantic_data_type: null, semantic_source_column: null, semantic_dax_expression: "SUM(Ledger[Amount])" },
      ];
      return route.fulfill({ json: { rows, count: rows.length, warnings: [] } });
    }

    const workspaceRead = /^\/api\/v1\/workspaces\/([^/]+)\/(reports|semantic-models)(?:\/([^/]+))?(?:\/(pages|metadata))?$/.exec(path);
    if (workspaceRead) {
      const [, workspaceId, kind, itemId, detail] = workspaceRead;
      const entry = inventory.get(workspaceId);
      if (kind === "reports" && !itemId) return route.fulfill({ json: { reports: entry?.reports ?? [] } });
      if (kind === "semantic-models" && !itemId) return route.fulfill({ json: { semantic_models: entry?.semanticModels ?? [] } });
      if (kind === "reports" && detail === "pages") return route.fulfill({ json: reportPages });
      if (kind === "reports" && !detail) {
        const selected = allReports.find((item) => item.id === itemId);
        if (selected) return route.fulfill({ json: selected });
      }
      if (kind === "semantic-models" && detail === "metadata") {
        return route.fulfill({ json: { reconciliation: { matched_count: 2, definition_only_count: 0, xmla_only_count: 0 } } });
      }
    }

    unhandled.push(`${request.method()} ${path}`);
    return route.fulfill({ json: {} });
  });
  return { requests, unhandled };
}

function collectBrowserErrors(page: Page) {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  return browserErrors;
}

async function openOverview(page: Page) {
  await page.goto("/workspace/overview");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible({ timeout: 60_000 });
}

function regions(page: Page) {
  return {
    workspaces: page.getByRole("region", { name: "Workspaces", exact: true }),
    reports: page.getByRole("region", { name: "Reports", exact: true }),
    semanticModels: page.getByRole("region", { name: "Semantic models", exact: true }),
  };
}

/** A total tile: the nearest block around the tile's label that also holds the settled, screen-reader value. */
function totalTile(page: Page, label: string) {
  return page.locator(
    `xpath=//main//span[normalize-space()="${label}"]/ancestor::div[.//span[contains(concat(" ", normalize-space(@class), " "), " sr-only ")]][1]`,
  );
}

async function expectTotal(page: Page, label: string, value: string) {
  const tile = totalTile(page, label);
  await expect(tile.locator(".sr-only")).toHaveText(value);
  // The count-up animation settles on the same number.
  await expect(tile.locator('span[aria-hidden="true"]')).toHaveText(value);
}

async function expectExplorerUrl(page: Page, params: Record<string, string>) {
  await expect(page).toHaveURL((url) =>
    url.pathname === "/workspace/explorer"
    && Object.entries(params).every(([key, value]) => url.searchParams.get(key) === value)
    && [...url.searchParams.keys()].length === Object.keys(params).length);
  await expect(page.getByRole("heading", { level: 1, name: "Explorer" })).toBeVisible({ timeout: 60_000 });
}

test.describe("Overview on desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("totals and three sections list every workspace, report, and semantic model grouped by workspace", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page);
    await openOverview(page);

    await expectTotal(page, "Workspaces", "4");
    await expectTotal(page, "Reports", "5");
    await expectTotal(page, "Semantic models", "4");
    await expect(totalTile(page, "Workspaces")).toContainText("Workspaces your account can open");
    await expect(totalTile(page, "Reports")).toContainText("Across 4 workspaces");

    const sections = page.getByRole("region", { name: /^(Workspaces|Reports|Semantic models)$/ });
    await expect(sections).toHaveCount(3);
    await expect(sections.nth(0)).toHaveAccessibleName("Workspaces");
    await expect(sections.nth(1)).toHaveAccessibleName("Reports");
    await expect(sections.nth(2)).toHaveAccessibleName("Semantic models");

    const { workspaces, reports, semanticModels } = regions(page);

    // Workspaces: one flat list by name, each with its inventory counts.
    const workspaceLinks = workspaces.getByRole("link");
    await expect(workspaceLinks).toHaveCount(4);
    await expect(workspaceLinks).toHaveText([/^Finance/, /^Marketing/, /^Operations/, /^Shared Data/]);
    await expect(workspaceLinks.nth(0)).toContainText("3 reports · 2 semantic models");
    await expect(workspaceLinks.nth(1)).toContainText("1 report · 1 semantic model");
    await expect(workspaceLinks.nth(2)).toContainText("1 report · 0 semantic models");
    await expect(workspaceLinks.nth(3)).toContainText("0 reports · 1 semantic model");
    await expect(workspaceLinks.nth(2)).toHaveAttribute("href", `/workspace/explorer?workspace=${operations.id}`);

    // Reports: grouped by workspace; Shared Data has none, so it has no group.
    const reportGroups = reports.getByRole("group");
    await expect(reportGroups).toHaveCount(3);
    await expect(reportGroups.nth(0)).toHaveAccessibleName("Finance");
    await expect(reportGroups.nth(1)).toHaveAccessibleName("Marketing");
    await expect(reportGroups.nth(2)).toHaveAccessibleName("Operations");
    await expect(reports.getByRole("group", { name: "Finance" }).getByRole("link")).toHaveText(["Budget Tracker", "Revenue Summary", "Variance Analysis"]);
    await expect(reports.getByRole("group", { name: "Marketing" }).getByRole("link")).toHaveText(["Campaign Results"]);
    await expect(reports.getByRole("group", { name: "Operations" }).getByRole("link")).toHaveText(["Fleet Status"]);
    await expect(reports.getByRole("group", { name: "Shared Data" })).toHaveCount(0);
    await expect(reports.getByRole("link", { name: "Revenue Summary, in Finance", exact: true })).toHaveAttribute(
      "href",
      `/workspace/explorer?workspace=${finance.id}&report=${revenueSummary.id}`,
    );

    // Semantic models: grouped by workspace; Operations has none, so it has no group.
    const modelGroups = semanticModels.getByRole("group");
    await expect(modelGroups).toHaveCount(3);
    await expect(modelGroups.nth(0)).toHaveAccessibleName("Finance");
    await expect(modelGroups.nth(1)).toHaveAccessibleName("Marketing");
    await expect(modelGroups.nth(2)).toHaveAccessibleName("Shared Data");
    await expect(semanticModels.getByRole("group", { name: "Finance" }).getByRole("link")).toHaveText(["Finance Model", "Forecast Model"]);
    await expect(semanticModels.getByRole("group", { name: "Shared Data" }).getByRole("link")).toHaveText(["Reference Model"]);
    await expect(semanticModels.getByRole("group", { name: "Operations" })).toHaveCount(0);
    await expect(semanticModels.getByRole("link", { name: "Forecast Model, in Finance", exact: true })).toHaveAttribute(
      "href",
      `/workspace/explorer?workspace=${finance.id}&model=${forecastModel.id}`,
    );

    // Overview reads only the shared workspace list and estate discovery — never one call per workspace.
    expect(backend.requests.filter((request) => /\/workspaces\/[^/]+\//.test(request))).toEqual([]);
    expect(backend.requests.filter((request) => request.endsWith("/lineage/estate/discover"))).toHaveLength(1);
    expect(backend.unhandled).toEqual([]);

    await page.screenshot({ path: "test-results/overview-desktop.png", fullPage: true });
    expect(browserErrors).toEqual([]);
  });

  test("each section's filter narrows its list", async ({ page }) => {
    await mockBackend(page);
    await openOverview(page);
    const { workspaces, reports, semanticModels } = regions(page);

    const reportFilter = reports.getByRole("searchbox", { name: "Filter reports" });
    await expect(reports.getByRole("link")).toHaveCount(5);
    await reportFilter.fill("revenue");
    await expect(reports.getByRole("link")).toHaveText(["Revenue Summary"]);
    await expect(reports.getByRole("group")).toHaveCount(1);
    await expect(reports.getByText("1 of 5", { exact: true })).toBeVisible();

    // A workspace-name match keeps that workspace's whole group.
    await reportFilter.fill("marketing");
    await expect(reports.getByRole("link")).toHaveText(["Campaign Results"]);

    await reportFilter.fill("no such report");
    await expect(reports.getByRole("link")).toHaveCount(0);
    await expect(reports.getByText(/Nothing matches/)).toContainText("no such report");

    await reportFilter.fill("");
    await expect(reports.getByRole("link")).toHaveCount(5);

    await workspaces.getByRole("searchbox", { name: "Filter workspaces" }).fill("oper");
    await expect(workspaces.getByRole("link")).toHaveText([/^Operations/]);

    await semanticModels.getByRole("searchbox", { name: "Filter semantic models" }).fill("forecast");
    await expect(semanticModels.getByRole("link")).toHaveText(["Forecast Model"]);

    // Filters are independent of one another.
    await expect(reports.getByRole("link")).toHaveCount(5);
  });

  test("a report link opens Explorer with that report selected on the Report details tab", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page);
    await openOverview(page);

    await regions(page).reports.getByRole("link", { name: "Revenue Summary, in Finance", exact: true }).click();
    await expectExplorerUrl(page, { workspace: finance.id, report: revenueSummary.id });

    await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(finance.id);
    await expect(page.getByLabel("Report", { exact: true })).toHaveValue(revenueSummary.id);
    await expect(page.getByText("Report ID:")).toContainText(revenueSummary.id);
    await expect(page.getByRole("tab", { name: "Report details", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Workspace content", exact: true })).toHaveAttribute("aria-selected", "false");
    await expect(page.getByRole("tab", { name: "Pages", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { name: "Report pages" })).toBeVisible();
    await expect(page.getByText("Summary", { exact: true })).toBeVisible();

    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("a semantic model link opens Explorer on the Semantic objects section of a report connected to it", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page);
    await openOverview(page);

    await regions(page).semanticModels.getByRole("link", { name: "Forecast Model, in Finance", exact: true }).click();
    await expectExplorerUrl(page, { workspace: finance.id, model: forecastModel.id });

    await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(finance.id);
    // Variance Analysis is the only Finance report bound to Forecast Model (and not the workspace's first report).
    await expect(page.getByLabel("Report", { exact: true })).toHaveValue(varianceAnalysis.id);
    await expect(page.getByRole("tab", { name: "Report details", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Semantic objects", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { name: "Semantic model objects" })).toBeVisible();
    await expect(page.getByText("Total Amount", { exact: true })).toBeVisible();

    // A model no report in its workspace is connected to opens Workspace content for that workspace instead.
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
    await regions(page).semanticModels.getByRole("link", { name: "Reference Model, in Shared Data", exact: true }).click();
    await expectExplorerUrl(page, { workspace: shared.id, model: referenceModel.id });
    await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(shared.id);
    await expect(page.getByRole("tab", { name: "Workspace content", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Report details", exact: true })).toHaveAttribute("aria-selected", "false");

    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("a workspace link opens Explorer on that workspace", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page);
    await openOverview(page);

    await regions(page).workspaces.getByRole("link", { name: /^Operations/ }).click();
    await expectExplorerUrl(page, { workspace: operations.id });

    await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(operations.id);
    await expect(page.getByText("Workspace ID:")).toContainText(operations.id);
    await expect(page.getByRole("tab", { name: "Workspace content", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Fleet Status", { exact: true }).first()).toBeVisible();

    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("when estate discovery is refused, workspaces still list and reports and models say they could not be loaded", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await mockBackend(page, { estateStatus: 403 });
    await openOverview(page);
    const { workspaces, reports, semanticModels } = regions(page);

    await expect(reports.getByText("Reports could not be loaded")).toBeVisible();
    await expect(semanticModels.getByText("Semantic models could not be loaded")).toBeVisible();
    await expect(reports.getByRole("link")).toHaveCount(0);
    await expect(semanticModels.getByRole("link")).toHaveCount(0);

    await expect(workspaces.getByRole("link")).toHaveText(["Finance", "Marketing", "Operations", "Shared Data"]);
    await expectTotal(page, "Workspaces", "4");
    // Report and model totals are unavailable rather than a misleading zero.
    await expect(page.locator("main").getByTitle("Unavailable")).toHaveCount(2);
    await expect(page.locator("main").getByTitle("Unavailable").first()).toHaveText("—");
    expect(browserErrors).toEqual([]);
  });

  test("when the workspace list fails, Overview asks for Power BI authentication", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page, { workspaceListStatus: 401 });
    await page.goto("/workspace/overview");

    await expect(page.getByRole("heading", { name: "Power BI authentication is required" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("then return to Overview.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Power BI setup" })).toHaveAttribute("href", "/workspace/power-bi");
    await expect(page.getByRole("region", { name: "Reports", exact: true })).toHaveCount(0);
    // Estate discovery waits for a successful workspace list, so it is never requested.
    expect(backend.requests.filter((request) => request.endsWith("/lineage/estate/discover"))).toEqual([]);
    expect(browserErrors).toEqual([]);
  });
});

test("Overview stacks its sections and stays contained on mobile", async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockBackend(page);
  await openOverview(page);
  await expect(page.getByRole("button", { name: "Workspace menu" })).toBeVisible();

  const { workspaces, reports, semanticModels } = regions(page);
  await expect(reports.getByRole("link")).toHaveCount(5);
  await expect(semanticModels.getByRole("link")).toHaveCount(4);

  const boxes: Array<{ x: number; y: number; width: number; height: number }> = [];
  for (const region of [workspaces, reports, semanticModels]) {
    const box = await region.boundingBox();
    expect(box).not.toBeNull();
    boxes.push(box!);
  }
  // One column: same left edge and width, each section below the one before it.
  for (let index = 1; index < boxes.length; index += 1) {
    expect(Math.abs(boxes[index].x - boxes[0].x)).toBeLessThanOrEqual(1);
    expect(Math.abs(boxes[index].width - boxes[0].width)).toBeLessThanOrEqual(1);
    expect(boxes[index].y).toBeGreaterThanOrEqual(boxes[index - 1].y + boxes[index - 1].height);
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "test-results/overview-mobile.png", fullPage: true });

  // Links still open Explorer from the stacked layout.
  await reports.getByRole("link", { name: "Campaign Results, in Marketing", exact: true }).scrollIntoViewIfNeeded();
  await reports.getByRole("link", { name: "Campaign Results, in Marketing", exact: true }).click();
  await expectExplorerUrl(page, { workspace: marketing.id, report: campaignResults.id });
  await expect(page.getByLabel("Report", { exact: true })).toHaveValue(campaignResults.id);
  expect(browserErrors).toEqual([]);
});
