# Features and Data Flows

## Application flow

```
Home
  -> animated walkthrough of the application's screens
  -> Setup Guide from the header Documents menu, the footer, or Home's button
       -> Entra app, service principal, workspace roles, Scanner, Snowflake read role
  -> Start
  -> Power BI setup
       -> device-code session OR service-principal session
       -> Power BI and Fabric readiness
  -> Database setup
       -> optional source-system session (currently Snowflake)
  -> Overview
       -> totals: workspaces / reports / semantic models
       -> any listed item -> Explorer with that item selected
  -> Explorer
       -> workspace -> report or semantic model
       -> report detail / semantic objects / mappings / diagrams
  -> Report Lineage
       -> report selected across the whole estate
       -> snapshot evidence tabs
       -> report / column / calculation diagrams
  -> Table Impact
       -> one search: semantic model tables | database tables (multi-select)
       -> tiles and the impact graph (database table -> ... -> visuals)
       -> reports / visuals / semantic models / measures grids, copyable and exportable
  -> Measure Impact
       -> workspace scope -> one measure
       -> tiles and the same impact graph
       -> tables / impacted measures / semantic model / reports / visuals / inputs grids
  -> API reference (header Documents menu)
       -> OpenAPI group and operation
       -> parameters and JSON body
       -> authenticated execution
       -> response body and headers
```

## Static Setup Guide

`app/routes/setup-guide.tsx` and
`app/components/setup-guide/setup-guide.tsx` render `/setup-guide`.
The guide performs no provider requests. Its scope is identities and access
only: how to create what the application signs in with, not how to host the
backend (that lives in the backend repository). It covers:

- the device-code app registration (public client flows, the four portal
  permissions behind the five delegated scopes the backend requests, and
  admin consent — required because the Fabric token is acquired silently);
- a separate service-principal app (no API permissions, client secret, security
  group, the "Service principals can call Fabric public APIs" tenant setting);
- a feature-by-feature workspace access table (Viewer for inventory and pages,
  Contributor for PBIR/TMDL definitions because Fabric `getDefinition` needs
  read and write on the item, gateway admin, XMLA Build);
- the Admin Scanner tenant settings;
- a copyable Snowflake script creating `LINEAGE_READER`: warehouse usage,
  `USAGE`/`SELECT` on all and future schemas and objects in each database,
  `IMPORTED PRIVILEGES` on `SNOWFLAKE` (ACCOUNT_USAGE incl. `ACCESS_HISTORY`),
  `VIEW LINEAGE`, a narrower `OBJECT_VIEWER`/`GOVERNANCE_VIEWER` alternative,
  a `TYPE = SERVICE` key-pair user, and verification queries;
- verification, troubleshooting, and official Microsoft/Snowflake references.

Wide tables and code examples scroll inside their containers rather than
widening mobile pages. It is reached from the header's Documents menu, the
footer, and Home's Setup guide button; the workspace sidebar does not link it.

## Home

`app/routes/home.tsx` renders `/` as a database-neutral product overview. Its
center is an animated walkthrough that clicks through the application's
screens in order: Power BI setup, Database, Overview, Explorer, Report
lineage, Table impact, Measure impact, Power AI, and the Documents menu (Setup
guide, API reference), with a caption for each step.
`public/how-to-use-light.gif` or `public/how-to-use-dark.gif` is shown to match
the active theme, and a still PNG poster replaces the animation when the viewer
prefers reduced motion. The recording uses fictional sample data only; it
replaced the static `public/product-lineage-view.png` capture. The page also
explains the investigation questions and evidence path at a high level and
offers a primary Start exploring action plus a Setup guide button. Navigation
links stay in the shared header and footer. Home disables the backend health
query because no connection is needed to read the overview. Regenerating the
walkthrough is covered in
[06-testing-and-deployment.md](06-testing-and-deployment.md#home-walkthrough-assets).

## Authentication and session behavior

### Device code (`app/components/workspace/power-bi-setup.tsx`)

1. Form posts tenant/client IDs to `POST /api/v1/auth/microsoft/device/start`.
2. Backend returns the Microsoft verification URL, user code, session ID.
3. Frontend polls/checks device session status
   (`GET /api/v1/auth/microsoft/device/{session_id}/status`).
4. FastAPI stores provider tokens server-side and sets the session cookie.

### Service principal

1. Form posts tenant ID, client ID, client secret to
   `POST /api/v1/auth/microsoft/service-principal/session`.
2. Power BI and Fabric application-token readiness are shown independently;
   status may be `authenticated` or `partial`.
3. The frontend clears the client secret field immediately after submission
   and never persists it (not in Zustand, not in query cache).

### Snowflake (`app/components/workspace/database-setup.tsx`)

Create/check/delete a backend Snowflake session
(`POST`/`GET`/`DELETE /api/v1/auth/snowflake/session[...]`). Optional
enrichment only — it does not replace Power BI estate discovery.

### Shared request rules

- All requests use `credentials: "include"` so the HTTP-only backend cookie
  is sent (`app/lib/use-api-executor.ts`).
- An optional administrative key lives only in Zustand memory
  (`useAppStore().adminKey`) and is attached by the shared executor as
  `X-Lineage-Admin-Key`. There is **no visible UI field** for it by design —
  it's meant to be set only by an approved host integration.
- Sensitive fields (password/secret/token/private-key/passcode) typed into
  the API-documentation JSON editor are cleared after execution.
- Successful Power BI auth invalidates Explorer/Report Lineage TanStack Query
  caches; logout removes those cached datasets.

## Overview (`app/components/workspace/overview.tsx`)

`/workspace/overview`, the first sidebar item after setup, answers "what can
this account open?" and is a jumping-off point into Explorer. It reads only two
cache entries other pages already share, so opening it never fans out per
workspace:

- The workspace list (`workspaceListKey`, `WORKSPACE_LIST_PATH` =
  `GET /api/v1/workspaces?top=100&skip=0`), shared with Explorer, Scanner, and
  both impact pages.
- Estate discovery (`estateDiscoveryKey`, `ESTATE_DISCOVER_PATH` =
  `GET /api/v1/lineage/estate/discover?top=5000&skip=0`), shared with Report
  Lineage and both impact pages. It is enabled only after the workspace list
  succeeds.

The workspace list is the page's universe, because Explorer can only open
workspaces from that list; each workspace's reports and semantic models come
from its estate-discovery entry. Everything is sorted by name.

1. **Totals**: three tiles (Workspaces, Reports, Semantic models). Each value
   counts up once from zero. The count-up is skipped under reduced motion, and
   assistive technology reads only the settled value.
2. **Three sections**: Workspaces (each with its report and semantic-model
   counts), Reports grouped by workspace, and Semantic models grouped by
   workspace. They sit side by side on large screens and stack vertically on
   smaller ones. Each section has a count badge and a filter box ("Filter
   workspaces", "Filter reports", "Filter semantic models"). A filter that
   matches a workspace name keeps that workspace's whole group; otherwise only
   items whose own name matches remain.
3. **Links**: every item is a link built with `explorerHref`. A workspace
   opens Explorer on that workspace, a report opens it on that report, and a
   semantic model opens the Semantic objects section of a report bound to it
   (see [Deep links](#deep-links)).

States degrade honestly. While the workspace list loads, a loading panel
shows. If it fails, the page shows `PowerBiAuthRequired`, and an empty list
shows "No Power BI workspaces found". While estate discovery loads, the
Reports and Semantic models totals, their lists, and the per-workspace counts
show skeletons. If estate discovery fails, the Workspaces tile and list still
work, the other two totals read "—", and their sections show "Reports could
not be loaded" / "Semantic models could not be loaded" with the error and a
pointer to Explorer. Motion is minimal and uses the theme's colors: blocks
fade and slide in with a short stagger (`motion-safe:` Tailwind `animate-in`
utilities), and a link's chevron nudges right and takes the brand color on
hover.

## Explorer (`app/components/workspace/explorer.tsx`, ~920 lines)

Workspace-scoped investigation, entry point `GET /api/v1/workspaces`. Names
are the primary UI identity; IDs are shown only as supporting context below a
selected name.

Levels, in order of drill-down:

1. Workspace assets and access.
2. Report detail and pages.
3. Report-specific semantic lineage.
4. Semantic tables, columns, measures, hierarchies, relationships, DAX.
5. Database-column → semantic-object mapping.
6. Column/measure dependency diagrams (React Flow).

Heavy report/semantic-model requests fire only after selection and are
cached via `heavyQueryOptions` (`staleTime: 5 min`, `gcTime: 30 min`,
`retry: false`) so tabs reuse prepared data instead of re-fetching. Domain
types (`Workspace`, `Report`, `SemanticModel`, `ParsedColumn`, ...) are
defined locally in the component, matching backend response shapes.

### Deep links

Explorer reads three optional search params once, when it mounts, to seed its
first selection:

- `?workspace=<id>` selects that workspace.
- `?report=<id>` also opens the Reports tab on that report.
- `?model=<id>` opens the Reports tab's Semantic objects section on the first
  report in the workspace bound to that model (`dataset_id`). If no report
  there uses it, Explorer falls back to Assets & access.

After that the selectors own the state, and changing a selection does not
rewrite the URL. An unknown ID falls back to Explorer's usual first-workspace
and first-report defaults. With no params, Explorer behaves exactly as before.
`explorerHref` in `app/lib/workspace-routes.ts` builds these URLs for
Overview.

**Important invariant**: a report can use a semantic model owned by a
*different* workspace. Never assume the report's workspace ID applies to its
model — the model's own workspace ID must be used unless estate evidence
confirms the model is local to the report's workspace.

## Report Lineage (`app/components/workspace/report-lineage.tsx` +
`report-lineage-diagrams.tsx`)

Cross-workspace, report-first view.

1. `GET /api/v1/lineage/estate/discover?top=5000&skip=0` returns an
   `EstateResponse`: reports from every accessible workspace, a
   `workspaces[]` inventory (each with `report_bindings` marking
   `matched`/`unresolved` semantic-model links), and a `graph` of
   `EstateNode`/edges for composite-model resolution.
2. The report selector shows `report name - workspace name`; the report ID
   appears only after selection.
3. `POST /api/v1/explorer/snapshot` prepares an `ExplorerSnapshot`: physical
   source rows, semantic-model object rows, measure/column dependency rows,
   report layout rows, and visual-source-lookup rows for the selected
   report — see the row types at the top of `report-lineage.tsx` for exact
   fields (`SourceRow`, `SemanticObjectRow`, `MeasureSourceRow`,
   `ReportLayoutRow`, `VisualSourceRow`).
4. Parsed TMDL and exact DAX dependency analysis load in the background.
5. Snapshot and exact-dependency results are cached for 10 minutes.

Evidence tabs: report information, database objects, semantic objects/DAX,
visual objects/pages/roles/fields, semantic source mapping, visual source
mapping, and lineage diagrams.

Diagram modes (`report-lineage-diagrams.tsx`, React Flow):

- **Report/database**: physical source → semantic table → semantic model →
  report → page → optional visual expansion.
- **Column lineage**: source evidence → selected semantic column →
  calculations that use it, 1–6 levels deep.
- **Measure/calculated column**: upstream inputs → selected target →
  downstream dependents, 1–6 levels deep.

React Flow stays mounted while graph identity changes. Once ELK finishes a
layout, the viewport API fits the visible nodes without discarding React Flow's
interaction state; a reset-layout control restores automatic positions after
manual dragging.

## Shared Lineage Diagram Engine

Explorer, Report Lineage, Table Impact, and Measure Impact build the same
`LineageGraph` contract and render it through
`app/components/workspace/lineage/lineage-diagram.tsx`. ELK computes layered
left-to-right or top-to-bottom positions in a Web Worker, React Flow renders
directed arrowheads and draggable nodes, and each custom node can collapse or
restore its descendants. Large graphs cull offscreen elements and avoid costly
edge animation; their initial viewport favors the target's nearest nodes while
the standard Fit View control remains available for the complete graph.
`app/lib/dependency-graph.ts` provides the shared breadth-first dependency
closure used to turn DAX references into those graphs.

`LineageDiagram` also takes an optional `defaultCollapsedKinds` prop: node
kinds that start collapsed, each with a +N badge, whenever the graph changes.
It is keyed by the kinds' content rather than the array's identity, so an
inline array does not reset the user's expansions on every render. The impact
graph passes `["report"]`.

## Impact Evidence

`app/lib/impact-analysis.ts` holds the report evidence both impact pages join
to their DAX closure. For each semantic model in play:

1. Estate discovery (`estateDiscoveryKey`), requested once a table or measure
   is selected, supplies the model's bound reports through
   `boundReportsForModel`, plus report names and workspaces.
2. `fetchImpactEvidence` posts those reports to
   `POST /api/v1/explorer/visual-source-lookup` through `fetchBatchedExplorer`
   (50 reports per request, first 300 bound reports per model). The query key
   is `impactEvidenceKey(page, apiOrigin, semanticModelId, reports)`, which is
   `[page, "visual-evidence", apiOrigin, semanticModelId, reportIds]`. The
   `visual-evidence` segment keeps it apart from cache entries of the older
   two-call shape.
3. `buildEvidenceIndex` keeps the `matched` rows that name a semantic object
   and indexes them by `evidenceKey` (`table[name]`, lowercased): which
   reports and which visuals read each object. It also records each report's
   name and workspace and each visual's page, name, and type, falling back to
   IDs (and "Visual") when a row leaves them out.
4. `buildReportNames` names reports from the estate first (each workspace's
   `reports[]`, then its bindings by ID) and fills any ID-only name from the
   evidence rows.

Visual evidence is the only usage signal: a report uses an object when one of
its visuals reads that object. `POST /api/v1/explorer/measure-source-lineage`
is no longer called. It lists every measure of the bound model for every bound
report, whether or not any visual shows it, so it made every bound report look
like it used every measure. Dropping it also saves one Explorer call per model
(per 50-report batch).

The module also holds `SourcedTable` (a parsed table with the `source_path` on
the table and its columns, which the shared `ParsedTable` type leaves out),
`tableSources` (the distinct physical sources behind a table, compared without
case), `tableSeeds` (every column, calculated column, and measure, plus the
table itself when it is calculated), `displayType`, and `EstateWithReports`.

## Impact Graph

`app/components/workspace/impact-lineage.tsx` draws the graph on both impact
pages. `buildImpactGraph` takes one scope per semantic model (focal objects,
closure members, the model's DAX dependencies, its evidence index, and the
physical sources per table) and returns one directed graph that reads top to
bottom:

```text
Database table --+
Semantic model --+--> Semantic table -> columns -> measures -> Reports -> Visuals
```

- A database table and the semantic model each point at a semantic table. A
  table points at its columns and measures. DAX edges run from each
  referenced object to the object that reads it. An object points at every
  report whose visuals read it, and a report points at those visuals.
- Object and table node IDs are namespaced by model (`<model key>|...`)
  because DAX reference keys are unique only within one model.
  Database-table nodes (`db|<PATH>`) and report nodes (`report|<id>`) are
  shared, so a physical table behind two models is one node.
- A focal object (a selected table's column or measure) is drawn only when a
  DAX edge links it to another drawn object or a visual reads it, so a
  table's unused columns stay out of the graph. A lone focal object (Measure
  Impact's measure) is always drawn.
- The selected tables (Table Impact) or the selected measure (Measure
  Impact) carry the focal ring.

`ImpactLineageDiagram` renders it with the same `LineageDiagram` settings as
Explorer's Snowflake table lineage: ELK top-to-bottom layout
(`direction="TB"`), animated edges in the app teal
(`edgeColor="var(--fabric-primary)"`), 20 px node and 44 px rank separation,
the focal ring, draggable nodes, per-node collapse and expand, reset layout,
and a tall canvas (760 px, at least 520 px). The Snowflake trace flows up
toward its sources; the impact graph flows down (`verticalFlow="down"`,
`collapseDirection="downstream"`) because impact reads from source to
consumer. A legend under the canvas lists the node kinds present.

Reports start collapsed (`defaultCollapsedKinds={["report"]}`), each with a +N
badge counting its hidden visuals. Clicking one expands it. This keeps a wide
fan-out of visuals from shrinking the whole graph. The graph also draws at
most 40 reports (ranked by visuals, then objects read) and 120 visuals.
Beyond that, a notice says how many reports and visuals were not drawn; the
grids always list every one.

## Table Impact

`app/components/workspace/table-impact.tsx` shows what uses any number of
tables at once, across every workspace. There is no workspace scope, column,
or direction control. The inventory always covers the whole workspace list, a
table is always analyzed whole, and traversal is always downstream.

**Search.** `fetchEstateInventory` parses every semantic model in every listed
workspace (`estateInventoryKey`). Inaccessible models are skipped and counted
in a status bar with a Refresh inventory button. One search box,
`MultiObjectSearch` from `impact-picker.tsx` (trigger "Tables", placeholder
"Search semantic model or database tables..."), shows two separate groups as
side-by-side columns, stacked on narrow screens:

- **Semantic model tables (N)**: each parsed table as
  table · model · workspace, plus `from <source>` when its definition names
  one.
- **Database tables (N)**: each distinct physical `source_path` on a parsed
  table or its columns, compared without case, listing the semantic tables
  behind it.

Every typed word must match. Matches are ranked by how well the name fits
the query (exact name, name prefix, a name segment starting with it, name
containing it, then matches on model/workspace/source text only), and each
group shows its first 100 after ranking, so a name match never hides behind
model or workspace matches. Clicking an entry toggles it and keeps the list
open. Picks show as removable chips tagged "Model" or "Database". A semantic
chip reads `Table (Model)`, so the same table name in two models stays
distinguishable. Clear and Done close out.

**Analysis.** A database table expands to every semantic table sourced from
it, in any model. Each semantic table seeds all its columns and measures,
plus the table itself when it is a calculated table (`tableSeeds`). DAX
reference keys are unique only within a model, so the rest runs per model:

1. `POST /api/v1/lineage/dax/analyze` for each touched model, through
   `useQueries` on the shared `daxAnalysisKey`. The request body is the
   parsed definition the inventory already holds, and a model Measure Impact
   already analyzed comes from the cache. `computeDependencyClosure` walks
   each table's downstream closure inside its model.
2. Visual evidence for each model with bound reports, as described in
   [Impact Evidence](#impact-evidence).

A report or visual uses the selection when a visual reads a selected table's
own column or measure ("Reads table fields") or anything in its downstream
DAX closure ("Through measures"). Measures are the closure's measure hops at
their shallowest depth: Direct at depth 1, otherwise Transitive.

**Results.** Two status bands report exact-DAX readiness and evidence
coverage. While estate discovery loads, the evidence band says it is finding
the bound reports rather than flashing "no reports bound". Four tiles count
Reports, Visuals, Semantic models, and Measures. The
[impact graph](#impact-graph) follows and covers every model in the selection
(titled `<Table> impact` for one table, `Impact of N tables` otherwise). Then
four `ImpactGrid`s, each sized to its rows (`fitRows`), with Copy table, CSV,
Excel, and per-cell copy:

| Grid | Columns on screen | Also in copies and exports |
| --- | --- | --- |
| Reports using the selected tables | Report, Workspace, Semantic model, Selected tables, Usage, Pages, Visuals, Objects used | Report ID, Semantic model ID |
| Visuals using the selected tables | Visual, Visual type, Page, Report, Workspace, Usage, Fields used | Selected tables, Report ID, Visual key |
| Semantic models | Semantic model, Workspace, Selected tables, Database tables, Measures, Reports using, Reports bound | Semantic model ID, Workspace ID |
| Measures using the selected tables | Measure, Semantic model, Workspace, Selected tables, Relationship, Depth, DAX reference, Reports, Visuals | Semantic model ID |

Every copy and export also starts with a `selected_tables` column. When the
resolved selection is exactly one semantic table, Ask Power AI appears and
receives it as context, and the graph uses that table as its focus node.

**Degradation.** A failed workspace list shows `PowerBiAuthRequired`, and a
failed inventory says so in the status bar. A model whose DAX analysis fails
is named in a warning. It adds no measures, and only direct reads of its
tables count as report usage. Failed estate discovery warns that report and
visual usage cannot be computed while the dependency results stay accurate.
The Reports and Visuals grids then say usage is unavailable, and the Semantic
models and Measures grids stay accurate. While usage is still being checked,
the Reports and Visuals grids read "Checking reports...". No bound reports,
the 300-report cap, and a dropped 50-report batch never block the page.

## Measure Impact

`app/components/workspace/measure-impact.tsx` answers "what does this measure
touch?" for one measure.

**Selection.** A "Workspace scope" multi-select (`WorkspaceScopeSelect`,
every workspace checked by default) scopes the inventory
(`fetchEstateInventory` under `estateInventoryKey`, the same entry Table
Impact reads at the all-workspaces default). One "Measure" search
(`ObjectSearchSelect`, entries `Table[Measure]` with model and workspace
beneath) picks the measure, and the first indexed measure is selected
automatically. A status bar counts indexed measures and skipped models and
offers Refresh inventory.

**Analysis.** Everything runs in the measure's one model:

1. `POST /api/v1/lineage/dax/analyze` on the shared `daxAnalysisKey`, posting
   the parsed definition. `computeDependencyClosure` returns upstream inputs
   (the columns, calculated columns, and measures it reads) and downstream
   dependents (the measures and calculated columns built on it) in one pass.
2. Visual evidence for the model's bound reports, as described in
   [Impact Evidence](#impact-evidence). A report or visual uses the measure
   when a visual shows the measure itself ("Shows the measure") or anything
   in its downstream closure ("Through impacted measures").

**Results.** The exact-DAX and evidence bands come first, then five tiles:
Tables, Measures impacted, Semantic models, Reports, and Visuals. Ask Power AI
("Explain this measure") sends the measure as context. The
[impact graph](#impact-graph) shows the database tables and semantic model
feeding the tables and columns it reads, the measure itself (focal), the
measures depending on it, and the reports and visuals that show them. Six
`fitRows` grids follow, all with Copy table, CSV, Excel, and per-cell copy:

| Grid | What it lists | Columns on screen | Also in copies and exports |
| --- | --- | --- | --- |
| Tables | The measure's home table, the tables whose columns and measures it reads, and the tables holding measures or calculated columns that depend on it, with the database tables behind each ("Not reported" when the definition names none) | Table, Relationship (Home table, Read by the measure, Holds impacted measures, Holds impacted calculations), Objects, Database tables, Semantic model | Workspace |
| Measures impacted by `<measure>` | Every measure that reads it, directly or through another calculation, with the reports and visuals showing each | Measure, Relationship (Direct at depth 1, otherwise Transitive), Depth, DAX reference, Reports, Visuals | — |
| Semantic model | The model holding the measure and how much of it the measure reaches | Semantic model, Workspace, Home table, Measures impacted, Calculated columns impacted, Reports using, Visuals using, Reports bound | Semantic model ID, Workspace ID |
| Reports | Reports with a visual showing the measure or something built on it | Report, Workspace, Usage, Pages, Visuals, Measures shown | Report ID |
| Visuals | Every such visual, with its page and report | Visual, Visual type, Page, Report, Workspace, Usage, Fields used | Report ID, Visual key |
| Inputs `<measure>` reads | The columns and measures it depends on, with the database table behind each plain column | Object, Type, Relationship, Depth, DAX reference, Database table | — |

Copies and exports prepend `parent_workspace_name`, `parent_workspace_id`,
`parent_semantic_model_name`, `parent_semantic_model_id`, and
`parent_measure`. Files are named from the model and measure:
`<model>-<measure>-tables`, `-impacted-measures`, `-semantic-model`,
`-reports`, `-visuals`, and `-inputs`.

**Degradation.** When exact DAX analysis fails, a warning says so, the Tables
grid keeps only the home table, and the Measures impacted and Inputs grids say
the analysis is unavailable. Visuals that show the measure itself still count.
Failed estate discovery, no bound reports, and the 300-report cap behave as
they do on Table Impact.

## Power BI Admin Scanner

`app/components/workspace/scanner.tsx`, `app/lib/scanner-api.ts`, and
`app/lib/use-workspace-scan.ts` implement the backend's four-step scanner
workflow: submit 1-100 workspace IDs, poll status every four seconds, stop at
`Succeeded`/`Failed`, and fetch the immutable result once. The page exposes
workspaces/tags, reports/dashboards/tiles, semantic objects and M expressions,
dependencies, and datasource instances. Explorer reuses the same hook for an
explicit single-workspace scan in Assets & access. Scans never start
automatically because Microsoft applies tenant quotas. The Scanner page is not
in the workspace sidebar; `/workspace/scanner` still renders it when opened
directly.

## API reference and execution
(`app/components/workspace/api-documentation.tsx` +
`api-execution-panel.tsx`)

The API reference opens from the header's Documents menu at
`/workspace/api-docs` (or `/workspace/<tag-slug>` for one OpenAPI tag). It
renders full-width, without the workspace sidebar or the mobile "Workspace
menu".

The app reads `/openapi.json` at runtime (`fetchOpenApi` in
`app/lib/api-catalog.ts`). `flattenEndpoints` converts each FastAPI
operation into an `ApiEndpoint`, grouped by its first OpenAPI tag.

Per operation, the UI provides:

- Method, route, operation name, description.
- Path/query/header inputs generated from OpenAPI `parameters`.
- Required-field validation and enum selectors (from `schema.enum`).
- An editable JSON body generated from the request schema (local `$ref`
  resolution across objects, arrays, enums, defaults, examples, `allOf`,
  `oneOf`, `anyOf` — see `api-catalog.ts`).
- Curated blank templates for credential/setup operations
  (`SETUP_ENDPOINT_DEFINITIONS`), so those operations still show up even if
  they're temporarily absent from the live OpenAPI doc.
- Authenticated execution via the shared `useApiExecutor` hook (same cookie +
  admin-key policy as the rest of the app).
- Status, elapsed duration, response body, response headers, with
  body/header tabs and copyable output.

## Table copy and export rules

- AG Grid enables text selection and per-cell copy controls.
- "Copy table" produces tab-separated content suitable for spreadsheets.
- CSV/Excel-compatible exports prepend parent workspace/report/semantic-model
  names and IDs; filenames use the selected parent object's *name*, not its
  internal ID. Measure Impact follows this rule: it prepends the measure's
  workspace, model, and `parent_measure`, and names files
  `<model>-<measure>-<grid>`. Table Impact is the exception because its
  selection can span models. It prepends `selected_tables` and uses fixed
  names (`table-impact-reports`, `table-impact-visuals`,
  `table-impact-semantic-models`, `table-impact-measures`).
- DAX expressions remain complete in copied/exported data even when
  visually truncated in a grid cell.
