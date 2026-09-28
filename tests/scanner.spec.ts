import { expect, test, type Page } from "@playwright/test";

const workspaceId = "11111111-1111-4111-8111-111111111111";
const workspaceId2 = "44444444-4444-4444-8444-444444444444";
const scanId = "9a7937c2-349f-4de3-b559-29a9f45c0daf";

test("scanner page runs a scan and populates every data category across its tabs", async ({ page }) => {
  test.setTimeout(45_000);
  await mockScannerBackend(page);

  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/workspace/scanner");
  await expect(page.getByRole("heading", { name: "Scanner" })).toBeVisible({ timeout: 60_000 });

  const scopeButton = page.getByRole("button", { name: "Workspaces to scan", exact: true });
  await scopeButton.click();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(scopeButton).toHaveText("All 2 workspaces");

  await page.getByRole("button", { name: "Run scan", exact: true }).click();

  // First poll reports "Running"; the fixed 4s poll interval keeps it visible until the next poll.
  await expect(page.getByText("Scanning (Running)...")).toBeVisible();
  await expect(page.getByText("Scanning (Running)...")).not.toBeVisible({ timeout: 10_000 });

  // Workspaces tab (default).
  await expect(page.getByRole("heading", { name: "Workspaces", exact: true })).toBeVisible();
  await expect(page.getByText("Finance", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tags", exact: true })).toBeVisible();

  // Reports & dashboards tab.
  await page.getByRole("tab", { name: "Reports & dashboards" }).click();
  await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible();
  await expect(page.getByText("Sales Performance")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboards", exact: true })).toBeVisible();
  await expect(page.getByText("Executive Overview").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard tiles" })).toBeVisible();
  await expect(page.getByText("Revenue", { exact: true })).toBeVisible();

  // Semantic models tab.
  await page.getByRole("tab", { name: "Semantic models" }).click();
  await expect(page.getByRole("heading", { name: "Semantic models", exact: true })).toBeVisible();
  await expect(page.getByText("Sales Model").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tables", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Columns", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Measures", exact: true })).toBeVisible();
  await expect(page.getByText("Total Sales", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Table sources (M-query)" })).toBeVisible();
  await expect(page.getByText("Snowflake.Databases", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dataset expressions" })).toBeVisible();
  await expect(page.getByText("SourceParam", { exact: true })).toBeVisible();

  // Dependencies tab.
  await page.getByRole("tab", { name: "Dependencies" }).click();
  await expect(page.getByRole("heading", { name: "Dependencies", exact: true })).toBeVisible();
  await expect(page.getByText("Semantic model", { exact: true }).first()).toBeVisible();

  // Datasource instances tab.
  await page.getByRole("tab", { name: "Datasource instances", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Misconfigured datasource instances" })).toBeVisible();
  await expect(page.getByText("ds-2", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Datasource instances", exact: true })).toBeVisible();
  await expect(page.getByText("acct.snowflakecomputing.com", { exact: true })).toBeVisible();

  await expect(page.getByRole("button", { name: "Copy table" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "CSV" }).first()).toBeVisible();

  await page.screenshot({ path: "test-results/scanner.png", fullPage: true });
  expect(browserErrors).toEqual([]);
});

test("explorer's Workspace content tab runs a scan for the current workspace and replaces the placeholders", async ({ page }) => {
  // Wide enough that AG Grid renders every Ownership column instead of virtualizing the last ones away.
  await page.setViewportSize({ width: 1600, height: 900 });
  await mockScannerBackend(page, { immediateSucceed: true });
  await page.route("**/api/v1/workspaces/*/reports", (route) => route.fulfill({ json: { reports: [] } }));
  await page.route("**/api/v1/workspaces/*/semantic-models", (route) => route.fulfill({ json: { semantic_models: [] } }));

  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/workspace/explorer");
  await expect(page.getByRole("heading", { name: "Explorer" })).toBeVisible({ timeout: 60_000 });

  await expect(page.getByText("Run a scan above to see this workspace's dashboards.")).toBeVisible();
  await page.getByRole("button", { name: "Run metadata scan" }).click();

  await expect(page.getByRole("heading", { name: "Dashboards" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Executive Overview")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Apps using this workspace" })).toBeVisible();
  await expect(page.getByText("No report or dashboard in this workspace is in an app.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ownership" })).toBeVisible();
  // The old mixed Owner column is split by kind of owner: a report's editor and creator, a semantic model's configurer.
  for (const header of ["Item type", "Item name", "Last modified by", "Created by", "Configured by"]) {
    await expect(page.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
  }
  await expect(page.locator('[role="gridcell"][col-id="lastModifiedBy"]').filter({ hasText: "sam@contoso.com" })).toHaveCount(1);
  await expect(page.locator('[role="gridcell"][col-id="createdBy"]').filter({ hasText: "alex@contoso.com" })).toHaveCount(1);
  await expect(page.locator('[role="gridcell"][col-id="configuredBy"]').filter({ hasText: "alex@contoso.com" })).toHaveCount(1);

  await page.screenshot({ path: "test-results/explorer-scanner-panel.png", fullPage: true });
  expect(browserErrors).toEqual([]);
});

async function mockScannerBackend(page: Page, options: { immediateSucceed?: boolean } = {}) {
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/workspaces?top=100&skip=0", (route) => route.fulfill({ json: { workspaces: [{ id: workspaceId, name: "Finance" }, { id: workspaceId2, name: "Marketing" }] } }));
  await page.route("**/api/v1/scanner/workspaces/scan", (route) => route.fulfill({ status: 202, json: { scan_id: scanId, created_at: "2026-09-11T00:00:00Z", status: "NotStarted", error: null } }));

  let statusCallCount = 0;
  await page.route(`**/api/v1/scanner/scans/${scanId}/status`, (route) => {
    statusCallCount += 1;
    const status = options.immediateSucceed || statusCallCount > 1 ? "Succeeded" : "Running";
    return route.fulfill({ json: { scan_id: scanId, created_at: "2026-09-11T00:00:00Z", status, error: null } });
  });
  await page.route(`**/api/v1/scanner/scans/${scanId}/result`, (route) => route.fulfill({ json: scanResult }));
}

const scanResult = {
  scan_id: scanId,
  sections: ["datasourceInstances", "misconfiguredDatasourceInstances", "workspaces"],
  summary: {
    workspace_count: 2,
    report_count: 1,
    dashboard_count: 1,
    semantic_model_count: 1,
    dataflow_count: 1,
    datamart_count: 1,
    table_count: 1,
    column_count: 2,
    measure_count: 1,
    relationship_count: 1,
    role_count: 1,
    dataset_expression_count: 1,
    table_source_expression_count: 1,
    datasource_instance_count: 1,
    misconfigured_datasource_instance_count: 1,
  },
  payload: {
    workspaces: [
      {
        id: workspaceId,
        name: "Finance",
        type: "Workspace",
        state: "Active",
        reports: [{ id: "r1", name: "Sales Performance", datasetId: "d1", createdBy: "alex@contoso.com", modifiedBy: "sam@contoso.com" }],
        dashboards: [{ id: "db1", displayName: "Executive Overview", isReadOnly: false, tiles: [{ id: "t1", title: "Revenue" }] }],
        datasets: [{
          id: "d1",
          name: "Sales Model",
          configuredBy: "alex@contoso.com",
          targetStorageMode: "PremiumFiles",
          contentProviderType: "PbixInDirectQueryMode",
          createdDate: "2026-01-01T00:00:00Z",
          tables: [{
            name: "Sales",
            columns: [{ name: "Amount" }, { name: "Quantity" }],
            measures: [{ name: "Total Sales", expression: "SUM(Sales[Amount])" }],
            source: [{ expression: "let\n    Source = Snowflake.Databases(\"acct.snowflakecomputing.com\")\nin\n    Source" }],
          }],
          expressions: [{ name: "SourceParam", description: "Shared parameter", expression: "\"acct.snowflakecomputing.com\" meta [IsParameterQuery=true]" }],
          relationships: [{ name: "Territory", fromTable: "Sales", fromColumn: "RegionId", toTable: "Region", toColumn: "RegionId", crossFilteringBehavior: "OneDirection", isActive: true }],
          roles: [{ name: "Sales Team", modelPermission: "Read", members: [{ memberName: "alex@contoso.com", memberId: "m-1", memberType: "User", identityProvider: "AzureAD" }], tablePermissions: [{ name: "Sales", filterExpression: "[Region] = \"West\"" }] }],
          datasourceUsages: [{ datasourceInstanceId: "ds-1" }],
          misconfiguredDatasourceUsages: [{ datasourceInstanceId: "ds-2" }],
        }],
        dataflows: [{ objectId: "df-1", name: "Azure SQL Ingest", configuredBy: "alex@contoso.com", modifiedBy: "alex@contoso.com", modifiedDateTime: "2026-02-01T00:00:00Z" }],
        datamarts: [{ id: "dm-1", name: "Sales Datamart", type: "Sql", state: "Active", status: "Available", configuredBy: "alex@contoso.com", modifiedBy: "alex@contoso.com", modifiedDateTime: "2026-02-02T00:00:00Z" }],
      },
      { id: workspaceId2, name: "Marketing", type: "Workspace", state: "Active", reports: [], dashboards: [], datasets: [] },
    ],
    datasourceInstances: [{ datasourceId: "ds-1", gatewayId: "gw-1", datasourceType: "Snowflake", connectionDetails: { server: "acct.snowflakecomputing.com" } }],
    misconfiguredDatasourceInstances: [{ datasourceId: "ds-2", gatewayId: "gw-2", datasourceType: "Snowflake" }],
  },
};
