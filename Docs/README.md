# Documentation Index

Focused contributor context for the **PBI Lineage Explorer Frontend**, based
on the current source tree. The root [README.md](../README.md) remains the
authoritative setup, deployment, security, troubleshooting, and complete file
handbook.

| File | Contents |
| --- | --- |
| [01-overview.md](01-overview.md) | Purpose, ownership boundary, stack, and prerequisites. |
| [02-architecture.md](02-architecture.md) | Folder layout, routing, global/workspace navigation, lazy boundaries, the shared lineage and impact-graph boundary, request flow, build (including Tailwind's `app/`-only class scan), and Azure runtime. |
| [03-features-and-data-flows.md](03-features-and-data-flows.md) | Home walkthrough, Setup, Overview, Explorer (including deep links), Report Lineage, shared impact evidence and graph, Table/Measure Impact, Scanner, API reference, and exports. |
| [04-state-and-api-layer.md](04-state-and-api-layer.md) | Zustand/TanStack Query ownership plus OpenAPI, lineage, impact-evidence, scanner, dependency, impact-picker, and export utilities. |
| [05-file-reference.md](05-file-reference.md) | Per-file responsibility map for source, tests, walkthrough tooling, CI/CD, and Azure scripts. |
| [06-testing-and-deployment.md](06-testing-and-deployment.md) | Commands, Playwright coverage, production build, Azure release, IIS, and verification. |
| [07-column-naming-standard.md](07-column-naming-standard.md) | The naming standard every grid, tile, message, and export follows (applied), with each old name beside its standard one, the export file names, and words to avoid. |

## Quick Facts

- Stack: React 19, React Router Framework Mode SPA, Vite 8, strict TypeScript,
  Tailwind CSS 4, and shadcn/Base UI. Tailwind scans only `app/` for class
  names (`@import "tailwindcss" source(".")` in `app/app.css`), so saving a
  Markdown, script, or test file never reloads the dev page.
- State: TanStack Query for server state; in-memory Zustand for API origin and
  the optional ephemeral administrative key.
- Names: one glossary, `app/lib/naming.ts`, following
  [07-column-naming-standard.md](07-column-naming-standard.md). Copy table,
  CSV, and Excel write the on-screen headers, context first and IDs last
  (`toExportTable` in `app/lib/grid-export.ts`).
- Look and motion: pill buttons, shared `ease-apple` easing, scroll reveal
  (`app/components/reveal.tsx`), and interaction helpers
  (`app/lib/interaction-styles.ts`), all off under reduced motion.
- Evidence UI: AG Grid for copyable/exportable tables; React Flow plus ELK
  for directed, draggable, collapsible lineage diagrams. Table and Measure
  Impact share one impact graph (`impact-lineage.tsx`), drawn like the
  Snowflake table lineage, from database table down to visual.
- Impact evidence: report and visual usage comes only from
  `POST /api/v1/explorer/visual-source-lookup` (`app/lib/impact-analysis.ts`);
  `measure-source-lineage` is no longer called.
- Backend: separate sibling FastAPI repository, reached through `/api/v1/*`
  and `/openapi.json` using backend-managed HTTP-only sessions.
- API model: live runtime OpenAPI parsing; Orval is installed but no generated
  client is committed.
- Production: static `build/client` on IIS, deployed to a Windows Azure VM via
  GitHub OIDC, private Blob Storage, VM Run Command, and versioned releases.
- Entry points: `app/routes.ts` maps Home at `/`, the Setup Guide at
  `/setup-guide`, and the operational shell at `/workspace/:section?`.
- Navigation: the header offers Home, Workspace, and a Documents menu (Setup
  guide, API reference). The workspace sidebar lists Power BI and Database
  setup, then Overview, Explorer, Report lineage, Table impact, and Measure
  impact. API reference renders full-width without that sidebar.

## Product Summary

The app begins with a high-level Home view and an animated walkthrough of its
screens, keeps a static administrator/operator Setup Guide under the header's
Documents menu, authenticates Power BI/Fabric, optionally connects a source
system through the current Snowflake connector, totals and links every
accessible workspace, report, and semantic model on Overview, explores
workspace/report/model evidence, maps semantic objects to physical sources,
renders report/column/calculation lineage, analyzes table and measure impact
down to the reports and visuals that use them, runs explicit Power BI Admin metadata scans, provides copy/CSV/Excel output,
and executes the backend's OpenAPI operations from the API reference. Provider credentials and tokens
are never stored by the frontend.

Before relying on this documentation from a fresh clone, confirm all required
source and Docs files are committed with `git status --short`; local builds can
see untracked files that CI and another computer cannot.
