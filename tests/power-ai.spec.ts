import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

const workspaceId = "11111111-1111-4111-8111-111111111111";
const reportId = "22222222-2222-4222-8222-222222222222";
const modelId = "33333333-3333-4333-8333-333333333333";
/** The report lineage fixtures keep the model in its own workspace, as real estates often do. */
const modelWorkspaceId = "44444444-4444-4444-8444-444444444444";

test.describe("Power AI — global docked panel", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  // These are the first tests in the suite to request PowerAiWidget's (dev-only,
  // per-module) source files, which occasionally races Vite's dev-server transform
  // cache on a cold start under concurrent workers — confirmed unrelated to app
  // logic (reproduces identically on unmodified, pre-existing spec files too; a
  // production build has no such transform step). A scoped retry absorbs it.
  test.describe.configure({ retries: 2 });

  test("the launcher is available identically on every page, including workspace and API docs", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });

    await page.goto("/");
    await expect(page.getByRole("button", { name: "Open Power AI" })).toBeVisible({ timeout: 60_000 });

    await page.goto("/setup-guide");
    await expect(page.getByRole("button", { name: "Open Power AI" })).toBeVisible({ timeout: 60_000 });

    await page.goto("/workspace/power-bi");
    await expect(page.getByRole("button", { name: "Open Power AI" })).toBeVisible({ timeout: 60_000 });

    await page.goto("/workspace/api-docs");
    await expect(page.getByRole("button", { name: "Open Power AI" })).toBeVisible({ timeout: 60_000 });
  });

  test("a 401 from the status endpoint locks Power AI behind Power BI setup", async ({ page }) => {
    await mockAiStatus(page, { status: 401, json: { detail: "Not authenticated" } });
    await gotoAfterAiStatus(page, "/");
    await expect(page.getByRole("button", { name: "Power AI is locked" })).toBeVisible({ timeout: 60_000 });

    await page.getByRole("button", { name: "Power AI is locked" }).click();
    await expect(page.getByRole("heading", { name: "Power AI", exact: true })).toBeVisible();
    await expect(page.getByText("Complete Power BI setup with a device code or a service principal to unlock the AI assistant.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Power BI setup" })).toBeVisible();
    await expect(page.getByPlaceholder("Ask Power AI...")).not.toBeVisible();
    await page.getByRole("button", { name: "Collapse Power AI" }).click();
    await expect(page.getByRole("heading", { name: "Power AI", exact: true })).not.toBeVisible();
  });

  test("a 403 from the status endpoint shows an insufficient-permissions message, not the auth-setup flow", async ({ page }) => {
    await mockAiStatus(page, { status: 403, json: { detail: "Forbidden" } });
    await gotoAfterAiStatus(page, "/");
    await page.getByRole("button", { name: "Power AI is locked" }).click();
    await expect(page.getByText("Your account doesn't have permission to use Power AI. Contact your workspace admin.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Power BI setup" })).not.toBeVisible();
  });

  // A reachable, authenticated backend that simply hasn't turned the feature on must say so, not send the user to redo Power BI setup.
  test("enabled=false shows a distinct 'not enabled' message", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ enabled: false }) });
    await gotoAfterAiStatus(page, "/");
    await page.getByRole("button", { name: "Power AI is locked" }).click();
    await expect(page.getByText("Power AI is not enabled for this environment.")).toBeVisible();
  });

  test("configured=false shows a distinct 'not configured' message", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ configured: false }) });
    await gotoAfterAiStatus(page, "/");
    await page.getByRole("button", { name: "Power AI is locked" }).click();
    await expect(page.getByText("Power AI hasn't been configured yet.")).toBeVisible();
  });

  test("enabled and configured becomes active", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await expect(page.getByPlaceholder("Ask Power AI...")).toBeVisible();
    // No persona picker: Power AI answers every question at one fixed level.
    await expect(page.getByRole("radio")).toHaveCount(0);
  });
});

test.describe("Power AI — context and Ask Power AI", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Ask Power AI opens the floating panel, seeding context and a starting question", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await mockTableImpactBackend(page);
    await page.goto("/workspace/table-impact");
    await expect(page.getByRole("heading", { name: "Table impact" })).toBeVisible({ timeout: 60_000 });
    // Table impact starts with nothing selected; Ask Power AI appears once one table is picked.
    await expect(page.getByRole("button", { name: "Ask Power AI" })).toHaveCount(0);
    await selectSemanticTable(page, "Sales");
    await expect(page.getByRole("button", { name: "Ask Power AI" })).toBeVisible();

    await page.getByRole("button", { name: "Ask Power AI" }).click();

    await expect(page.getByRole("heading", { name: "Power AI", exact: true })).toBeVisible();
    await expect(page.getByText("Current context")).toHaveCount(0);
    await expect(page.getByPlaceholder("Ask Power AI...")).toHaveValue("Explain the Sales table");
  });

  test("the outgoing chat request carries the selected object as context, not a full payload", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await mockTableImpactBackend(page);

    let capturedBody: Record<string, unknown> | null = null;
    await page.route("**/api/v1/ai/chat/stream", (route) => {
      capturedBody = route.request().postDataJSON();
      return route.fulfill(sseResponse({ deltas: ["Sales feeds three downstream measures."] }));
    });

    await page.goto("/workspace/table-impact");
    await expect(page.getByRole("heading", { name: "Table impact" })).toBeVisible({ timeout: 60_000 });
    await selectSemanticTable(page, "Sales");
    await page.getByRole("button", { name: "Ask Power AI" }).click();
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("Sales feeds three downstream measures.")).toBeVisible();
    expect(capturedBody).not.toBeNull();
    expect(capturedBody).toMatchObject({
      message: "Explain the Sales table",
      audience: "developer",
      context: { workspace_id: workspaceId, semantic_model_id: modelId, semantic_model_workspace_id: workspaceId, object_type: "table", object_name: "Sales" },
    });
  });

  test("on report lineage the request carries the model's own workspace, not just the report's", async ({ page }) => {
    await mockReportLineageBackend(page);
    await mockAiStatus(page, { status: 200, json: readyStatus() });

    let capturedBody: Record<string, unknown> | null = null;
    await page.route("**/api/v1/ai/chat/stream", (route) => {
      capturedBody = route.request().postDataJSON();
      return route.fulfill(sseResponse({ deltas: ["Sales Overview is a report in workspace 'Finance'."] }));
    });

    await page.goto("/workspace/report-lineage");
    await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Ask Power AI" }).click();
    await expect(page.getByPlaceholder("Ask Power AI...")).toHaveValue("Explain this report");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("Sales Overview is a report in workspace 'Finance'.")).toBeVisible();
    expect(capturedBody).toMatchObject({
      context: {
        workspace_id: workspaceId,
        report_id: reportId,
        semantic_model_id: modelId,
        semantic_model_workspace_id: modelWorkspaceId,
        object_type: "report",
        object_name: "Sales Overview",
      },
    });
  });
});

test.describe("Power AI — chat transports", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("streams a multi-frame response and replaces the accumulated text with the authoritative final answer", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: true }) });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill(
        sseResponse({
          deltas: ["Gross Margin ", "depends on Sales[Amount]."],
          complete: chatResponse({ answer: "Gross Margin depends on Sales[Amount]." }),
        }),
      ),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("Gross Margin depends on Sales[Amount].", { exact: true })).toBeVisible();
  });

  test("complete's answer wins over deltas that carried only part of it, and shows exactly once", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill(sseResponse({ deltas: ["Total Revenue adds "], complete: chatResponse({ answer: "Total Revenue adds up Revenue." }) })),
    );

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByText("Total Revenue adds up Revenue.", { exact: true })).toHaveCount(1);
    await expect(page.getByText(/Total Revenue adds/)).toHaveCount(1);
  });

  test("a complete event without an answer keeps the streamed text instead of emptying the bubble", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill(sseResponse({ deltas: ["Total Revenue ", "adds up Revenue."], complete: chatResponse({ answer: "" }) })),
    );

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByText("Total Revenue adds up Revenue.", { exact: true })).toBeVisible();
  });

  test("streamed text keeps its exact newlines and DAX indentation, laid out as sections", async ({ page }) => {
    const answer = [
      "Total Revenue is a measure in table Orders of semantic model 'Sales Model' (workspace 'Finance').",
      "",
      "Definition",
      "- Total Revenue (measure in table Orders; format #,0)",
      "    SUM(Orders[Revenue])",
    ].join("\n");
    // Split the way the backend chunks: each piece carries its own trailing whitespace.
    const deltas = [
      "Total Revenue is a measure in table ",
      "Orders of semantic model 'Sales Model' ",
      "(workspace 'Finance').\n\nDefinition\n",
      "- Total Revenue (measure in table Orders; format #,0)\n    ",
      "SUM(Orders[Revenue])",
    ];
    expect(deltas.join("")).toBe(answer);

    await recordClipboard(page);
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) => route.fulfill(sseResponse({ deltas, complete: chatResponse({ answer }) })));

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByRole("heading", { name: "Definition", exact: true })).toBeVisible();
    // The answer's four-space code indent marks DAX; the block shows the DAX itself.
    const dax = page.locator("pre", { hasText: "SUM(Orders[Revenue])" });
    await expect(dax).toBeVisible();
    expect(await dax.evaluate((element) => element.textContent)).toBe("SUM(Orders[Revenue])");
    // Formatting is presentation only: copying the answer gives back exactly the text that streamed in.
    await page.getByRole("button", { name: "Copy answer" }).click();
    expect(await copiedText(page)).toBe(answer);
  });

  test("an error frame shows the vetted copy for its reason, never the raw backend message", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill(sseErrorResponse({ code: "AI_DISABLED", message: "The AI subsystem is disabled.", reason: "disabled" })),
    );

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByRole("alert")).toContainText("Power AI is not enabled for this environment.");
    await expect(page.getByText("The AI subsystem is disabled.")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  });

  test("a long wait says Power AI is gathering lineage evidence", async ({ page }) => {
    await page.clock.install();
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/v1/ai/chat/stream", async (route) => {
      await held;
      return route.fulfill(sseResponse({ deltas: ["Total Revenue adds up Revenue."] })).catch(() => {});
    });

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByText("Thinking", { exact: true })).toBeVisible();
    await page.clock.fastForward(7_000);
    await expect(page.getByText("Gathering lineage evidence...", { exact: true })).toBeVisible();
    release();
    await expect(page.getByText("Total Revenue adds up Revenue.", { exact: true })).toBeVisible();
  });

  test("falls back to the non-streaming endpoint when the backend reports streaming_enabled=false", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: false }) });

    let streamCalled = false;
    await page.route("**/api/v1/ai/chat/stream", (route) => {
      streamCalled = true;
      return route.fulfill(sseResponse({ deltas: ["should not be used"] }));
    });
    await page.route("**/api/v1/ai/chat", (route) =>
      route.fulfill({ json: chatResponse({ answer: "Gross Margin is Gross Profit divided by Net Sales." }) }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("Gross Margin is Gross Profit divided by Net Sales.")).toBeVisible();
    expect(streamCalled).toBe(false);
  });

  test("stopping mid-stream cancels cleanly without an error", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", async (route) => {
      // Leave enough time for the browser to paint the in-flight state even
      // when the full suite has the dev server and data-grid workers busy.
      await new Promise((resolve) => setTimeout(resolve, 5000));
      return route.fulfill(sseResponse({ deltas: ["This should never fully arrive."] }));
    });

    const browserErrors: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin");
    await page.getByRole("button", { name: "Send message" }).click();

    const stopButton = page.getByRole("button", { name: "Stop generating" });
    await expect(stopButton).toBeVisible();
    await stopButton.click();

    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
    await expect(page.getByText("This should never fully arrive.")).not.toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test("a rate-limited response shows friendly copy, never the raw backend message", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ detail: "quota_exceeded_internal_id_58213" }) }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByRole("alert")).toContainText("Power AI is receiving too many requests right now");
    await expect(page.getByText("quota_exceeded_internal_id_58213")).not.toBeVisible();
  });

  test("an unreachable backend shows a generic unavailable message", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) => route.abort("connectionrefused"));

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByRole("alert")).toContainText("The AI backend is temporarily unavailable");
  });
});

test.describe("Power AI — evidence and claim states", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("renders verified evidence and grounded claims with citation markers", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: false }) });
    await page.route("**/api/v1/ai/chat", (route) =>
      route.fulfill({
        json: chatResponse({
          answer: "Gross Margin % is calculated from Gross Profit and Net Sales.",
          claims: [{ text: "Gross Margin % is calculated from Gross Profit and Net Sales.", evidence_ids: ["E1"] }],
          evidence: [
            evidenceItem({
              evidence_id: "E1",
              object_type: "measure",
              object_id: "Sales[Gross Margin %]",
              object_name: "Gross Margin %",
              fact_type: "definition",
              value: "DIVIDE([Gross Profit], [Net Sales])",
              plain_language: "Gross Margin % divides Gross Profit by Net Sales.",
              display_value: "measure in table Sales; format 0.0%",
            }),
          ],
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Explain Gross Margin %");
    await page.getByRole("button", { name: "Send message" }).click();

    await page.getByRole("button", { name: "Sources (1)" }).click();
    const sources = page.getByTestId("power-ai-sources");
    await expect(sources.getByText("[E1]").first()).toBeVisible();
    await expect(sources.getByText("Gross Margin %", { exact: true })).toBeVisible();
    await expect(sources.getByText("measure in table Sales; format 0.0%", { exact: true })).toBeVisible();
    await expect(sources.locator("pre", { hasText: "DIVIDE([Gross Profit], [Net Sales])" })).toBeVisible();
    await expect(sources.getByText("Gross Margin % divides Gross Profit by Net Sales.", { exact: true })).toBeVisible();
  });

  test("sources start collapsed and expand into answer sections, in section order", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) =>
      route.fulfill(sseResponse({ complete: chatResponse({ answer: contextSentence, agent: "measure_agent", evidence: dossierEvidence }) })),
    );

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByText(contextSentence, { exact: true })).toBeVisible();
    const toggle = page.getByRole("button", { name: "Sources (4)" });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId("power-ai-sources")).toHaveCount(0);

    await toggle.click();

    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const sources = page.getByTestId("power-ai-sources");
    await expect(sources.getByRole("heading", { level: 4 })).toHaveText(["Definition", "Reads from (database lineage)", "Visual impact", "What was checked"]);
    await expect(sources.getByText("Snowflake view PBI_DB.MART.V_ORDERS -> semantic table Orders (columns: REVENUE)", { exact: true })).toBeVisible();
    await expect(sources.getByText("Report 'Sales Overview' > page 'Overview' > 'Margin Card' (card) (through Profit Margin %)", { exact: true })).toBeVisible();
    await expect(sources.getByText("Visual impact was checked in 1 report: 'Sales Overview'. 1 visual would be affected.", { exact: true })).toBeVisible();
    // The context sentence is the answer's opening line, so the evidence list doesn't repeat it.
    await expect(page.getByText(contextSentence, { exact: true })).toHaveCount(1);
  });

  test("insufficient evidence is rendered as a valid, clearly labeled answer state", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: false }) });
    await page.route("**/api/v1/ai/chat", (route) =>
      route.fulfill({
        json: chatResponse({
          status: "insufficient_evidence",
          answer: "I could not determine the physical source from available lineage metadata.",
          evidence: [],
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("Where does this column come from?");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("I could not determine the physical source from available lineage metadata.")).toBeVisible();
    // A soft note in the message, not a warning box.
    await expect(page.getByText("I need a bit more to go on", { exact: true })).toBeVisible();
    await expect(page.getByText("Insufficient evidence to fully answer this")).toHaveCount(0);
  });

  test("conflicting evidence shows both sides grouped by source, without Power AI choosing one", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: false }) });
    await page.route("**/api/v1/ai/chat", (route) =>
      route.fulfill({
        json: chatResponse({
          status: "conflicting_evidence",
          answer: "Definition metadata and runtime metadata disagree on this relationship's direction.",
          evidence: [
            evidenceItem({ evidence_id: "E1", object_type: "relationship", object_name: "Sales -> Region", fact_type: "relationship", source_type: "tmdl", verification_status: "partial" }),
            evidenceItem({ evidence_id: "E2", object_type: "relationship", object_name: "Sales -> Region", fact_type: "relationship", source_type: "xmla", verification_status: "partial" }),
          ],
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("What is the relationship direction?");
    await page.getByRole("button", { name: "Send message" }).click();

    // The status note is visible whether or not the sources are expanded.
    await expect(page.getByText("Conflicting evidence found")).toBeVisible();
    await page.getByRole("button", { name: "Sources (2)" }).click();
    await expect(page.getByText("Semantic model definition (TMDL)", { exact: true })).toBeVisible();
    await expect(page.getByText("Live model (XMLA)", { exact: true })).toBeVisible();
  });
});

test.describe("Power AI — measure definition panel", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("shows only the definition: header, tabs, cards, and no definition diagram", async ({ page }) => {
    const explainBodies: Array<Record<string, unknown>> = [];
    await openMeasurePanel(page, (body) => {
      explainBodies.push(body);
      // The first answer is written up by a model; the second straight from the evidence, and shorter.
      return explainBodies.length === 1
        ? chatResponse({ answer: panelAnswer, agent: "measure_agent", evidence: panelEvidence, usage: { provider: "openai", model: "gpt-4o", tokens: 812 } })
        : chatResponse({ answer: measureAnswer, agent: "measure_agent", evidence: panelEvidence.slice(0, 2) });
    });

    await page.getByRole("button", { name: "Power AI definition" }).click();

    const panel = page.getByTestId("measure-definition");
    const badge = panel.getByText("Written by Power AI", { exact: true });
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute("title", "Model: gpt-4o");
    await expect(panel.getByRole("heading", { name: "Total Revenue", exact: true })).toBeVisible();
    expect(explainBodies[0]).toMatchObject({
      audience: "developer",
      context: {
        report_id: reportId,
        semantic_model_id: modelId,
        semantic_model_workspace_id: modelWorkspaceId,
        object_type: "measure",
        object_name: "Orders[Total Revenue]",
      },
    });

    // Only the definition: no facts row and no evidence list repeating the answer's sections.
    await expect(panel.getByText("DAX expression", { exact: true })).toHaveCount(0);
    await expect(panel.getByText("Reads from", { exact: true })).toHaveCount(0);
    await expect(panel.getByText("Reads from (database lineage)", { exact: true })).toHaveCount(1);
    await expect(panel.getByRole("heading", { name: "In plain English", exact: true })).toBeVisible();
    await expect(panel.locator("pre", { hasText: "SUM(Orders[Revenue])" })).toBeVisible();

    const tabs = panel.getByRole("navigation", { name: "Answer sections" }).getByRole("button");
    await expect(tabs).toHaveText(["Overview", "DAX", "Semantic lineage", "Database", "Impact", "Visuals"]);
    await tabs.filter({ hasText: "Database" }).click();
    await expect(tabs.filter({ hasText: "Database" })).toHaveAttribute("aria-current", "true");
    await expect(panel.locator("section", { has: page.getByRole("heading", { name: "Reads from (database lineage)" }) })).toHaveClass(/ring-2/);

    await expect(panel.locator("[data-layer]")).toHaveCount(0);
    await expect(panel.getByRole("button", { name: "Orders[Profit Margin %]", exact: true })).toHaveClass(/font-semibold/);

    // The download still carries every evidence item the screen no longer lists.
    const downloaded = page.waitForEvent("download");
    await panel.getByRole("button", { name: ".md" }).click();
    const markdown = readFileSync((await (await downloaded).path())!, "utf8");
    expect(markdown).toContain(panelAnswer);
    expect(markdown).toContain("## Reads from (database lineage)");
    expect(markdown).toContain("- Snowflake view PBI_DB.MART.V_ORDERS -> semantic table Orders (columns: REVENUE) (physical_source, snowflake, verified)");
    expect(markdown).toContain("## Visual impact");

    await page.getByRole("button", { name: "Power AI definition" }).click();

    await expect(panel.getByText("From lineage evidence", { exact: true })).toBeVisible();
    await expect(panel.getByText("Written by Power AI", { exact: true })).toHaveCount(0);
    // Tabs exist only for the sections this answer has.
    await expect(tabs).toHaveText(["Overview", "DAX"]);
  });

  test("names are explorable, and follow-ups go to the chat with the measure as context", async ({ page }) => {
    await openMeasurePanel(page, () =>
      chatResponse({ answer: panelAnswer, agent: "measure_agent", evidence: panelEvidence, suggested_questions: ["Which visuals use Total Revenue?"] }),
    );
    const chatBodies: Array<Record<string, any>> = [];
    await page.route("**/api/v1/ai/chat/stream", (route) => {
      chatBodies.push(route.request().postDataJSON());
      return route.fulfill(sseResponse({ deltas: ["Margin Card uses Total Revenue through Profit Margin %."] }));
    });

    await page.getByRole("button", { name: "Power AI definition" }).click();
    const answer = page.getByTestId("measure-definition").locator('[data-answer-view="panel"]');

    // A measure this panel doesn't list is asked in the chat: seeded, not sent.
    await answer.getByRole("button", { name: "Orders[Profit Margin %]", exact: true }).click();
    await expect(page.getByPlaceholder("Ask Power AI...")).toHaveValue("Explain Orders[Profit Margin %]");
    await expect(page.getByTestId("power-ai-context")).toContainText("Measure: Orders[Profit Margin %]");
    expect(chatBodies).toHaveLength(0);

    // A follow-up is sent straight away, about the measure the panel defined.
    await page.getByRole("button", { name: "Which visuals use Total Revenue?" }).click();
    await expect(page.getByText("Margin Card uses Total Revenue through Profit Margin %.")).toBeVisible();
    expect(chatBodies).toHaveLength(1);
    expect(chatBodies[0]).toMatchObject({
      message: "Which visuals use Total Revenue?",
      context: { report_id: reportId, semantic_model_id: modelId, object_type: "measure", object_name: "Orders[Total Revenue]" },
    });
  });
});

test.describe("Power AI — interactive answers", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("titles with a trailing colon and model-written aliases render as section headings", async ({ page }) => {
    await mockChatAnswers(page, () => chatResponse({
      answer: [
        "Gross Margin divides profit by sales.",
        "",
        "Semantic model lineage:",
        "- Sales[Amount] (column, referenced directly)",
        "",
        "DAX",
        "    DIVIDE([Gross Profit], [Net Sales])",
      ].join("\n"),
    }));

    await askFromHome(page, "Explain Gross Margin");

    await expect(page.getByRole("heading", { name: "Semantic model lineage", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "DAX", exact: true })).toBeVisible();
    await expect(page.getByText("Semantic model lineage:", { exact: true })).toHaveCount(0);
  });

  test("names backed by evidence are chips: a tooltip with the fact, and a click asks about them", async ({ page }) => {
    const bodies = await mockChatAnswers(page, (count) => chatResponse({
      answer: count === 1 ? "Orders[Total Revenue] adds up Orders[Revenue]." : "Total Revenue sums Revenue.",
      evidence: [
        evidenceItem({ evidence_id: "E1", object_type: "measure", object_id: "Orders[Total Revenue]", display_value: "measure in table Orders; format #,0" }),
        evidenceItem({ evidence_id: "E2", object_type: "column", object_id: "Orders[Revenue]", object_name: "Revenue", fact_type: "dependency", display_value: "Orders[Revenue] (column, referenced directly)" }),
      ],
    }));

    await askFromHome(page, "Explain Total Revenue");

    const chip = page.getByRole("button", { name: "Orders[Total Revenue]", exact: true });
    await expect(chip).toBeVisible();
    await chip.hover();
    await expect(page.locator('[data-slot="tooltip-content"]')).toContainText("measure in table Orders; format #,0");

    await chip.click();

    await expect(page.getByText("Total Revenue sums Revenue.")).toBeVisible();
    await expect(page.getByText("Explain Orders[Total Revenue]", { exact: true })).toBeVisible();
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toMatchObject({ message: "Explain Orders[Total Revenue]", context: { object_type: "measure", object_name: "Orders[Total Revenue]" } });
  });

  test("the DAX copy button copies the exact original DAX", async ({ page }) => {
    await recordClipboard(page);
    const dax = ["VAR base = SUM(Orders[Revenue])", "RETURN", "    base * 1.1 // uplift"];
    await mockChatAnswers(page, () => chatResponse({
      answer: ["Definition", "- Total Revenue (measure in table Orders)", ...dax.map((line) => `    ${line}`)].join("\n"),
    }));

    await askFromHome(page, "Explain Total Revenue");
    await page.getByRole("button", { name: "Copy DAX" }).click();

    expect(await copiedText(page)).toBe(dax.join("\n"));
  });

  test("a long answer starts with its later sections collapsed, and 'Show full answer' opens them", async ({ page }) => {
    const titles = ["Definition", "Depends on (semantic model lineage)", "Reads from (database lineage)", "Measures and columns built on it", "Visual impact"];
    await mockChatAnswers(page, () => chatResponse({
      answer: ["Total Revenue adds up Revenue.", ...titles.flatMap((title) => ["", title, `- ${title} one`, `- ${title} two`])].join("\n"),
    }));

    await askFromHome(page, "Explain Total Revenue");

    const toggle = (title: string) => page.getByRole("button", { name: title, exact: true });
    await expect(toggle(titles[0])).toHaveAttribute("aria-expanded", "true");
    await expect(toggle(titles[1])).toHaveAttribute("aria-expanded", "true");
    for (const title of titles.slice(2)) await expect(toggle(title)).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("Visual impact one", { exact: true })).toHaveCount(0);

    await page.getByRole("button", { name: /Show full answer/ }).click();

    for (const title of titles) await expect(toggle(title)).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("Visual impact one", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Show full answer/ })).toHaveCount(0);
  });

  test("a non-answer says what it needs, with its suggestions as chips that send", async ({ page }) => {
    const bodies = await mockChatAnswers(page, (count) => count === 1
      ? chatResponse({
          status: "insufficient_evidence",
          answer: "I don't know which report you mean.",
          suggested_questions: ["Tell me about report Sales Overview", "How many reports do we have?"],
        })
      : chatResponse({ answer: "Sales Overview is a report in workspace 'Finance'." }));

    await askFromHome(page, "tell me about the report");

    await expect(page.getByText("I need a bit more to go on", { exact: true })).toBeVisible();
    await expect(page.getByText("Try one of these:")).toBeVisible();
    await page.getByRole("button", { name: "Tell me about report Sales Overview" }).click();

    await expect(page.getByText("Sales Overview is a report in workspace 'Finance'.")).toBeVisible();
    expect(bodies[1]).toMatchObject({ message: "Tell me about report Sales Overview" });
  });

  test("every reply offers Copy answer, Ask again and its follow-ups", async ({ page }) => {
    const bodies = await mockChatAnswers(page, () => chatResponse({ answer: "Total Revenue adds up Revenue.", suggested_questions: ["What depends on Total Revenue?"] }));

    await askFromHome(page, "Explain Total Revenue");

    await expect(page.getByRole("button", { name: "What depends on Total Revenue?" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy answer" })).toBeVisible();
    await page.getByRole("button", { name: "Ask again" }).click();
    await expect(page.getByText("Total Revenue adds up Revenue.")).toHaveCount(2);
    expect(bodies.map((body) => body.message)).toEqual(["Explain Total Revenue", "Explain Total Revenue"]);
  });
});

test.describe("Power AI — context chip", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("with nothing in context it says so", async ({ page }) => {
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await expect(page.getByTestId("power-ai-context")).toHaveText("Nothing selected - ask about a report or measure by name");
  });

  test("shows the page's report and model, then the answer's focus, and can be cleared", async ({ page }) => {
    await mockReportLineageBackend(page);
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    const bodies: Array<Record<string, any>> = [];
    await page.route("**/api/v1/ai/chat/stream", (route) => {
      bodies.push(route.request().postDataJSON());
      return route.fulfill(sseResponse({
        complete: chatResponse({
          answer: "Inventory Review is a report in workspace 'Operations'.",
          focus: { source: "question", workspace_name: "Operations", report_id: "r-2", report_name: "Inventory Review", semantic_model_name: "Inventory Model" },
        }),
      }));
    });

    await page.goto("/workspace/report-lineage");
    await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Open Power AI" }).click();

    const chip = page.getByTestId("power-ai-context");
    await expect(chip).toContainText("Report: Sales Overview · Model: Sales Model");
    await expect(chip.getByRole("img", { name: "From this page" })).toBeVisible();

    await page.getByPlaceholder("Ask Power AI...").fill("tell me about report Inventory Review");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(chip).toContainText("Report: Inventory Review · Model: Inventory Model");
    await expect(chip.getByRole("img", { name: "Named in your question" })).toBeVisible();

    await chip.getByRole("button", { name: "Clear context for the next question" }).click();
    await expect(chip).toHaveText("Nothing selected - ask about a report or measure by name");

    await page.getByPlaceholder("Ask Power AI...").fill("which measures are used?");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect.poll(() => bodies.length).toBe(2);
    expect(bodies[1].context.report_id).toBeUndefined();
    expect(bodies[1].context.semantic_model_id).toBeUndefined();
    expect(bodies[1].context.route).toBe("/workspace/report-lineage");
  });
});

test.describe("Power AI — reveal pacing", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  const longAnswer = Array.from({ length: 40 }, (_, index) => `Line ${index + 1} of a grounded answer that arrives in one burst.`).join("\n");

  for (const reducedMotion of ["reduce", "no-preference"] as const) {
    test(`with reduced motion '${reducedMotion}' the answer ${reducedMotion === "reduce" ? "appears at once" : "is revealed progressively"}`, async ({ page }) => {
      await page.emulateMedia({ reducedMotion });
      await page.addInitScript(() => {
        const seen: Array<[number, number]> = [];
        (window as unknown as { __reveals: typeof seen }).__reveals = seen;
        new MutationObserver(() => {
          document.querySelectorAll<HTMLElement>("[data-revealed]").forEach((element) => seen.push([Number(element.dataset.revealed), Number(element.dataset.total)]));
        }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-revealed"] });
      });
      await mockAiStatus(page, { status: 200, json: readyStatus() });
      await page.route("**/api/v1/ai/chat/stream", (route) =>
        route.fulfill(sseResponse({ deltas: [longAnswer.slice(0, 900), longAnswer.slice(900)], complete: chatResponse({ answer: longAnswer }) })),
      );

      await askFromHome(page, "Explain Total Revenue");
      await expect(page.getByText("Line 40 of a grounded answer that arrives in one burst.")).toBeVisible();

      const reveals = await page.evaluate(() => (window as unknown as { __reveals: Array<[number, number]> }).__reveals);
      const settled = reveals.filter(([, total]) => total === longAnswer.length);
      expect(settled.at(-1)).toEqual([longAnswer.length, longAnswer.length]);
      if (reducedMotion === "reduce") expect(reveals.every(([revealed, total]) => revealed === total)).toBe(true);
      else expect(settled.some(([revealed]) => revealed < longAnswer.length)).toBe(true);
    });
  }
});

test.describe("Power AI — survives responsive transitions", () => {
  test("a conversation started on desktop remains intact after resizing to mobile", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockAiStatus(page, { status: 200, json: readyStatus() });
    await page.route("**/api/v1/ai/chat/stream", (route) => route.fulfill(sseResponse({ deltas: ["Table impact analysis is ready."] })));

    await page.goto("/");
    await page.getByRole("button", { name: "Open Power AI" }).click();
    await page.getByPlaceholder("Ask Power AI...").fill("What changed?");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText("Table impact analysis is ready.")).toBeVisible();

    // The same widget stays open across the resize — no re-opening needed.
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByText("What changed?")).toBeVisible();
    await expect(page.getByText("Table impact analysis is ready.")).toBeVisible();
  });
});

function readyStatus(overrides: Partial<{ enabled: boolean; configured: boolean; streaming_enabled: boolean; provider: string; model: string }> = {}) {
  return { enabled: true, configured: true, streaming_enabled: true, provider: "openai", model: "gpt-4o", ...overrides };
}

type EvidenceFixture = Record<string, unknown>;

/** One evidence item exactly as the backend sends it: every nullable field present, as null. */
function evidenceItem(overrides: EvidenceFixture = {}): EvidenceFixture {
  return {
    evidence_id: "E1",
    object_type: "measure",
    object_id: null,
    object_name: "Total Revenue",
    fact_type: "definition",
    source_type: "tmdl",
    value: null,
    plain_language: null,
    display_value: null,
    workspace_id: null,
    report_id: null,
    semantic_model_id: null,
    verification_status: "verified",
    retrieved_at: "2026-09-24T09:30:00Z",
    source_reference: null,
    ...overrides,
  };
}

type ChatResponseFixture = {
  conversation_id: string;
  status: string;
  answer: string;
  claims: Array<{ text: string; evidence_ids: string[] }>;
  evidence: EvidenceFixture[];
  agent: string | null;
  suggested_questions: string[];
  tool_trace: Array<Record<string, unknown>>;
  usage: { provider: string; model: string; tokens: number } | null;
  /** Newer backends only; left out, as older ones do, unless a test sets it. */
  focus?: Record<string, unknown> | null;
};

/** A full AiChatResponse, the shape of `/chat`, `/explain` and the stream's `complete` event. */
function chatResponse(overrides: Partial<ChatResponseFixture> = {}): ChatResponseFixture {
  return {
    conversation_id: "conv-1",
    status: "answered",
    answer: "",
    claims: [],
    evidence: [],
    agent: null,
    suggested_questions: [],
    tool_trace: [],
    usage: null,
    ...overrides,
  };
}

function sseFrame(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/**
 * The backend's real stream, frame for frame — these mirror
 * `app/ai/services/streaming.py` in PBI-Lineage-Backend: metadata, then the
 * evidence, then one `{text, delta}` frame per chunk, then the full response
 * as `complete`. Mocks written to what the frontend expected instead of this
 * are how an empty-bubble bug once passed every test.
 */
function sseResponse(options: { deltas?: string[]; complete?: ChatResponseFixture }) {
  const deltas = options.deltas ?? [];
  const complete = options.complete ?? chatResponse({ answer: deltas.join("") });
  const frames = [
    sseFrame("metadata", {
      conversation_id: complete.conversation_id,
      status: complete.status,
      agent: complete.agent,
      ...(complete.focus !== undefined ? { focus: complete.focus } : {}),
    }),
    sseFrame("evidence", { evidence: complete.evidence }),
    ...deltas.map((text) => sseFrame("delta", { text, delta: text })),
    sseFrame("complete", complete),
  ];
  return { contentType: "text/event-stream", body: frames.join("") };
}

/** On failure the backend's only frame is an error; `error` duplicates `message`. */
function sseErrorResponse(error: { code: string; message: string; reason: string }) {
  return { contentType: "text/event-stream", body: sseFrame("error", { code: error.code, message: error.message, error: error.message, reason: error.reason }) };
}

async function askFromHome(page: Page, question: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open Power AI" }).click();
  await page.getByPlaceholder("Ask Power AI...").fill(question);
  await page.getByRole("button", { name: "Send message" }).click();
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

async function copiedText(page: Page) {
  await expect.poll(() => page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.length)).toBeGreaterThan(0);
  return page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1));
}

/** Non-streaming chat: each request is answered by `respond(n)`, n counting from 1. Returns the posted bodies. */
async function mockChatAnswers(page: Page, respond: (count: number) => ChatResponseFixture) {
  const bodies: Array<Record<string, any>> = [];
  await mockAiStatus(page, { status: 200, json: readyStatus({ streaming_enabled: false }) });
  await page.route("**/api/v1/ai/chat", (route) => {
    bodies.push(route.request().postDataJSON());
    return route.fulfill({ json: respond(bodies.length) });
  });
  return bodies;
}

/** Report lineage on its Database mapping section, with `/ai/explain` answered by `respond`. */
async function openMeasurePanel(page: Page, respond: (body: Record<string, unknown>) => ChatResponseFixture) {
  await mockReportLineageBackend(page);
  await mockAiStatus(page, { status: 200, json: readyStatus() });
  await page.route("**/api/v1/ai/explain", (route) => route.fulfill({ json: respond(route.request().postDataJSON()) }));
  await page.goto("/workspace/report-lineage");
  await expect(page.getByRole("heading", { name: "Report lineage" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Database mapping", exact: true }).click();
  await expect(page.getByText("Measure definition with Power AI")).toBeVisible();
}

const contextSentence = "Total Revenue is a measure in table Orders of semantic model 'Sales Model' (workspace 'Finance').";

/** A measure dossier in the backend's order — deliberately not section order, so grouping is exercised. */
const dossierEvidence = [
  evidenceItem({ evidence_id: "E1", object_type: "context", object_id: "Orders[Total Revenue]", fact_type: "relationship", value: { table: "Orders" }, display_value: contextSentence }),
  evidenceItem({ evidence_id: "E2", object_type: "measure", object_id: "Orders[Total Revenue]", fact_type: "definition", value: "SUM(Orders[Revenue])", plain_language: "Total Revenue adds up Revenue.", display_value: "measure in table Orders; format #,0", source_reference: "definition/tables/Orders.tmdl" }),
  evidenceItem({ evidence_id: "E3", object_type: "visual", object_name: "Margin Card", fact_type: "impact", source_type: "pbir", value: { visual_type: "card" }, display_value: "Report 'Sales Overview' > page 'Overview' > 'Margin Card' (card) (through Profit Margin %)" }),
  evidenceItem({ evidence_id: "E4", object_type: "physical_source", object_name: "PBI_DB.MART.V_ORDERS", fact_type: "source", source_type: "snowflake", value: { columns: ["REVENUE"] }, display_value: "Snowflake view PBI_DB.MART.V_ORDERS -> semantic table Orders (columns: REVENUE)" }),
  evidenceItem({ evidence_id: "E5", object_type: "coverage", object_name: "Visual impact", fact_type: "relationship", source_type: "other", value: { reports_checked: 1 }, display_value: "Visual impact was checked in 1 report: 'Sales Overview'. 1 visual would be affected." }),
];

const measureAnswer = [
  contextSentence,
  "",
  "In plain English",
  "Total Revenue adds up Revenue.",
  "",
  "Definition",
  "- Total Revenue (measure in table Orders; format #,0)",
  "    SUM(Orders[Revenue])",
].join("\n");

/** A full measure dossier: one item for every lineage layer, plus a table it affects and coverage. */
const panelEvidence = [
  dossierEvidence[0],
  dossierEvidence[1],
  evidenceItem({ evidence_id: "E3", object_type: "column", object_id: "Orders[Revenue]", object_name: "Revenue", fact_type: "dependency", value: { qualified_name: "Orders[Revenue]", distance: 1 }, display_value: "Orders[Revenue] (column, referenced directly)" }),
  evidenceItem({ evidence_id: "E4", object_type: "physical_source", object_name: "V_ORDERS", fact_type: "source", source_type: "snowflake", value: { database: "PBI_DB", schema_name: "MART", object_name: "V_ORDERS", columns: ["REVENUE"] }, display_value: "Snowflake view PBI_DB.MART.V_ORDERS -> semantic table Orders (columns: REVENUE)" }),
  evidenceItem({ evidence_id: "E5", object_type: "measure", object_id: "Orders[Profit Margin %]", object_name: "Profit Margin %", fact_type: "impact", value: { qualified_name: "Orders[Profit Margin %]", distance: 1 }, display_value: "Orders[Profit Margin %] (measure, referenced directly)" }),
  evidenceItem({ evidence_id: "E6", object_type: "semantic_table", object_id: "Orders", object_name: "Orders", fact_type: "impact", value: { table: "Orders" }, display_value: "Orders: Total Revenue, Profit Margin % depend on it" }),
  evidenceItem({ evidence_id: "E7", object_type: "visual", object_name: "Margin Card", fact_type: "impact", source_type: "pbir", value: { report: "Sales Overview", page: "Overview", visual_type: "card" }, display_value: "Report 'Sales Overview' > page 'Overview' > 'Margin Card' (card) (through Profit Margin %)" }),
  evidenceItem({ evidence_id: "E8", object_type: "coverage", object_name: "Coverage", fact_type: "relationship", source_type: "other", display_value: "Visual impact was checked in 1 report: 'Sales Overview'. 1 visual would be affected." }),
];

/** The deterministic renderer's layout for `panelEvidence`. */
const panelAnswer = [
  contextSentence,
  "",
  "In plain English",
  "Total Revenue adds up Revenue.",
  "",
  "Definition",
  "- Total Revenue (measure in table Orders; format #,0)",
  "    SUM(Orders[Revenue])",
  "",
  "Depends on (semantic model lineage)",
  "- Orders[Revenue] (column, referenced directly)",
  "",
  "Reads from (database lineage)",
  "- Snowflake view PBI_DB.MART.V_ORDERS -> semantic table Orders (columns: REVENUE)",
  "",
  "Measures and columns built on it",
  "- Orders[Profit Margin %] (measure, referenced directly)",
  "",
  "Tables affected",
  "- Orders: Total Revenue, Profit Margin % depend on it",
  "",
  "Visual impact",
  "- Report 'Sales Overview' > page 'Overview' > 'Margin Card' (card) (through Profit Margin %)",
  "",
  "What was checked",
  "- Visual impact was checked in 1 report: 'Sales Overview'. 1 visual would be affected.",
].join("\n");

/**
 * The pre-rendered SPA shell already shows the launcher as "Power AI is locked"
 * (no status yet), and a click on it before hydration is lost. Only a hydrated
 * client requests the status, so its response means the launcher is live.
 */
async function gotoAfterAiStatus(page: Page, path: string) {
  const statusLoaded = page.waitForResponse("**/api/v1/ai/status");
  await page.goto(path);
  await statusLoaded;
}

async function mockAiStatus(page: Page, response: { status: number; json: unknown }) {
  await page.route("**/openapi.json", (route) => route.fulfill({ json: { openapi: "3.1.0", info: { title: "PBI Lineage", version: "1" }, paths: {} } }));
  await page.route("**/api/v1/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/v1/ai/status", (route) => route.fulfill({ status: response.status, json: response.json }));
}

/** Picks one semantic table in Table impact's single "Tables" search, then closes the list. */
async function selectSemanticTable(page: Page, tableName: string) {
  await page.getByRole("button", { name: "Tables", exact: true }).click();
  await page.getByPlaceholder("Search semantic tables or database tables...").fill(tableName);
  await page
    .getByRole("group", { name: /^Semantic tables \(\d+\)$/ })
    .getByRole("option")
    .filter({ has: page.getByText(tableName, { exact: true }) })
    .click();
  await expect(page.getByRole("list", { name: "Selected tables" }).getByRole("listitem")).toHaveCount(1);
  await page.getByRole("button", { name: "Done", exact: true }).click();
}

async function mockTableImpactBackend(page: Page) {
  await page.route("**/api/v1/workspaces?top=100&skip=0", (route) => route.fulfill({ json: { workspaces: [{ id: workspaceId, name: "Finance" }] } }));
  await page.route("**/api/v1/workspaces/*/semantic-models", (route) => route.fulfill({ json: { semantic_models: [{ id: modelId, name: "Sales Model" }] } }));
  await page.route("**/api/v1/workspaces/*/semantic-models/*/definition/parsed**", (route) => route.fulfill({ json: parsedModel }));
  await page.route("**/api/v1/lineage/dax/analyze", (route) => route.fulfill({ json: { objects: [], dependencies: [], warnings: [], object_count: 2, dependency_count: 0 } }));
  await page.route("**/api/v1/lineage/estate/discover**", (route) => route.fulfill({ json: { workspaces: [], graph: { nodes: [], edges: [] }, warnings: [], workspace_count: 0, report_count: 0, semantic_model_count: 0 } }));
}

/**
 * Report lineage over one report whose model lives in another workspace. One
 * handler for every lineage read; Power AI routes fall through to their own mocks.
 */
async function mockReportLineageBackend(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/v1/ai/")) return route.fallback();
    if (path.includes("/lineage/estate/discover")) return route.fulfill({ json: lineageEstate });
    if (path.endsWith("/explorer/snapshot")) return route.fulfill({ json: lineageSnapshot });
    if (path.endsWith("/pages")) return route.fulfill({ json: { pages: [{ name: "overview", display_name: "Overview", order: 0 }] } });
    if (path.endsWith(`/reports/${reportId}`)) return route.fulfill({ json: lineageReport });
    return route.fulfill({ json: {} });
  });
}

const lineageReport = { id: reportId, name: "Sales Overview", dataset_id: modelId, dataset_workspace_id: modelWorkspaceId, report_type: "PowerBIReport", format: "PBIR" };

const lineageEstate = {
  workspaces: [
    { workspace: { id: workspaceId, name: "Finance" }, reports: [lineageReport], semantic_models: [], report_bindings: [{ report_id: reportId, semantic_model_id: modelId, status: "matched" }] },
    { workspace: { id: modelWorkspaceId, name: "Shared Models" }, reports: [], semantic_models: [{ id: modelId, name: "Sales Model" }], report_bindings: [] },
  ],
  graph: {
    nodes: [
      { node_id: "report-node", node_type: "report", name: "Sales Overview", workspace_id: workspaceId, report_id: reportId },
      { node_id: "model-node", node_type: "semantic_model", name: "Sales Model", workspace_id: modelWorkspaceId, semantic_model_id: modelId },
    ],
    edges: [{ source_id: "report-node", target_id: "model-node" }],
  },
  warnings: [],
  workspace_count: 2,
  report_count: 1,
  semantic_model_count: 1,
};

const lineageRowContext = { workspace_id: workspaceId, workspace_name: "Finance", report_id: reportId, report_name: "Sales Overview", semantic_model_id: modelId };

const lineageSnapshot = {
  warnings: [],
  semantic_model_objects: {
    count: 2,
    rows: [
      { ...lineageRowContext, semantic_table: "Orders", semantic_object_type: "column", semantic_object_name: "Revenue", semantic_data_type: "decimal", semantic_source_column: "REVENUE", semantic_dax_expression: null },
      { ...lineageRowContext, semantic_table: "Orders", semantic_object_type: "measure", semantic_object_name: "Total Revenue", semantic_data_type: null, semantic_source_column: null, semantic_dax_expression: "SUM(Orders[Revenue])" },
    ],
  },
  measure_source_lineage: { count: 1, rows: [{ semantic_table: "Orders", semantic_object_name: "Total Revenue", source_column_name: "REVENUE", source_fully_qualified_name: "PBI_DB.MART.V_ORDERS" }] },
  source_database_lineage: { count: 1, rows: [{ semantic_table: "Orders", source_fully_qualified_name: "PBI_DB.MART.V_ORDERS" }] },
};

const parsedModel = {
  workspace_id: workspaceId,
  semantic_model_id: modelId,
  format: "TMDL",
  tables: [{
    name: "Sales",
    source_path: "ANALYTICS.PUBLIC.SALES",
    expression: null,
    columns: [{ name: "Amount", source_path: "ANALYTICS.PUBLIC.SALES", source_column: "AMOUNT", data_type: "decimal", expression: null }],
    measures: [{ name: "Total Sales", expression: "SUM(Sales[Amount])" }],
    hierarchies: [],
  }],
  relationships: [],
  warnings: [],
};
