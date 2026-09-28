import { expect, test, type Page } from "@playwright/test";

/*
 * Explorer › Report details › Database mapping ("Semantic objects mapped to
 * database columns"): every semantic object of the report's semantic model next
 * to the database columns and database tables it reads. This replaces the old
 * "Physical column lineage" spec, which tested a tab that was never built.
 *
 * Fictional fixture: workspace Finance, report Payments Overview, bound to
 * Payments Model. FACT_PAYMENTS and DIM_CUSTOMER load from Snowflake tables;
 * Measures is a measure table with no database source at all.
 */

// The mapping grid has 13 columns; a wide viewport keeps the leading ones rendered by AG Grid.
test.use({ viewport: { width: 1920, height: 1080 } });

const workspaceId = "11111111-1111-4111-8111-111111111111";
const reportId = "22222222-2222-4222-8222-222222222222";
const semanticModelId = "33333333-3333-4333-8333-333333333333";
const explorerUrl = `/workspace/explorer?workspace=${workspaceId}&report=${reportId}`;

/** Docs/07-column-naming-standard.md, Database mapping: names first, then every ID. */
const mappingHeaders = ["Semantic table", "Object name", "Object type", "Data type", "Database columns", "Database tables", "DAX expression", "Workspace name", "Report name", "Semantic model", "Workspace ID", "Report ID", "Semantic model ID"];
const ids = [workspaceId, reportId, semanticModelId];

test("the Database mapping section maps each semantic object to the database columns and tables it reads", async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await recordClipboard(page);
  const backend = await mockBackend(page);

  await page.goto(explorerUrl);
  await expect(page.getByRole("heading", { level: 1, name: "Explorer" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("tab", { name: "Report details", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Report pages" })).toBeVisible();

  // The snapshot is the expensive call behind this section: it must not fire until the section is opened.
  expect(backend.snapshotBodies).toEqual([]);
  await page.getByRole("tab", { name: "Database mapping", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Semantic objects mapped to database columns" })).toBeVisible();
  await expect.poll(() => backend.snapshotBodies.length).toBe(1);
  // Gateway lookups cost real gateway-admin calls, so they are off unless explicitly asked for.
  expect(backend.snapshotBodies[0]).toMatchObject({
    reports: [{ workspace_id: workspaceId, report_id: reportId }],
    include_gateway_sources: false,
    include_cross_model_matching: false,
    resolve_cross_workspace_sources: true,
  });

  // Backend warnings are shown as they came.
  await expect(page.getByText("Partition query could not be parsed.", { exact: true })).toBeVisible();

  // On-screen headers are the standard names (the leading ones; AG Grid leaves off-screen columns out of the DOM).
  for (const header of mappingHeaders.slice(0, 6)) {
    await expect(page.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
  }
  const grid = page.getByRole("grid");
  await expect(grid.locator('[role="gridcell"][col-id="objectName"]')).toHaveText(["PAYMENT_AMOUNT", "Total Payment", "Customer Tier", "Payment Count"]);
  await expect(grid.locator('[role="gridcell"][col-id="objectType"]')).toHaveText(["Column", "Measure", "Calculated column", "Measure"]);

  // Copy table carries every column, headed exactly as on screen. A column maps through the database column it
  // loads from; a measure or calculated column through the columns its DAX reads. An object with no database
  // match is kept and says "Not found"; a missing value says "Not available"; a column has no DAX ("Not applicable").
  expect(await copyTable(page)).toBe(tsv([
    mappingHeaders,
    ["FACT_PAYMENTS", "PAYMENT_AMOUNT", "Column", "decimal", "PAYMENT_AMOUNT", "SALES_ANALYTICS.WAREHOUSE.FACT_PAYMENTS", "Not applicable", "Finance", "Payments Overview", "Payments Model", ...ids],
    ["FACT_PAYMENTS", "Total Payment", "Measure", "Not available", "PAYMENT_AMOUNT", "SALES_ANALYTICS.WAREHOUSE.FACT_PAYMENTS", "SUM(FACT_PAYMENTS[PAYMENT_AMOUNT])", "Finance", "Payments Overview", "Payments Model", ...ids],
    ["DIM_CUSTOMER", "Customer Tier", "Calculated column", "string", "REVENUE", "SALES_ANALYTICS.WAREHOUSE.DIM_CUSTOMER", "IF(DIM_CUSTOMER[REVENUE] > 1000, \"Gold\", \"Silver\")", "Finance", "Payments Overview", "Payments Model", ...ids],
    ["Measures", "Payment Count", "Measure", "Not available", "Not found", "Not found", "COUNTROWS(FACT_PAYMENTS)", "Finance", "Payments Overview", "Payments Model", ...ids],
  ]));

  // Downloads use the same headers and are named report-<report>-database-mapping.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV", exact: true }).first().click();
  expect((await download).suggestedFilename()).toBe("report-payments-overview-database-mapping.csv");

  // The mapping feeds the panels beneath it: the measure definition picker and the Snowflake column trace.
  await expect(page.getByText("Measure definition with Power AI")).toBeVisible();
  await expect(page.getByText("Snowflake column lineage")).toBeVisible();
  await expect(page.getByLabel("Database table", { exact: true })).toHaveValue("SALES_ANALYTICS.WAREHOUSE.DIM_CUSTOMER");
  await expect(page.getByLabel("Database column", { exact: true })).toHaveValue("REVENUE");

  // Opting in to gateway sources re-reads the snapshot with the flag set; nothing else turns it on.
  await page.getByLabel("Include gateway sources").check();
  await expect.poll(() => backend.snapshotBodies.length).toBe(2);
  expect(backend.snapshotBodies[1]).toMatchObject({ include_gateway_sources: true });

  await page.screenshot({ path: "test-results/database-mapping.png", fullPage: true });
  expect(backend.unhandled).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("a failed mapping request says why instead of blanking the section", async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await mockBackend(page, { snapshotStatus: 503 });

  await page.goto(explorerUrl);
  await expect(page.getByRole("heading", { level: 1, name: "Explorer" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Database mapping", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Semantic objects mapped to database columns" })).toBeVisible();
  await expect(page.getByText("The Fabric capacity behind this semantic model is paused.")).toBeVisible();
  await expect(page.getByRole("grid")).toHaveCount(0);

  // The other sections still work.
  await page.getByRole("tab", { name: "Pages", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Report pages" })).toBeVisible();
  await expect(page.getByText("Summary", { exact: true })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

function collectBrowserErrors(page: Page) {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  return browserErrors;
}

function tsv(rows: string[][]) {
  return rows.map((row) => row.join("\t")).join("\n");
}

async function copyTable(page: Page) {
  const before = await copiedCount(page);
  await page.getByRole("button", { name: "Copy table", exact: true }).first().click();
  await expect.poll(() => copiedCount(page)).toBe(before + 1);
  return page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1));
}

/** Records what the page hands to `navigator.clipboard.writeText`; the OS clipboard is shared by parallel workers. */
async function recordClipboard(page: Page) {
  await page.addInitScript(() => {
    const copied: string[] = [];
    (window as unknown as { __copied: string[] }).__copied = copied;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => { copied.push(text); } },
    });
  });
}

function copiedCount(page: Page) {
  return page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.length);
}

/**
 * One handler for every backend read Explorer makes on the way to Database
 * mapping. Anything it does not recognise is recorded in `unhandled`.
 */
async function mockBackend(page: Page, options: { snapshotStatus?: number } = {}) {
  const snapshotBodies: Array<Record<string, unknown>> = [];
  const unhandled: string[] = [];
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/**", (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const path = pathname.slice(pathname.indexOf("/api/v1"));

    if (path === "/api/v1/health") return route.fulfill({ json: { status: "ok" } });
    if (path === "/api/v1/ai/status") return route.fulfill({ json: { enabled: true, configured: true, streaming_enabled: true } });
    if (path === "/api/v1/workspaces") return route.fulfill({ json: { workspaces: [{ id: workspaceId, name: "Finance" }] } });
    if (path === `/api/v1/workspaces/${workspaceId}/reports`) return route.fulfill({ json: { reports: [paymentsOverview] } });
    if (path === `/api/v1/workspaces/${workspaceId}/semantic-models`) return route.fulfill({ json: { semantic_models: [paymentsModel] } });
    if (path === `/api/v1/workspaces/${workspaceId}/reports/${reportId}`) return route.fulfill({ json: paymentsOverview });
    if (path === `/api/v1/workspaces/${workspaceId}/reports/${reportId}/pages`) {
      return route.fulfill({ json: { pages: [{ name: "summary", display_name: "Summary", order: 0 }] } });
    }
    if (path === "/api/v1/explorer/snapshot") {
      snapshotBodies.push(request.postDataJSON());
      return options.snapshotStatus
        ? route.fulfill({ status: options.snapshotStatus, json: { detail: "The Fabric capacity behind this semantic model is paused." } })
        : route.fulfill({ json: snapshotResponse });
    }

    unhandled.push(`${request.method()} ${path}`);
    return route.fulfill({ json: {} });
  });
  return { snapshotBodies, unhandled };
}

const paymentsModel = { id: semanticModelId, name: "Payments Model", target_storage_mode: "Import", is_refreshable: true };
const paymentsOverview = {
  id: reportId,
  name: "Payments Overview",
  dataset_id: semanticModelId,
  report_type: "PowerBIReport",
  format: "PBIR",
  is_owned_by_me: true,
};

const context = { workspace_id: workspaceId, workspace_name: "Finance", report_id: reportId, report_name: "Payments Overview", semantic_model_id: semanticModelId };

const snapshotResponse = {
  warnings: [{ code: "partition_query_unparsed", message: "Partition query could not be parsed." }],
  semantic_model_objects: {
    count: 4,
    rows: [
      { ...context, semantic_table: "FACT_PAYMENTS", semantic_object_type: "column", semantic_object_name: "PAYMENT_AMOUNT", semantic_data_type: "decimal", semantic_source_column: "PAYMENT_AMOUNT", semantic_dax_expression: null },
      { ...context, semantic_table: "FACT_PAYMENTS", semantic_object_type: "measure", semantic_object_name: "Total Payment", semantic_data_type: null, semantic_source_column: null, semantic_dax_expression: "SUM(FACT_PAYMENTS[PAYMENT_AMOUNT])" },
      { ...context, semantic_table: "DIM_CUSTOMER", semantic_object_type: "calculated_column", semantic_object_name: "Customer Tier", semantic_data_type: "string", semantic_source_column: null, semantic_dax_expression: "IF(DIM_CUSTOMER[REVENUE] > 1000, \"Gold\", \"Silver\")" },
      { ...context, semantic_table: "Measures", semantic_object_type: "measure", semantic_object_name: "Payment Count", semantic_data_type: null, semantic_source_column: null, semantic_dax_expression: "COUNTROWS(FACT_PAYMENTS)" },
    ],
  },
  // The database columns each calculation's DAX reads, as the backend traced them.
  measure_source_lineage: {
    count: 2,
    rows: [
      { semantic_table: "FACT_PAYMENTS", semantic_object_name: "Total Payment", source_column_name: "PAYMENT_AMOUNT", source_fully_qualified_name: "SALES_ANALYTICS.WAREHOUSE.FACT_PAYMENTS" },
      { semantic_table: "DIM_CUSTOMER", semantic_object_name: "Customer Tier", source_column_name: "REVENUE", source_fully_qualified_name: "SALES_ANALYTICS.WAREHOUSE.DIM_CUSTOMER" },
    ],
  },
  // The database table behind each semantic table; the Measures table has none.
  source_database_lineage: {
    count: 2,
    rows: [
      { semantic_table: "FACT_PAYMENTS", source_fully_qualified_name: "SALES_ANALYTICS.WAREHOUSE.FACT_PAYMENTS" },
      { semantic_table: "DIM_CUSTOMER", source_fully_qualified_name: "SALES_ANALYTICS.WAREHOUSE.DIM_CUSTOMER" },
    ],
  },
};
