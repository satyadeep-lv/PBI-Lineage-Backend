# PBI Lineage Explorer Frontend

Browser application for exploring Power BI assets, semantic models, DAX
dependencies, physical database evidence, report visuals, and downstream
lineage. It runs as a separate source-control project from the FastAPI backend
and is built as a static SPA for IIS. The current automated production path
deploys both services on the same Windows Azure VM behind
`https://lvpowerbilineage.com`.

Developed by **Satyadeep Singh**.

## Latest Changes

- **Naming standard applied.** Every page, grid, tile, status message, and
  export now uses one plain-language name per thing, as set out in
  [`Docs/07-column-naming-standard.md`](Docs/07-column-naming-standard.md).
  `app/lib/naming.ts` is the single glossary: `COLUMN` (headers such as
  "Report name", "Semantic model ID", "Number of visuals", "Steps away", "How
  it is used"), `VALUE` ("Not available", "Not found", "Not applicable",
  "Yes"/"No"/"Unknown", "Direct"/"Indirect", "Uses it directly"/"Through a
  measure"), and translators for report type, report format, storage mode, and
  object type. Renamed places:
  - Explorer tabs: **Workspace content** and **Report details** (were Assets &
    access, and Reports).
  - The five report sections shared by Explorer and Report lineage: **Pages**,
    **Data sources**, **Semantic objects**, **Database mapping**, **Visual
    fields** (were Page details, Source DB lineage, Semantic objects, Semantic
    - DB objects mappings, Report visuals).
  - Table impact searches **Semantic tables** and **Database tables**; its tiles
    read Reports, Visuals, Semantic models, Impacted measures.
  - Measure impact shows a measure as "Total Sales" with its **Semantic table**
    beside it, instead of `Sales[Total Sales]`; its tiles read Semantic tables,
    Impacted measures, Semantic models, Reports, Visuals.
  - Explorer's scan panel shows **Apps using this workspace**, and Ownership is
    split into **Last modified by**, **Created by**, and **Configured by**.
- **Exports match the screen.** Copy table, CSV, and Excel write exactly the
  headers the grid shows (see Table Copy And Export Rules). No `parent_…`,
  camelCase, or Title Case headers remain, and file names follow
  `<page>-<subject>-<grid>`.
- **Buttons and motion restyled after apple.com.** Pill-shaped buttons with a
  slight press-in, eased colour changes, and a soft focus ring; smooth, shared
  easing on menus, dialogs, sheets, tooltips, tabs, and the sidebar; a frosted
  header whose underlines grow in on hover; and a Home page whose headline
  rises in line by line while the walkthrough and sections fade up as they
  scroll into view. All motion is off under `prefers-reduced-motion`. See
  Buttons And Motion.
- **Snowflake column lineage no longer shows a detached node.** The backend's
  column-level `qualified_name` already ends in the column
  (`DB.SCHEMA.TABLE.COLUMN`); the diagram appended the column a second time,
  so the traced column appeared twice, once unconnected. Names are now built
  from the database, schema, and object parts, and the highlighted node is
  picked from the traced dependencies instead of being added on its own.
- **Tests and walkthrough follow the new names.** Every spec asserts the
  standard headers, values, and export order. `tests/column-lineage.spec.ts`
  tested a "Physical column lineage" tab that was never built; it was replaced
  by `tests/database-mapping.spec.ts`, which covers Explorer's Database mapping
  section. The Home walkthrough GIFs were re-recorded with the new names and
  styling.

- **Measure impact redesigned.** It keeps the workspace scope and the measure
  search. After a measure is picked it shows five tiles (Tables, Measures
  impacted, Semantic models, Reports, Visuals), the impact graph, and six
  grids, each with Copy table, CSV, Excel, and per-cell copy: **Tables** (the
  measure's home table, the tables it reads, and the tables holding
  calculations built on it, with the database tables behind each),
  **Measures impacted by `<measure>`**, **Semantic model**, **Reports**,
  **Visuals**, and **Inputs `<measure>` reads**. The old single
  Upstream/Downstream grid is gone. See Measure Impact Data Flow.
- **One impact graph for both impact pages.**
  `app/components/workspace/impact-lineage.tsx` draws the chain Database
  table + Semantic model -> Semantic table -> columns -> measures -> Reports
  -> Visuals with the same diagram settings as Explorer's Snowflake table
  lineage: top-to-bottom, animated teal edges, a focal ring, draggable nodes,
  collapse/expand, reset layout, and a tall canvas, plus a legend. Reports
  start collapsed with a +N visuals badge (new optional `LineageDiagram` prop
  `defaultCollapsedKinds`). The graph draws at most 40 reports and 120
  visuals and says how many it left out. Table impact now shows the graph for
  any selection, including one that spans several semantic models.
- **Report usage now comes from visuals only.** Both impact pages read
  `POST /api/v1/explorer/visual-source-lookup` and no longer call
  `measure-source-lineage`. That endpoint lists every measure of the bound
  model for every bound report, whether or not a visual shows it, so it made
  every bound report look like a user of every measure. Dropping it saves
  one backend call per model (per 50-report batch). The shared evidence code
  moved to `app/lib/impact-analysis.ts`, and the shared tiles and status bands
  to `app/components/workspace/impact-ui.tsx`.
- **Search and grid fixes.** The Tables search ranks name matches first
  (exact, prefix, word start, contains) before its 100-per-group cap, and
  semantic chips read `Table (Model)` (`SearchEntry.chipText`), so the same
  table name in two models stays distinguishable. `ImpactGrid` is keyed by its
  empty message, so "Checking reports..." gives way to the real no-rows text.
  While estate discovery loads, the evidence band says so instead of briefly
  claiming no reports are bound.
- **The dev page no longer reloads when docs or scripts are saved.**
  `app/app.css` now opens with `@import "tailwindcss" source(".")`, so
  Tailwind scans only `app/` for class names. It previously scanned the whole
  repository, and saving `README.md`, `Docs/*.md`, or `scripts/*.py` forced a
  full page reload because the Vite plugin cannot hot-update those files.
- **Table impact redesigned.** One **Tables** search replaces the Workspace
  scope, Table, Column, and Downstream/Upstream controls. It lists every table
  in every accessible workspace in two separate result groups shown side by
  side: **Semantic model tables** and **Database tables** (the physical
  `source_path` values the parsed model definitions report). Pick any number of
  either kind; each pick becomes a removable chip. A database table stands for
  every semantic table built on it, in any model. The results are status
  bands, four summary tiles (Reports, Visuals, Semantic models, Measures), the
  impact graph, and four grids, each with Copy table, CSV, Excel, and per-cell
  copy: **Reports using the selected tables**, **Visuals using the selected
  tables**, **Semantic models**, and **Measures using the selected tables**.
  See Table Impact Data Flow.
- **Logo cleaned up.** The supplied logo had a transparency checkerboard
  painted into its pixels. `public/tab_logo.png` is now a transparent 512 px
  mark cut from it (the original stays in `logos/tab_logo.png`), and
  `public/tab_logo-dark.png` swaps its navy strokes for light slate so it stays
  visible in dark theme. The header shows the mark with no frame, the footer
  uses it too, and `public/favicon.ico` (16/32/48 px) was regenerated from it.
  `app/root.tsx` links the ICO first and the PNG as the high-resolution icon.
- **Navigation reorganized.** The header now reads **Home**, **Workspace**,
  and a **Documents** dropdown holding **Setup guide** and **API reference**
  (the mobile sheet groups the same two links under a "Documents" label). The
  workspace sidebar lost its Setup guide, Overview (which linked to Home),
  Scanner, and API documentation entries and its "Explore" label; it now
  lists Power BI and Database setup, then Overview, Explorer, Report lineage,
  Table impact, and Measure impact. `/workspace/scanner` still works when opened directly, and
  the API reference renders full-width without the workspace sidebar.
  Active-state rules live in `app/lib/workspace-routes.ts`.
- **Added an Overview page** (`/workspace/overview`): totals of workspaces,
  reports, and semantic models, then three filterable lists, each item a link
  that opens Explorer with that item selected. It reads only the shared
  workspace list and estate discovery cache entries.
- **Explorer accepts deep links**: `?workspace=`, `?report=`, and `?model=`
  seed its first selection once, on mount. Without them nothing changes.
- **Home shows an animated walkthrough** of the application's tabs, in light
  and dark versions with a still poster for reduced motion, replacing the old
  `product-lineage-view.png` screenshot. `scripts/walkthrough/` regenerates it
  from fictional data.
- **Semantic objects is now report-scoped.** Its nested semantic-model picker
  is gone: the section follows the model the selected report is actually bound
  to, reading `POST /api/v1/explorer/snapshot` instead of the model-scoped
  `definition/parsed`. Rows carry a Semantic model column and are keyed by
  `semantic_model_id`, so a response covering several models renders them
  together in one grid with a banner naming the count. Two side effects worth
  knowing: Power BI's Auto Date/Time tables are now excluded (the backend
  filters them for this dataset, which `definition/parsed` does not), and the
  Relationships metric is gone because the dataset carries no relationships —
  it is replaced by a Semantic models count.
- **Power AI no longer shows a context panel or a persona picker.** The widget
  takes any question, and every answer is requested at full technical detail
  (`audience: "developer"`); the previously persisted audience choice was
  dropped so an old selection in localStorage cannot strand anyone.
- **Fixed the measure definition coming back as a bare dependency list.** The
  backend's `classify_intent` matches impact keywords before it looks at the
  declared object type, so the old prompt's "depends on" routed the question to
  the impact agent, which gathers no DAX definition — hence an answer with only
  "Depends on" and "Downstream impact" sections. The prompt now avoids those
  words and reaches the measure agent, which returns definition, upstream
  lineage and impact evidence together. The panel also renders the backend's
  verified evidence grouped by fact type beside the prose, so the DAX and its
  source tables are visible even when model composition falls back.
- **Backend reads are now cached for the whole session.** `QueryProvider` sets
  `staleTime: Infinity`, `gcTime: Infinity` and turns off refetch-on-mount,
  -focus and -reconnect, and every per-query `staleTime`/`gcTime` override was
  removed so that one config is the only place caching is decided. Walking the
  whole Explorer a second time issues zero requests; leaving for another page
  and coming back issues zero. Queries with their own `refetchInterval`
  (backend health, Power AI status, scanner status) keep polling, because an
  interval is independent of staleness. Since nothing expires on its own, the
  header gained a **Refresh data** control (`queryClient.resetQueries()`) that
  reloads what is on screen and re-fetches everything else when next opened.
  The cache is in memory only — a browser reload starts a new session.
- Added a **Snowflake column lineage** panel beneath the Power AI panel in
  Semantic - DB objects mappings: pick a fully qualified table and one of its
  database columns, both composed from the grid above, and trace that column
  upstream. It shares its trace call, result table and error handling with the
  table-level panel. Neither panel offers a direction control: both send
  `UPSTREAM`, and `object_domain` is fixed per panel (`TABLE` / `COLUMN`).
- Added a **Snowflake object lineage** panel beneath Explorer's Source DB
  lineage grid (`app/components/workspace/snowflake-object-lineage.tsx`): pick
  a `DATABASE.SCHEMA.OBJECT` name composed from the evidence in that grid and
  `POST /api/v1/lineage/snowflake/trace` returns the object/dependency counts
  and the dependency edges for what feeds it. The picker
  only offers rows that actually have a physical name to trace — unresolved
  rows and cross-workspace model sources are left out rather than offered and
  then failing. This route needs the **Snowflake** session, not the Power BI
  one, so a 401 here says exactly that and links to database setup.
- Added an Explorer **Semantic - DB objects mappings** section: one row per
  semantic object beside the `sourceColumn` and `sourceTable` it resolves to.
  A plain column resolves through its declared TMDL source column; measures and
  calculated columns have no source column of their own, so theirs come from
  the DAX dependencies the backend already traced (a measure over two columns
  lists both).
- Added a **Measure definition with Power AI** panel beneath that grid
  (`app/components/workspace/measure-ai-definition.tsx`): pick a measure and a
  reader — Business, General, or Developer, mapped to the backend's existing
  `audience` field — and `POST /api/v1/ai/chat` returns a full grounded
  definition, rendered in place and downloadable as `.md` (with the DAX and the
  evidence list) or `.txt`. It uses the same `GET /api/v1/ai/status` lock as
  the chat widget, so a backend with AI disabled or a dead session shows the
  locked panel rather than a broken button.
  It reads `POST /api/v1/explorer/snapshot` once rather than calling
  `semantic-model-objects`, `measure-source-lineage`, and
  `source-database-lineage` separately, which would repeat the expensive
  workspace/report/TMDL fetches three times.
- Removed the **Visibility** column from Semantic objects and the **Status**
  and **Confidence** columns from Report visuals, in the row data as well as
  the grid so exports match what is on screen.
- Audited every frontend API call and removed the unused one: Explorer issued
  `POST /api/v1/lineage/dax/analyze` on every model, posting the whole parsed
  definition as the request body, and never read the response — its DAX columns
  come from the parsed definition itself. Explorer's remaining heavy calls are
  now gated on the open section instead of firing on report selection, and
  duplicate cross-page requests (workspace list, estate discovery, estate
  inventory, parsed definitions) were consolidated onto shared query keys.
- Report Lineage now uses the shared `requestJson`; it carried a private copy
  that read only FastAPI's `detail`, discarding the backend's error envelope
  and every `request_id`. Explorer's Page details, Semantic objects, and Report
  visuals sections were likewise switched from a hardcoded sentence to
  `EvidenceError`, which distinguishes 401 from 403 and shows the `request_id`.
- Restructured Explorer from seven flat tabs to **two**: **Assets & access**
  and **Reports**. The report picker now sits once at the top of the Reports
  tab, above four report-scoped sections — Page details, Source DB lineage,
  Semantic objects, Report visuals — instead of being repeated inside each
  tab. The **Table lineage** and **Column mapping** tabs were removed, along
  with their `/api/v1/explorer/source-database-lineage`,
  `/api/v1/explorer/visual-source-lookup`, and
  `/api/v1/lineage/physical-sources/analyze` calls, the client-side graph
  depth-limiting helpers, and the `include_cross_model_matching` opt-in that
  only Table lineage used.
- Added the **Source DB lineage** section, calling
  `/api/v1/explorer/report-source-tables` for the selected report. Rows with no
  resolved physical source (`source_object_type: "unknown"`) are listed as
  unresolved rather than hidden, and account/database/schema blanks read
  "Not applicable", "Not resolved", or "Not reported" so an inapplicable value
  is distinguishable from a missing one.
- Added one global, lazy-loaded Power AI launcher and floating panel across
  Home, Setup Guide, workspace, and API routes.
- Added evidence/claim rendering, context-aware questions, general/business/
  developer audiences, SSE streaming with cancellation, non-streaming fallback,
  and distinct disabled/auth/permission/provider states.
- Added persistent desktop navigation collapse, a tablet icon rail, and
  independent mobile navigation and Power AI drawers.
- Added `app-shell.spec.ts` and `power-ai.spec.ts` coverage for the new shell,
  status gating, context, transport, evidence, errors, and responsive state.
- Moved frontend production artifacts to an ORAS/ACR release path while keeping
  atomic IIS promotion and rollback.
- Removed the unreachable `ui/sonner.tsx` primitive that referenced uninstalled
  `sonner` and `next-themes` packages and caused clean GitHub typecheck failures.
- Added backend GitHub `production` switches for `ENABLE_API_DOCS` and
  `AI_ENABLED`; the frontend deliberately has no duplicate AI feature flag.

## What This Project Does

The application turns the backend API surface into guided operational views:

- See how the application works from an animated walkthrough on Home.
- Read a setup guide covering Microsoft Entra registration, Power BI and
  Fabric tenant settings, Scanner metadata, database-provider access,
  backend environment policy, verification, and official references, from the
  header's Documents menu or Home.
- Authenticate Power BI and Fabric with a device code or service principal.
- Create and inspect an optional source-system session through the currently
  implemented Snowflake connector.
- See totals of every accessible workspace, report, and semantic model on
  Overview, with each one linking into Explorer.
- Browse Power BI workspaces, reports, and semantic models by name.
- Inspect report pages, semantic objects, DAX, source paths, and XMLA evidence.
- Map physical database columns to semantic columns and calculations.
- Trace report, column, measure, and calculated-column lineage through
  directed, collapsible diagrams with automatic layout.
- Analyze table impact: pick any number of semantic model tables, or the
  database tables behind them, from one search across every workspace, and
  see every report, visual, semantic model, and measure that uses them in an
  impact graph and four grids. Each grid can be copied or downloaded.
- Analyze measure impact: for one measure, the tables it reads and the tables
  holding calculations built on it, the other measures it impacts, its
  semantic model, the reports and visuals that show it or an impacted
  measure, and the inputs it reads, in the same impact graph and six
  copyable, downloadable grids.
- Run the Power BI Admin metadata scanner (one workspace from Explorer, or up
  to 100 at once from a dedicated Scanner page at `/workspace/scanner`, which
  is not linked from the sidebar) to see dashboards, app
  linkage, ownership, datasource instances and misconfiguration, and
  per-table M-query source expressions.
- Use the global Power AI panel on every route for evidence-grounded answers,
  persona-specific explanations, streamed responses, citations, and contextual
  questions seeded from impact-analysis selections.
- Copy individual table values or full tables for analysis.
- Download table data as CSV or Excel-compatible `.xls` files whose headers
  match the screen, starting with the workspace, report, or semantic model
  they belong to.
- Browse and execute every operation published by FastAPI OpenAPI from the
  in-application API reference under the header's Documents menu.

The frontend does not own Power BI, Fabric, or database-provider credentials.
It sends them to FastAPI when required and relies on backend-managed HTTP-only
session cookies for subsequent requests.

## Repository Boundary

Keep the backend and frontend as sibling directories and independent Git
repositories:

```text
C:\Users\Administrator\Desktop\
|-- PBI-Lineage-Backend\       FastAPI, backend tests, Docker image, backend Git repo
`-- PBI-Lineage-Frontend\      React application, static build, frontend Git repo
```

Do not place the frontend inside the backend repository and do not copy backend
runtime files, Python environments, secrets, or Docker volumes into this
project. The two applications communicate only over HTTP.

Backend reference context:

```text
C:\Users\Administrator\Desktop\PBI-Lineage-Backend\REF_DOC\PROJECT_CONTEXT.md
```

Frontend reference context:

```text
C:\Users\Administrator\Desktop\PBI-Lineage-Frontend\REF_DOC\PROJECT_CONTEXT.md
```

`REF_DOC/` is currently ignored by this repository, so the frontend context is
local documentation unless the ignore rule is intentionally changed.

The shorter contributor documentation is indexed at
[`Docs/README.md`](Docs/README.md). This root README remains the authoritative
setup, behavior, deployment, and troubleshooting handbook.

### Source-Control Readiness

The impact-analysis, scanner, shared-lineage, documentation, and browser-test
files are required application source. Before cloning this project onto a new
computer or triggering CI/CD, run:

```powershell
git status --short
git ls-files app tests Docs
```

Review every `??` entry and add the intended source files to Git before
committing. A local build can succeed with untracked files while a fresh clone
and GitHub Actions fail because those files were never included in the commit.
Never add generated `node_modules/`, `.react-router/`, `build/`,
`test-results/`, or `playwright-report/` directories.

## Technology Stack

| Area | Implementation | Responsibility |
| --- | --- | --- |
| Language | TypeScript | Strict application and API integration types. |
| UI | React 19 | Component rendering and local interaction state. |
| Framework | React Router Framework Mode | Route definitions, SPA build, metadata, and error boundary. |
| Build | Vite | Development server, dependency optimization, proxy, and production bundling. |
| Styling | Tailwind CSS 4 | Utility styling and design tokens. |
| Components | shadcn/ui with Base UI | Accessible buttons, inputs, dialogs, sheets, tabs, and related primitives. |
| Icons | Lucide React | Consistent interface icons. |
| Server state | TanStack Query v5 | API caching, loading/error states, invalidation, and background preparation. |
| UI state | Zustand | API origin/admin key, persisted desktop layout preference, and minimally persisted Power AI audience preference. |
| Graphs | XYFlow / React Flow with `elkjs` layout | Worker-laid-out, directed, draggable, collapsible report, Snowflake, column, measure, and impact diagrams. |
| Tables | AG Grid Community | Sortable/filterable analysis tables and selectable values. |
| Forms | React Hook Form and Zod | Setup form state and validation. |
| API catalog | Runtime OpenAPI parser | Discovers and groups current FastAPI operations. |
| API generation | Orval installed | Available for future generated clients; no generated Orval client is currently committed. |
| Unit/component tests | Vitest and React Testing Library installed | Test dependencies are ready; focused unit suites have not yet been added. |
| E2E | Playwright | Home/setup, navigation, Overview, app shell, Power AI, API execution, lineage, impact, and scanner browser coverage. |
| Production frontend | IIS static site on Azure VM | Serves versioned `build/client` releases and provides SPA fallback/reverse proxy rules. |
| Production backend | Windows Docker deployment on the same VM | FastAPI remains independently built and operated behind IIS. |

## Prerequisites

1. Windows machine with the backend available at `http://127.0.0.1:8000` for
   local development.
2. Node.js and npm on `PATH`.
3. Power BI/Fabric application registration and permissions expected by the
   backend.
4. Optional Snowflake connection details for Snowflake enrichment.
5. Playwright browser binaries when running browser tests.

This project was last validated locally with:

```text
Node.js v24.19.0
npm 11.17.0
```

## Installation

Open a new PowerShell window after installing Node.js, then run:

```powershell
cd C:\Users\Administrator\Desktop\PBI-Lineage-Frontend
node --version
npm --version
npm ci
npx playwright install chromium
```

Use `npm ci` for a reproducible installation from `package-lock.json`. Use
`npm install` only when dependencies are intentionally being changed.

If PowerShell blocks `npm.ps1`, use the Windows command shim:

```powershell
npm.cmd ci
npm.cmd run dev
```

## Environment Configuration

The preferred deployment is same-origin: IIS serves the frontend and proxies
backend routes. In that model no frontend environment variable is required.

Optional `.env`:

```dotenv
VITE_API_ORIGIN=
```

Behavior:

- Blank `VITE_API_ORIGIN` means same-origin requests such as `/api/v1/health`.
- During development, Vite proxies `/api`, `/openapi.json`, and `/docs` to
  `http://127.0.0.1:8000`.
- A non-empty value must be the backend origin without `/api/v1`; trailing
  slashes and a final `/api/v1` are normalized by the Zustand store.
- Cross-origin production deployment requires matching backend CORS and cookie
  `SameSite`/`Secure` configuration. Same-origin proxying is strongly preferred.

### Power AI configuration

The frontend has no `VITE_AI_ENABLED` setting and must never receive an AI
provider key. It calls the authenticated backend status endpoint and renders
the returned state:

```text
GET /api/v1/ai/status
```

The backend owns `AI_ENABLED`, provider configuration, credentials, evidence
grounding, and authorization. Locally, set `AI_ENABLED=true` in the backend
`.env` and restart FastAPI. In production, use the backend repository's GitHub
`production` environment variable `AI_ENABLED`; changing it requires a Backend
CD redeployment because it becomes a container environment variable.

The current automated deployment uses the deterministic `fake` provider. Real
provider credentials belong in Azure Key Vault and must never be added to this
frontend repository, a `VITE_*` variable, or browser storage. See the backend
README section **GitHub production feature switches** for the exact setup.

Never put tenant secrets, client secrets, Snowflake passwords, access tokens,
session IDs, or API keys in `.env`, source files, route state, or Git.

## Development

Start FastAPI first and verify:

```text
http://127.0.0.1:8000/docs
```

Then start the frontend:

```powershell
cd C:\Users\Administrator\Desktop\PBI-Lineage-Frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

Use `localhost` consistently. Binding the server to `127.0.0.1` while React
Router generates development imports for `localhost` can cause failed dynamic
module requests during optimization reloads.

Vite explicitly prebundles the runtime packages imported by the route graph,
including Base UI, forms, TanStack Query, XYFlow, AG Grid, the ELK API, cmdk,
Lucide, and Zustand. React Router's virtual route entry otherwise lets some
lazy-route dependencies be discovered in later waves; each new wave can
invalidate modules already requested by the browser. A clean install can spend
time building this dependency cache once, but the application should not blank
or restart optimization on first analysis navigation.

Do not run `npm run build` while actively using the same Vite process. The build
writes `build/`, which can trigger development file-watcher reloads. Stop the
development server, build, and then restart it.

Tailwind scans only `app/` for class names. `app/app.css` opens with
`@import "tailwindcss" source(".")`, and the path is relative to the
stylesheet, so `.` is `app/`. Left to automatic source detection, Tailwind
scanned the whole repository, including `README.md`, `Docs/*.md`, and
`scripts/*.py`. None of those are modules the Tailwind Vite plugin can
hot-update, so saving any of them while `npm run dev` ran forced a full page
reload. With the scan scoped, editing docs, scripts, or tests leaves the
open page alone. Write class names only in files under `app/`: a class that
appears only elsewhere is not generated. A change to that `@import` line
takes effect after the dev server restarts.

## Commands

| Command | Purpose |
| --- | --- |
| `npm ci` | Install exact locked dependencies. |
| `npm run dev` | Start React Router/Vite development server. |
| `npm run typecheck` | Generate React Router types and run strict TypeScript checks. |
| `npm run build` | Produce the SPA client and React Router server artifacts. |
| `npm run start` | Serve `build/server/index.js`; useful for optional Node-hosted validation, not the target IIS deployment. |
| `npx playwright test` | Run all Playwright browser tests. |
| `npx playwright test tests/report-lineage.spec.ts` | Run only report-lineage desktop/mobile coverage. |
| `npx playwright test tests/impact-analysis.spec.ts` | Run only table-impact/measure-impact coverage. |
| `npx playwright test tests/database-mapping.spec.ts` | Run only Explorer's Database mapping section coverage. |
| `npx playwright test tests/scanner.spec.ts` | Run only Scanner page and Explorer scan-panel coverage. |
| `npx playwright test tests/app-shell.spec.ts` | Run desktop/tablet/mobile shell, collapsible navigation, and floating Power AI layout coverage. |
| `npx playwright test tests/power-ai.spec.ts` | Run Power AI status, context, chat transport, evidence, error, and responsive-state coverage. |
| `npx playwright test tests/home.spec.ts` | Run only Home content, navigation, walkthrough-image, and desktop/mobile UX coverage. |
| `npx playwright test tests/navigation.spec.ts` | Run only header Home/Workspace/Documents, mobile sheet, and workspace sidebar navigation coverage. |
| `npx playwright test tests/overview.spec.ts` | Run only Overview totals, linked sections, filters, Explorer deep links, and degraded-estate coverage. |
| `npx playwright test tests/setup-guide.spec.ts` | Run only Setup Guide route, navigation, references, and responsive-containment coverage. |
| `node scripts/walkthrough/capture.cjs` | Capture Home walkthrough frames from the dev server on `:5173` (see Home Walkthrough). |
| `python scripts/walkthrough/compose.py` | Compose those frames into the Home walkthrough GIFs and posters (Python 3 + Pillow). |

## Route Map

| Route | View | Data responsibility |
| --- | --- | --- |
| `/` | Home | High-level product purpose, animated walkthrough of the application, evidence path, investigation questions, and Start exploring / Setup guide actions. |
| `/setup-guide` | Setup Guide | Static prerequisites for Microsoft, Fabric, Scanner, XMLA, the current Snowflake connector, backend hosting, and application verification. |
| `/workspace` | Power BI setup | Default workspace route. |
| `/workspace/power-bi` | Power BI setup | Device-code and service-principal authentication. |
| `/workspace/database` | Database setup | Snowflake connection, status, and logout. |
| `/workspace/overview` | Overview | Totals and linked lists of every accessible workspace, report, and semantic model, from the shared workspace list and estate discovery. |
| `/workspace/explorer` | Explorer | Workspace-scoped report/model investigation; optional `?workspace=`, `?report=`, `?model=` deep link. |
| `/workspace/report-lineage` | Report Lineage | Report-focused evidence across all accessible workspaces. |
| `/workspace/table-impact` | Table impact | One grouped multi-select search over every semantic model table and database table in every workspace, then the impact graph and the reports, visuals, semantic models, and measures that use the selection, in four exportable grids. |
| `/workspace/measure-impact` | Measure impact | Workspace scope and one measure, then the impact graph and six exportable grids: tables, impacted measures, semantic model, reports, visuals, and the inputs it reads. |
| `/workspace/scanner` | Scanner | Power BI Admin metadata scan across one or more workspaces: dashboards, datasource instances, table sources, dataset ownership. Opened directly; not in the sidebar. |
| `/workspace/api-docs` | API reference | Grouped OpenAPI reference and execution workbench, full-width without the workspace sidebar. |
| `/workspace/<tag-slug>` | Filtered API reference | API reference prefiltered to one OpenAPI tag when opened by URL. |

Unknown workspace sections fall back to the API reference. Unknown top-level
routes are handled by the React Router error boundary in development and require
IIS SPA fallback in production.

## Navigation

The header (`app/components/app-header.tsx`) links **Home** and **Workspace**
(`/workspace/power-bi`) and opens a **Documents** dropdown with **Setup guide**
(`/setup-guide`) and **API reference** (`/workspace/api-docs`). On small
screens the header's "Mobile navigation" sheet lists Home and Workspace, then
a "Documents" group label with those two links indented beneath it. The footer
keeps its own flat links to all four destinations.

`app/lib/workspace-routes.ts` decides what counts as a workspace screen:

- `WORKSPACE_SECTIONS` holds the working slugs: `power-bi`, `database`,
  `overview`, `explorer`, `report-lineage`, `table-impact`, `measure-impact`,
  and `scanner`.
- `isApiReferencePath(pathname)` is true for any other `/workspace/<slug>`.
  Workspace is marked active on every other `/workspace` path; Documents is
  marked active on `/setup-guide` and on API reference paths, and the current
  item is marked inside the menu.
- `explorerHref({ workspaceId, reportId?, semanticModelId? })` builds Explorer
  deep links for Overview.

The workspace sidebar (`app/components/workspace/workspace-sidebar.tsx`, reused
as the desktop sidebar, tablet icon rail, and mobile "Workspace menu" sheet)
shows a **Setup** group (Power BI "Step 1", Database "Step 2"), a separator,
then **Overview**, **Explorer**, **Report lineage**, **Table impact**, and
**Measure impact**. It has no Setup guide, Scanner, or API documentation entry.
The workspace route hides the sidebar and the mobile "Workspace menu" on API
reference paths so the reference renders full-width.

## Application Flow

```text
Home
  -> animated walkthrough of the application's tabs
  -> Setup Guide from the header Documents menu, the footer, or Home's button
       -> roles, permissions, current connector, backend, and hosting checks
  -> Start
  -> Power BI setup
       -> device-code session OR service-principal session
       -> Power BI and Fabric readiness
  -> Global Power AI launcher on every route
       -> backend status decides locked, disabled, unavailable, or ready
       -> selected object context sends identifiers, never full graphs
       -> streamed or non-streamed grounded answer with evidence
  -> Database setup
       -> optional source-system session (currently Snowflake)
  -> Overview
       -> totals: workspaces / reports / semantic models
       -> any listed item -> Explorer with that item selected
  -> Explorer
       -> workspace
       -> report
       -> pages / data sources / semantic objects /
          database mapping / visual fields
  -> Report Lineage
       -> report selected across the whole estate
       -> the same five report sections Explorer shows
  -> Table Impact
       -> one search: semantic model tables | database tables (pick any number)
       -> tiles and the impact graph (database table -> ... -> visuals)
       -> reports / visuals / semantic models / measures grids, copyable and downloadable
  -> Measure Impact
       -> workspace scope -> one measure search
       -> tiles and the same impact graph
       -> tables / impacted measures / semantic model / reports / visuals / inputs grids
  -> Scanner (opened directly at /workspace/scanner)
       -> workspace scope (1-100) -> run scan -> poll status
       -> dashboards, datasource instances, table sources, dataset ownership
  -> API reference (header Documents menu)
       -> OpenAPI group and operation
       -> parameters and JSON body
       -> authenticated execution
       -> response body and headers
```

## Authentication And Session Behavior

### Device Code

1. The setup form sends tenant and client IDs to
   `POST /api/v1/auth/microsoft/device/start`.
2. The backend returns the Microsoft verification URL, user code, and session
   identifier.
3. The browser polls or manually checks device session status.
4. FastAPI stores provider tokens in its session and sets the browser cookie.

### Service Principal

1. The form posts tenant ID, client ID, and client secret to
   `POST /api/v1/auth/microsoft/service-principal/session`.
2. Power BI and Fabric application-token readiness are presented independently.
3. Status may be `authenticated` or `partial`.
4. The frontend clears the client secret after submission and never persists it.

### Snowflake

The database setup form creates, checks, and deletes the backend Snowflake
session. Snowflake is optional enrichment; it does not replace Power BI estate
discovery.

### Shared Request Rules

- Requests use `credentials: "include"` so HTTP-only backend cookies are sent.
- The optional lineage administrative key exists only in Zustand memory and is
  added as `X-Lineage-Admin-Key` by shared request helpers.
- The API execution UI never renders that administrative header as a field.
- Password, secret, token, private-key, and passcode fields entered in the API
  JSON editor are cleared after execution.
- Successful Power BI authentication invalidates Explorer and Report Lineage
  caches. Logout removes those cached datasets.
- Every workspace page (Overview, Explorer, Report Lineage, Table Impact,
  Measure Impact, Scanner) shows the same `PowerBiAuthRequired` empty state
  (`app/components/workspace/auth-required.tsx`) whenever its first Power
  BI-backed query fails — a heading, a one-line explanation, and a button
  back to Power BI setup, rather than a page-specific error message.

## Overview Data Flow

`app/components/workspace/overview.tsx` renders `/workspace/overview`. It reads
only two cache entries that other pages already share, so it never fans out
per workspace:

1. The workspace list (`workspaceListKey`, `WORKSPACE_LIST_PATH` =
   `GET /api/v1/workspaces?top=100&skip=0`), shared with Explorer, Scanner,
   Table Impact, and Measure Impact. It is the page's universe, because
   Explorer can only open workspaces from this list.
2. Estate discovery (`estateDiscoveryKey`, `ESTATE_DISCOVER_PATH` =
   `GET /api/v1/lineage/estate/discover?top=5000&skip=0`), shared with Report
   Lineage, Table Impact, and Measure Impact, and requested only after the
   workspace list succeeds. Each workspace's reports and semantic models come
   from its entry here.

The page shows three total tiles (Workspaces, Reports, Semantic models) whose
values count up once, then three sections: Workspaces (with per-workspace
report and model counts), Reports grouped by workspace, and Semantic models
grouped by workspace. The sections sit side by side on large screens and
stack vertically on phones. Each has a count and a filter box; a filter that
matches a workspace name keeps that workspace's whole group. Every item is a
link built with `explorerHref`: a workspace opens Explorer on it, a report
opens the Report details tab on that report, and a semantic model opens the
Semantic objects section of a report connected to it.

A failed workspace list shows `PowerBiAuthRequired`. A failed estate discovery
leaves the Workspaces tile and list working, shows "—" for the other two
totals, and replaces their lists with "Reports could not be loaded" /
"Semantic models could not be loaded" and the error message. Motion is
limited to a short staggered fade-in, the count-up, and a hover nudge on each
link's chevron, all disabled under `prefers-reduced-motion`.

## Explorer Data Flow

Explorer begins with `GET /api/v1/workspaces` and keeps names as the primary UI
identity. IDs appear below selected names only as supporting technical context.

Major levels:

1. **Workspace content** — the workspace's reports, semantic models, and (after
   an explicit scan) dashboards, the apps using the workspace, and owners.
2. **Report details** — one report selected once, then five sections against it:
   1. Pages.
   2. Data sources: every physical table/view backing the selected
      report's semantic model, one row per table, with tables whose source
      could not be traced (`source_object_type: "unknown"`) listed as
      unresolved rather than omitted — plus an inline Snowflake trace panel
      for any row with a fully qualified physical name.
   3. Semantic objects: tables, columns, measures, and hierarchies for the
      model the report is bound to, with their DAX expressions. No model
      picker — several models, if returned, share one grid.
   4. Database mapping: every semantic object joined to the database columns
      and database tables it reads, plus an inline Power AI panel that writes a
      downloadable definition of any measure and a Snowflake column trace.
   5. Visual fields: each field used in a visual, matched to its semantic
      object and followed through DAX to the database columns and tables it
      reads.

Explorer also accepts deep links. It reads `?workspace=<id>`, `?report=<id>`,
and `?model=<id>` once, on mount, to seed its first selection: a report opens
the Report details tab on that report, and a model opens that tab's Semantic
objects section on the first report in that workspace connected to the model,
or Workspace content when none is. Later selections do not rewrite the URL, an
unknown ID falls back to the usual first-item defaults, and without params
Explorer behaves as before.

Every heavy request is gated on the section that reads it actually being open,
and is then cached by TanStack Query for five minutes — so moving between
sections stays instant, but evidence for a section nobody opened is never
fetched. Nothing is prefetched in the background.

Requests that are identical no matter which page issues them share one query
key from `app/lib/lineage-api.ts` (`workspaceListKey`, `estateDiscoveryKey`,
`estateInventoryKey`, `parsedSemanticModelKey`, `daxAnalysisKey`) rather than
being namespaced per page. Overview, Explorer, Scanner, Table Impact and
Measure Impact therefore share one workspace list, and Overview, Report
Lineage and both impact pages share one estate discovery. Table Impact always
builds the estate inventory over every listed workspace, which is the same
entry Measure Impact uses while its scope is left at the all-workspaces
default. That inventory is the single most expensive thing the frontend does
(it lists and parses every semantic model in scope). Both impact pages also
share `daxAnalysisKey`, so a model analyzed on one page is not analyzed again
on the other.

A report can use a semantic model from another workspace. Never substitute the
report workspace ID for the model workspace ID unless estate evidence confirms
the model is local.

Data sources calls the same `/api/v1/explorer/*` bulk endpoint Table
Impact and Measure Impact already use elsewhere, but scoped to the single
selected report rather than batched across a workspace. It defaults to
`include_gateway_sources: false`; checking "Include gateway sources"
re-fetches with the flag set to `true` — that costs real gateway-admin
lookups, so it is never default-on.

The Workspace content tab's dashboards, apps, and ownership sections are
empty until the operator explicitly runs a metadata scan for the selected
workspace (see Scanner Data Flow) — this is never triggered automatically.

## Report Lineage Data Flow

Report Lineage and Explorer show the same report-scoped evidence. They differ
only in how you reach a report: Explorer makes you pick a workspace first,
while Report Lineage lists every accessible report across every accessible
workspace, including reports whose semantic model lives elsewhere. Past that
selection both render `ReportEvidence`, so the tabs, the endpoints behind them,
and the exports are identical, and the granularity stays exactly one report.

1. `GET /api/v1/lineage/estate/discover?top=5000&skip=0` returns reports from
   all accessible workspaces plus graph bindings.
2. The selector displays `Report name (Workspace name)` and shows the report ID
   after selection. The estate graph's own report-to-model edge resolves which
   workspace the bound semantic model actually lives in.
3. The selected report is handed to `ReportEvidence` as a `ReportBinding`, which
   fetches each section's evidence only once that section is opened.

Sections, and the endpoint behind each:

| Section | Endpoint |
| --- | --- |
| Pages | `GET .../reports/{id}` and `GET .../reports/{id}/pages` |
| Data sources | `POST /explorer/report-source-tables`, plus `POST /lineage/snowflake/trace` for a selected table |
| Semantic objects | `POST /explorer/semantic-model-objects` and `GET .../semantic-models/{id}/metadata` |
| Database mapping | `POST /explorer/snapshot`, plus `POST /ai/explain` and a column-level `POST /lineage/snowflake/trace` |
| Visual fields | `POST .../definition/normalized`, `POST .../semantic-lineage`, `POST .../definition/parsed` |

## Lineage Diagram Engine

Report Lineage, Snowflake tracing, Table Impact, and Measure Impact render
their diagrams through one shared engine in
`app/components/workspace/lineage/`, so every dependency diagram in the
application looks and behaves the same way:

- `lineage-types.ts` defines the diagram-agnostic `LineageGraph` shape
  (`LineageGraphNode`/`LineageGraphEdge`) that every feature builds toward.
- `lineage-layout.ts` lazy-loads `elkjs` and runs its layered algorithm in a
  Web Worker to compute left-to-right or top-to-bottom positions without
  blocking the interface; no feature hand-computes `x`/`y` coordinates.
- `lineage-node.tsx` renders a tone-colored card per object kind with a
  collapse/expand chevron. Collapsing a node hides every node strictly
  farther from the diagram's root through it (an undirected "display tree"
  computed with breadth-first search, rooted at the focal node or at
  in-degree-zero nodes), so collapse behaves correctly even in bidirectional
  upstream+downstream diagrams (the default `"connected"` mode). A diagram
  can instead collapse along its edges only: `collapseDirection`
  `"downstream"` (the impact graph) hides what a node feeds, and `"upstream"`
  (the Snowflake trace) hides what feeds it.
- `lineage-diagram.tsx` exports `<LineageDiagram>`, which owns collapse state,
  derives the currently visible node/edge subset, lays it out with ELK, and
  renders draggable nodes with React Flow. It keeps the flow mounted across
  layouts, offers an automatic-layout reset, culls offscreen elements for
  large traces, focuses the nearest target context first, and limits costly
  edge animation. Edges always carry an arrowhead (`MarkerType.ArrowClosed`),
  so dependency direction is visible without reading labels. Its optional
  `defaultCollapsedKinds` prop lists node kinds that start collapsed, each
  with a +N badge, whenever the graph changes. The prop is keyed by the kinds'
  content, not the array's identity, so an inline array does not reset the
  user's expansions on every render.

`app/lib/dependency-graph.ts` complements the diagram engine with
`computeDependencyClosure`, a single multi-source breadth-first search over
`dax/analyze`'s flat dependency-edge list that Table Impact and Measure Impact
use to answer "what feeds this object, and what does it feed" from one or more
seed objects. In each edge, `source` is the referenced object and `target` the
object whose expression reads it. `closureToLineageGraph` turns a closure into
a `LineageGraph` for the calculation diagrams in `report-lineage-diagrams.tsx`;
the impact pages build their graph with `buildImpactGraph` instead (see Impact
Evidence And Graph). `app/lib/lineage-api.ts`'s `fetchEstateInventory`
complements both: it parses every semantic model across a workspace scope up
front, so Table Impact can offer one grouped, multi-select table search and
Measure Impact one searchable measure picker, instead of a
workspace-then-model-then-table cascade.

## Impact Evidence And Graph

Table Impact and Measure Impact share their report evidence, their graph, and
their page furniture:

| File | Shared piece |
| --- | --- |
| `app/lib/impact-analysis.ts` | Bound-report visual evidence and the parsed-definition helpers. |
| `app/components/workspace/impact-lineage.tsx` | `buildImpactGraph` and `ImpactLineageDiagram`. |
| `app/components/workspace/impact-ui.tsx` | `SummaryTile`, `ImpactSection`, `StatusBand`, `EvidenceStatus`, `LoadingState`, `EmptyState`. |

### Evidence

For each semantic model in play:

1. Estate discovery (`estateDiscoveryKey`), requested once a table or
   measure is selected, supplies the model's bound reports through
   `boundReportsForModel`, plus report names and workspaces.
2. `fetchImpactEvidence` posts those reports to
   `POST /api/v1/explorer/visual-source-lookup` through
   `fetchBatchedExplorer`: 50 reports per request, at most the first 300
   bound reports per model. The query key comes from `impactEvidenceKey` and
   is `[page, "visual-evidence", apiOrigin, semanticModelId, reportIds]`, where
   `page` is `table-impact` or `measure-impact`. The `visual-evidence` segment
   keeps it apart from cache entries of the older two-call shape.
3. `buildEvidenceIndex` keeps the `matched` rows that name a semantic object
   and indexes them by `evidenceKey` (`table[name]`, lowercased): which
   reports and which visuals read each object. It also records each report's
   name and workspace and each visual's page, name, and type from the row,
   falling back to IDs (and "Visual") when a field is missing.
4. `buildReportNames` names reports from the estate first (each workspace's
   `reports[]`, then its bindings by ID) and fills any ID-only name from the
   evidence rows.

Visual evidence is the only usage signal: a report uses an object when one of
its visuals reads it. `POST /api/v1/explorer/measure-source-lineage` is no
longer called. It returns every measure of the bound model for every bound
report, whether or not any visual shows it, so joining it made every bound
report look like it used every measure. Dropping it removes one backend call
per model (per 50-report batch).

The module also exports `SourcedTable` (a parsed table with the `source_path`
on the table and its columns, which the shared `ParsedTable` type leaves
out), `tableSources` (distinct physical sources behind a table, compared
without case), `tableSeeds` (every column, calculated column, and measure,
plus the table itself when it is calculated), `displayType`, and
`EstateWithReports` (estate discovery including each workspace's
`reports[]`).

### Graph

`buildImpactGraph` takes one scope per semantic model (the focal objects, the
closure members, the model's DAX dependencies, its evidence index, and the
physical sources per table) and returns one directed graph:

```text
Database table --+
Semantic model --+--> Semantic table -> columns -> measures -> Reports -> Visuals
```

- A database table and the semantic model each point at a semantic table; a
  table points at its columns and measures; DAX edges run from each
  referenced object to the one that reads it; an object points at every
  report whose visuals read it; a report points at those visuals.
- Object and table node IDs are namespaced by model (`<model key>|...`)
  because DAX reference keys are unique only within one model. Database-table
  nodes (`db|<PATH>`) and report nodes (`report|<id>`) are shared, so a
  physical table behind two models is one node.
- A focal object (a selected table's column or measure) is drawn only when a
  DAX edge links it to another drawn object or a visual reads it, which keeps
  a table's unused columns out of the graph. A lone focal object (Measure
  Impact's measure) is always drawn.
- The selected tables (Table Impact) or the selected measure (Measure
  Impact) carry the focal ring.

`ImpactLineageDiagram` renders the graph with the same `<LineageDiagram>`
settings as Explorer's Snowflake table lineage: ELK top-to-bottom layout
(`direction="TB"`), animated edges in the app teal
(`edgeColor="var(--fabric-primary)"`), 20 px node and 44 px rank separation,
a focal ring, draggable nodes, per-node collapse and expand, reset layout, and
a tall canvas (760 px, at least 520 px). The Snowflake trace flows up toward
its sources; the impact graph flows down (`verticalFlow="down"`,
`collapseDirection="downstream"`) because impact reads from source to
consumer. A legend under the canvas names the node kinds present.

Reports start collapsed (`defaultCollapsedKinds={["report"]}`), each with a +N
badge counting its hidden visuals; clicking a report expands it. This keeps a
wide fan-out of visuals from shrinking the whole graph. The graph also draws
at most 40 reports (ranked by visuals, then by objects read) and 120 visuals.
Past those caps, a notice under the graph says how many reports and visuals
were not drawn. The grids always list every one.

## Table Impact Data Flow

`app/components/workspace/table-impact.tsx` answers "what uses these
tables?" for any number of tables at once, across every accessible workspace.
It has no workspace scope, column, or Downstream/Upstream control. The
inventory always spans the whole workspace list, a table is always analyzed
whole, and traversal is always downstream.

1. **Inventory.** `fetchEstateInventory` runs over every workspace in the
   shared workspace list (`estateInventoryKey`). It lists each workspace's
   semantic models and parses each definition, with limited concurrency. An
   inaccessible model is skipped and counted instead of failing the page. A
   status bar reports "N semantic tables and M database tables indexed across
   W workspaces", plus any skipped models, and offers **Refresh inventory**.
2. **One search, two groups.** A single **Tables** search
   (`MultiObjectSearch` in `impact-picker.tsx`, placeholder "Search semantic
   tables or database tables...") lists every table in two separate groups.
   They sit side by side on wider screens and stack on phones, and each
   heading shows its match count:
   - **Semantic tables**: every parsed table, labeled
     table · semantic model · workspace, plus `from <source>` when its
     definition names a physical source.
   - **Database tables**: every distinct physical `source_path` on a parsed
     table or any of its columns (compared without case), listing the
     semantic tables behind it. The page reads `source_path` from the parsed
     definition through a local type, because the shared `ParsedTable` type
     leaves it out.

   Typing filters both groups: every word must appear in the name, model,
   workspace, or source. Matches are then ranked by how well the name fits
   the query: exact name, name prefix, a name segment starting with it, name
   containing it, then entries that matched only on model, workspace, or
   source text. Ranking runs before the cap, so a name match never hides
   behind model or workspace matches. Each group shows its first 100 ranked
   matches, with a "refine your search" note past that. Clicking an entry
   toggles it and leaves the list open, so several tables can be picked in a
   row. **Clear** empties the selection and **Done** closes the list. Picks
   appear under the box as removable chips tagged "Semantic" or "Database" (list
   "Selected tables", buttons `Remove <chip text>`). A semantic chip reads
   `Table (Model)` (`SearchEntry.chipText`), so the same table name in two
   models stays distinguishable; a database chip shows its path. When a
   refreshed inventory no longer contains a pick, the pick is dropped without
   a notice.
3. **Resolve.** A semantic-table pick is analyzed as itself. A
   database-table pick expands to every semantic table sourced from it, in
   every model. Each result row remembers which picks led to it (the
   "Selected tables" column). Each semantic table seeds every column,
   calculated column, and measure on it, plus the table itself when it is a
   calculated table (`tableSeeds`).
4. **DAX analysis per model.** Reference keys are unique only within one
   model, so the page runs one `POST /api/v1/lineage/dax/analyze` query for
   each model the selection touches (`useQueries` over the shared
   `daxAnalysisKey`). Each query posts the parsed definition the inventory
   already holds. A model that Measure Impact or an earlier selection already
   analyzed is served from the cache. `computeDependencyClosure` then walks
   each table's downstream closure inside its own model.
5. **Visual evidence.** Estate discovery is requested once a table is
   picked. `GET /api/v1/lineage/estate/discover` is shared with Overview,
   Report Lineage, and Measure Impact. For each model with bound reports,
   `POST /api/v1/explorer/visual-source-lookup` runs through
   `fetchBatchedExplorer` (see Impact Evidence And Graph). The evidence is
   joined to the downstream DAX closure of every column and measure of the
   selected tables. A report or visual uses the selection when a visual reads
   one of a selected table's own columns or measures ("Uses it directly")
   or any object in its downstream closure ("Through a measure").
6. **Results.** Two status bands report whether exact DAX dependencies are
   ready and how far the visual evidence reached. While estate discovery
   loads, the evidence band says it is finding the bound reports rather than
   flashing that no report is connected. Four summary tiles count Reports,
   Visuals, Semantic models, and Impacted measures. The impact graph comes next (see
   Impact Evidence And Graph). It covers every model in the selection and is
   titled `<Table> impact` for one table or `Impact of N semantic tables`
   otherwise.
   Four `ImpactGrid`s follow. Each grid shrinks to fit its rows (`fitRows`)
   and has **Copy table**, **CSV**, **Excel**, and per-cell copy. Copies and
   exports use the on-screen headers with every ID last. Each grid has its
   own Selected tables column naming the picks behind each row, so the
   selection is not repeated as a context column. Files are named
   `table-impact-<table>-<grid>` after the one picked table (semantic or
   database), or `table-impact-multiple-tables-<grid>` when several are
   picked; the grids are `reports`, `visuals`, `semantic-models`, and
   `measures`.

   | Grid | Columns on screen | Also in copies and exports |
   | --- | --- | --- |
   | Reports using the selected tables | Report name, Workspace name, Semantic model, Selected tables, How it is used, Number of pages, Number of visuals, Objects used | Report ID, Semantic model ID |
   | Visuals using the selected tables | Visual name, Visual type, Page name, Report name, Workspace name, How it is used, Objects used, Selected tables | Report ID, Visual ID |
   | Semantic models | Semantic model, Workspace name, Selected tables, Database tables, Number of impacted measures, Number of reports using it, Number of connected reports | Semantic model ID, Workspace ID |
   | Measures using the selected tables | Measure name, Semantic table, Semantic model, Workspace name, Selected tables, Dependency (Direct at 1 step, otherwise Indirect), Steps away, Referenced as, Number of reports, Number of visuals | Semantic model ID |

7. **Power AI.** When the resolved selection is exactly one semantic table,
   **Ask Power AI** appears, that table becomes the Power AI context, and the
   graph uses it as its focus node.
8. **Degradation.** Each source fails independently:
   - A failed workspace list shows `PowerBiAuthRequired`. A failed inventory
     says the table inventory is unavailable for this identity.
   - A model whose DAX analysis fails is named in a warning. This happens,
     for example, when the administrative key is missing or a `/lineage/*`
     route is unreachable. That model contributes no measures, and only
     direct reads of its tables count toward report usage.
   - Failed estate discovery shows a warning that report and visual usage
     cannot be computed while the dependency results stay accurate. The
     Reports and Visuals grids say usage is unavailable, while the Semantic
     models and Measures grids stay accurate. While usage is still being
     checked, the Reports and Visuals grids read "Checking reports...".
   - No bound reports and the 300-report cap each show a visible notice. A
     failed 50-report batch is dropped instead of blanking the page.

## Measure Impact Data Flow

`app/components/workspace/measure-impact.tsx` answers "what does this
measure touch?" for one measure: the tables it reads and affects, the other
measures it impacts, its semantic model, and every report and visual that
shows it or an impacted measure.

1. **Selection.** A "Workspace scope" multi-select (`WorkspaceScopeSelect`,
   every accessible workspace checked by default) and `fetchEstateInventory`
   (`estateInventoryKey`, the same entry Table Impact uses at the
   all-workspaces default) populate one searchable "Measure" combobox
   (`ObjectSearchSelect`, entries labeled with the measure name, and its
   semantic table, semantic model, and workspace beneath). The first indexed measure is selected automatically.
   A status bar counts indexed measures and skipped models and offers
   **Refresh inventory**.
2. **DAX closure.** One `POST /api/v1/lineage/dax/analyze` query for the
   measure's model, on the shared `daxAnalysisKey`, posts the parsed
   definition. `computeDependencyClosure` returns the measure's upstream
   inputs (columns, calculated columns, and measures it reads) and its
   downstream dependents (measures and calculated columns built on it) in
   one pass.
3. **Visual evidence.** Estate discovery is requested once a measure is
   selected, and the model's bound reports go to
   `POST /api/v1/explorer/visual-source-lookup` (see Impact Evidence And
   Graph). A report or visual uses the measure when a visual shows the
   measure itself ("Uses it directly") or anything in its downstream
   closure ("Through a measure").
4. **Results.** The exact-DAX and evidence status bands, then five tiles:
   Semantic tables, Impacted measures, Semantic models, Reports, and Visuals. **Ask
   Power AI** ("Explain this measure") sends the measure as context. The
   impact graph shows the database tables and semantic model feeding the
   tables and columns the measure reads, the measure itself (focal), the
   measures depending on it, and the reports and visuals that show them. Six
   `fitRows` grids follow, each with **Copy table**, **CSV**, **Excel**, and
   per-cell copy:

   | Grid | What it lists | Columns on screen | Also in copies and exports |
   | --- | --- | --- | --- |
   | Semantic tables | The measure's own table, the tables whose columns and measures it reads, and the tables holding measures or calculated columns that depend on it, with the database tables behind each ("Not available" when the definition names none) | Semantic table, Connection to the measure (Holds the measure, Read by the measure, Holds impacted measures, Holds impacted calculations), Objects involved, Database tables, Semantic model | Workspace name |
   | Measures impacted by `<measure>` | Every measure that reads it, directly or through another calculation, with the reports and visuals showing each | Measure name, Semantic table, Dependency (Direct at 1 step, otherwise Indirect), Steps away, Referenced as, Number of reports, Number of visuals | — |
   | Semantic model | The model holding the measure and how much of it the measure reaches | Semantic model, Workspace name, Measure's semantic table, Number of impacted measures, Number of impacted calculated columns, Number of reports using it, Number of visuals using it, Number of connected reports | Semantic model ID, Workspace ID |
   | Reports | Reports with a visual that shows the measure or something built on it | Report name, Workspace name, How it is used, Number of pages, Number of visuals, Objects used | Report ID |
   | Visuals | Every such visual, with its page and report | Visual name, Visual type, Page name, Report name, Workspace name, How it is used, Objects used | Report ID, Visual ID |
   | Inputs `<measure>` reads | The columns and measures it depends on, with the database table behind each plain column ("Not applicable" for measures and calculations) | Object name, Semantic table, Object type, Dependency, Steps away, Referenced as, Database table | — |

   Copies and exports start with the context columns Workspace name,
   Semantic model, and Selected measure (each left out when the grid already
   has that column) and end with Workspace ID and Semantic model ID. The
   Reports and Visuals files leave the measure's workspace out, because each
   row already carries its report's own workspace. Files are named
   `measure-impact-<measure>-<grid>`: `semantic-tables`, `impacted-measures`,
   `semantic-model`, `reports`, `visuals`, and `inputs`.
5. **Degradation.** When exact DAX analysis fails, a warning says so, the
   Semantic tables grid keeps only the measure's own table, and the impacted
   measures and Inputs grids say the calculation links could not be loaded; visuals that show the
   measure itself still count. Failed estate discovery, no bound reports,
   and the 300-report cap behave as they do on Table Impact.

## Scanner Data Flow

`app/lib/scanner-api.ts` and `app/lib/use-workspace-scan.ts` drive Microsoft's
real four-step Power BI Admin "metadata scanning" workflow
(`GetModifiedWorkspaces` / `PostWorkspaceInfo` / `GetScanStatus` /
`GetScanResult`, wrapped 1:1 by the backend's `/api/v1/scanner/*` router).
This is the only asynchronous, multi-step backend workflow in the
application — everything else is a single cached request.

1. The operator explicitly picks a workspace scope (1 to 100 workspaces; the
   backend rejects more) and clicks "Run scan" — never automatic, since
   submissions, status checks, and result reads all count against the
   tenant's real hourly Power BI Admin API quota (Microsoft caps modified-
   workspace discovery at 30/hour, scan submissions at 500/hour with at most
   16 simultaneous, and result reads at 500/hour; the backend does not
   locally emulate or soften these limits).
2. `POST /api/v1/scanner/workspaces/scan` returns a `scan_id`.
   `useWorkspaceScan` polls `GET .../scans/{id}/status` on a fixed 4-second
   interval (via TanStack Query's `refetchInterval`) until `status` is
   `Succeeded` or `Failed`, then stops polling.
3. Once `Succeeded`, `GET .../scans/{id}/result` is fetched once and cached
   indefinitely for that `scan_id` (a completed scan's result is immutable,
   and re-fetching it would burn the same result-read quota for no benefit).
4. The result's `payload` is Microsoft's raw, backend-unvalidated JSON. The
   frontend reads it defensively and never assumes a field is present. It
   never contains app *display names* (only `appId` linkage) or full sharing
   ACLs (only `createdBy`/`modifiedBy`/`configuredBy` identities) — the UI is
   labeled accordingly rather than overclaiming.
5. `get_artifact_users` (which can return user identifiers) is never set to
   `true` anywhere in the frontend and has no UI toggle.

`app/lib/scanner-api.ts` models the payload field-for-field against Microsoft's
own reference
([Get Scan Result](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result)):
every type in that page's "Definitions" section (`WorkspaceInfo`,
`WorkspaceInfoReport`, `WorkspaceInfoDashboard`, `WorkspaceInfoTile`,
`WorkspaceInfoDataset`, `Table`, `Column`, `Measure`, dataset `Expression`s,
`Role`/`RoleMember`/`RoleTablePermission`, `WorkspaceInfoDataflow`,
`WorkspaceInfoDatamart`, `Datasource`/`DatasourceConnectionDetails`,
dependency/tag/endorsement/sensitivity-label/user-access types, and so on) has
a corresponding TypeScript type in `app/lib/scanner-api.ts`. The Scanner page
currently exposes five tabs, each one or more stacked, exportable AG Grid
tables:

- **Workspaces** — one row per scanned workspace, plus every tag applied
  anywhere in the scan (workspace, report, dashboard, semantic model,
  dataflow, or datamart).
- **Reports & dashboards** — reports, dashboards, and dashboard tiles.
- **Semantic models** — datasets, tables, columns, measures, table M-query
  sources, and dataset-level shared/parameter expressions. Each dataset row
  also carries table/expression/role/relationship counts.
- **Dependencies** — every report-to-semantic-model link plus each item's
  declared upstream dataflows, datamarts, and semantic models, in one grid.
- **Datasource instances** — full connection details for both the regular and
  misconfigured instance lists, each cross-referenced back to which datasets/
  dataflows/datamarts use it.

Relationships, RLS roles/role members, dataflows, datamarts, and per-item
`*User` access-right arrays are still fully typed in `scanner-api.ts` and
still contribute counts to the top-level summary strip and to the Workspaces/
Semantic models grids — they don't currently have their own dedicated
browsing tab.

Explorer's per-workspace scan panel (see below) intentionally stays a small,
three-section subset of this — the full field-by-field browser lives only on
the dedicated Scanner page.

Two surfaces share this same hook and data layer:
- **Explorer's Workspace content tab** scans only the currently selected
  workspace and fills in three sections that were previously placeholders:
  Dashboards, Apps using this workspace, and Ownership (Last modified by,
  Created by, and Configured by).
- **The dedicated Scanner page** (opened directly at `/workspace/scanner`;
  it is no longer in the workspace sidebar) scans up to 100 workspaces at once and
  browses the fuller payload across all of them: Dashboards, Datasource
  instances (with a separately highlighted Misconfigured datasource
  instances section), Table sources (the actual M-query `source` expression
  per table, across every scanned workspace without per-report navigation),
  and Dataset ownership/configuration.

Scan progress and results are held in component/query memory only and reset
when the workspace scope changes or the component unmounts — consistent with
the rest of the application's no-persistence-beyond-session posture.

## API Reference And Execution

The API reference opens from the header's Documents menu at
`/workspace/api-docs`, or at `/workspace/<tag-slug>` for one OpenAPI tag, and
renders full-width without the workspace sidebar.

The application reads `/openapi.json` at runtime. `flattenEndpoints` converts
each FastAPI operation into the frontend endpoint model and groups operations by
their first OpenAPI tag.

For every operation, the documentation view provides:

- Method, route, operation name, and description.
- Path, query, and ordinary header inputs from OpenAPI parameters.
- Required-field validation.
- Enum selectors where OpenAPI supplies enum values.
- An editable JSON body generated from the request schema.
- Curated blank templates for credential/setup operations.
- Authenticated execution with cookies and the existing ephemeral key policy.
- HTTP status, elapsed duration, response body, and response headers.
- Body/header tabs and copyable output.
- Backend validation/error details for non-success responses.

The runtime schema template generator resolves local
`#/components/schemas/...` references, objects, arrays, enums, defaults,
examples, `allOf`, `oneOf`, and `anyOf`. Templates are starting points; the
operator must still enter IDs and values valid for the connected tenant.

## Table Copy And Export Rules

Every grid exports through one path, `toExportTable` in
`app/lib/grid-export.ts`, so screen and file always agree:

- AG Grid enables text selection and per-cell copy controls.
- **Copy table** writes tab-separated text for spreadsheets; **CSV** writes
  UTF-8 with a byte-order mark and CRLF line endings; **Excel** writes an
  Excel-compatible `.xls` HTML table.
- **Headers are the on-screen headers**, in the standard names from
  `app/lib/naming.ts`. Columns that exist only in files (IDs) are hidden
  column definitions with standard names too.
- **Column order:** context columns first (Workspace name, Report name,
  Semantic model, Selected tables, Selected measure), then the grid's own
  columns, then the grid's ID columns, then the context IDs. Every header
  ending in " ID" is last.
- **No duplicate headers:** a context column is left out when the grid already
  has a column of that name, so a file never has two columns called, say,
  "Workspace name" or "Selected tables".
- **Missing values** read Not available, Not found, or Not applicable, never
  `--` or an empty guess. Yes/No columns read Yes, No, or Unknown.
- **File names** are `<page>-<subject>-<grid>` in lower case:
  `explorer-<workspace>-reports` (and `-semantic-models`, `-dashboards`,
  `-owners`), `report-<report>-<grid>` for the five report sections on both
  Explorer and Report lineage (`pages`, `data-sources`, `semantic-objects`,
  `database-mapping`, `visual-fields`), `table-impact-<table>-<grid>` or
  `table-impact-multiple-tables-<grid>`, and `measure-impact-<measure>-<grid>`.
- DAX expressions remain complete in copied and exported data even when
  shortened in a cell.
- `ImpactGrid` is keyed by its empty message, because AG Grid reads its
  no-rows overlay only once; the key rebuilds the grid so "Checking
  reports..." is replaced by the final no-rows text.

## Naming Standard

[`Docs/07-column-naming-standard.md`](Docs/07-column-naming-standard.md) is
the reference for every name on screen and in files: sentence case, object
first ("Report name", "Visual type"), counts as "Number of …", IDs as
"<Object> ID", and plain words instead of API terms (connected, not bound;
Reached through, not via; Steps away, not depth). The document keeps each old
name beside its standard one.

`app/lib/naming.ts` holds those names in code. Add a new header or value to
`COLUMN` or `VALUE` there first, then use it in the grid; never type a header
string inside a page. The Playwright suite asserts the headers and export
order of every grid it covers, so a drifting name fails a test.

## Buttons And Motion

The interface follows apple.com's interaction style, in the app's teal:

- **Buttons** (`app/components/ui/button.tsx`) are pills with generous side
  padding. Colour changes ease over 200 ms with `ease-apple`, a click presses
  the button in slightly (`scale 0.97`, skipped on menu triggers), keyboard
  focus shows a soft 4 px ring, and a trailing arrow marked
  `data-icon="inline-end"` leans right on hover. `outline-brand` is the
  outlined brand pill used beside a filled one.
- **Hand-built controls** take the same behaviour from
  `app/lib/interaction-styles.ts`: underlined section tabs, segmented controls
  (the lineage diagram switcher, the sign-in method, Power AI's audience), and
  small text and icon actions.
- **Motion tokens** live in `app/app.css`: `ease-apple`
  (`cubic-bezier(0.28, 0.11, 0.32, 1)`) for content, `ease-apple-snappy` for
  controls, and the `animate-rise` / `animate-rise-zoom` entrances. They also
  drive tw-animate-css, so menus, selects, tooltips, dialogs, and sheets open
  with the same curve.
- **Scroll reveal:** `app/components/reveal.tsx` fades sections up the first
  time they scroll into view (Home's walkthrough grows in from 94%).
- **Page motion:** Home's headline block rises in line by line; the header is
  frosted and translucent, with underlines that grow from the centre; each
  workspace section fades in when opened; the sidebar's current-item marker
  grows in.
- **Reduced motion:** every animation is disabled under
  `prefers-reduced-motion`, and `Reveal` then shows content as-is.

## State Ownership

| State | Owner | Lifetime |
| --- | --- | --- |
| Backend health | TanStack Query in `AppHeader` | Refetched every 15 seconds on setup/workspace routes; disabled on Home. |
| OpenAPI document | TanStack Query in workspace route | Current browser query cache. |
| Overview/Explorer/report data | TanStack Query | Selection-keyed cache with feature-specific stale times. |
| Explorer selection | Explorer component state, seeded once from `?workspace`, `?report`, `?model` | Current Explorer mount; later selections do not rewrite the URL. |
| Table Impact selection | `TableImpact` component state (selected semantic/database table keys) | Current mount; picks missing from a refreshed inventory are dropped. Not in the URL. |
| Measure Impact scope and measure | `MeasureImpact` component state | Current mount; the scope defaults to every workspace and the measure to the first indexed one, which also replaces a pick missing from a refreshed inventory. Not in the URL. |
| API execution result | `useApiExecutor` | Current workspace route mount. |
| API origin | Zustand | In-memory page lifetime, initialized from `VITE_API_ORIGIN`. |
| Administrative key | Zustand | Ephemeral memory only; no visible input or persistence. |
| Diagram collapse/expand state | `LineageDiagram` component state | Current graph; resets whenever the underlying graph changes, to the kinds in `defaultCollapsedKinds` (report nodes in the impact graph) or to fully expanded. |
| Scan progress (`scan_id`, status, result) | `useWorkspaceScan` + TanStack Query | Component/query memory only; resets when the workspace scope changes or the component unmounts. |
| Form inputs | React Hook Form or component state | Current component mount. |
| Power BI/Snowflake session | FastAPI cookie/session | Backend policy controls lifetime. |

## Folder Hierarchy

Generated `node_modules/`, `.react-router/`, `build/`, `test-results/`, and
`playwright-report/` directories are intentionally omitted.

```text
PBI-Lineage-Frontend/
|-- .azure/
|   `-- scripts/
|       |-- deploy-frontend.ps1
|       |-- deploy-frontend-from-acr.ps1
|       `-- download-frontend-artifact.ps1
|-- .agents/
|   `-- skills/react-router/
|       |-- SKILL.md
|       `-- references/
|           |-- declarative-mode.md
|           |-- data-mode.md
|           |-- framework-mode.md
|           `-- rsc.md
|-- .github/
|   `-- workflows/
|       |-- azure-oidc-test.yml
|       |-- cd.yml
|       |-- ci.yml
|       `-- storage-upload-test.yml
|-- scripts/
|   `-- walkthrough/
|       |-- .gitignore
|       |-- capture.cjs
|       |-- compose.py
|       `-- mock-backend.cjs
|-- Docs/
|   |-- 01-overview.md
|   |-- 02-architecture.md
|   |-- 03-features-and-data-flows.md
|   |-- 04-state-and-api-layer.md
|   |-- 05-file-reference.md
|   |-- 06-testing-and-deployment.md
|   |-- 07-column-naming-standard.md
|   `-- README.md
|-- app/
|   |-- components/
|   |   |-- power-ai/
|   |   |   |-- ai-error-banner.tsx
|   |   |   |-- ask-power-ai-button.tsx
|   |   |   |-- chat-input.tsx
|   |   |   |-- context-indicator.tsx
|   |   |   |-- conversation-view.tsx
|   |   |   |-- evidence-view.tsx
|   |   |   |-- persona-selector.tsx
|   |   |   |-- power-ai-content.tsx
|   |   |   |-- power-ai-header.tsx
|   |   |   |-- power-ai-locked.tsx
|   |   |   |-- power-ai-trigger.tsx
|   |   |   |-- power-ai-widget.tsx
|   |   |   `-- suggested-questions.tsx
|   |   |-- setup-guide/
|   |   |   `-- setup-guide.tsx
|   |   |-- ui/
|   |   |   |-- badge.tsx
|   |   |   |-- button.tsx
|   |   |   |-- card.tsx
|   |   |   |-- checkbox.tsx
|   |   |   |-- command.tsx
|   |   |   |-- dialog.tsx
|   |   |   |-- dropdown-menu.tsx
|   |   |   |-- input-group.tsx
|   |   |   |-- input.tsx
|   |   |   |-- label.tsx
|   |   |   |-- select.tsx
|   |   |   |-- separator.tsx
|   |   |   |-- sheet.tsx
|   |   |   |-- skeleton.tsx
|   |   |   |-- switch.tsx
|   |   |   |-- table.tsx
|   |   |   |-- tabs.tsx
|   |   |   |-- textarea.tsx
|   |   |   |-- toast.tsx
|   |   |   `-- tooltip.tsx
|   |   |-- workspace/
|   |   |   |-- api-documentation.tsx
|   |   |   |-- api-execution-panel.tsx
|   |   |   |-- auth-required.tsx
|   |   |   |-- database-setup.tsx
|   |   |   |-- evidence-ui.tsx
|   |   |   |-- explorer.tsx
|   |   |   |-- impact-grid.tsx
|   |   |   |-- impact-lineage.tsx
|   |   |   |-- impact-picker.tsx
|   |   |   |-- impact-ui.tsx
|   |   |   |-- lineage/
|   |   |   |   |-- lineage-diagram.tsx
|   |   |   |   |-- lineage-layout.ts
|   |   |   |   |-- lineage-node.tsx
|   |   |   |   `-- lineage-types.ts
|   |   |   |-- measure-ai-definition.tsx
|   |   |   |-- measure-impact.tsx
|   |   |   |-- overview.tsx
|   |   |   |-- power-bi-setup.tsx
|   |   |   |-- report-evidence.tsx
|   |   |   |-- report-lineage.tsx
|   |   |   |-- scanner.tsx
|   |   |   |-- snowflake-object-lineage.tsx
|   |   |   |-- table-impact.tsx
|   |   |   `-- workspace-sidebar.tsx
|   |   |-- app-footer.tsx
|   |   |-- app-header.tsx
|   |   `-- reveal.tsx
|   |-- lib/
|   |   |-- api-catalog.ts
|   |   |-- dependency-graph.ts
|   |   |-- grid-export.ts
|   |   |-- impact-analysis.ts
|   |   |-- interaction-styles.ts
|   |   |-- lineage-api.ts
|   |   |-- naming.ts
|   |   |-- power-ai-api.ts
|   |   |-- power-ai-suggestions.ts
|   |   |-- query-provider.tsx
|   |   |-- scanner-api.ts
|   |   |-- use-api-executor.ts
|   |   |-- use-power-ai-chat.ts
|   |   |-- use-power-ai-status.ts
|   |   |-- use-workspace-scan.ts
|   |   |-- utils.ts
|   |   `-- workspace-routes.ts
|   |-- routes/
|   |   |-- home.tsx
|   |   |-- setup-guide.tsx
|   |   `-- workspace.tsx
|   |-- stores/
|   |   |-- app-store.ts
|   |   |-- layout-store.ts
|   |   `-- power-ai-store.ts
|   |-- app.css
|   |-- root.tsx
|   `-- routes.ts
|-- logos/
|   `-- tab_logo.png
|-- public/
|   |-- favicon.ico
|   |-- how-to-use-dark.gif
|   |-- how-to-use-light.gif
|   |-- (PNG posters for each GIF)
|   |-- tab_logo-dark.png
|   |-- tab_logo.png
|   `-- web.config
|-- tests/
|   |-- api-documentation.spec.ts
|   |-- app-shell.spec.ts
|   |-- database-mapping.spec.ts
|   |-- home.spec.ts
|   |-- impact-analysis.spec.ts
|   |-- navigation.spec.ts
|   |-- overview.spec.ts
|   |-- power-ai-units.spec.ts
|   |-- power-ai.spec.ts
|   |-- report-lineage.spec.ts
|   |-- scanner.spec.ts
|   `-- setup-guide.spec.ts
|-- .dockerignore
|-- .gitignore
|-- components.json
|-- Dockerfile
|-- package-lock.json
|-- package.json
|-- playwright.config.ts
|-- react-router.config.ts
|-- README.md
|-- tsconfig.json
`-- vite.config.ts
```

## File Responsibilities

### Root Configuration

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `README.md` | Primary source-controlled setup, architecture, operation, deployment, troubleshooting, and file-reference handbook. |
| `Docs/README.md` | Index for focused contributor documentation covering architecture, features, state/API behavior, files, tests, and deployment. |
| `package.json` | Declares runtime/dev dependencies and the `dev`, `build`, `start`, and `typecheck` commands. |
| `package-lock.json` | Locks the exact dependency graph for reproducible `npm ci` installs. |
| `vite.config.ts` | Registers React Router and Tailwind plugins, resolves `~/*`, prebundles the complete runtime import set to prevent cold lazy-route optimizer invalidation, and proxies local backend paths. |
| `react-router.config.ts` | Selects SPA mode with `ssr: false` for IIS static hosting. |
| `tsconfig.json` | Enforces strict TypeScript, browser/ES2022 libraries, bundler resolution, and `~/*` aliases. |
| `components.json` | Configures shadcn style, aliases, Tailwind CSS entry, Base UI behavior, and Lucide icons. |
| `playwright.config.ts` | Defines browser-test directory, localhost dev server reuse, timeouts, traces, and failure screenshots. |
| `Dockerfile` | Optional Node 24 multi-stage build/server image retained for non-IIS validation; IIS static hosting remains the production target. |
| `.dockerignore` | Excludes dependencies, generated builds, local context, and README from Docker build context. |
| `.gitignore` | Excludes dependencies, generated React Router/build/test artifacts, environment files, and local context documents. Walkthrough frames are ignored by `scripts/walkthrough/.gitignore`. |
| `logos/tab_logo.png` | The logo artwork as supplied (about 4.8 MB, with a transparency checkerboard painted into its pixels). It is the source for the cleaned `public/tab_logo*.png` marks and is never served. |
| `public/favicon.ico` | 16/32/48 px browser-tab icon generated from the transparent logo mark; linked first by the React Router root links. |
| `public/how-to-use-light.gif` / `public/how-to-use-dark.gif` | Animated Home walkthrough of the application's tabs, one per theme, each with a still PNG poster shown under reduced motion. Generated by `scripts/walkthrough/` from fictional data; replaces the former `product-lineage-view.png`. |
| `public/tab_logo.png` / `public/tab_logo-dark.png` | Transparent 512 px logo mark (cleaned from `logos/tab_logo.png`) used by the header and footer, plus a dark-theme copy with light slate strokes; `tab_logo.png` is also the high-resolution PNG tab icon. |
| `public/web.config` | IIS rewrite configuration copied into every production artifact; proxies API/OpenAPI requests to FastAPI and falls back application routes to `index.html`. |
| `.github/workflows/ci.yml` | Main-branch/pull-request quality gate using Node 22, `npm ci`, strict typecheck, and production build. |
| `.github/workflows/cd.yml` | Production deployment gate: builds the successful main commit, publishes the static ZIP to Azure Container Registry with ORAS, invokes the VM ACR deployment script, and smoke-tests IIS. |
| `.github/workflows/azure-oidc-test.yml` | Manual Azure federated-identity and resource-group access diagnostic. |
| `.github/workflows/storage-upload-test.yml` | Manual production-environment build and Azure Blob upload validation without changing the IIS site. |
| `.azure/scripts/download-frontend-artifact.ps1` | Uses the Azure VM managed identity to download a named release ZIP from Blob Storage and emits a machine-readable success marker. |
| `.azure/scripts/deploy-frontend.ps1` | Validates and stages a versioned release, atomically repoints IIS, performs local HTTP validation, rolls back on failure, records the release, and prunes old releases. |
| `.azure/scripts/deploy-frontend-from-acr.ps1` | Pulls the ORAS frontend artifact from ACR with VM identity and delegates validated IIS promotion to the deployment script. |

### Application Bootstrap And Routes

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/routes.ts` | Declares the Home index, `/setup-guide`, and optional workspace section route in React Router Framework Mode. |
| `app/root.tsx` | Creates the HTML shell, links the tab icons (`favicon.ico` first, then the 512 px `tab_logo.png`), installs QueryProvider and the single global Power AI widget, renders route outlets/scripts, restores scroll, and handles route errors. |
| `app/app.css` | Imports Tailwind, shadcn, animation, and Geist font styles; defines light/dark design tokens, radii, global minimum width, the motion tokens (`ease-apple`, `ease-apple-snappy`, `animate-rise`, `animate-rise-zoom`), the `[data-reveal]` scroll-reveal styles, the pointer cursor for every enabled button, and the trailing-arrow hover nudge. `@import "tailwindcss" source(".")` limits Tailwind's class scan to `app/`, so saving Markdown, Python, or test files no longer forces a dev-page reload. |
| `app/routes/setup-guide.tsx` | Wraps the static setup guide with route metadata plus the shared header and footer. |
| `app/routes/home.tsx` | Renders `/`: a centred hero that rises in line by line, the theme-matched animated walkthrough (with a reduced-motion poster) that grows into place as it scrolls into view, the evidence path cards, the investigation prompts, and the Start exploring / Setup guide actions. |
| `app/routes/workspace.tsx` | Owns the shared workspace shell, OpenAPI query, endpoint catalog, API executor, sidebar routing, mobile navigation, the full-width (sidebar-free) API reference, and lazy loading for Overview, Explorer, Report Lineage, Table Impact, Measure Impact, and Scanner. |

### Shared Application Components

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/components/app-header.tsx` | Renders product identity (the transparent logo mark with no frame, `tab_logo.png` in light theme and `tab_logo-dark.png` in dark), active Home/Workspace links and the Documents dropdown (Setup guide, API reference), the mobile navigation sheet with its "Documents" group, and an optional TanStack Query backend-health badge. Active state comes from `isApiReferencePath`. Home disables the health request and badge. |
| `app/components/reveal.tsx` | `Reveal`: fades and lifts its content into place the first time it scrolls into view (optionally staggered, or growing from 94% for large media). It arms before the first paint, so nothing flickers, and shows content as-is under reduced motion or without IntersectionObserver. |
| `app/components/app-footer.tsx` | Renders the logo mark (light/dark copies) beside the product name, shared navigation, mandatory developer attribution, and current-year copyright on all pages. |
| `app/components/setup-guide/setup-guide.tsx` | Renders the static, role-oriented Microsoft/Fabric/Scanner/XMLA/Snowflake/backend setup handbook, ordered application handoff, troubleshooting matrix, and authoritative external references. It performs no provider API calls. |

### Power AI Components

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/components/power-ai/power-ai-widget.tsx` | Mounts one lazy-loaded floating launcher/panel across Home, Setup Guide, workspace, and API routes without reducing the main canvas width. |
| `app/components/power-ai/power-ai-trigger.tsx` | Shows the ready or locked global launcher based on backend status. |
| `app/components/power-ai/power-ai-content.tsx` | Composes status-aware locked/chat states and the active conversation controls. |
| `app/components/power-ai/power-ai-header.tsx` | Displays the panel title, context summary entry point, and collapse command. |
| `app/components/power-ai/power-ai-locked.tsx` | Presents distinct disabled, unconfigured, unauthenticated, forbidden, and unavailable guidance. |
| `app/components/power-ai/chat-input.tsx` | Handles message entry plus send/stop behavior during streamed responses. |
| `app/components/power-ai/conversation-view.tsx` | Renders user/assistant messages, answer status, claims, and generated follow-up questions. |
| `app/components/power-ai/evidence-view.tsx` | Renders backend-verified evidence and claim citation markers without deriving facts in the browser. |
| `app/components/power-ai/context-indicator.tsx` | Shows the selected workspace/report/model/object identifiers and names supplied as chat context. |
| `app/components/power-ai/persona-selector.tsx` | Selects general, business, or developer explanation style. |
| `app/components/power-ai/suggested-questions.tsx` | Displays backend or context-derived question shortcuts. |
| `app/components/power-ai/ask-power-ai-button.tsx` | Opens the global panel from analysis views and seeds object context plus a starting question. |
| `app/components/power-ai/ai-error-banner.tsx` | Converts normalized AI failures into concise user-facing error states. |

### Workspace Components

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/components/workspace/workspace-sidebar.tsx` | Defines the Setup group (Power BI, Database), then Overview, Explorer, Report lineage, Table impact, and Measure impact navigation for desktop, tablet, and mobile shells. No Setup guide, Scanner, or API entry. |
| `app/components/workspace/power-bi-setup.tsx` | Validates and executes device-code/service-principal setup, presents provider readiness, clears secrets, and invalidates identity-dependent caches. |
| `app/components/workspace/database-setup.tsx` | Validates Snowflake connection input and presents connect/status/logout information without raw setup JSON. |
| `app/components/workspace/overview.tsx` | Renders `/workspace/overview`: totals of accessible workspaces, reports, and semantic models, then three filterable lists whose items link into Explorer via `explorerHref`. Reads only the shared workspace-list and estate-discovery cache entries and degrades to inline notices when estate discovery fails. |
| `app/components/workspace/explorer.tsx` | Implements workspace-scoped exploration across two tabs — Workspace content, and Report details (one report picker above the shared `ReportEvidence` sections) — plus an opt-in metadata scan panel for the current workspace's dashboards, app linkage, and ownership. Seeds its first selection once from `?workspace`, `?report`, and `?model`. |
| `app/components/workspace/report-lineage.tsx` | Discovers reports across every accessible workspace, resolves each one's bound semantic model (including a model owned by another workspace) from the estate graph, and renders the shared `ReportEvidence` sections for the selected report. |
| `app/components/workspace/report-evidence.tsx` | The five report-scoped views — Pages, Data sources, Semantic objects, Database mapping, Visual fields — with their section tabs and every call behind them. Their files are named `report-<report>-<grid>` on both screens. Shared by Explorer and Report Lineage so both screens stay identical below the report picker. |
| `app/components/workspace/evidence-ui.tsx` | Shared evidence primitives: the AG Grid wrapper with its copy/CSV/Excel toolbar, `makeExportContext` (Workspace name, Report name, Semantic model, and their IDs), the DAX column, and the loading/empty/warning/error states (including the 401-means-session-gone message). |
| `app/components/workspace/snowflake-object-lineage.tsx` | The Snowflake object (table) and column trace panels under Data sources and Database mapping, their result table, and the upward trace diagram. Builds node names from the database/schema/object parts plus the column once, and picks the highlighted node from the traced dependencies. |
| `app/components/workspace/measure-ai-definition.tsx` | The Measure definition with Power AI panel under Database mapping: one `POST /api/v1/ai/explain` per measure, rendered in place and downloadable as `.md` or `.txt`. |
| `app/components/workspace/table-impact.tsx` | Indexes every semantic model table, and the database tables behind them (`source_path` from parsed definitions), across every workspace into one grouped multi-select search. For the selected tables it runs DAX analysis and visual evidence per model, expands database tables to every semantic table sourced from them, and renders status bands, four summary tiles, the impact graph across every selected model, and four exportable grids (reports, visuals, semantic models, measures). |
| `app/components/workspace/measure-impact.tsx` | Keeps a workspace scope and one measure search, joins the measure's upstream/downstream DAX closure to its model's visual evidence, and renders status bands, five tiles, the impact graph, and six exportable grids: Tables, Measures impacted, Semantic model, Reports, Visuals, and Inputs. |
| `app/components/workspace/impact-lineage.tsx` | The impact graph both impact pages share. `buildImpactGraph` builds Database table + Semantic model -> Semantic table -> columns -> measures -> Reports -> Visuals, with node IDs namespaced per model and at most 40 reports and 120 visuals. `ImpactLineageDiagram` renders it with the Snowflake table lineage's `LineageDiagram` settings, flowing down, with reports collapsed by default, a legend, and a notice for anything not drawn. |
| `app/components/workspace/impact-ui.tsx` | Presentational pieces both impact pages share: `SummaryTile`, `ImpactSection`, `StatusBand`, `EvidenceStatus` (estate failure, estate loading, no bound reports, checking, 300-report cap, success), `LoadingState`, and `EmptyState`. |
| `app/components/workspace/auth-required.tsx` | `PowerBiAuthRequired`: the shared "Power BI authentication is required" empty state shown whenever a page's first Power BI-backed query fails, with a link back to Power BI setup. Used by Overview, Explorer, Report Lineage, Table Impact, Measure Impact, and Scanner. |
| `app/components/workspace/impact-grid.tsx` | Shared AG Grid wrapper for Table Impact and Measure Impact: teal theme, copyable cells, and a copy/CSV/Excel export toolbar. The grid is a fixed 420 px tall by default; the optional `fitRows` prop shrinks it to its rows (never below three rows or above 420 px), which both impact pages use so their stacked grids stay compact. `AgGridReact` is keyed by `emptyMessage`, so the no-rows overlay (which AG Grid reads once) updates when the message changes. |
| `app/components/workspace/scanner.tsx` | Rendered at `/workspace/scanner` (not linked from the sidebar). Runs the Power BI Admin metadata scanner across a chosen workspace scope (1-100) and browses the result across five tabs (Workspaces, Reports & dashboards, Semantic models, Dependencies, Datasource instances), each an exportable AG Grid table modeled field-for-field against Microsoft's GetScanResult schema. |
| `app/components/workspace/impact-picker.tsx` | Shared pickers. `WorkspaceScopeSelect` is a multi-select workspace scope with select-all/clear, used by Measure Impact and Scanner. `ObjectSearchSelect` is a `Command`-based single-select combobox over a preloaded inventory, used by Measure Impact. `MultiObjectSearch`, used by Table Impact, is one search box over several labeled result groups (`SearchGroup`) shown as side-by-side columns. It filters every entry itself on all typed words, ranks matches by name fit (`matchRank`: exact, prefix, segment start, contains, other text) before showing the first 100 per group, selects any number, and lists picks as removable chips with Clear/Done. A chip shows `SearchEntry.chipText` when set (Table Impact's `Table (Model)`), otherwise `primary`. |
| `app/components/workspace/api-documentation.tsx` | The API reference: groups/searches OpenAPI operations and expands the selected operation into the active execution workbench. |
| `app/components/workspace/api-execution-panel.tsx` | Renders parameter/body inputs, validates JSON, executes through the shared hook, clears sensitive values, and presents copyable body/header output. |

### Lineage Diagram Engine

Shared by Report Lineage, Snowflake tracing, Table Impact, and Measure Impact
so every dependency diagram in the application is directed, auto-laid-out,
and collapsible in the same way.

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/components/workspace/lineage/lineage-types.ts` | Declares the diagram-agnostic `LineageGraph`/`LineageGraphNode`/`LineageGraphEdge` shapes every feature builds toward, plus the React Flow node-data type. |
| `app/components/workspace/lineage/lineage-layout.ts` | Lazy-loads a worker-backed `elkjs` layered layout for a given direction (`LR`/`TB`), provides fallback positions, and estimates node height from detail-text length. |
| `app/components/workspace/lineage/lineage-node.tsx` | Custom React Flow node: tone-colored card per object kind, with a collapse/expand chevron and a hidden-descendant count when the node has children. |
| `app/components/workspace/lineage/lineage-diagram.tsx` | Exports `<LineageDiagram>`: builds an undirected "display tree", owns collapse state (optionally starting with the node kinds in `defaultCollapsedKinds` collapsed), derives the visible subgraph, runs ELK without remounting React Flow, and renders draggable nodes, reset/viewport controls, culling, and directed arrowheads. |

### API, Query, Utility, And State Files

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/lib/api-catalog.ts` | Defines OpenAPI/frontend endpoint types, fallback setup operations, request templates, schema example generation, endpoint flattening, URL construction, response parsing, method styles, and formatting helpers. |
| `app/lib/dependency-graph.ts` | Pure multi-source DAX dependency traversal (`computeDependencyClosure`) shared by Table Impact and Measure Impact, plus `closureToLineageGraph`, which turns a closure into a `LineageGraph` for the calculation diagrams in `report-lineage-diagrams.tsx` (the impact pages use `buildImpactGraph`). |
| `app/lib/impact-analysis.ts` | Evidence layer shared by Table Impact and Measure Impact: `fetchImpactEvidence` (`visual-source-lookup` only; `measure-source-lineage` is deliberately not used) and `impactEvidenceKey`, `buildEvidenceIndex` (reports and visuals per semantic object, with report, page, and visual names), `buildReportNames`, and the `SourcedTable`/`tableSources`/`tableSeeds`/`displayType` helpers. |
| `app/lib/lineage-api.ts` | Shared admin-key-aware `requestJson` fetch helper for every `/lineage/*` and `/explorer/*` call, plus `boundReportsForModel`, chunked/concurrency-limited `fetchBatchedExplorer`, `fetchEstateInventory` (table/measure inventory with parsed definitions, over every workspace for Table Impact and the chosen scope for Measure Impact), and lineage query-key factories. |
| `app/lib/scanner-api.ts` | Typed `startScan`/`getScanStatus`/`getScanResult` calls onto `/api/v1/scanner/*` (built on `requestJson`), `DEFAULT_SCAN_FLAGS`, and a full, defensive TypeScript model of Microsoft's real (backend-untyped) GetScanResult payload — every type and field from the official reference page. |
| `app/lib/workspace-routes.ts` | `WORKSPACE_SECTIONS` (working `/workspace/:section` slugs), `isApiReferencePath` (header active state and the full-width API reference), and `explorerHref` (Explorer deep links used by Overview). |
| `app/lib/use-workspace-scan.ts` | `useWorkspaceScan` hook: drives the scanner's submit-then-poll-then-fetch workflow via TanStack Query's `refetchInterval`, never runs automatically, and resets when the workspace scope changes. Shared by Explorer's scan panel and the Scanner page. |
| `app/lib/grid-export.ts` | The one export path for every grid: `toExportTable` turns rows, column definitions, and context into headers and cells (context names, then grid columns, then grid IDs, then context IDs; a context column the grid already has is left out), and `exportTableToTsv`, `downloadExportCsv` (UTF-8 BOM, CRLF), and `downloadExportExcel` write it. Also `filePart` for file names and `copyText`. |
| `app/lib/naming.ts` | The naming glossary from `Docs/07-column-naming-standard.md`: `COLUMN` headers, `VALUE` display values, `yesNo`, `dependencyLabel`, the report type/format, storage mode, and object type translators, `nameWithParent`, and the `gridColumn`/`exportOnlyColumn` column helpers. Add a header here before a grid uses it. |
| `app/lib/interaction-styles.ts` | Class helpers that give hand-built controls the Button's motion: `sectionTabClass` (underlined section tabs), `segmentGroupClass`/`segmentClass` (segmented controls), `textActionClass`, and `iconActionClass`. |
| `app/lib/use-api-executor.ts` | Executes a catalog endpoint with path/query/header values, cookies, optional ephemeral key, JSON body handling, timing, headers, and normalized failure results. |
| `app/lib/power-ai-api.ts` | Canonical Power AI wire types plus status, non-streaming chat, SSE streaming, cancellation, and normalized error handling for `/api/v1/ai/*`. |
| `app/lib/power-ai-suggestions.ts` | Produces safe route/object-aware starter questions without generating factual answers. |
| `app/lib/use-power-ai-status.ts` | Caches the authenticated backend AI status and refreshes it every 30 seconds. |
| `app/lib/use-power-ai-chat.ts` | Coordinates message state, streamed/non-streamed transport selection, cancellation, final response replacement, and friendly errors. |
| `app/lib/query-provider.tsx` | Creates one QueryClient with default retry, stale-time, and focus-refetch behavior for the application lifetime. |
| `app/lib/utils.ts` | Exposes shared class-name composition used by shadcn and custom components. |
| `app/stores/app-store.ts` | Owns normalized API origin and ephemeral admin-key memory using Zustand. |
| `app/stores/layout-store.ts` | Persists only the desktop navigation collapsed preference; drawer state remains local and sensitive state is excluded. |
| `app/stores/power-ai-store.ts` | Owns conversation/UI state and persists only the selected audience; messages, context, errors, and panel-open state are not persisted. |

### UI Primitives

These files are local shadcn/Base UI building blocks. Keep application behavior
in feature components and primitive behavior/styling here.

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `app/components/ui/badge.tsx` | Compact status/category labels. |
| `app/components/ui/button.tsx` | Pill-shaped button variants (`default`, `outline`, `outline-brand`, `secondary`, `ghost`, `destructive`, `link`) and sizes, eased colour changes, a slight press-in (skipped on menu triggers), a soft focus ring, and rendered-link/button behavior. |
| `app/components/ui/card.tsx` | Small framed content surfaces used where information is genuinely grouped. |
| `app/components/ui/checkbox.tsx` | Accessible binary checkbox control. |
| `app/components/ui/command.tsx` | Command/search list composition based on cmdk. |
| `app/components/ui/dialog.tsx` | Accessible modal dialog primitives. |
| `app/components/ui/dropdown-menu.tsx` | Accessible menu trigger, content, item, and submenu primitives. |
| `app/components/ui/input-group.tsx` | Inputs with leading/trailing controls or content. |
| `app/components/ui/input.tsx` | Standard text/password/number input styling. |
| `app/components/ui/label.tsx` | Accessible form labels. |
| `app/components/ui/select.tsx` | Base UI select trigger, content, and option primitives. |
| `app/components/ui/separator.tsx` | Horizontal/vertical semantic separators. |
| `app/components/ui/sheet.tsx` | Responsive side sheet used by mobile workspace navigation. |
| `app/components/ui/textarea.tsx` | Multi-line input used by JSON request editors. |
| `app/components/ui/skeleton.tsx` | Stable loading placeholders. |
| `app/components/ui/switch.tsx` | Accessible binary feature control. |
| `app/components/ui/table.tsx` | Semantic table structure for compact non-grid content. |
| `app/components/ui/tabs.tsx` | Accessible tab list, trigger, and panel primitives. |
| `app/components/ui/toast.tsx` | Local toast state and renderer with no external toast/theme dependency. |
| `app/components/ui/tooltip.tsx` | Accessible hover/focus descriptions for compact icon controls. |

`app/components/ui/sonner.tsx` is intentionally not part of the project. It
was unreachable and referenced the uninstalled `sonner` and `next-themes`
packages, so retaining it caused clean-clone and GitHub TypeScript failures.

### Tests And Context

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `tests/report-lineage.spec.ts` | Mocks backend contracts and verifies the five report sections, their standard export headers and order, that the replaced section names are gone, the Snowflake table and column traces (including that a traced column is never drawn as a detached node), desktop layout, and mobile containment. |
| `tests/database-mapping.spec.ts` | Verifies Explorer's Database mapping section: the snapshot request waits until the section opens and keeps gateway lookups off until opted in, each semantic object's database columns and tables, the Not found / Not available / Not applicable values, the export headers and file name, the panels it feeds, and the error state. |
| `tests/impact-analysis.spec.ts` | Mocks a two-workspace, two-model backend fixture and verifies Table Impact's grouped multi-select table search and multi-model results, Measure Impact's workspace scope and measure search, the impact graphs, every grid's standard headers, values, and export order, the file names, and the status bands, including a failed list of reports. |
| `tests/scanner.spec.ts` | Mocks the four `/api/v1/scanner/*` endpoints (including a status route that reports "Running" before "Succeeded", proving the poll loop works) against a fixture covering every entity type, and verifies both the dedicated Scanner page's multi-workspace scan-and-browse flow across all five tabs and Explorer's single-workspace scan panel replacing its dashboards/app-linkage/ownership placeholders. |
| `tests/api-documentation.spec.ts` | Mocks OpenAPI/backend operations and verifies GET/POST execution, JSON validation, response metadata, and output copying behavior. |
| `tests/app-shell.spec.ts` | Verifies desktop navigation persistence, tablet icon rail behavior, mobile drawers, and the non-resizing floating Power AI overlay. |
| `tests/power-ai.spec.ts` | Verifies availability states, Power BI auth/permission locks, persona persistence, object context, SSE/non-SSE chat, cancellation, evidence, friendly errors, and responsive conversation continuity. |
| `tests/power-ai-units.spec.ts` | Runs the pure Power AI answer modules (answer parsing, section tabs, entity chips, DAX highlighting, lineage layers) directly in Playwright's Node process, with no page. |
| `tests/home.spec.ts` | Verifies the Home route, the Start exploring and Setup guide actions, database-neutral copy, no Home health request, the walkthrough image, header navigation including the Documents menu, and desktop/mobile containment. |
| `tests/navigation.spec.ts` | Verifies the header's Home/Workspace/Documents navigation, the grouped mobile sheet, and the workspace sidebar's items. |
| `tests/overview.spec.ts` | Verifies Overview totals, the three linked sections and their filters, Explorer deep links, and the estate-discovery failure state. |
| `tests/setup-guide.spec.ts` | Verifies `/setup-guide`, required setup sections and official links, reaching the guide from the Documents menu and Home, and desktop/mobile layouts. |
| `REF_DOC/PROJECT_CONTEXT.md` | Local continuity document containing current frontend contracts and implementation constraints; ignored by Git. |

### Home Walkthrough Tooling

Development-only scripts; they are not part of the build or the deployed
artifact.

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `scripts/walkthrough/mock-backend.cjs` | Playwright route mocks serving a fictional estate, so the capture needs no tenant or real data. |
| `scripts/walkthrough/capture.cjs` | Drives the dev server on `:5173` through each tab in light and dark themes and saves frames to `scripts/walkthrough/.frames/`. |
| `scripts/walkthrough/.gitignore` | Keeps the captured `.frames/` directory out of Git. |
| `scripts/walkthrough/compose.py` | Composes the frames into `public/how-to-use-light.gif`, `public/how-to-use-dark.gif`, and their PNG posters. Needs Python 3 and Pillow. |

### Local Agent Reference Files

| File | Purpose and fulfilled responsibility |
| --- | --- |
| `.agents/skills/react-router/SKILL.md` | Local coding-agent instructions for React Router work. It is tooling guidance, not runtime code. |
| `.agents/skills/react-router/references/framework-mode.md` | Agent reference for Framework Mode conventions. |
| `.agents/skills/react-router/references/data-mode.md` | Agent reference for Data Mode conventions. |
| `.agents/skills/react-router/references/declarative-mode.md` | Agent reference for Declarative Mode conventions. |
| `.agents/skills/react-router/references/rsc.md` | Agent reference for React Server Component considerations. |

## Testing

Run static checks:

```powershell
npm run typecheck
npm run build
```

Run browser tests:

```powershell
npx playwright test
```

Playwright starts or reuses `http://localhost:5173`, intercepts backend calls,
and does not require a live authenticated tenant for contract-driven UI tests.
Use a real tenant-authenticated session for final provider acceptance because
mocked tests cannot prove Microsoft/Fabric permissions or tenant data quality.

Generated browser artifacts are written to ignored `test-results/` and
`playwright-report/` directories.

## Home Walkthrough

The animated walkthrough on Home (`public/how-to-use-light.gif`,
`public/how-to-use-dark.gif`, and a still PNG poster for each) is recorded from
the running application with fictional data only. Regenerate it after a
visible UI change:

```powershell
npm run dev                                # keep it running on http://localhost:5173
node scripts/walkthrough/capture.cjs       # in a second window: frames -> scripts/walkthrough/.frames/
python scripts/walkthrough/compose.py      # Python 3 + Pillow: GIFs and posters -> public/
```

`capture.cjs` serves the fictional estate from `mock-backend.cjs` and clicks
through Power BI setup, Database, Overview, Explorer, Report lineage, Table
impact, Measure impact, Power AI, and the Documents menu in both themes. The
frames directory is gitignored; commit the regenerated files under
`public/`.

## Production Build

Stop the development server and run:

```powershell
cd C:\Users\Administrator\Desktop\PBI-Lineage-Frontend
npm ci
npm run typecheck
npm run build
```

Deploy this directory to the IIS site root:

```text
C:\Users\Administrator\Desktop\PBI-Lineage-Frontend\build\client
```

Do not deploy source, `node_modules`, `.env`, tests, Playwright output, or the
React Router server bundle when IIS is serving the static SPA.

## Automated Azure Deployment

The production workflow in `.github/workflows/cd.yml` deploys the static IIS
artifact to the Windows Azure VM. It runs only when `DEPLOYMENT_ENABLED` is
`true` and either:

1. `Frontend CI` completed successfully for `main`.
2. A maintainer manually dispatched the workflow from `main`.

The workflow deliberately uses `cancel-in-progress: false` so one production
release cannot interrupt another. Its deployment sequence is:

1. Resolve and check out the exact release commit.
2. Use Node 22 and `npm ci` to reproduce the locked dependency graph.
3. Build the SPA and require both `build/client/index.html` and
   `build/client/web.config`.
4. ZIP only the contents of `build/client`.
5. Authenticate GitHub Actions to Azure through OIDC, without a stored Azure
   client secret.
6. Resolve the ACR login server, install ORAS on the runner, and push the ZIP
   plus `deploy-frontend.ps1` as a versioned OCI artifact.
7. Invoke Azure VM Run Command with
   `.azure/scripts/deploy-frontend-from-acr.ps1`.
8. Let the VM managed identity obtain a short-lived ACR token, pull the exact
   release with ORAS, and invoke `deploy-frontend.ps1`.
9. Stage and validate a versioned release, repoint the `PBI-Lineage` IIS site,
   recycle its application pool, and roll back automatically on failure.
10. Smoke-test the deployed site through IIS on the VM.

Required GitHub `production` environment secrets:

| Secret | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID of the Azure federated identity used by GitHub OIDC. |
| `AZURE_TENANT_ID` | Microsoft Entra tenant containing the deployment identity. |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription containing the production resources. |

Required GitHub repository/environment variables:

| Variable | Purpose |
| --- | --- |
| `DEPLOYMENT_ENABLED` | Must equal `true` before the production job is allowed to run. |
| `AZURE_RESOURCE_GROUP` | Resource group containing the target VM. |
| `AZURE_VM_NAME` | Windows VM reached through Azure VM Run Command. |
| `ACR_NAME` | Azure Container Registry that stores the frontend OCI artifact. |
| `ACR_REPOSITORY` | ACR repository name used for versioned frontend releases. |
| `PRODUCTION_URL` | Public application URL shown in the GitHub deployment environment. |

Production VM layout:

```text
C:\pbi-lineage\
|-- deploy\                         Temporary ORAS pull workspace
`-- frontend\
    |-- current-release.txt
    `-- releases\
        `-- <commit-sha>\
            |-- index.html
            |-- web.config
            `-- assets\
```

The GitHub OIDC identity needs ACR push access and permission to run commands on
the VM. The VM managed identity needs ACR pull access. Azure CLI and ORAS must
be available on the VM. IIS and the `PBI-Lineage` site must already exist;
deployment moves versioned static files and changes the site physical path but
does not install IIS or create the site.

Use `.github/workflows/azure-oidc-test.yml` to verify federated Azure access.
`storage-upload-test.yml` remains a manual legacy Blob diagnostic and is not
part of the current ACR production release path.

## IIS Setup

Recommended Windows features/modules:

1. IIS Static Content.
2. IIS URL Rewrite module.
3. Application Request Routing (ARR) with proxy enabled.

Recommended site settings:

- Physical path: deployed `build/client` directory.
- Application pool: `No Managed Code`.
- HTTPS binding for production.
- Backend container published only to loopback or an internal interface.

Place a `web.config` in the deployed `build/client` directory. Example:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="FastAPI API" stopProcessing="true">
          <match url="^(api/.*|openapi\.json)$" />
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:0}" />
        </rule>
        <rule name="React SPA" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>
    <staticContent>
      <remove fileExtension=".json" />
      <mimeMap fileExtension=".json" mimeType="application/json" />
    </staticContent>
  </system.webServer>
</configuration>
```

Keep `/docs` private unless there is an explicit operational requirement. The
application documentation uses `/openapi.json` and does not need to expose the
Swagger page publicly.

## Deployment Verification

After IIS deployment verify:

1. `/` loads Home and its walkthrough animation without a Node process, and
   `/setup-guide` loads directly.
2. `/workspace/overview` and `/workspace/report-lineage` load directly after a
   hard refresh.
3. `/workspace/table-impact`, `/workspace/measure-impact`, and
   `/workspace/scanner` load directly after hard refreshes.
4. `/api/v1/health/live` returns through IIS.
5. `/openapi.json` returns through IIS.
6. Power BI login sets and reuses the backend session cookie.
7. The API reference can execute a harmless GET such as health/status.
8. CSV/Excel downloads work in the browser.
9. The footer shows `Developed by Satyadeep Singh` and copyright.
10. `C:\pbi-lineage\frontend\current-release.txt` contains the deployed
    commit SHA after an automated release.

## Troubleshooting

### `npm` or `node` is not recognized

- Install Node.js for all users or add its installation directory to system
  `PATH`.
- Close and reopen PowerShell after changing `PATH`.
- Verify with `where.exe node` and `where.exe npm`.

### PowerShell blocks `npm.ps1`

Use `npm.cmd`, or apply an approved organizational execution policy. Do not
disable machine security policy only for this project.

### Vite shows `bundling dependencies` for a long time

- Wait for the first dependency optimization to complete.
- Use `http://localhost:5173`, not a different host name.
- Avoid refreshing continuously while optimization is running.
- Stop concurrent `npm run build` processes.
- If the optimizer cache is genuinely stale, stop Vite, remove
  `node_modules/.vite`, and start it again.

### Page remains on `Loading Explorer`

- Check the Vite console for a failed dynamic import.
- Confirm `localhost:5173` matches the server URL.
- Confirm the complete runtime import list remains in `optimizeDeps.include`;
  lazy imports that are omitted can trigger another optimizer generation.
- Run `npm run typecheck` to catch a failed lazy module compilation.

### The dev page reloads when a Markdown or script file is saved

- Confirm `app/app.css` still opens with `@import "tailwindcss" source(".")`.
  Without `source(".")`, Tailwind scans the whole repository, and saving
  `README.md`, `Docs/*.md`, or `scripts/*.py` forces a full page reload
  because the Vite plugin cannot hot-update those files.
- Restart the dev server after changing that line.
- Run only one dev server. A second Vite process on another port shares the
  optimizer cache and can trigger reloads in the first.

### Backend badge is offline

- Verify FastAPI at `http://127.0.0.1:8000/api/v1/health`.
- Verify Vite proxy configuration.
- Check Docker port publishing and Windows Firewall rules.

### API execution returns 401 or 403

- Complete Power BI setup for Microsoft operations.
- Complete Snowflake setup for Snowflake operations.
- Confirm the connected identity has required Power BI/Fabric permissions.
- A protected lineage route can require an administrative key supplied by the
  approved host integration; the visible UI intentionally does not request it.

### Report is listed but definition/semantic tabs are partial

Listing permission does not guarantee PBIR, TMDL, Fabric, or XMLA access. Read
the warning shown for the selected report and verify provider permissions and
capacity. The UI intentionally keeps available evidence visible.

### Direct IIS route returns 404

Install URL Rewrite and verify the SPA fallback rewrites non-file/non-directory
requests to `/index.html` after the API proxy rule.

### Authentication works in development but not IIS

- Prefer same-origin IIS proxying.
- Verify HTTPS, cookie domain/path, `Secure`, and `SameSite` policy.
- Confirm ARR preserves relevant headers and response cookies.

## Security Rules

- Never commit credentials, tokens, cookies, API keys, `.env`, or provider
  response captures.
- Do not expose FastAPI port 8000 to the public internet.
- Do not add a visible admin-key field without an explicit security decision.
- Keep service-principal and Snowflake secrets transient.
- Treat downloaded lineage data as tenant metadata and protect it accordingly.
- Review DELETE/logout or scan-start operations before running them from the
  API reference; the workbench executes the selected backend operation exactly.

## Current Limitations

- Live provider acceptance requires a real Power BI/Fabric session and tenant
  permissions.
- XMLA and definition access depend on capacity and provider policy.
- Physical source analysis can require optional backend administrative policy.
- Dashboards, app linkage, and ownership are only available after an explicit
  metadata scan (Explorer's Assets tab, or the Scanner page at
  `/workspace/scanner`) — never invented
  or assumed present before a scan has succeeded. The scan payload never
  contains app *names* (only `appId` linkage) or full sharing ACLs, only
  creator/last-editor/configuring identities.
- Orval, Vitest, and React Testing Library are installed but generated clients
  and focused unit/component suites are not yet committed.
- Explorer has no spec of its own for its tab layout (`tests/explorer.spec.ts`
  does not exist). Its Database mapping section is covered by
  `tests/database-mapping.spec.ts`, its report sections through Report
  lineage (they are the same component), its deep links by
  `tests/overview.spec.ts`, and its scan panel by `tests/scanner.spec.ts`.
- The Measure impact graph also links reports that use the measure's inputs.
  For example, a visual that reads only `Sales[Amount]` is drawn under a
  report even though it is not affected by `Sales[Total Sales]`. The Reports
  and Visuals grids are correct. `tests/impact-analysis.spec.ts` flags this
  with soft checks, so that test fails until the graph is fixed.
- Table Impact and Measure Impact compute cross-report/visual evidence from at
  most the first 300 reports bound to a semantic model (a visible notice
  appears if that cap is reached). Table Impact applies the cap to each model
  in the selection separately. See "Suggested Backend Endpoints" below for
  the change that would remove it.
- Table Impact and Measure Impact count report and visual usage only from
  `visual-source-lookup`: a report is listed when one of its visuals reads an
  impacted object. A report bound to the model that shows none of those
  objects is not listed, though it still counts toward "Reports bound".
- The impact graph draws at most 40 reports and 120 visuals, keeping the
  most-used ones, and says how many it left out. The grids list every report
  and visual.
- Table Impact and Measure Impact know a database table only through the
  `source_path` values in parsed semantic model definitions. A semantic table
  whose definition reports no source adds no database-table entry, and its
  Database tables cell reads "Not available".
- Scan progress and results are not persisted: navigating away from Explorer
  or the Scanner page and back starts fresh. Scans are also subject to real
  Microsoft tenant hourly limits (30 modified-workspace checks, 500 scan
  submissions, 500 result reads) that the backend passes through rather than
  emulating locally — repeated scanning can be throttled by Microsoft, not
  just by this application.

## Suggested Backend Endpoints

Table Impact and Measure Impact are built entirely on existing
`PBI-Lineage-Backend` endpoints (`dax/analyze`, `estate/discover`,
`explorer/visual-source-lookup`). Three
backend additions would simplify or remove current limitations; none are
implemented here because this repository does not modify the backend:

1. `GET /api/v1/lineage/estate/bindings?semantic_model_id={id}`: return only
   the report/workspace pairs bound to one model, instead of filtering a full
   `estate/discover` response client-side.
2. `POST /api/v1/lineage/impact/table` and `.../impact/measure`: return a
   pre-joined dependency closure plus report/visual evidence in one call (for
   Table Impact, for a set of tables that may span models), removing the
   client-side 50-report chunking in `fetchBatchedExplorer` and the per-model
   request fan-out.
3. Raise or remove `ExplorerRequest.reports`' 50-item cap, or add a
   `semantic_model_id`-scoped variant of `visual-source-lookup`, so
   cross-report evidence is not capped at 300 bound reports client-side.
