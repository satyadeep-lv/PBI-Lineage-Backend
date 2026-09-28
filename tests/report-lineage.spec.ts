import { expect, test, type Page } from "@playwright/test";

// Reading a grid's own export back is the only reliable way to assert on columns
// AG Grid has virtualized out of the DOM.
test.use({ permissions: ["clipboard-read", "clipboard-write"] });

const workspaceId = "11111111-1111-4111-8111-111111111111";
const reportId = "22222222-2222-4222-8222-222222222222";
const modelId = "33333333-3333-4333-8333-333333333333";
const snowflakeTarget = "PBI_LINEAGE_DEMO.MART.FACT_PBI_SALES_STORY";
const snowflakeColumnTable = "ANALYTICS.PUBLIC.SALES";
const snowflakeColumn = "AMOUNT";

/** The five report-scoped views, shared with Explorer, in the order they are offered. */
const sections = [
  ["Page details", "Report page details"],
  ["Source DB lineage", "Source database lineage"],
  ["Semantic objects", "Semantic model objects"],
  ["Semantic - DB objects mappings", "Semantic to database object mappings"],
  ["Report visuals", "Report visual lineage"],
] as const;

test("report lineage offers the explorer report sections for one estate-wide report", async ({ page }) => {
  await mockBackend(page);

  const browserErrors: string[] = [];
  page.on("pageerror", (error) => {
    browserErrors.push(error.message);
    console.log(`Browser error: ${error.message}`);
  });
  page.on("requestfailed", (request) => console.log(`Request failed: ${request.url()} (${request.failure()?.errorText})`));

  await page.goto("/workspace/report-lineage");
  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });

  // Granularity is one report, picked by name from anywhere in the estate.
  await expect(page.getByLabel("Report", { exact: true })).toHaveValue(`${workspaceId}:${reportId}`);
  await expect(page.getByText("Selected report ID:")).toContainText(reportId);
  await expect(page.getByText("Sales Performance", { exact: true }).first()).toBeVisible();

  const tabs = page.getByRole("tab");
  await expect(tabs).toHaveText(sections.map(([label]) => label));

  for (const [tab, heading] of sections) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy table" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "CSV" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Excel" }).first()).toBeVisible();
  }

  // Source DB lineage carries the composite-model hop and offers its tables to a Snowflake trace.
  // The Via column is off-screen at this width and AG Grid keeps off-screen cells
  // out of the DOM entirely, so it is read back through the export instead.
  await page.getByRole("tab", { name: "Source DB lineage", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Source database lineage" })).toBeVisible();
  await page.getByRole("button", { name: "Copy table" }).first().click();
  const exported = await page.evaluate(() => navigator.clipboard.readText());
  expect(exported).toContain("via");
  expect(exported).toContain("Shared / Reference Model / Region");
  expect(exported).toContain("Direct");
  // An unresolved row is still listed rather than hidden.
  expect(exported).toContain("Not resolved");
  await expect(page.getByText("Snowflake object lineage")).toBeVisible();
  await expect(page.getByLabel("Fully qualified table")).toHaveValue("ANALYTICS.PUBLIC.SALES");

  // The mapping grid feeds both the measure definition panel and the column trace.
  await page.getByRole("tab", { name: "Semantic - DB objects mappings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Semantic to database object mappings" })).toBeVisible();
  await expect(page.getByText("Measure definition with Power AI")).toBeVisible();
  await expect(page.getByLabel("Measure", { exact: true })).toBeVisible();
  await expect(page.getByText("Snowflake column lineage")).toBeVisible();
  await expect(page.getByLabel("Database column")).toHaveValue("AMOUNT");

  await page.getByRole("tab", { name: "Report visuals", exact: true }).click();
  await expect(page.getByText("Linked semantic model:")).toContainText("Sales Model");
  await expect(page.getByText("2 rows").first()).toBeVisible();
  await page.getByRole("button", { name: "Copy table" }).first().click();
  const visualExport = await page.evaluate(() => navigator.clipboard.readText());
  expect(visualExport).toContain("sourceColumn\tsourceTable");
  expect(visualExport).toContain("AMOUNT, QUANTITY");
  expect(visualExport).toContain("ANALYTICS.PUBLIC.FACT_SALES, ANALYTICS.PUBLIC.FACT_QUANTITY");

  await page.screenshot({ path: "test-results/report-lineage.png", fullPage: true });
  expect(browserErrors).toEqual([]);
});

test("the removed report lineage tabs are gone", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/workspace/report-lineage");
  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });

  for (const gone of ["Report information", "Database objects", "Visual objects", "Semantic source mapping", "Visual source mapping", "Lineage"]) {
    await expect(page.getByRole("tab", { name: gone, exact: true })).toHaveCount(0);
  }
});

test("Snowflake object trace renders a collapsible upward table lineage after its result table", async ({ page }) => {
  await mockBackend(page);

  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/workspace/report-lineage");
  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Data sources", exact: true }).click();
  await page.getByLabel("Database table", { exact: true }).selectOption(snowflakeTarget);
  await page.getByRole("button", { name: "Trace lineage" }).click();

  // The API's tabular evidence stays first, followed by the table-name-only graph.
  await expect(page.getByRole("columnheader", { name: "Steps away" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Snowflake table lineage" })).toBeVisible();
  const nodes = page.locator(".react-flow__node");
  const edges = page.locator(".react-flow__edge");
  await expect(nodes).toHaveCount(14);
  await expect(edges).toHaveCount(16);
  await expect(page.locator(".react-flow__edge.animated")).toHaveCount(16);

  const targetNode = nodes.filter({ hasText: "FACT_PBI_SALES_STORY" });
  const firstSourceNode = nodes.filter({ hasText: "T_SALES_STORY" });
  await expect(targetNode).toHaveCount(1);
  await expect(firstSourceNode).toHaveCount(1);
  await expect(targetNode).toContainText(snowflakeTarget);
  await expect(targetNode.locator("[title]")).toHaveAttribute("title", snowflakeTarget);
  await expect.poll(async () => {
    const targetBox = await targetNode.boundingBox();
    const sourceBox = await firstSourceNode.boundingBox();
    return Boolean(targetBox && sourceBox && targetBox.y < sourceBox.y);
  }).toBe(true);

  const markerEnd = await page.locator(".react-flow__edge-path").first().getAttribute("marker-end");
  expect(markerEnd).toContain("url(");
  await page.locator(".react-flow").screenshot({ path: "test-results/snowflake-object-lineage-diagram.png" });
  await page.screenshot({ path: "test-results/snowflake-object-lineage.png", fullPage: true });

  // ELK supplies the initial layout; React Flow keeps subsequent manual node positions.
  const beforeDrag = await firstSourceNode.boundingBox();
  expect(beforeDrag).not.toBeNull();
  if (!beforeDrag) throw new Error("Source node has no bounding box");
  const beforeTransform = await firstSourceNode.evaluate((element) => (element as HTMLElement).style.transform);
  await page.mouse.move(beforeDrag.x + beforeDrag.width / 2, beforeDrag.y + beforeDrag.height / 2);
  await page.mouse.down();
  await page.mouse.move(beforeDrag.x + beforeDrag.width / 2 + 80, beforeDrag.y + beforeDrag.height / 2 + 24, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => {
    const afterDrag = await firstSourceNode.boundingBox();
    return Boolean(afterDrag && Math.abs(afterDrag.x - beforeDrag.x) > 40);
  }).toBe(true);

  await page.getByRole("button", { name: "Reset automatic layout" }).click();
  await expect.poll(
    () => firstSourceNode.evaluate((element) => (element as HTMLElement).style.transform),
  ).toBe(beforeTransform);

  // The selected target is the tree root, so collapsing it leaves only that target visible.
  await targetNode.getByRole("button", { name: "Collapse descendants" }).click();
  await expect(nodes).toHaveCount(1);
  await expect(targetNode.getByRole("button", { name: "Expand descendants" })).toBeVisible();

  expect(browserErrors).toEqual([]);
});

test("Snowflake column trace renders a directed animated graph with column names", async ({ page }) => {
  await mockBackend(page);

  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/workspace/report-lineage");
  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Database mapping", exact: true }).click();
  await expect(page.getByLabel("Database table", { exact: true })).toHaveValue(snowflakeColumnTable);
  await expect(page.getByLabel("Database column", { exact: true })).toHaveValue(snowflakeColumn);
  await page.getByRole("button", { name: "Trace column" }).click();

  await expect(page.getByRole("columnheader", { name: "Steps away" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Snowflake column lineage", exact: true })).toBeVisible();
  const targetQualifiedColumn = `${snowflakeColumnTable}.${snowflakeColumn}`;
  // qualified_name already carries the column, so it must not be appended a second time.
  await expect(page.getByRole("cell", { name: targetQualifiedColumn, exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: `${targetQualifiedColumn}.${snowflakeColumn}` })).toHaveCount(0);

  // Four columns joined by three links: the traced column is one of them, never a fifth, unconnected node.
  const nodes = page.locator(".react-flow__node");
  const edges = page.locator(".react-flow__edge");
  await expect(nodes).toHaveCount(4);
  await expect(edges).toHaveCount(3);
  await expect(page.locator(".react-flow__edge.animated")).toHaveCount(3);

  const sourceQualifiedColumn = "STAGE.PUBLIC.CLEAN_SALES.NET_AMOUNT";
  const targetNode = nodes.filter({ has: page.getByTitle(targetQualifiedColumn, { exact: true }) });
  const sourceNode = nodes.filter({ has: page.getByTitle(sourceQualifiedColumn, { exact: true }) });
  await expect(targetNode).toHaveCount(1);
  await expect(sourceNode).toHaveCount(1);
  await expect(targetNode.getByText(snowflakeColumnTable, { exact: true })).toBeVisible();
  await expect(targetNode.getByText(snowflakeColumn, { exact: true })).toBeVisible();
  await expect(sourceNode.getByText("STAGE.PUBLIC.CLEAN_SALES", { exact: true })).toBeVisible();
  await expect(sourceNode.getByText("NET_AMOUNT", { exact: true })).toBeVisible();
  await expect(targetNode.locator("[title]")).toHaveAttribute("title", targetQualifiedColumn);
  await expect.poll(async () => {
    const targetBox = await targetNode.boundingBox();
    const sourceBox = await sourceNode.boundingBox();
    return Boolean(targetBox && sourceBox && targetBox.y < sourceBox.y);
  }).toBe(true);

  const markerEnd = await page.locator(".react-flow__edge-path").first().getAttribute("marker-end");
  expect(markerEnd).toContain("url(");
  await page.locator(".react-flow").screenshot({ path: "test-results/snowflake-column-lineage-diagram.png" });

  await targetNode.getByRole("button", { name: "Collapse descendants" }).click();
  await expect(nodes).toHaveCount(1);
  await expect(targetNode.getByRole("button", { name: "Expand descendants" })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test("report lineage remains contained and usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockBackend(page);
  await page.goto("/workspace/report-lineage");

  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Workspace menu" })).toBeVisible();

  await page.getByRole("tab", { name: "Semantic objects", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Semantic model objects" })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "test-results/report-lineage-mobile.png", fullPage: true });
});

/**
 * One handler for every backend read, so the routes stay in an order-independent
 * switch rather than relying on Playwright's reverse-registration matching.
 */
async function mockBackend(page: Page) {
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/**", (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.includes("/lineage/estate/discover")) return route.fulfill({ json: estateResponse });
    if (url.endsWith("/lineage/snowflake/trace")) {
      const body = route.request().postDataJSON();
      if (body.object_domain === "COLUMN") {
        expect(body).toEqual({
          object_name: snowflakeColumnTable,
          column_name: snowflakeColumn,
          object_domain: "COLUMN",
          direction: "UPSTREAM",
          max_depth: 50,
          max_concurrency: 8,
          max_nodes: 5000,
          max_edges: 10000,
          max_queries: 2000,
          include_process: true,
        });
        return route.fulfill({ json: snowflakeColumnTraceResponse });
      }
      expect(route.request().postDataJSON()).toEqual({
        object_name: snowflakeTarget,
        object_domain: "TABLE",
        direction: "UPSTREAM",
        max_depth: 50,
        max_concurrency: 8,
        max_nodes: 5000,
        max_edges: 10000,
        max_queries: 2000,
        include_process: true,
      });
      return route.fulfill({ json: snowflakeTraceResponse });
    }
    if (url.endsWith("/explorer/report-source-tables")) return route.fulfill({ json: reportSourceTables });
    if (url.endsWith("/explorer/semantic-model-objects")) return route.fulfill({ json: { rows: semanticObjects, count: semanticObjects.length, warnings: [] } });
    if (url.endsWith("/explorer/snapshot")) return route.fulfill({ json: snapshotResponse });
    if (url.endsWith("/explorer/report-visual-source-columns")) {
      expect(route.request().postDataJSON()).toEqual({ workspace_id: workspaceId, report_id: reportId, include_gateway_sources: false });
      return route.fulfill({ json: reportVisualSourceColumns });
    }
    if (url.endsWith("/pages")) return route.fulfill({ json: reportPages });
    if (url.endsWith("/definition/normalized")) return route.fulfill({ json: normalizedReport });
    if (url.endsWith("/metadata")) return route.fulfill({ json: { reconciliation: { matched_count: 5, definition_only_count: 0, xmla_only_count: 0 } } });
    if (url.endsWith(`/reports/${reportId}`)) return route.fulfill({ json: reportDetail });
    return route.fulfill({ json: {} });
  });
}

const reportDetail = { id: reportId, name: "Sales Performance", dataset_id: modelId, report_type: "PowerBIReport", format: "PBIR", is_owned_by_me: true };

const estateResponse = {
  workspaces: [{
    workspace: { id: workspaceId, name: "Finance" },
    reports: [reportDetail],
    semantic_models: [{ id: modelId, name: "Sales Model" }],
    report_bindings: [{ report_id: reportId, semantic_model_id: modelId, status: "matched" }],
  }],
  graph: {
    nodes: [
      { node_id: "report-node", node_type: "report", name: "Sales Performance", workspace_id: workspaceId, report_id: reportId },
      { node_id: "model-node", node_type: "semantic_model", name: "Sales Model", workspace_id: workspaceId, semantic_model_id: modelId },
    ],
    edges: [{ source_id: "report-node", target_id: "model-node" }],
  },
  warnings: [],
  workspace_count: 1,
  report_count: 1,
  semantic_model_count: 1,
};

const reportPages = { pages: [{ name: "overview", display_name: "Overview", order: 0 }, { name: "detail", display_name: "Detail", order: 1 }] };

const context = { workspace_id: workspaceId, workspace_name: "Finance", report_id: reportId, report_name: "Sales Performance", semantic_model_id: modelId };

const semanticObjects = [
  { ...context, semantic_table: "Sales", semantic_object_type: "column", semantic_object_name: "Amount", semantic_data_type: "decimal", semantic_source_column: "AMOUNT", semantic_dax_expression: null },
  { ...context, semantic_table: "Sales", semantic_object_type: "column", semantic_object_name: "Quantity", semantic_data_type: "int64", semantic_source_column: "QUANTITY", semantic_dax_expression: null },
  { ...context, semantic_table: "Sales", semantic_object_type: "calculated_column", semantic_object_name: "Extended", semantic_data_type: "decimal", semantic_source_column: null, semantic_dax_expression: "Sales[Amount] * Sales[Quantity]" },
  { ...context, semantic_table: "Sales", semantic_object_type: "measure", semantic_object_name: "Total Sales", semantic_data_type: null, semantic_source_column: null, semantic_dax_expression: "SUM(Sales[Amount])" },
];

/** A direct table plus one reached through another workspace's model, to exercise the Via column. */
const reportSourceTables = {
  rows: [
    { workspace_name: "Finance", report_name: "Sales Performance", report_id: reportId, semantic_model_id: modelId, source_account: "account.snowflakecomputing.com", source_database: "ANALYTICS", source_schema: "PUBLIC", table_name: "SALES", source_object_type: "table" },
    { workspace_name: "Finance", report_name: "Sales Performance", report_id: reportId, semantic_model_id: modelId, source_account: "account.snowflakecomputing.com", source_database: "PBI_LINEAGE_DEMO", source_schema: "MART", table_name: "FACT_PBI_SALES_STORY", source_object_type: "table" },
    { workspace_name: "Finance", report_name: "Sales Performance", report_id: reportId, semantic_model_id: modelId, source_account: null, source_database: null, source_schema: null, table_name: null, source_object_type: "unknown", via_workspace_name: "Shared", via_semantic_model_name: "Reference Model", via_semantic_table: "Region" },
  ],
  count: 3,
  warnings: [],
};

const snapshotResponse = {
  warnings: [],
  semantic_model_objects: { count: semanticObjects.length, rows: semanticObjects },
  measure_source_lineage: { count: 1, rows: [{ semantic_table: "Sales", semantic_object_name: "Total Sales", source_column_name: "AMOUNT", source_fully_qualified_name: "ANALYTICS.PUBLIC.SALES" }] },
  source_database_lineage: { count: 1, rows: [{ semantic_table: "Sales", source_fully_qualified_name: "ANALYTICS.PUBLIC.SALES" }] },
};

const normalizedReport = { page_count: 2, visual_count: 2, source_part_count: 6, warnings: [] };

const reportVisualSourceColumns = {
  workspace_id: workspaceId,
  workspace_name: "Finance",
  report_id: reportId,
  report_name: "Sales Performance",
  semantic_model_id: modelId,
  semantic_model_name: "Sales Model",
  semantic_model_workspace_id: workspaceId,
  total_field_reference_count: 2,
  resolved_count: 2,
  partial_count: 0,
  unresolved_count: 0,
  rows: [
    { page_name: "Overview", page_id: "overview", visual_id: "total-sales", visual_title: "Total sales", visual_type: "card", field_role: "Values", semantic_table: "Sales", semantic_object_name: "Total Sales", semantic_object_type: "measure", dax_expression: "SUM(Sales[Amount])", source_columns: ["AMOUNT", "QUANTITY"], source_tables: ["ANALYTICS.PUBLIC.FACT_SALES", "ANALYTICS.PUBLIC.FACT_QUANTITY"], via_workspace_name: null, resolution_status: "resolved", resolution_note: null },
    { page_name: "Overview", page_id: "overview", visual_id: "sales-by-quantity", visual_title: "Sales by quantity", visual_type: "columnChart", field_role: "Values", semantic_table: "Sales", semantic_object_name: "Amount", semantic_object_type: "column", dax_expression: null, source_columns: ["AMOUNT"], source_tables: ["ANALYTICS.PUBLIC.FACT_SALES"], via_workspace_name: null, resolution_status: "resolved", resolution_note: null },
  ],
  warnings: [],
};

const snowflakeLineageRows = [
  ["PBI_LINEAGE_DEMO.MART.T_SALES_STORY", snowflakeTarget, "TABLE", 1, "01c74560-0002-1e6e-000f-b02200045992"],
  ["PBI_LINEAGE_DEMO.ANALYTICS.V_SALES_TARGET_STATUS", "PBI_LINEAGE_DEMO.MART.T_SALES_STORY", "TABLE", 2, "01c74560-0002-1cd9-000f-b02200042d4e"],
  ["PBI_LINEAGE_DEMO.ANALYTICS.T_ORDER_BEHAVIOR", "PBI_LINEAGE_DEMO.ANALYTICS.V_SALES_TARGET_STATUS", "VIEW", 3, null],
  ["PBI_LINEAGE_DEMO.RAW.RAW_MONTHLY_TARGETS", "PBI_LINEAGE_DEMO.ANALYTICS.V_SALES_TARGET_STATUS", "VIEW", 3, null],
  ["PBI_LINEAGE_DEMO.CORE.V_ORDER_BEHAVIOR", "PBI_LINEAGE_DEMO.ANALYTICS.T_ORDER_BEHAVIOR", "TABLE", 4, "01c74560-0002-1e6e-000f-b02200045986"],
  ["PBI_LINEAGE_DEMO.RAW.DEMO_FILES", "PBI_LINEAGE_DEMO.RAW.RAW_MONTHLY_TARGETS", "TABLE", 4, "01c7455f-0002-1e6e-000f-b02200045946"],
  ["PBI_LINEAGE_DEMO.CORE.T_ORDER_FINANCIALS", "PBI_LINEAGE_DEMO.CORE.V_ORDER_BEHAVIOR", "VIEW", 5, null],
  ["PBI_LINEAGE_DEMO.CORE.V_ORDER_ENRICHED", "PBI_LINEAGE_DEMO.CORE.T_ORDER_FINANCIALS", "TABLE", 6, "01c74560-0002-1e6e-000f-b02200045982"],
  ["PBI_LINEAGE_DEMO.RAW.RAW_CUSTOMERS", "PBI_LINEAGE_DEMO.CORE.V_ORDER_ENRICHED", "VIEW", 7, null],
  ["PBI_LINEAGE_DEMO.RAW.RAW_PRODUCTS", "PBI_LINEAGE_DEMO.CORE.V_ORDER_ENRICHED", "VIEW", 7, null],
  ["PBI_LINEAGE_DEMO.STAGE.T_ORDER_VALIDATED", "PBI_LINEAGE_DEMO.CORE.V_ORDER_ENRICHED", "VIEW", 7, null],
  ["PBI_LINEAGE_DEMO.RAW.DEMO_FILES", "PBI_LINEAGE_DEMO.RAW.RAW_CUSTOMERS", "TABLE", 8, "01c7455f-0002-1cd9-000f-b02200042d06"],
  ["PBI_LINEAGE_DEMO.RAW.DEMO_FILES", "PBI_LINEAGE_DEMO.RAW.RAW_PRODUCTS", "TABLE", 8, "01c7455f-0002-1cd9-000f-b02200042d0a"],
  ["PBI_LINEAGE_DEMO.STAGE.V_ORDER_VALIDATED", "PBI_LINEAGE_DEMO.STAGE.T_ORDER_VALIDATED", "TABLE", 8, "01c74560-0002-1e6e-000f-b0220004597a"],
  ["PBI_LINEAGE_DEMO.RAW.RAW_ORDER_LINES", "PBI_LINEAGE_DEMO.STAGE.V_ORDER_VALIDATED", "VIEW", 9, null],
  ["PBI_LINEAGE_DEMO.RAW.DEMO_FILES", "PBI_LINEAGE_DEMO.RAW.RAW_ORDER_LINES", "TABLE", 10, "01c7455f-0002-1e6e-000f-b0220004593e"],
] as const;

function snowflakeReference(tableName: string, objectDomain: string, columnName: string | null = null) {
  const [database, schemaName, ...objectName] = tableName.split(".");
  // Like the real deep trace, a column reference's qualified_name already ends in the column.
  const qualifiedName = columnName ? `${tableName}.${columnName}` : tableName;
  return {
    object_id: qualifiedName,
    database,
    schema_name: schemaName,
    object_name: objectName.join("."),
    object_domain: objectDomain,
    qualified_name: qualifiedName,
    column_name: columnName,
    status: null,
  };
}

const snowflakeDependencies = snowflakeLineageRows.map(([source, target, domain, distance, process]) => ({
  source: snowflakeReference(source, domain),
  target: snowflakeReference(target, "TABLE"),
  dependency_type: "GET_LINEAGE",
  distance,
  process: process ? { query_id: process } : null,
}));

const snowflakeObjects = Array.from(new Map(
  snowflakeDependencies.flatMap((dependency) => [dependency.source, dependency.target]).map((reference) => [reference.qualified_name, reference]),
).values());

const snowflakeTraceResponse = {
  account_identifier: "PBI_LINEAGE_DEMO",
  starting_object_name: snowflakeTarget,
  starting_column_name: null,
  object_domain: "TABLE",
  direction: "UPSTREAM",
  max_depth: 50,
  query_count: 16,
  truncated: false,
  snapshot: {
    account_identifier: "PBI_LINEAGE_DEMO",
    objects: snowflakeObjects,
    dependencies: snowflakeDependencies,
    warnings: [],
    object_count: snowflakeObjects.length,
    dependency_count: snowflakeDependencies.length,
  },
  warnings: [],
};

const snowflakeColumnLineageRows = [
  ["STAGE.PUBLIC.CLEAN_SALES", "NET_AMOUNT", snowflakeColumnTable, snowflakeColumn, 1],
  ["RAW.PUBLIC.RAW_SALES", "GROSS_AMOUNT", "STAGE.PUBLIC.CLEAN_SALES", "NET_AMOUNT", 2],
  ["RAW.PUBLIC.RAW_SALES", "DISCOUNT_AMOUNT", "STAGE.PUBLIC.CLEAN_SALES", "NET_AMOUNT", 2],
] as const;

// Snowflake reports a column row's domain as its container's (TABLE), not COLUMN.
const snowflakeColumnDependencies = snowflakeColumnLineageRows.map(([sourceTable, sourceColumn, targetTable, targetColumn, distance]) => ({
  source: snowflakeReference(sourceTable, "TABLE", sourceColumn),
  target: snowflakeReference(targetTable, "TABLE", targetColumn),
  dependency_type: "GET_LINEAGE",
  distance,
  process: null,
}));

const snowflakeColumnObjects = Array.from(new Map(
  snowflakeColumnDependencies
    .flatMap((dependency) => [dependency.source, dependency.target])
    .map((reference) => [reference.qualified_name, reference]),
).values());

const snowflakeColumnTraceResponse = {
  account_identifier: "ANALYTICS",
  starting_object_name: snowflakeColumnTable,
  starting_column_name: snowflakeColumn,
  object_domain: "COLUMN",
  direction: "UPSTREAM",
  max_depth: 50,
  query_count: 3,
  truncated: false,
  snapshot: {
    account_identifier: "ANALYTICS",
    objects: snowflakeColumnObjects,
    dependencies: snowflakeColumnDependencies,
    warnings: [],
    object_count: snowflakeColumnObjects.length,
    dependency_count: snowflakeColumnDependencies.length,
  },
  warnings: [],
};
