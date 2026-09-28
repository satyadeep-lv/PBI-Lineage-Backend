import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

/*
 * A fictional two-workspace estate:
 * - Finance holds Sales Model, whose tables are Sales (ANALYTICS.PUBLIC.SALES),
 *   Customers (ANALYTICS.PUBLIC.CUSTOMERS, with a calculated Value Band column
 *   that reads [Total Sales]) and Metrics (a measure table with no database
 *   source; Sales per Customer reads [Total Sales] and [Customer Count]).
 *   Sales Performance, Customer Insights and Executive Summary are connected to it.
 *   Executive Summary has no visual evidence at all — only measure-source-lineage
 *   rows, which list model measures whether or not a visual shows them — so it
 *   must never count as using anything.
 * - Marketing holds Marketing Model, whose tables are Campaigns
 *   (ANALYTICS.PUBLIC.CAMPAIGNS) and Attributed Sales — also sourced from
 *   ANALYTICS.PUBLIC.SALES, so that database table sits behind two semantic
 *   tables in two models. Campaign Tracker is connected to it.
 * Inventory: 5 semantic tables, 3 database tables, 7 measures.
 *
 * Headers, values, and file names follow Docs/07-column-naming-standard.md:
 * copies and exports use the on-screen headers, context columns come first
 * (left out when the grid already has a column of that name), and every
 * "… ID" column comes last.
 */
const workspaceId = "11111111-1111-4111-8111-111111111111";
const workspaceId2 = "44444444-4444-4444-8444-444444444444";
const reportId = "22222222-2222-4222-8222-222222222222";
const reportId2 = "66666666-6666-4666-8666-666666666666";
const reportId3 = "77777777-7777-4777-8777-777777777777";
const reportId4 = "88888888-8888-4888-8888-888888888888";
const modelId = "33333333-3333-4333-8333-333333333333";
const modelId2 = "55555555-5555-4555-8555-555555555555";
const salesModelKey = `${workspaceId}:${modelId}`;

const tablesPlaceholder = "Search semantic tables or database tables...";
const semanticGroupName = /^Semantic tables \(\d+\)$/;
const databaseGroupName = /^Database tables \(\d+\)$/;
const reportListFailedBand = "The list of reports could not be loaded for your account. Report and visual usage cannot be shown; the dependency results remain accurate.";
const reportListFailedGrid = "Report usage is not available because the list of reports could not be loaded.";

const tableImpactHeaders = {
  reports: ["Report name", "Workspace name", "Semantic model", "Selected tables", "How it is used", "Number of pages", "Number of visuals", "Objects used", "Report ID", "Semantic model ID"],
  visuals: ["Visual name", "Visual type", "Page name", "Report name", "Workspace name", "How it is used", "Objects used", "Selected tables", "Report ID", "Visual ID"],
  models: ["Semantic model", "Workspace name", "Selected tables", "Database tables", "Number of impacted measures", "Number of reports using it", "Number of connected reports", "Semantic model ID", "Workspace ID"],
  measures: ["Measure name", "Semantic table", "Semantic model", "Workspace name", "Selected tables", "Dependency", "Steps away", "Referenced as", "Number of reports", "Number of visuals", "Semantic model ID"],
};

test.describe("table impact", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("one search lists semantic and database tables separately, and a multi-table selection shows every report, visual, semantic model, and measure using them", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await recordClipboard(page);
    const backend = await mockBackend(page);

    await page.goto("/workspace/table-impact");
    await expect(page.getByRole("heading", { level: 1, name: "Table impact" })).toBeVisible({ timeout: 60_000 });
    const main = page.locator("main");

    // The inventory spans every workspace: no scope, column, or direction controls — just one search.
    await expect(page.getByText("5 semantic tables and 3 database tables indexed across 2 workspaces.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Workspace scope" })).toHaveCount(0);
    await expect(page.getByLabel("Column", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Direction", { exact: true })).toHaveCount(0);
    await expect(main.locator("select")).toHaveCount(0);
    await expect(main.locator("input")).toHaveCount(0);
    await expect(page.getByText("No tables selected", { exact: true })).toBeVisible();

    const tablesButton = page.getByRole("button", { name: "Tables", exact: true });
    await expect(tablesButton).toHaveCount(1);
    await expect(tablesButton).toContainText(tablesPlaceholder);
    await tablesButton.click();
    await expect(tablesButton).toHaveAttribute("aria-expanded", "true");

    const search = page.getByPlaceholder(tablesPlaceholder);
    await expect(search).toBeFocused();
    await expect(main.locator("input")).toHaveCount(1);

    // Two separated groups, side by side, each with its own count.
    const semanticGroup = page.getByRole("group", { name: semanticGroupName });
    const databaseGroup = page.getByRole("group", { name: databaseGroupName });
    await expect(page.getByText("Semantic tables (5)", { exact: true })).toBeVisible();
    await expect(page.getByText("Database tables (3)", { exact: true })).toBeVisible();
    await expect(semanticGroup.getByRole("option")).toHaveText([/^Attributed Sales/, /^Campaigns/, /^Customers/, /^Metrics/, /^Sales/]);
    await expect(databaseGroup.getByRole("option")).toHaveText([/^ANALYTICS\.PUBLIC\.CAMPAIGNS/, /^ANALYTICS\.PUBLIC\.CUSTOMERS/, /^ANALYTICS\.PUBLIC\.SALES/]);
    await expect(option(semanticGroup, "Customers")).toContainText("Sales Model · Finance · from ANALYTICS.PUBLIC.CUSTOMERS");
    await expect(option(semanticGroup, "Metrics")).toContainText("Sales Model · Finance");
    await expect(option(semanticGroup, "Metrics")).not.toContainText("from");
    // Sources differing only in case are one database table.
    await expect(option(databaseGroup, "ANALYTICS.PUBLIC.SALES")).toContainText("Behind 2 semantic tables: Sales (Sales Model), Attributed Sales (Marketing Model)");
    const semanticBox = await semanticGroup.boundingBox();
    const databaseBox = await databaseGroup.boundingBox();
    expect(semanticBox && databaseBox).toBeTruthy();
    expect(databaseBox!.x).toBeGreaterThanOrEqual(semanticBox!.x + semanticBox!.width - 1);
    expect(Math.abs(databaseBox!.y - semanticBox!.y)).toBeLessThanOrEqual(2);

    // Typing filters both groups at once; every whitespace-separated term must match.
    await search.fill("campaign");
    await expect(page.getByText("Semantic tables (1)", { exact: true })).toBeVisible();
    await expect(page.getByText("Database tables (1)", { exact: true })).toBeVisible();
    await expect(semanticGroup.getByRole("option")).toHaveText([/^Campaigns/]);
    await expect(databaseGroup.getByRole("option")).toHaveText([/^ANALYTICS\.PUBLIC\.CAMPAIGNS/]);

    await search.fill("sales marketing");
    await expect(semanticGroup.getByRole("option")).toHaveText([/^Attributed Sales/]);
    await expect(databaseGroup.getByRole("option")).toHaveText([/^ANALYTICS\.PUBLIC\.SALES/]);

    // Results are ranked by relevance, not only alphabetically: the exact name comes first, then a
    // name segment match, then entries that matched only on their model, workspace, or source.
    await search.fill("sales");
    await expect(page.getByText("Semantic tables (4)", { exact: true })).toBeVisible();
    await expect(semanticGroup.getByRole("option")).toHaveText([/^Sales/, /^Attributed Sales/, /^Customers/, /^Metrics/]);
    await expect(databaseGroup.getByRole("option")).toHaveText([/^ANALYTICS\.PUBLIC\.SALES/, /^ANALYTICS\.PUBLIC\.CUSTOMERS/]);
    await search.fill("customers");
    await expect(semanticGroup.getByRole("option").first()).toContainText("Customers");
    await expect(databaseGroup.getByRole("option").first()).toContainText("ANALYTICS.PUBLIC.CUSTOMERS");

    await search.fill("no such table");
    await expect(page.getByText("Semantic tables (0)", { exact: true })).toBeVisible();
    await expect(page.getByText("Database tables (0)", { exact: true })).toBeVisible();
    await expect(page.getByText("No matches.", { exact: true })).toHaveCount(2);

    // Multi-select across both groups: a semantic table, then a database table.
    await search.fill("customers");
    await option(semanticGroup, "Customers").click();
    await expect(option(semanticGroup, "Customers")).toHaveAttribute("data-checked", "true");
    await search.fill("public.sales");
    await expect(semanticGroup.getByRole("option")).toHaveText([/^Attributed Sales/, /^Sales/]);
    await option(databaseGroup, "ANALYTICS.PUBLIC.SALES").click();
    await expect(option(databaseGroup, "ANALYTICS.PUBLIC.SALES")).toHaveAttribute("data-checked", "true");
    await expect(tablesButton).toContainText("2 selected");

    // A semantic chip names its model too ("Table (Model)"), so same-named tables stay distinct.
    const chips = page.getByRole("list", { name: "Selected tables" }).getByRole("listitem");
    await expect(chips).toHaveText([/^Semantic\s*Customers \(Sales Model\)$/, /^Database\s*ANALYTICS\.PUBLIC\.SALES$/]);
    await expect(page.getByRole("button", { name: "Remove Customers (Sales Model)", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Remove ANALYTICS.PUBLIC.SALES", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(search).toHaveCount(0);
    await expect(tablesButton).toHaveAttribute("aria-expanded", "false");

    // The database table expands to both semantic tables behind it, in both models.
    await expect(page.getByText("10 calculation links found in 2 semantic models", { exact: true })).toBeVisible();
    await expect(page.getByText("Checked the visuals in 4 connected reports.", { exact: true })).toBeVisible();
    await expectTiles(page, { Reports: "3", Visuals: "5", "Semantic models": "2", "Impacted measures": "6" });
    await expect(summaryTile(page, "Semantic models")).toContainText("3 semantic tables selected");

    // The impact graph spans both models, drawn like the table lineage diagram: reports start collapsed.
    await expect(page.getByRole("heading", { name: "Impact of 3 semantic tables" })).toBeVisible();
    await expect(page.getByText("23 nodes · 34 links", { exact: true })).toBeVisible();
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(23);
    await expect(graphNodes(page, "report|")).toHaveCount(3);
    await expect(graphNode(page, `report|${reportId4}`)).toHaveCount(0);
    await expect(graphNodes(page, "visual|")).toHaveCount(0);
    // Every selected semantic table is a focal node: Customers and Sales, plus Attributed Sales behind the database table.
    for (const table of ["customers", "sales"]) await expect(graphNode(page, `${salesModelKey}|table|${table}`).locator(".ring-2")).toHaveCount(1);
    await expect(graphNode(page, `${workspaceId2}:${modelId2}|table|attributed sales`).locator(".ring-2")).toHaveCount(1);
    await expect(page.locator(".react-flow__node .ring-2")).toHaveCount(3);
    await expect(graphLegend(page).getByRole("listitem")).toHaveText(["Database table", "Semantic model", "Semantic table", "Column", "Calculated column", "Measure", "Report", "Visual"]);

    const reports = impactSection(page, "Reports using the selected tables");
    const visuals = impactSection(page, "Visuals using the selected tables");
    const models = impactSection(page, "Semantic models");
    const measures = impactSection(page, "Measures using the selected tables");
    // On-screen headers are the standard names in sentence case, the same words the copies and exports
    // below use. (AG Grid leaves columns scrolled out of view out of the DOM, so only the first few are read here.)
    const leadingHeaders = [[reports, tableImpactHeaders.reports], [visuals, tableImpactHeaders.visuals], [models, tableImpactHeaders.models], [measures, tableImpactHeaders.measures]] as const;
    for (const [section, headers] of leadingHeaders) {
      for (const header of headers.slice(0, 3)) await expect(section.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
    }
    await expect(reports.getByText("3 rows", { exact: true })).toBeVisible();
    await expect(columnCells(reports, "Report name")).toHaveText(["Campaign Tracker", "Customer Insights", "Sales Performance"]);
    await expect(visuals.getByText("5 rows", { exact: true })).toBeVisible();
    await expect(columnCells(visuals, "Visual name")).toHaveText(["Attributed revenue card", "Active share card", "Sales per customer", "Amount by region", "Total sales card"]);
    await expect(models.getByText("2 rows", { exact: true })).toBeVisible();
    await expect(columnCells(models, "Semantic model")).toHaveText(["Sales Model", "Marketing Model"]);
    // A measure is named on its own, with its semantic table beside it, instead of Table[Measure].
    await expect(measures.getByText("6 rows", { exact: true })).toBeVisible();
    await expect(columnCells(measures, "Measure name")).toHaveText(["Attributed Revenue", "Customer Count", "Sales per Customer", "KPI", "Total Sales", "Active Share"]);
    await expect(columnCells(measures, "Semantic table")).toHaveText(["Attributed Sales", "Metrics", "Metrics", "Sales", "Sales", "Metrics"]);

    // Every grid can be copied and downloaded, and each copy carries the full rows. Each grid already has a
    // "Selected tables" column saying which pick led to that row, so the selection is not repeated as context.
    for (const section of [reports, visuals, models, measures]) {
      for (const name of ["Copy table", "CSV", "Excel"]) await expect(section.getByRole("button", { name, exact: true })).toBeEnabled();
    }
    expect(await copyTable(page, reports)).toBe(tsv([
      tableImpactHeaders.reports,
      ["Campaign Tracker", "Marketing", "Marketing Model", "ANALYTICS.PUBLIC.SALES", "Uses it directly", "1", "1", "Attributed Sales[Attributed Revenue]", reportId3, modelId2],
      ["Customer Insights", "Finance", "Sales Model", "Customers (Sales Model), ANALYTICS.PUBLIC.SALES", "Through a measure", "1", "2", "Metrics[Active Share], Metrics[Sales per Customer]", reportId2, modelId],
      ["Sales Performance", "Finance", "Sales Model", "ANALYTICS.PUBLIC.SALES", "Uses it directly", "1", "2", "Sales[Amount], Sales[Total Sales]", reportId, modelId],
    ]));
    expect(await copyTable(page, visuals)).toBe(tsv([
      tableImpactHeaders.visuals,
      ["Attributed revenue card", "card", "Spend", "Campaign Tracker", "Marketing", "Uses it directly", "Attributed Sales[Attributed Revenue]", "ANALYTICS.PUBLIC.SALES", reportId3, `${reportId3}:spend:revenue-card`],
      ["Active share card", "card", "Regions", "Customer Insights", "Finance", "Through a measure", "Metrics[Active Share]", "Customers (Sales Model)", reportId2, `${reportId2}:regions:share-card`],
      ["Sales per customer", "card", "Regions", "Customer Insights", "Finance", "Through a measure", "Metrics[Sales per Customer]", "Customers (Sales Model), ANALYTICS.PUBLIC.SALES", reportId2, `${reportId2}:regions:spc-card`],
      ["Amount by region", "tableEx", "Overview", "Sales Performance", "Finance", "Uses it directly", "Sales[Amount]", "ANALYTICS.PUBLIC.SALES", reportId, `${reportId}:overview:amount-table`],
      ["Total sales card", "card", "Overview", "Sales Performance", "Finance", "Uses it directly", "Sales[Total Sales]", "ANALYTICS.PUBLIC.SALES", reportId, `${reportId}:overview:sales-card`],
    ]));
    expect(await copyTable(page, models)).toBe(tsv([
      tableImpactHeaders.models,
      ["Sales Model", "Finance", "Customers, Sales", "ANALYTICS.PUBLIC.CUSTOMERS, ANALYTICS.PUBLIC.SALES", "5", "2", "3", modelId, workspaceId],
      ["Marketing Model", "Marketing", "Attributed Sales", "ANALYTICS.PUBLIC.SALES", "1", "1", "1", modelId2, workspaceId2],
    ]));
    expect(await copyTable(page, measures)).toBe(tsv([
      tableImpactHeaders.measures,
      ["Attributed Revenue", "Attributed Sales", "Marketing Model", "Marketing", "ANALYTICS.PUBLIC.SALES", "Direct", "1", "Attributed Sales[Revenue]", "1", "1", modelId2],
      ["Customer Count", "Metrics", "Sales Model", "Finance", "Customers (Sales Model)", "Direct", "1", "Customers[Customer ID]", "0", "0", modelId],
      ["Sales per Customer", "Metrics", "Sales Model", "Finance", "Customers (Sales Model), ANALYTICS.PUBLIC.SALES", "Direct", "1", "[Total Sales]", "1", "1", modelId],
      ["KPI", "Sales", "Sales Model", "Finance", "ANALYTICS.PUBLIC.SALES", "Direct", "1", "[Total Sales]", "0", "0", modelId],
      ["Total Sales", "Sales", "Sales Model", "Finance", "ANALYTICS.PUBLIC.SALES", "Direct", "1", "Sales[Amount]", "1", "1", modelId],
      ["Active Share", "Metrics", "Sales Model", "Finance", "Customers (Sales Model)", "Indirect", "2", "[Customer Count]", "1", "1", modelId],
    ]));

    // A single cell copies just its value.
    const firstReportCell = columnCells(reports, "Report name").first();
    await firstReportCell.hover();
    await firstReportCell.getByRole("button", { name: "Copy cell value" }).click();
    await expect.poll(() => lastCopied(page)).toBe("Campaign Tracker");

    // Files are named table-impact-<table>-<grid>; with several tables picked the subject is "multiple-tables".
    const csvDownload = page.waitForEvent("download");
    await reports.getByRole("button", { name: "CSV", exact: true }).click();
    const csv = await csvDownload;
    expect(csv.suggestedFilename()).toBe("table-impact-multiple-tables-reports.csv");
    const csvText = readFileSync((await csv.path())!, "utf8");
    expect(csvText.startsWith(`﻿${tableImpactHeaders.reports.map((header) => `"${header}"`).join(",")}\r\n`)).toBe(true);
    expect(csvText).toContain(`"Sales Performance","Finance","Sales Model","ANALYTICS.PUBLIC.SALES","Uses it directly","1","2","Sales[Amount], Sales[Total Sales]","${reportId}","${modelId}"`);
    expect(csvText).not.toContain("Executive Summary");
    expect(csvText).not.toContain("parent_");

    const visualsDownload = page.waitForEvent("download");
    await visuals.getByRole("button", { name: "CSV", exact: true }).click();
    expect((await visualsDownload).suggestedFilename()).toBe("table-impact-multiple-tables-visuals.csv");

    const excelDownload = page.waitForEvent("download");
    await measures.getByRole("button", { name: "Excel", exact: true }).click();
    const excel = await excelDownload;
    expect(excel.suggestedFilename()).toBe("table-impact-multiple-tables-measures.xls");
    const excelText = readFileSync((await excel.path())!, "utf8");
    expect(excelText).toContain("<th>Measure name</th><th>Semantic table</th><th>Semantic model</th>");
    expect(excelText).toContain("<td>Active Share</td><td>Metrics</td><td>Sales Model</td><td>Finance</td><td>Customers (Sales Model)</td><td>Indirect</td><td>2</td>");

    await page.screenshot({ path: "test-results/table-impact.png", fullPage: true });

    // Removing the semantic chip leaves only the database table: both semantic tables behind it, in both models.
    await page.getByRole("button", { name: "Remove Customers (Sales Model)", exact: true }).click();
    await expect(chips).toHaveText([/^Database\s*ANALYTICS\.PUBLIC\.SALES$/]);
    await expect(tablesButton).toContainText("1 selected");
    await expectTiles(page, { Reports: "3", Visuals: "4", "Semantic models": "2", "Impacted measures": "4" });
    await expect(summaryTile(page, "Semantic models")).toContainText("2 semantic tables selected");
    await expect(columnCells(reports, "Report name")).toHaveText(["Campaign Tracker", "Customer Insights", "Sales Performance"]);
    await expect(columnCells(visuals, "Visual name")).toHaveText(["Attributed revenue card", "Sales per customer", "Amount by region", "Total sales card"]);
    await expect(columnCells(models, "Semantic model")).toHaveText(["Sales Model", "Marketing Model"]);
    await expect(columnCells(measures, "Measure name")).toHaveText(["Attributed Revenue", "Sales per Customer", "KPI", "Total Sales"]);
    expect(await copyTable(page, models)).toBe(tsv([
      tableImpactHeaders.models,
      ["Sales Model", "Finance", "Sales", "ANALYTICS.PUBLIC.SALES", "3", "2", "3", modelId, workspaceId],
      ["Marketing Model", "Marketing", "Attributed Sales", "ANALYTICS.PUBLIC.SALES", "1", "1", "1", modelId2, workspaceId2],
    ]));
    // One database table picked: the files are named after it.
    const singleDownload = page.waitForEvent("download");
    await models.getByRole("button", { name: "CSV", exact: true }).click();
    expect((await singleDownload).suggestedFilename()).toBe("table-impact-analytics-public-sales-semantic-models.csv");

    // Clear empties the selection.
    await tablesButton.click();
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect(chips).toHaveCount(0);
    await expect(page.getByText("No tables selected", { exact: true })).toBeVisible();

    // One table in one model: its graph is focused on the table and offers Power AI.
    await search.fill("customers");
    await option(semanticGroup, "Customers").click();
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page.getByText("9 calculation links found in 1 semantic model", { exact: true })).toBeVisible();
    await expect(page.getByText("Checked the visuals in 3 connected reports.", { exact: true })).toBeVisible();
    await expectTiles(page, { Reports: "1", Visuals: "2", "Semantic models": "1", "Impacted measures": "3" });
    await expect(reports.getByText("1 row", { exact: true })).toBeVisible();
    await expect(columnCells(reports, "Report name")).toHaveText(["Customer Insights"]);
    await expect(columnCells(visuals, "Visual name")).toHaveText(["Active share card", "Sales per customer"]);
    await expect(columnCells(measures, "Measure name")).toHaveText(["Customer Count", "Active Share", "Sales per Customer"]);
    await expect(page.getByRole("button", { name: "Ask Power AI" })).toBeVisible();

    await expect(page.getByRole("heading", { name: "Customers impact" })).toBeVisible();
    await expect(page.getByText("9 nodes · 12 links", { exact: true })).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(9);
    await expect(page.locator(".react-flow__edge")).toHaveCount(12);
    await expect(page.getByRole("button", { name: "Reset automatic layout" })).toBeVisible();
    await expect(graphNode(page, `${salesModelKey}|table|customers`).locator(".ring-2")).toHaveCount(1);
    await expect(page.locator(".react-flow__node .ring-2")).toHaveCount(1);
    await expect(graphLegend(page).getByRole("listitem")).toHaveText(["Database table", "Semantic model", "Semantic table", "Column", "Measure", "Report", "Visual"]);

    // The report node starts collapsed with a +2 badge; expanding it reveals its visuals, collapsing hides them again.
    const reportNode = graphNode(page, `report|${reportId2}`);
    await expect(reportNode).toContainText("Customer Insights");
    await expect(graphNodes(page, "visual|")).toHaveCount(0);
    const expand = reportNode.getByRole("button", { name: "Expand descendants" });
    await expect(expand).toHaveText("2");
    await expand.click();
    await expect(page.getByText("11 nodes · 14 links", { exact: true })).toBeVisible();
    await expect(graphNodes(page, "visual|")).toHaveCount(2);
    await expect(graphNode(page, `visual|${reportId2}:regions:share-card`)).toContainText("Active share card");
    await expect(graphNode(page, `visual|${reportId2}:regions:spc-card`)).toContainText("Sales per customer");
    await reportNode.getByRole("button", { name: "Collapse descendants" }).click();
    await expect(page.getByText("9 nodes · 12 links", { exact: true })).toBeVisible();
    await expect(graphNodes(page, "visual|")).toHaveCount(0);

    await page.getByRole("button", { name: "Remove Customers (Sales Model)", exact: true }).click();
    await expect(page.getByText("No tables selected", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Selected tables" })).toHaveCount(0);

    // Shared reads are made once; each model's definition is analyzed once; usage comes only from visual evidence.
    expect(backend.requests.filter((request) => request.includes("/lineage/estate/discover"))).toHaveLength(1);
    expect(backend.requests.filter((request) => request.endsWith("/lineage/dax/analyze"))).toHaveLength(2);
    expect(backend.requests.filter((request) => request.endsWith("/explorer/visual-source-lookup"))).toHaveLength(2);
    expect(backend.requests.filter((request) => request.includes("measure-source-lineage"))).toEqual([]);
    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("while the list of reports is still loading, usage shows as pending rather than as no reports", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    const backend = await mockBackend(page, { holdEstate: true });

    await page.goto("/workspace/table-impact");
    await expect(page.getByRole("heading", { level: 1, name: "Table impact" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("5 semantic tables and 3 database tables indexed across 2 workspaces.", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Tables", exact: true }).click();
    await page.getByPlaceholder(tablesPlaceholder).fill("customers");
    await option(page.getByRole("group", { name: semanticGroupName }), "Customers").click();
    await page.getByRole("button", { name: "Done", exact: true }).click();

    const reports = impactSection(page, "Reports using the selected tables");
    const visuals = impactSection(page, "Visuals using the selected tables");
    const measures = impactSection(page, "Measures using the selected tables");
    await expect(page.getByText("Finding the reports connected to these semantic models...", { exact: true })).toBeVisible();
    await expect(page.getByText("No report you can open is connected to the semantic models holding these tables.")).toHaveCount(0);
    await expect(summaryTile(page, "Reports").getByLabel("Still checking")).toBeVisible();
    await expect(summaryTile(page, "Visuals").getByLabel("Still checking")).toBeVisible();
    await expect(reports.getByText("Checking reports...")).toBeVisible();
    await expect(visuals.getByText("Checking reports...")).toBeVisible();
    // Dependencies do not wait for the list of reports.
    await expect(measures.getByText("3 rows", { exact: true })).toBeVisible();
    await expect(page.getByText("9 calculation links found in 1 semantic model", { exact: true })).toBeVisible();

    backend.releaseEstate();
    await expect(page.getByText("Finding the reports connected to these semantic models...", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Checked the visuals in 3 connected reports.", { exact: true })).toBeVisible();
    await expectTiles(page, { Reports: "1", Visuals: "2", "Semantic models": "1", "Impacted measures": "3" });
    await expect(columnCells(reports, "Report name")).toHaveText(["Customer Insights"]);
    await expect(reports.getByText("Checking reports...")).toHaveCount(0);
    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("when the list of reports fails, measures and semantic models still show with a warning", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await mockBackend(page, { estateStatus: 403 });

    await page.goto("/workspace/table-impact");
    await expect(page.getByRole("heading", { level: 1, name: "Table impact" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("5 semantic tables and 3 database tables indexed across 2 workspaces.", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Tables", exact: true }).click();
    await page.getByPlaceholder(tablesPlaceholder).fill("customers");
    await option(page.getByRole("group", { name: databaseGroupName }), "ANALYTICS.PUBLIC.CUSTOMERS").click();
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page.getByRole("list", { name: "Selected tables" }).getByRole("listitem")).toHaveText([/^Database\s*ANALYTICS\.PUBLIC\.CUSTOMERS$/]);

    await expect(page.getByText(reportListFailedBand, { exact: true })).toBeVisible();
    await expect(page.getByText("9 calculation links found in 1 semantic model", { exact: true })).toBeVisible();
    await expectTiles(page, { Reports: "0", Visuals: "0", "Semantic models": "1", "Impacted measures": "3" });

    const reports = impactSection(page, "Reports using the selected tables");
    const visuals = impactSection(page, "Visuals using the selected tables");
    const models = impactSection(page, "Semantic models");
    const measures = impactSection(page, "Measures using the selected tables");
    await expect(reports.getByText("0 rows", { exact: true })).toBeVisible();
    await expect(reports.getByRole("button", { name: "Copy table", exact: true })).toBeDisabled();
    // The empty usage grids say why they are empty, rather than still claiming to check.
    await expect(reports.getByText(reportListFailedGrid, { exact: true })).toBeVisible();
    await expect(reports.getByText("Checking reports...")).toHaveCount(0);
    await expect(visuals.getByText("0 rows", { exact: true })).toBeVisible();
    await expect(visuals.getByText(reportListFailedGrid, { exact: true })).toBeVisible();

    await expect(measures.getByText("3 rows", { exact: true })).toBeVisible();
    await expect(columnCells(measures, "Measure name")).toHaveText(["Customer Count", "Active Share", "Sales per Customer"]);
    await expect(measures.getByRole("button", { name: "Copy table", exact: true })).toBeEnabled();
    await expect(models.getByText("1 row", { exact: true })).toBeVisible();
    await expect(columnCells(models, "Semantic model")).toHaveText(["Sales Model"]);
    await expect(columnCells(models, "Selected tables")).toHaveText(["Customers"]);

    // The graph still draws the dependency chain, just without reports.
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    await expect(graphNodes(page, "report|")).toHaveCount(0);
    await expect(graphLegend(page)).not.toContainText("Report");
    expect(browserErrors).toEqual([]);
  });
});

test.describe("measure impact", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a measure shows the semantic tables, impacted measures, semantic model, reports, and visuals it touches", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await recordClipboard(page);
    const backend = await mockBackend(page);

    await page.goto("/workspace/measure-impact");
    await expect(page.getByRole("heading", { level: 1, name: "Measure impact" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("button", { name: "Workspace scope", exact: true })).toHaveText("All 2 workspaces");
    await expect(page.getByText("7 measures indexed across 2 workspaces.", { exact: true })).toBeVisible();

    // Entries read "Total Sales", then "Sales · Sales Model · Finance": the measure name first, then where it lives.
    const measureButton = page.getByRole("button", { name: "Measure", exact: true });
    await measureButton.click();
    await page.getByPlaceholder("Search a measure by name...").fill("Total Sales");
    const totalSalesOption = page.getByRole("option", { name: "Total Sales" });
    await expect(totalSalesOption).toContainText("Sales · Sales Model · Finance");
    await totalSalesOption.click();
    await expect(measureButton).toHaveText("Total Sales");

    await expect(page.getByText("9 calculation links found", { exact: true })).toBeVisible();
    await expect(page.getByText("Checked the visuals in 3 connected reports.", { exact: true })).toBeVisible();
    await expectTiles(page, { "Semantic tables": "3", "Impacted measures": "2", "Semantic models": "1", Reports: "2", Visuals: "2" });
    await expect(summaryTile(page, "Semantic models")).toContainText("Sales Model");

    // The graph is focused on the measure: its input above, dependents and reports below, reports collapsed.
    await expect(page.getByRole("heading", { name: "Total Sales impact" })).toBeVisible();
    await expect(page.getByText(/^13 nodes · \d+ links$/)).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(13);
    // Only the measure and its dependents lead to reports. Soft, so every check below still runs: this
    // currently fails because buildImpactGraph also links report usage of the measure's upstream inputs,
    // so Sales[Amount] -> Sales Performance is drawn (17 links) and that report shows "2 visuals",
    // including "Amount by region", which reads only Sales[Amount] and is not impacted by Total Sales.
    // The Reports and Visuals grids below correctly list one Sales Performance visual.
    await expect.soft(page.getByText("13 nodes · 16 links", { exact: true }), "graph links only impacted objects to reports").toBeVisible({ timeout: 5_000 });
    await expect.soft(graphNode(page, `report|${reportId}`), "report node counts only impacted visuals").toContainText("Finance · 1 visual", { timeout: 5_000 });
    const focal = graphNode(page, `${salesModelKey}|measure|sales|total sales`);
    await expect(focal).toContainText("Sales[Total Sales]");
    await expect(focal.locator(".ring-2")).toHaveCount(1);
    await expect(page.locator(".react-flow__node .ring-2")).toHaveCount(1);
    for (const label of ["Sales[Amount]", "Sales[KPI]", "Metrics[Sales per Customer]", "Customers[Value Band]", "ANALYTICS.PUBLIC.SALES", "ANALYTICS.PUBLIC.CUSTOMERS"]) {
      await expect(page.locator(".react-flow__node").getByText(label, { exact: true }), label).toBeVisible();
    }
    await expect(graphNode(page, `model|${salesModelKey}`)).toContainText("Sales Model");
    for (const table of ["sales", "metrics", "customers"]) await expect(graphNode(page, `${salesModelKey}|table|${table}`)).toBeVisible();
    await expect(graphNodes(page, "report|")).toHaveCount(2);
    await expect(graphNode(page, `report|${reportId4}`)).toHaveCount(0);
    await expect(graphNodes(page, "visual|")).toHaveCount(0);
    await expect(graphLegend(page).getByRole("listitem")).toHaveText(["Database table", "Semantic model", "Semantic table", "Column", "Calculated column", "Measure", "Report", "Visual"]);
    await graphNode(page, `report|${reportId}`).getByRole("button", { name: "Expand descendants" }).click();
    await expect(graphNode(page, `visual|${reportId}:overview:sales-card`)).toContainText("Total sales card");
    await expect.soft(graphNode(page, `visual|${reportId}:overview:amount-table`), "a visual reading only an input is not drawn as impacted").toHaveCount(0, { timeout: 5_000 });
    await expect.soft(page.getByText("14 nodes · 17 links", { exact: true })).toBeVisible({ timeout: 5_000 });

    const measureLabel = "Total Sales";
    const tables = impactSection(page, "Semantic tables");
    const impacted = impactSection(page, `Measures impacted by ${measureLabel}`);
    const model = impactSection(page, "Semantic model");
    const reports = impactSection(page, "Reports");
    const visuals = impactSection(page, "Visuals");
    const inputs = impactSection(page, `Inputs ${measureLabel} reads`);

    await expect(tables.getByText("3 rows", { exact: true })).toBeVisible();
    await expect(columnCells(tables, "Semantic table")).toHaveText(["Sales", "Metrics", "Customers"]);
    await expect(impacted.getByText("2 rows", { exact: true })).toBeVisible();
    await expect(columnCells(impacted, "Measure name")).toHaveText(["Sales per Customer", "KPI"]);
    await expect(columnCells(impacted, "Semantic table")).toHaveText(["Metrics", "Sales"]);
    await expect(model.getByText("1 row", { exact: true })).toBeVisible();
    await expect(columnCells(model, "Semantic model")).toHaveText(["Sales Model"]);
    // Executive Summary lists Total Sales only in measure-source-lineage, which is not visual evidence.
    await expect(reports.getByText("2 rows", { exact: true })).toBeVisible();
    await expect(columnCells(reports, "Report name")).toHaveText(["Customer Insights", "Sales Performance"]);
    await expect(visuals.getByText("2 rows", { exact: true })).toBeVisible();
    await expect(columnCells(visuals, "Visual name")).toHaveText(["Sales per customer", "Total sales card"]);
    await expect(inputs.getByText("1 row", { exact: true })).toBeVisible();
    await expect(columnCells(inputs, "Object name")).toHaveText(["Amount"]);

    for (const section of [tables, impacted, model, reports, visuals, inputs]) {
      for (const name of ["Copy table", "CSV", "Excel"]) await expect(section.getByRole("button", { name, exact: true })).toBeEnabled();
    }

    // Context columns (workspace, semantic model, the selected measure) come first unless the grid already
    // has that column, and every "… ID" comes last. Report and visual files carry each report's own
    // workspace in the grid, so the measure's workspace is not added to them as context.
    expect(await copyTable(page, tables)).toBe(tsv([
      ["Selected measure", "Semantic table", "Connection to the measure", "Objects involved", "Database tables", "Semantic model", "Workspace name", "Workspace ID", "Semantic model ID"],
      [measureLabel, "Sales", "Holds the measure, Read by the measure, Holds impacted measures", "Sales[Total Sales], Sales[Amount], Sales[KPI]", "ANALYTICS.PUBLIC.SALES", "Sales Model", "Finance", workspaceId, modelId],
      [measureLabel, "Metrics", "Holds impacted measures", "Metrics[Sales per Customer]", "Not available", "Sales Model", "Finance", workspaceId, modelId],
      [measureLabel, "Customers", "Holds impacted calculations", "Customers[Value Band]", "ANALYTICS.PUBLIC.CUSTOMERS", "Sales Model", "Finance", workspaceId, modelId],
    ]));
    expect(await copyTable(page, impacted)).toBe(tsv([
      ["Workspace name", "Semantic model", "Selected measure", "Measure name", "Semantic table", "Dependency", "Steps away", "Referenced as", "Number of reports", "Number of visuals", "Workspace ID", "Semantic model ID"],
      ["Finance", "Sales Model", measureLabel, "Sales per Customer", "Metrics", "Direct", "1", "[Total Sales]", "1", "1", workspaceId, modelId],
      ["Finance", "Sales Model", measureLabel, "KPI", "Sales", "Direct", "1", "[Total Sales]", "0", "0", workspaceId, modelId],
    ]));
    expect(await copyTable(page, model)).toBe(tsv([
      ["Selected measure", "Semantic model", "Workspace name", "Measure's semantic table", "Number of impacted measures", "Number of impacted calculated columns", "Number of reports using it", "Number of visuals using it", "Number of connected reports", "Semantic model ID", "Workspace ID"],
      [measureLabel, "Sales Model", "Finance", "Sales", "2", "1", "2", "2", "3", modelId, workspaceId],
    ]));
    expect(await copyTable(page, reports)).toBe(tsv([
      ["Semantic model", "Selected measure", "Report name", "Workspace name", "How it is used", "Number of pages", "Number of visuals", "Objects used", "Report ID", "Semantic model ID"],
      ["Sales Model", measureLabel, "Customer Insights", "Finance", "Through a measure", "1", "1", "Metrics[Sales per Customer]", reportId2, modelId],
      ["Sales Model", measureLabel, "Sales Performance", "Finance", "Uses it directly", "1", "1", "Sales[Total Sales]", reportId, modelId],
    ]));
    expect(await copyTable(page, visuals)).toBe(tsv([
      ["Semantic model", "Selected measure", "Visual name", "Visual type", "Page name", "Report name", "Workspace name", "How it is used", "Objects used", "Report ID", "Visual ID", "Semantic model ID"],
      ["Sales Model", measureLabel, "Sales per customer", "card", "Regions", "Customer Insights", "Finance", "Through a measure", "Metrics[Sales per Customer]", reportId2, `${reportId2}:regions:spc-card`, modelId],
      ["Sales Model", measureLabel, "Total sales card", "card", "Overview", "Sales Performance", "Finance", "Uses it directly", "Sales[Total Sales]", reportId, `${reportId}:overview:sales-card`, modelId],
    ]));
    expect(await copyTable(page, inputs)).toBe(tsv([
      ["Workspace name", "Semantic model", "Selected measure", "Object name", "Semantic table", "Object type", "Dependency", "Steps away", "Referenced as", "Database table", "Workspace ID", "Semantic model ID"],
      ["Finance", "Sales Model", measureLabel, "Amount", "Sales", "Column", "Direct", "1", "Sales[Amount]", "ANALYTICS.PUBLIC.SALES", workspaceId, modelId],
    ]));

    // Files are named measure-impact-<measure>-<grid>.
    const csvDownload = page.waitForEvent("download");
    await reports.getByRole("button", { name: "CSV", exact: true }).click();
    const csv = await csvDownload;
    expect(csv.suggestedFilename()).toBe("measure-impact-total-sales-reports.csv");
    expect(readFileSync((await csv.path())!, "utf8")).not.toContain("Executive Summary");
    const excelDownload = page.waitForEvent("download");
    await tables.getByRole("button", { name: "Excel", exact: true }).click();
    const excel = await excelDownload;
    expect(excel.suggestedFilename()).toBe("measure-impact-total-sales-semantic-tables.xls");
    expect(readFileSync((await excel.path())!, "utf8")).toContain("<td>Customers</td><td>Holds impacted calculations</td><td>Customers[Value Band]</td>");

    await page.screenshot({ path: "test-results/measure-impact.png", fullPage: true });

    // Cross-workspace merge: the second workspace's measure is discoverable from the same search.
    await measureButton.click();
    await page.getByPlaceholder("Search a measure by name...").fill("ROI");
    await page.getByRole("option", { name: "ROI" }).click();
    await expect(page.getByRole("heading", { name: "ROI impact" })).toBeVisible();
    await expect(page.getByText("1 calculation link found", { exact: true })).toBeVisible();
    await expect(page.getByText("Checked the visuals in 1 connected report.", { exact: true })).toBeVisible();
    await expectTiles(page, { "Semantic tables": "1", "Impacted measures": "0", "Semantic models": "1", Reports: "0", Visuals: "0" });
    await expect(page.getByText("4 nodes · 3 links", { exact: true })).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(4);
    await expect(graphLegend(page).getByRole("listitem")).toHaveText(["Database table", "Semantic model", "Semantic table", "Measure"]);
    const roiTables = impactSection(page, "Semantic tables");
    await expect(columnCells(roiTables, "Semantic table")).toHaveText(["Campaigns"]);
    const roiImpacted = impactSection(page, "Measures impacted by ROI");
    await expect(roiImpacted.getByText("0 rows", { exact: true })).toBeVisible();
    await expect(roiImpacted.getByText("No other measure depends on this measure.", { exact: true })).toBeVisible();
    await expect(roiImpacted.getByRole("button", { name: "Copy table", exact: true })).toBeDisabled();
    await expect(reports.getByText("0 rows", { exact: true })).toBeVisible();
    await expect(reports.getByText("No report visual shows this measure or anything depending on it.", { exact: true })).toBeVisible();
    await expect(impactSection(page, "Inputs ROI reads").getByText("This measure reads no other semantic objects.", { exact: true })).toBeVisible();

    expect(backend.requests.filter((request) => request.includes("measure-source-lineage"))).toEqual([]);
    expect(backend.unhandled).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("when the list of reports fails, only report and visual usage degrade", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await recordClipboard(page);
    await mockBackend(page, { estateStatus: 403 });

    await page.goto("/workspace/measure-impact");
    await expect(page.getByRole("heading", { level: 1, name: "Measure impact" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("7 measures indexed across 2 workspaces.", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Measure", exact: true }).click();
    await page.getByPlaceholder("Search a measure by name...").fill("Total Sales");
    await page.getByRole("option", { name: "Total Sales" }).click();

    await expect(page.getByText(reportListFailedBand, { exact: true })).toBeVisible();
    await expect(page.getByText("9 calculation links found", { exact: true })).toBeVisible();
    await expectTiles(page, { "Semantic tables": "3", "Impacted measures": "2", "Semantic models": "1", Reports: "0", Visuals: "0" });

    const reports = impactSection(page, "Reports");
    const visuals = impactSection(page, "Visuals");
    for (const section of [reports, visuals]) {
      await expect(section.getByText("0 rows", { exact: true })).toBeVisible();
      await expect(section.getByText(reportListFailedGrid, { exact: true })).toBeVisible();
      await expect(section.getByText("Checking reports...")).toHaveCount(0);
      await expect(section.getByRole("button", { name: "Copy table", exact: true })).toBeDisabled();
    }

    await expect(columnCells(impactSection(page, "Semantic tables"), "Semantic table")).toHaveText(["Sales", "Metrics", "Customers"]);
    await expect(columnCells(impactSection(page, "Measures impacted by Total Sales"), "Measure name")).toHaveText(["Sales per Customer", "KPI"]);
    await expect(columnCells(impactSection(page, "Inputs Total Sales reads"), "Object name")).toHaveText(["Amount"]);
    const model = impactSection(page, "Semantic model");
    expect(await copyTable(page, model)).toBe(tsv([
      ["Selected measure", "Semantic model", "Workspace name", "Measure's semantic table", "Number of impacted measures", "Number of impacted calculated columns", "Number of reports using it", "Number of visuals using it", "Number of connected reports", "Semantic model ID", "Workspace ID"],
      ["Total Sales", "Sales Model", "Finance", "Sales", "2", "1", "0", "0", "0", modelId, workspaceId],
    ]));

    // The graph keeps the dependency chain and simply has no report or visual nodes.
    await expect(page.getByText("11 nodes · 14 links", { exact: true })).toBeVisible();
    await expect(graphNode(page, `${salesModelKey}|measure|sales|total sales`).locator(".ring-2")).toHaveCount(1);
    await expect(graphNodes(page, "report|")).toHaveCount(0);
    await expect(graphLegend(page)).not.toContainText("Report");
    expect(browserErrors).toEqual([]);
  });
});

function collectBrowserErrors(page: Page) {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  return browserErrors;
}

/** An option in a search group, found by its exact primary line (the table name). */
function option(group: Locator, primary: string) {
  return group.getByRole("option").filter({ has: group.page().getByText(primary, { exact: true }) });
}

/** A summary tile: the nearest block around the tile's uppercase label that holds its value line. */
function summaryTile(page: Page, label: string) {
  return page.locator(
    `xpath=//main//span[contains(concat(" ", normalize-space(@class), " "), " uppercase ") and normalize-space()="${label}"]/ancestor::div[p][1]`,
  );
}

async function expectTiles(page: Page, values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) {
    const tile = summaryTile(page, label);
    await expect(tile.locator("p").first(), `${label} tile`).toHaveText(value);
    await expect(tile.getByLabel("Still checking")).toHaveCount(0);
  }
}

/** The result section under one grid heading. */
function impactSection(page: Page, title: string) {
  return page.locator(`xpath=//main//h2[normalize-space()="${title}"]/ancestor::section[1]`);
}

/** The rendered cells of one grid column, in row order (AG Grid keeps DOM order in step with the rows). */
function columnCells(section: Locator, column: string) {
  return section.locator(`[role="gridcell"][col-id="${column}"]`);
}

/** One drawn impact-graph node by its graph id (React Flow stamps it as `data-id`). */
function graphNode(page: Page, id: string) {
  return page.locator(`.react-flow__node[data-id="${id}"]`);
}

/** Every drawn impact-graph node whose id starts with a prefix such as `report|` or `visual|`. */
function graphNodes(page: Page, prefix: string) {
  return page.locator(`.react-flow__node[data-id^="${prefix}"]`);
}

function graphLegend(page: Page) {
  return page.getByRole("list", { name: "Graph legend" });
}

function tsv(rows: string[][]) {
  return rows.map((row) => row.join("\t")).join("\n");
}

async function copyTable(page: Page, section: Locator) {
  const before = await copiedCount(page);
  await section.getByRole("button", { name: "Copy table", exact: true }).click();
  await expect.poll(() => copiedCount(page)).toBe(before + 1);
  return lastCopied(page);
}

/**
 * Records what the page hands to `navigator.clipboard.writeText`. Reading the
 * OS clipboard back is unreliable here: parallel workers share it, and Windows
 * rewrites its line endings.
 */
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

function lastCopied(page: Page) {
  return page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1));
}

/** `holdEstate` keeps estate discovery pending until the test calls `releaseEstate()`. */
type MockOptions = { estateStatus?: number; holdEstate?: boolean };

/**
 * One handler for every backend read Table impact and Measure impact make, so
 * no request reaches a real backend. Anything it does not recognise is recorded
 * in `unhandled` (and answered with `{}`) so a test can prove it mocked everything.
 */
async function mockBackend(page: Page, options: MockOptions = {}) {
  const requests: string[] = [];
  const unhandled: string[] = [];
  let release = () => {};
  const estateGate = options.holdEstate ? new Promise<void>((resolve) => { release = resolve; }) : Promise.resolve();
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const path = pathname.slice(pathname.indexOf("/api/v1"));
    requests.push(`${request.method()} ${path}`);

    if (path === "/api/v1/health") return route.fulfill({ json: { status: "ok" } });
    if (path === "/api/v1/ai/status") return route.fulfill({ json: { enabled: true, configured: true, streaming_enabled: true } });
    if (path === "/api/v1/workspaces") return route.fulfill({ json: { workspaces: [{ id: workspaceId, name: "Finance" }, { id: workspaceId2, name: "Marketing" }] } });
    if (path === "/api/v1/lineage/estate/discover") {
      await estateGate;
      return options.estateStatus
        ? route.fulfill({ status: options.estateStatus, json: { detail: "Estate discovery is not permitted for this account." } })
        : route.fulfill({ json: estateResponse });
    }
    if (path === "/api/v1/lineage/dax/analyze") {
      const body = request.postDataJSON() as { semantic_model_id?: string } | null;
      return route.fulfill({ json: body?.semantic_model_id === modelId2 ? daxAnalysis2 : daxAnalysis });
    }
    // Still answered like the backend would, so a regression back to this endpoint shows up as wrong counts.
    if (path === "/api/v1/explorer/measure-source-lineage") return route.fulfill({ json: { rows: evidenceFor(request.postDataJSON(), measureSourceLineageRows) } });
    if (path === "/api/v1/explorer/visual-source-lookup") return route.fulfill({ json: { rows: evidenceFor(request.postDataJSON(), visualSourceLookupRows) } });

    const modelList = /^\/api\/v1\/workspaces\/([^/]+)\/semantic-models$/.exec(path);
    if (modelList) {
      const semanticModels = modelList[1] === workspaceId2 ? [{ id: modelId2, name: "Marketing Model" }] : [{ id: modelId, name: "Sales Model" }];
      return route.fulfill({ json: { semantic_models: semanticModels } });
    }
    const parsed = /^\/api\/v1\/workspaces\/[^/]+\/semantic-models\/([^/]+)\/definition\/parsed$/.exec(path);
    if (parsed) return route.fulfill({ json: parsed[1] === modelId2 ? parsedModel2 : parsedModel });

    unhandled.push(`${request.method()} ${path}`);
    return route.fulfill({ json: {} });
  });
  return { requests, unhandled, releaseEstate: () => release() };
}

/** Evidence endpoints answer only for the reports posted to them, as the backend does. */
function evidenceFor<T extends { report_id: string }>(body: unknown, rows: T[]) {
  const reportIds = new Set(((body as { reports?: Array<{ report_id: string }> } | null)?.reports ?? []).map((report) => report.report_id));
  return rows.filter((row) => reportIds.has(row.report_id));
}

const salesPerformance = { id: reportId, name: "Sales Performance", dataset_id: modelId, report_type: "PowerBIReport", format: "PBIR", is_owned_by_me: true };
const customerInsights = { id: reportId2, name: "Customer Insights", dataset_id: modelId, report_type: "PowerBIReport", format: "PBIR", is_owned_by_me: true };
const campaignTracker = { id: reportId3, name: "Campaign Tracker", dataset_id: modelId2, report_type: "PowerBIReport", format: "PBIR", is_owned_by_me: true };
const executiveSummary = { id: reportId4, name: "Executive Summary", dataset_id: modelId, report_type: "PowerBIReport", format: "PBIR", is_owned_by_me: true };

const estateResponse = {
  workspaces: [
    {
      workspace: { id: workspaceId, name: "Finance" },
      reports: [salesPerformance, customerInsights, executiveSummary],
      semantic_models: [{ id: modelId, name: "Sales Model" }],
      report_bindings: [
        { report_id: reportId, semantic_model_id: modelId, status: "matched" },
        { report_id: reportId2, semantic_model_id: modelId, status: "matched" },
        { report_id: reportId4, semantic_model_id: modelId, status: "matched" },
      ],
    },
    {
      workspace: { id: workspaceId2, name: "Marketing" },
      reports: [campaignTracker],
      semantic_models: [{ id: modelId2, name: "Marketing Model" }],
      report_bindings: [{ report_id: reportId3, semantic_model_id: modelId2, status: "matched" }],
    },
  ],
  graph: { nodes: [], edges: [] },
  warnings: [],
  workspace_count: 2,
  report_count: 4,
  semantic_model_count: 2,
};

/** Model-level lineage: lists measures per bound report whether or not a visual shows them. Never usage evidence. */
const measureSourceLineageRows = [
  { report_id: reportId, semantic_table: "Sales", semantic_object_name: "Total Sales" },
  { report_id: reportId2, semantic_table: "Metrics", semantic_object_name: "Active Share" },
  { report_id: reportId3, semantic_table: "Attributed Sales", semantic_object_name: "Attributed Revenue" },
  { report_id: reportId4, semantic_table: "Sales", semantic_object_name: "Total Sales" },
  { report_id: reportId4, semantic_table: "Sales", semantic_object_name: "KPI" },
  { report_id: reportId4, semantic_table: "Metrics", semantic_object_name: "Customer Count" },
];

/** Visual evidence, carrying names like the backend's VisualSourceLookupRow. Executive Summary has none. */
const visualSourceLookupRows = [
  { report_id: reportId, report_name: "Sales Performance", workspace_name: "Finance", page_id: "overview", page_name: "Overview", visual_id: "sales-card", visual_name: "Total sales card", visual_type: "card", semantic_table: "Sales", semantic_object_name: "Total Sales", match_status: "matched" },
  { report_id: reportId, report_name: "Sales Performance", workspace_name: "Finance", page_id: "overview", page_name: "Overview", visual_id: "amount-table", visual_name: "Amount by region", visual_type: "tableEx", semantic_table: "Sales", semantic_object_name: "Amount", match_status: "matched" },
  { report_id: reportId2, report_name: "Customer Insights", workspace_name: "Finance", page_id: "regions", page_name: "Regions", visual_id: "share-card", visual_name: "Active share card", visual_type: "card", semantic_table: "Metrics", semantic_object_name: "Active Share", match_status: "matched" },
  { report_id: reportId2, report_name: "Customer Insights", workspace_name: "Finance", page_id: "regions", page_name: "Regions", visual_id: "spc-card", visual_name: "Sales per customer", visual_type: "card", semantic_table: "Metrics", semantic_object_name: "Sales per Customer", match_status: "matched" },
  { report_id: reportId3, report_name: "Campaign Tracker", workspace_name: "Marketing", page_id: "spend", page_name: "Spend", visual_id: "revenue-card", visual_name: "Attributed revenue card", visual_type: "card", semantic_table: "Attributed Sales", semantic_object_name: "Attributed Revenue", match_status: "matched" },
  { report_id: reportId3, report_name: "Campaign Tracker", workspace_name: "Marketing", page_id: "spend", page_name: "Spend", visual_id: "spend-chart", visual_name: "Spend by month", visual_type: "lineChart", semantic_table: "Campaigns", semantic_object_name: "Spend", match_status: "matched" },
  // Unmatched visuals are never counted.
  { report_id: reportId3, report_name: "Campaign Tracker", workspace_name: "Marketing", page_id: "spend", page_name: "Spend", visual_id: "legacy-table", visual_name: "Legacy revenue table", visual_type: "tableEx", semantic_table: "Attributed Sales", semantic_object_name: "Revenue", match_status: "unmatched" },
];

const parsedModel = {
  workspace_id: workspaceId,
  semantic_model_id: modelId,
  format: "TMDL",
  tables: [
    {
      name: "Sales",
      source_path: "ANALYTICS.PUBLIC.SALES",
      expression: null,
      columns: [
        { name: "Amount", source_path: "ANALYTICS.PUBLIC.SALES", source_column: "AMOUNT", data_type: "decimal", expression: null },
        { name: "Quantity", source_path: "ANALYTICS.PUBLIC.SALES", source_column: "QUANTITY", data_type: "int64", expression: null },
        { name: "Extended", source_path: null, source_column: null, data_type: "decimal", expression: "Sales[Amount] * Sales[Quantity]" },
      ],
      measures: [
        { name: "KPI", expression: "DIVIDE([Total Sales], 100)" },
        { name: "Total Sales", expression: "SUM(Sales[Amount])" },
      ],
      hierarchies: [],
    },
    {
      name: "Customers",
      source_path: "ANALYTICS.PUBLIC.CUSTOMERS",
      expression: null,
      columns: [
        { name: "Customer ID", source_path: "ANALYTICS.PUBLIC.CUSTOMERS", source_column: "CUSTOMER_ID", data_type: "string", expression: null },
        { name: "Region", source_path: "ANALYTICS.PUBLIC.CUSTOMERS", source_column: "REGION", data_type: "string", expression: null },
        // A calculated column that reads a measure: it changes when Total Sales changes.
        { name: "Value Band", source_path: null, source_column: null, data_type: "string", expression: "IF([Total Sales] > 1000, \"High\", \"Low\")" },
      ],
      measures: [],
      hierarchies: [],
    },
    {
      // A measure table: no columns, so no database source behind it.
      name: "Metrics",
      source_path: null,
      expression: null,
      columns: [],
      measures: [
        { name: "Customer Count", expression: "DISTINCTCOUNT(Customers[Customer ID])" },
        { name: "Active Share", expression: "DIVIDE([Customer Count], 500)" },
        { name: "Sales per Customer", expression: "DIVIDE([Total Sales], [Customer Count])" },
      ],
      hierarchies: [],
    },
  ],
  relationships: [],
  warnings: [],
};

const parsedModel2 = {
  workspace_id: workspaceId2,
  semantic_model_id: modelId2,
  format: "TMDL",
  tables: [
    {
      name: "Campaigns",
      source_path: "ANALYTICS.PUBLIC.CAMPAIGNS",
      expression: null,
      columns: [
        { name: "Spend", source_path: "ANALYTICS.PUBLIC.CAMPAIGNS", source_column: "SPEND", data_type: "decimal", expression: null },
      ],
      measures: [
        { name: "ROI", expression: "DIVIDE([Revenue], [Spend])" },
      ],
      hierarchies: [],
    },
    {
      name: "Attributed Sales",
      source_path: "ANALYTICS.PUBLIC.SALES",
      expression: null,
      columns: [
        { name: "Revenue", source_path: "ANALYTICS.PUBLIC.SALES", source_column: "AMOUNT", data_type: "decimal", expression: null },
        // The same physical table, reported in a different case.
        { name: "Campaign Key", source_path: "analytics.public.sales", source_column: "CAMPAIGN_KEY", data_type: "string", expression: null },
      ],
      measures: [
        { name: "Attributed Revenue", expression: "SUM('Attributed Sales'[Revenue])" },
      ],
      hierarchies: [],
    },
  ],
  relationships: [],
  warnings: [],
};

const ref = (object_type: string, table_name: string, object_name: string) => ({ object_type, table_name, object_name, qualified_name: `${table_name}[${object_name}]` });
const daxAnalysis = {
  objects: [],
  dependencies: [
    { source: ref("column", "Sales", "Amount"), target: ref("measure", "Sales", "Total Sales"), reference_text: "Sales[Amount]" },
    { source: ref("column", "Sales", "Amount"), target: ref("calculated_column", "Sales", "Extended"), reference_text: "Sales[Amount]" },
    { source: ref("column", "Sales", "Quantity"), target: ref("calculated_column", "Sales", "Extended"), reference_text: "Sales[Quantity]" },
    { source: ref("measure", "Sales", "Total Sales"), target: ref("measure", "Sales", "KPI"), reference_text: "[Total Sales]" },
    { source: ref("column", "Customers", "Customer ID"), target: ref("measure", "Metrics", "Customer Count"), reference_text: "Customers[Customer ID]" },
    { source: ref("measure", "Metrics", "Customer Count"), target: ref("measure", "Metrics", "Active Share"), reference_text: "[Customer Count]" },
    { source: ref("measure", "Sales", "Total Sales"), target: ref("measure", "Metrics", "Sales per Customer"), reference_text: "[Total Sales]" },
    { source: ref("measure", "Metrics", "Customer Count"), target: ref("measure", "Metrics", "Sales per Customer"), reference_text: "[Customer Count]" },
    { source: ref("measure", "Sales", "Total Sales"), target: ref("calculated_column", "Customers", "Value Band"), reference_text: "[Total Sales]" },
  ],
  warnings: [],
  object_count: 11,
  dependency_count: 9,
};

// ROI deliberately has no recorded dependencies (the measure impact test expects it alone).
const daxAnalysis2 = {
  objects: [],
  dependencies: [
    { source: ref("column", "Attributed Sales", "Revenue"), target: ref("measure", "Attributed Sales", "Attributed Revenue"), reference_text: "Attributed Sales[Revenue]" },
  ],
  warnings: [],
  object_count: 5,
  dependency_count: 1,
};
