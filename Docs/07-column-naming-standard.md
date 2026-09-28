# Column naming standard

This document proposes one naming standard for every table (grid), summary
tile, and export column on the four analysis pages in the workspace sidebar:
**Explorer**, **Report lineage**, **Table impact**, and **Measure impact**.
Today the same thing is named several ways, sometimes on the same screen. For
example, a semantic model is called "Semantic model", "Model name", "Linked
model", "Dataset ID", and `parent_semantic_model_name`, depending on the grid.
Downloads and copied tables also use internal code names (`semanticModel`,
`sourceTable`, `parent_workspace_id`) instead of the headers people see. The
standard gives each object one plain-language name that a business user of
Power BI can read without help, and uses that same name on screen, in
**Copy table**, and in **CSV** and **Excel** files.

> **Status: applied (2026-09-29).** Every page now uses the "Proposed" names
> below. The mapping tables keep the old name beside each standard name as a
> record of what changed. The names live in one glossary,
> [`app/lib/naming.ts`](../app/lib/naming.ts), and the export rule (screen
> header = file header, context first, IDs last) lives in
> [`app/lib/grid-export.ts`](../app/lib/grid-export.ts). The Playwright suite
> asserts the headers and export order of every grid it covers.

## At a glance: the ten most important renames

| # | Today | Proposed | Where |
| --- | --- | --- | --- |
| 1 | `parent_workspace_name`, `parent_report_id`, `parent_semantic_model_name` … (shown as headers, and in every export) | **Workspace name**, **Report ID**, **Semantic model** … | Semantic to database mapping grid; every export |
| 2 | Export headers `name`, `type`, `kind`, `dataType`, `sourceTable`, `reportCount` … | Export header = the on-screen header, for example **Report name**, **Object type**, **Data type**, **Database table** | Every grid |
| 3 | "Table" (unqualified), "Table name" | **Semantic table** or **Database table**, never just "Table" | All pages |
| 4 | "Source column", `sourceColumn`, "Source table", `sourceTable`, "Source DB" | **Database column**, **Database table**, **Database** | Report evidence, measure definition download |
| 5 | "Model name", "Linked model", "Dataset ID" | **Semantic model**, **Semantic model ID** | Explorer, Page details, Source DB lineage |
| 6 | "Access" (means *owned by you* in one grid, *read-only* in another) | **Owned by you** (Yes/No) and **Read-only** (Yes/No) | Explorer |
| 7 | "Type" on its own (report type, item type, object type) | **Report type**, **Item type**, **Object type**, **Visual type** | All pages |
| 8 | "Relationship: Direct / Transitive", "Depth" | **Dependency: Direct / Indirect**, **Steps away** | Table impact, Measure impact |
| 9 | "Usage: Reads table fields / Through measures / Shows the measure" | **How it is used: Uses it directly / Through a measure** | Table impact, Measure impact |
| 10 | `Sales[Total Sales]` as the only name column | **Measure name** "Total Sales" + **Semantic table** "Sales" | Table impact, Measure impact |

## Core principles

1. **One name per thing, everywhere.** A concept keeps the same name on every
   page, in every grid, tile, filter, message, and export. The vocabulary
   below is the only source of names.
2. **Sentence case.** Capitalize only the first word and proper names:
   "Semantic model", "Report name", "Power BI report". Never Title Case
   ("Semantic Model"), camelCase (`semanticModel`), or snake_case
   (`semantic_model`).
3. **Object first, then attribute.** "Report name", "Report ID", "Visual
   type", "Database table". A header must make sense on its own after it is
   pasted into Excel, with no page around it.
4. **The export header equals the screen header.** Copy table, CSV, and Excel
   use exactly the headers shown in the grid, in the same order.
   Export-only columns (IDs) get standard names too.
5. **Context columns come first, with normal names.** The workspace, report,
   semantic model, or selection a download belongs to is written as the first
   columns ("Workspace name", "Report name", "Selected tables" …), never as
   `parent_…` keys.
6. **IDs are "<Object> ID" and sit last.** "Report ID", "Semantic model ID",
   "Visual ID". Write "ID" in capitals. Identity columns (names) come first,
   IDs last.
7. **Counts are "Number of <objects>".** For example "Number of reports" and
   "Number of visuals". Summary tiles are the only exception: they keep a short plural
   ("Reports") because the big number beside it makes the meaning obvious.
   A plural header without "Number of" ("Selected tables", "Objects used")
   always holds a list of names, never a number.
8. **Yes/No columns name the fact; values are Yes, No, or Unknown.**
   "Refresh enabled", "Gateway required", "Owned by you", "Read-only".
   Do not merge "No" and "Unknown" into one value.
9. **Plain words, not code or API terms.** No "kind", "origin", "domain",
   "via", "estate", "bound", "closure", "evidence", "resolved", "XMLA", or
   "TMDL" in headers (see [Words to avoid](#words-to-avoid)). Raw API values
   are translated too ("PowerBIReport" → "Power BI report").
10. **Short headers.** Aim for four words or fewer. Put longer explanations in
    the section description above the grid, not in the header.
11. **Say why a value is missing.** Use one of three values instead of `--`,
    "Not reported", "Not resolved", or "Unresolved":
    - **Not available**: Power BI or the database did not provide the value.
    - **Not found**: the app looked but could not trace it.
    - **Not applicable**: the value does not exist for this kind of item (for
      example, a schema for a file).
12. **Allowed abbreviations:** ID, DAX, URL, and product names (Power BI,
    Fabric, Snowflake). Everything else is written out ("Database", not "DB").

## Object vocabulary

The standard names for every object the four pages show. Use the standard name
exactly. Where "Avoid" lists a word, that word should not appear in headers,
tiles, or messages for this object.

### Power BI objects

| Standard name | What it means (business definition) | Avoid |
| --- | --- | --- |
| Workspace | A Power BI workspace that holds reports, dashboards, and semantic models. | Group |
| App | A published Power BI app that bundles reports and dashboards for an audience. | Linked app |
| Report | A Power BI report (interactive or paginated). | — |
| Page | One page (tab) inside a report. | Report page, section |
| Visual | One chart, table, card, or other item on a report page. | Visual object, tile (tiles belong to dashboards) |
| Dashboard | A Power BI dashboard made of pinned tiles. | — |
| Dashboard tile | One pinned item on a dashboard. | Tile (on its own) |
| Semantic model | The Power BI data model a report reads from (formerly called a dataset). | Dataset, model, linked model, bound model |
| Semantic table | A table inside a semantic model. | Table (on its own), semantic model table |
| Column | A column of a semantic table that holds data. | Field (on its own) |
| Calculated column | A column whose values come from a DAX expression. | — |
| Calculated table | A semantic table built from a DAX expression. | — |
| Measure | A DAX calculation such as "Total Sales". | Metric, KPI |
| Hierarchy | A drill path such as Year → Month in a semantic table. | — |
| Hierarchy level | One level of a hierarchy. | — |
| Semantic object | Any column, calculated column, measure, calculated table, or hierarchy. Use it only when a grid mixes these types. | Object (on its own), field, semantic model object |
| Owner | A person responsible for an item. Always say which kind: Created by, Last modified by, or Configured by. | Owner (as a single mixed column) |

### Database objects

| Standard name | What it means | Avoid |
| --- | --- | --- |
| Data source | Anything a semantic model loads data from: a database table or view, a native query, a file, a web URL, or an endpoint. | Origin, source object |
| Data source type | The kind of data source: Database table, Database view, Native query, File, Web URL, Endpoint, Not found. | Origin, source object type |
| Database account | The database service account or server, for example a Snowflake account. | Source account, account |
| Database | A database inside that account, for example "ANALYTICS". | Source DB, source database |
| Schema | A schema inside a database, for example "FINANCE". | Source schema |
| Database table | A physical table or view, shown as its full name `DATABASE.SCHEMA.TABLE`, for example "ANALYTICS.FINANCE.FACT_SALES". | Source table, `sourceTable`, table name, physical table |
| Database column | A column of a database table. | Source column, `sourceColumn` |

### Lineage and impact words

| Standard name | Meaning | Avoid |
| --- | --- | --- |
| Depends on / Inputs | What an object reads (the things it needs). "Inputs" is used as a section title. | Upstream (in headers) |
| Used by / Impacted | What reads an object and so changes when it changes. "Impacted" is used in titles and counts. | Downstream (in headers) |
| Dependency: Direct / Indirect | Direct = reads it itself. Indirect = reads it through another calculation. | Transitive, directness |
| Steps away | How many links separate two objects (1 = direct). | Depth, distance |
| How it is used | How a report or visual uses the selected item: **Uses it directly** or **Through a measure** (or **Through a calculation**). | Usage, reads table fields |
| Connected report | A report whose data comes from a given semantic model. | Bound report |
| Selected tables / Selected measure | What the user picked in the search. | Selected as |
| Reached through | For composite models: the workspace › semantic model › semantic table a data source was reached through; "Directly" when there is no hop. | Via, via (composite model) |
| Traced: Fully / Partly / Not traced | Whether a visual field was followed all the way to a database column. | Resolved, partial, unresolved |

## Column patterns

Reusable templates. Every header in the page mapping follows one of these.

| Pattern | Template | Examples |
| --- | --- | --- |
| Name | `<Object> name` | Report name, Page name, Visual name, Dashboard name, Workspace name, Measure name, Object name |
| Name (standard object with no attribute) | The object name alone | Semantic model, Semantic table, Database table, Database column, Database, Schema |
| ID | `<Object> ID` (always last) | Workspace ID, Report ID, Semantic model ID, Page ID, Visual ID, Dashboard ID, App ID |
| Type | `<Object> type` | Report type, Visual type, Object type, Item type, Data type, Data source type |
| Count | `Number of <objects>` | Number of pages, Number of visuals, Number of dashboard tiles, Number of impacted measures |
| Yes/No | The fact, values Yes / No / Unknown | Owned by you, Read-only, Refresh enabled, Gateway required |
| Expression | `DAX expression` / `Referenced as` | DAX expression (full formula), Referenced as (the part of the formula that points at the object, for example `[Total Sales]`) |
| List of names | Plural noun | Selected tables, Objects used, Database tables |
| Relationship | Vocabulary above | Dependency, Steps away, How it is used, Reached through |
| Person | `Created by` / `Last modified by` / `Configured by` | Last modified by |
| Status | Plain adjective | Traced, Answer status |
| Context (export) | Same as name/ID patterns, first in the file | Workspace name, Workspace ID, Report name, Report ID, Semantic model, Semantic model ID, Selected tables, Selected measure |

### Value standards

| Today (raw value) | Proposed display value |
| --- | --- |
| `PowerBIReport` / `PaginatedReport` | Power BI report / Paginated report |
| `PBIR` / `PBIRLegacy` / `PBIX` | PBIR / PBIR (legacy) / PBIX (a report file format; keep the codes and explain them in the column description) |
| Storage mode `Abf` / `PremiumFiles` / `DirectLake` | Import / Import (large model) / Direct Lake |
| `calculated_column`, `hierarchy_level` … | Calculated column, Hierarchy level … |
| "You" / "Shared" (Access) | Owned by you: Yes / No |
| "Read-only" / "Editable" | Read-only: Yes / No |
| "Refreshable" / "Not reported" | Refresh enabled: Yes / Unknown |
| "Required" / "Not required" | Gateway required: Yes / No (Unknown when not provided) |
| `--`, "Not reported", "Not resolved", "Unresolved", "No model returned" | Not available / Not found / Not applicable (principle 11) |
| "Direct" / "Transitive" | Direct / Indirect |
| "Reads table fields" / "Shows the measure" / "Through measures" / "Through impacted measures" | Uses it directly / Through a measure |

## Page-by-page mapping

Each table lists every column of one grid in its current order: the header
shown today, the export header written today, and the proposed name used for
both. "(export only)" marks a column that exists only in Copy table, CSV,
and Excel. Rows in *italics* are proposed additions or removals.

### Explorer

#### Workspace content tab (today "Assets & access") › Reports

`explorer.tsx`: export file today `<workspace>-reports`.

| Current screen header | Current export header | Proposed header (screen and export) | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_name` | Workspace name | Context column, first |
| (export only) | `parent_workspace_id` | Workspace ID | Context column; move to the end with the other IDs |
| Report name | `name` | Report name | |
| Type | `type` | Report type | Values: Power BI report / Paginated report |
| Semantic model | `semanticModel` | Semantic model | Replace fallbacks "Model in another workspace" → "In another workspace", "External or unresolved model" → "Not found", "No model returned" → "Not available" |
| Format | `format` | Report format | |
| Access | `access` | Owned by you | Yes / No |
| (export only) | `reportId` | Report ID | Last |

#### Workspace content › Semantic models

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_name` | Workspace name | Context |
| (export only) | `parent_workspace_id` | Workspace ID | Context |
| Model name | `name` | Semantic model | Same name as in the Reports grid |
| Storage mode | `storage` | Storage mode | Translate values (Import, Direct Lake …) |
| Refresh | `refresh` | Refresh enabled | Yes / No / Unknown |
| Gateway | `gateway` | Gateway required | Yes / No / Unknown |
| (export only) | `semanticModelId` | Semantic model ID | Last |

#### Workspace content › Dashboards (after a metadata scan)

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_name`, `parent_workspace_id` | Workspace name, Workspace ID | Context |
| Dashboard | `name` | Dashboard name | |
| Tiles | `tiles` | Number of dashboard tiles | |
| Access | `readOnly` | Read-only | Yes / No |
| Linked app ID | `app` | App ID | "Not in an app" when empty |
| *—* | *—* | *Dashboard ID* | *Add as the last export column; today no ID is exported* |

#### Workspace content › App linkage (after a metadata scan)

A chip list with no header and no export today. Proposed title "Apps using
this workspace"; if it becomes a grid, use **App ID** and **Number of items**.

#### Workspace content › Ownership (after a metadata scan)

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_name`, `parent_workspace_id` | Workspace name, Workspace ID | Context |
| Type | `kind` | Item type | Values: Report / Semantic model |
| Name | `name` | Item name | |
| Owner | `owner` | Last modified by | *Split the mixed column:* **Last modified by**, **Created by** (reports), **Configured by** (semantic models) |
| *—* | *—* | *Item ID* | *Add as the last export column* |

#### Explorer labels

| Location | Current | Proposed |
| --- | --- | --- |
| Tab | Assets & access (tooltip "1. Reports, dashboards, apps, and access") | Workspace content |
| Tab | Reports (tooltip "2. Report-scoped evidence") | Report details |
| Header metrics | Reports / Semantic models | Reports / Semantic models (tiles keep short plurals) |
| Selector | Workspace / Report, helper "Selected workspace ID:" | Workspace / Report, helper "Workspace ID:" / "Report ID:" |
| Scan notice | "report and dataset creators" | "report and semantic model owners" |
| Page badge / sidebar meta | Name-based explorer / Inventory | Workspace browser / Inventory (pick one term and reuse it) |

### Report evidence (Explorer › Report details tab and Report lineage)

Both pages show the same five sections, so they share one naming.

| Section tab today | Proposed tab | Proposed heading |
| --- | --- | --- |
| Page details | Pages | Report pages |
| Source DB lineage | Data sources | Data sources behind this report |
| Semantic objects | Semantic objects | Semantic model objects |
| Semantic - DB objects mappings | Database mapping | Semantic objects mapped to database columns |
| Report visuals | Visual fields | Visual fields traced to the database |

#### Pages (today "Page details")

Summary items today: Report type · Format · Linked model · Pages →
**Report type · Report format · Semantic model · Number of pages**.

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_name`, `parent_workspace_id`, `parent_report_name`, `parent_report_id`, `parent_semantic_model_name`, `parent_semantic_model_id` | Workspace name, Report name, Semantic model (+ their IDs at the end) | Context |
| Order | `order` | Page order | |
| Page name | `displayName` | Page name | |
| (export only) | `pageName` | Page ID | Today's `pageName` holds the internal page ID, not the name |

#### Data sources (today "Source DB lineage")

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_*`, `parent_report_*` | Workspace name, Report name (+ IDs last) | Context; also removes the duplicates below |
| Workspace name | `workspaceName` | *Remove from the grid* | *Duplicates the context column* |
| Report name | `reportName` | *Remove from the grid* | *Duplicates the context column* |
| Report ID | `reportId` | Report ID | Last |
| Dataset ID | `datasetId` | Semantic model ID | Last |
| Origin | `origin` | Data source type | Database table, Database view, Native query, File, Web URL, Endpoint, Not found |
| Source account | `sourceAccount` | Database account | |
| Source DB | `sourceDatabase` | Database | |
| Schema | `sourceSchema` | Schema | |
| Table name | `tableName` | Data source name | The table, view, file, or URL name |
| Source object type | `sourceObjectType` | *Remove* | *Raw duplicate of Data source type* |
| Via (composite model) | `via` | Reached through | "Directly" when there is no hop |

Recommended order: Data source type · Database account · Database · Schema ·
Data source name · Reached through · Report ID · Semantic model ID.

**Snowflake trace panels** (inside Data sources and Database mapping):

| Current | Proposed |
| --- | --- |
| Select "Fully qualified table" / "Database column" | Database table / Database column |
| Metrics: Objects · Dependencies · Queries read · Account | Objects traced · Dependencies found · Queries read · Database account |
| Grid: Source · Target · Domain · Dependency · Distance · Process | From object · To object · Object level (Table / Column) · Dependency type · Steps away · Process |
| Diagram titles "Snowflake table lineage" / "Snowflake column lineage graph" | Snowflake table lineage / Snowflake column lineage |

#### Semantic objects

Summary items today: Semantic models · Tables · Columns · Measures →
**Semantic models · Semantic tables · Columns · Measures** (short plurals,
same as tiles). The live-model check today reads "Matched with XMLA ·
Definition only · XMLA only". Proposed: **In definition and live model · Only in
definition · Only in live model**. The note title "Runtime XMLA
reconciliation" becomes **Live model check**.

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_*`, `parent_report_*`, `parent_semantic_model_*` | Workspace name, Report name, Semantic model (+ IDs last) | Context |
| Semantic model | `semanticModel` | Semantic model | |
| Table | `table` | Semantic table | |
| Object name | `name` | Object name | |
| Object type | `kind` | Object type | |
| Data type | `dataType` | Data type | |
| Source column | `sourceColumn` | Database column | "Not applicable" for measures |
| DAX expression | `daxExpression` | DAX expression | |

#### Database mapping (today "Semantic - DB objects mappings")

Today this grid shows the raw export keys as its on-screen headers.

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| parent_workspace_name | `parent_workspace_name` | Workspace name | |
| parent_workspace_id | `parent_workspace_id` | Workspace ID | Move to the end |
| parent_report_name | `parent_report_name` | Report name | |
| parent_report_id | `parent_report_id` | Report ID | Move to the end |
| parent_semantic_model_name | `parent_semantic_model_name` | Semantic model | |
| parent_semantic_model_id | `parent_semantic_model_id` | Semantic model ID | Move to the end |
| table | `table` | Semantic table | |
| name | `name` | Object name | |
| kind | `kind` | Object type | |
| dataType | `dataType` | Data type | |
| daxExpression | `daxExpression` | DAX expression | |
| sourceColumn | `sourceColumn` | Database columns | Plural: can list several |
| sourceTable | `sourceTable` | Database tables | Plural: full names |

Recommended order: Semantic table · Object name · Object type · Data type ·
Database columns · Database tables · DAX expression · Workspace name · Report
name · Semantic model · Workspace ID · Report ID · Semantic model ID.

**Measure definition download** (Power AI panel in this section), fields
today → proposed: Semantic table → Semantic table · Workspace → Workspace
name · Report → Report name · Semantic model → Semantic model · Source column
→ Database columns · Source table → Database tables · Answer status → Answer
status · Written by → Written by.

#### Visual fields (today "Report visuals")

Summary items today: Pages · Visuals · Definition parts, then Field references
· Resolved · Partial · Unresolved. Proposed: **Pages · Visuals · Report
definition files**, then **Fields in visuals · Fully traced · Partly traced ·
Not traced**. The note "Linked semantic model:" becomes **Semantic
model:**.

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `parent_workspace_*`, `parent_report_*`, `parent_semantic_model_*` | Workspace name, Report name, Semantic model (+ IDs last) | Context |
| Report page | `page` | Page name | |
| Visual | `visual` | Visual name | "Untitled visual" stays as a value |
| Semantic table | `semanticTable` | Semantic table | "Unresolved" → "Not found" |
| Semantic object | `semanticObject` | Object name | Same name as in Semantic objects |
| Type | `type` | Object type | |
| DAX expression | `daxExpression` | DAX expression | "No DAX expression declared" → "Not applicable" |
| sourceColumn | `sourceColumn` | Database columns | Today shown as a raw key |
| sourceTable | `sourceTable` | Database tables | Today shown as a raw key |

### Report lineage (page-specific parts)

| Location | Current | Proposed |
| --- | --- | --- |
| Header summary | Workspace · Report · Semantic model · Report type | Workspace name · Report name · Semantic model · Report type |
| Report selector option | "Sales Performance - Finance" | "Sales Performance (Finance)", the same "Name (Parent)" style as Table impact chips |
| Diagram metrics | Database objects · Semantic objects · Report pages / Page visuals | Data sources · Semantic objects · Pages / Visuals |
| Diagram selectors | Diagram scope · Semantic table · Column · Target calculation | Diagram scope · Semantic table · Column · Calculation |
| Diagram tabs | Report & database · Column lineage · Measure & calculated column | Report and database · Column lineage · Measures and calculated columns |

### Table impact

| Location | Current | Proposed |
| --- | --- | --- |
| Search groups | Semantic model tables (N) · Database tables (N) | Semantic tables (N) · Database tables (N) |
| Chips | "MODEL Sales (Finance Model)", "DATABASE ANALYTICS.FINANCE.FACT_SALES" | Keep; tags "Semantic" / "Database" |
| Tiles | Reports · Visuals · Semantic models · Measures | Reports · Visuals · Semantic models · Impacted measures |
| Export context | `selected_tables` | Selected tables |

#### Reports using the selected tables

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| (export only) | `selected_tables` | Selected tables | Context, first |
| Report | `Report` | Report name | |
| Workspace | `Workspace` | Workspace name | |
| Semantic model | `Semantic model` | Semantic model | |
| Selected tables | `Selected tables` | Selected tables | List of names |
| Usage | `Usage` | How it is used | Uses it directly / Through a measure |
| Pages | `Pages` | Number of pages | |
| Visuals | `Visuals` | Number of visuals | |
| Objects used | `Objects used` | Objects used | |
| (export only) | `Report ID` | Report ID | Last |
| (export only) | `Semantic model ID` | Semantic model ID | Last |

Today's on-screen headers here come out in Title Case ("Semantic Model",
"Selected Tables", "Objects Used"), because AG Grid builds them from the field
names. With the standard they are sentence case.

#### Visuals using the selected tables

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Visual | `Visual` | Visual name | |
| Visual type | `Visual type` | Visual type | |
| Page | `Page` | Page name | |
| Report | `Report` | Report name | |
| Workspace | `Workspace` | Workspace name | |
| Usage | `Usage` | How it is used | |
| Fields used | `Fields used` | Objects used | Same name as in the Reports grid |
| (export only) | `Selected tables` | Selected tables | Show on screen too |
| (export only) | `Report ID` | Report ID | Last |
| (export only) | `Visual key` | Visual ID | Last |

#### Semantic models

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Semantic model | `Semantic model` | Semantic model | |
| Workspace | `Workspace` | Workspace name | |
| Selected tables | `Selected tables` | Selected tables | |
| Database tables | `Database tables` | Database tables | |
| Measures | `Measures` | Number of impacted measures | |
| Reports using | `Reports using` | Number of reports using it | |
| Reports bound | `Reports bound` | Number of connected reports | "Bound" is avoided |
| (export only) | `Semantic model ID`, `Workspace ID` | Semantic model ID, Workspace ID | Last |

#### Measures using the selected tables

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Measure | `Measure` | Measure name | "Total Sales" instead of `Sales[Total Sales]` |
| *—* | *—* | *Semantic table* | *New: the measure's table, "Sales"* |
| Semantic model | `Semantic model` | Semantic model | |
| Workspace | `Workspace` | Workspace name | |
| Selected tables | `Selected tables` | Selected tables | |
| Relationship | `Relationship` | Dependency | Direct / Indirect |
| Depth | `Depth` | Steps away | |
| DAX reference | `DAX reference` | Referenced as | |
| Reports | `Reports` | Number of reports | |
| Visuals | `Visuals` | Number of visuals | |
| (export only) | `Semantic model ID` | Semantic model ID | Last |

### Measure impact

| Location | Current | Proposed |
| --- | --- | --- |
| Tiles | Tables · Measures impacted · Semantic models · Reports · Visuals | Semantic tables · Impacted measures · Semantic models · Reports · Visuals |
| Search | Measure, entries "Sales[Total Sales]" | Measure, entries "Total Sales (Sales · Finance Model)" |
| Export context | `parent_workspace_name`, `parent_workspace_id`, `parent_semantic_model_name`, `parent_semantic_model_id`, `parent_measure` | Workspace name, Semantic model, Selected measure (+ Workspace ID, Semantic model ID last) |

#### Semantic tables (today "Tables")

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Table | `Table` | Semantic table | |
| Relationship | `Relationship` | Connection to the measure | Values: Holds the measure · Read by the measure · Holds impacted measures · Holds impacted calculations |
| Objects | `Objects` | Objects involved | |
| Database tables | `Database tables` | Database tables | |
| Semantic model | `Semantic model` | Semantic model | |
| (export only) | `Workspace` | Workspace name | |

#### Measures impacted by the selected measure

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Measure | `Measure` | Measure name | |
| *—* | *—* | *Semantic table* | *New* |
| Relationship | `Relationship` | Dependency | Direct / Indirect |
| Depth | `Depth` | Steps away | |
| DAX reference | `DAX reference` | Referenced as | |
| Reports | `Reports` | Number of reports | |
| Visuals | `Visuals` | Number of visuals | |

#### Semantic model

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Semantic model | `Semantic model` | Semantic model | |
| Workspace | `Workspace` | Workspace name | |
| Home table | `Home table` | Measure's semantic table | |
| Measures impacted | `Measures impacted` | Number of impacted measures | |
| Calculated columns impacted | `Calculated columns impacted` | Number of impacted calculated columns | |
| Reports using | `Reports using` | Number of reports using it | |
| Visuals using | `Visuals using` | Number of visuals using it | |
| Reports bound | `Reports bound` | Number of connected reports | |
| (export only) | `Semantic model ID`, `Workspace ID` | Semantic model ID, Workspace ID | Last |

#### Reports

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Report | `Report` | Report name | |
| Workspace | `Workspace` | Workspace name | |
| Usage | `Usage` | How it is used | Uses it directly / Through a measure |
| Pages | `Pages` | Number of pages | |
| Visuals | `Visuals` | Number of visuals | |
| Measures shown | `Measures shown` | Objects used | Same name as on Table impact |
| (export only) | `Report ID` | Report ID | Last |

#### Visuals

Same columns and names as **Table impact › Visuals using the selected tables**:
Visual name · Visual type · Page name · Report name · Workspace name · How it
is used · Objects used · Report ID · Visual ID (today `Visual key`).

#### Inputs the selected measure reads

| Current screen header | Current export header | Proposed header | Notes |
| --- | --- | --- | --- |
| Object | `Object` | Object name | "Amount" instead of `Sales[Amount]` |
| *—* | *—* | *Semantic table* | *New* |
| Type | `Type` | Object type | |
| Relationship | `Relationship` | Dependency | Direct / Indirect |
| Depth | `Depth` | Steps away | |
| DAX reference | `DAX reference` | Referenced as | |
| Database table | `Database table` | Database table | "Not applicable" for measures (today `--`) |

### Impact graph (Table impact and Measure impact)

The legend already follows the vocabulary: Database table · Semantic model ·
Semantic table · Column · Calculated column · Calculated table · Measure ·
Report · Visual. Keep it. In node details, use "Semantic model · Finance"
and "Database table" as today. Change "N visuals" on report nodes to "Number
of visuals: N" only if space allows; otherwise keep "N visuals".

### Status and empty messages

| Today | Proposed |
| --- | --- |
| "Estate discovery is unavailable for this identity …" | "The list of reports could not be loaded for your account …" |
| "Finding the reports bound to these semantic models…" | "Finding the reports connected to these semantic models…" |
| "Visual usage checked across N bound reports." | "Checked the visuals in N connected reports." |
| "N exact DAX relationships ready across N semantic models" | "N calculation links found in N semantic models" |
| "No reports in the accessible estate are bound to …" | "No report you can open is connected to …" |
| "Usage is unavailable because estate discovery failed." | "Report usage is not available because the list of reports could not be loaded." |

## Export file names

Pattern: `<page>-<subject>-<grid>` in lower case with hyphens. The subject is
the workspace, report, table, or measure the file is about. Files from the
shared report sections use `report-<report>-<grid>` on both pages, because
their content is identical.

| Grid | Today | Proposed (example) |
| --- | --- | --- |
| Explorer › Reports | `finance-reports.csv` | `explorer-finance-reports.csv` |
| Explorer › Semantic models | `finance-semantic-models.csv` | `explorer-finance-semantic-models.csv` |
| Explorer › Dashboards | `finance-dashboards.csv` | `explorer-finance-dashboards.csv` |
| Explorer › Ownership | `finance-ownership.csv` | `explorer-finance-owners.csv` |
| Pages | `sales-performance-pages.csv` | `report-sales-performance-pages.csv` |
| Data sources | `sales-performance-source-db-lineage.csv` | `report-sales-performance-data-sources.csv` |
| Semantic objects | `sales-performance-semantic-objects.csv` | `report-sales-performance-semantic-objects.csv` |
| Database mapping | `sales-performance-semantic-db-mappings.csv` | `report-sales-performance-database-mapping.csv` |
| Visual fields | `sales-performance-report-semantic.csv` | `report-sales-performance-visual-fields.csv` |
| Table impact grids | `table-impact-reports.csv` … | `table-impact-sales-reports.csv` (first selected table; "multiple-tables" when several) |
| Measure impact grids | `finance-model-total-sales-reports.csv` … | `measure-impact-total-sales-reports.csv` |

## Words to avoid

| Avoid | Use instead |
| --- | --- |
| Dataset, model, linked model, bound model | Semantic model |
| Table (on its own), table name | Semantic table / Database table / Data source name |
| Source table, source column, source DB, `sourceTable`, `sourceColumn` | Database table, Database column, Database |
| Origin, source object type, domain | Data source type, Object level |
| Kind | Item type / Object type |
| Access (on its own) | Owned by you / Read-only |
| Owner (as one mixed column) | Created by / Last modified by / Configured by |
| Via | Reached through |
| Transitive, directness, depth, distance | Indirect, Dependency, Steps away |
| Upstream / downstream (in headers) | Inputs / Impacted (Depends on / Used by) |
| Usage, reads table fields, shows the measure | How it is used: Uses it directly / Through a measure |
| Bound, estate, estate discovery, accessible estate | Connected, the list of reports |
| Resolved / partial / unresolved | Fully traced / Partly traced / Not traced, or Not found |
| Evidence (in headers and tiles) | (describe what it is, for example "Checked the visuals …") |
| XMLA, runtime reconciliation, definition parts, TMDL, PBIR (without explanation) | Live model check, report definition files |
| `--`, Not reported, Not resolved | Not available / Not found / Not applicable |
| `parent_…`, camelCase or snake_case headers | The standard name in sentence case |
| Title Case headers ("Semantic Model") | Sentence case ("Semantic model") |

## Adoption notes for developers

These notes were written before the standard was applied; all of them are now
done. Keep following them when you add or change a grid:

- A new header or value goes into `COLUMN` or `VALUE` in `app/lib/naming.ts`
  first, then the grid uses it. Do not type a header string inside a page.
- One behaviour to know: when a grid already has a column with the same name
  as a context column (for example Table impact's per-row **Selected tables**),
  the export keeps only the grid's column, so a file never has two columns with
  one name.

- **Set `headerName` on every column.** When `headerName` is missing, AG
  Grid Title-Cases the field name, which is why Table impact and Measure
  impact show "Semantic Model" and "Selected Tables".
- **Export with the headers, not the row keys.** `ExplorerGrid`
  (`app/components/workspace/evidence-ui.tsx`) and `ImpactGrid`
  (`app/components/workspace/impact-grid.tsx`) both write raw row keys to
  Copy table, CSV, and Excel. They could map each key to its column's
  `headerName` and give export-only columns (IDs) an explicit label. Then
  screen and file always match, without renaming every row key.
- **Replace `parent_…` context keys** from `makeExportContext`
  (`evidence-ui.tsx`) and the page context objects with the standard names.
  Put them first and their IDs last.
- **Keep one glossary.** A single shared module of header and value labels
  (for example "Semantic model", "Database table", "Not found") would stop
  the names drifting again. Page descriptions and empty messages should use
  the same words.
- **Translate raw values in one place.** Report type, storage mode, object
  type, and the Yes/No/Unknown flags should be translated once, not per
  grid.
- **Test the headers.** The Playwright suite could assert each grid's
  header list, so a future change that breaks the standard fails a test.
- **Apply page by page.** Suggested order: Database mapping (raw keys on
  screen today), then the export-header change (all grids at once), then
  Table and Measure impact wording, then Explorer.
