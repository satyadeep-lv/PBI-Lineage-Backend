import { canonicalType, type DaxReference } from "~/lib/dependency-graph";
import { fetchBatchedExplorer, type EstateDiscoveryResponse, type ExplorerReportSelection, type ParsedTable } from "~/lib/lineage-api";
import { objectTypeLabel, VALUE } from "~/lib/naming";

/**
 * Shared by Table impact and Measure impact: the bound-report evidence both
 * pages join to a DAX dependency closure, and the parsed-definition helpers
 * that turn a semantic table into seeds and physical sources.
 */

/**
 * The fields the impact pages read from `/explorer/visual-source-lookup` rows
 * (the backend returns more). These are the only usage evidence: a report uses
 * an object when one of its visuals reads it. `/explorer/measure-source-lineage`
 * is deliberately not used — it lists every measure of the bound model for
 * every report, whether or not any visual shows it.
 */
export type VisualSourceLookupRow = {
  report_id: string;
  report_name?: string | null;
  workspace_name?: string | null;
  page_id: string;
  page_name?: string | null;
  visual_id: string;
  visual_name?: string | null;
  visual_type?: string | null;
  semantic_table?: string | null;
  semantic_object_name?: string | null;
  match_status: "matched" | "unmatched";
};
export type EvidenceData = { rows: VisualSourceLookupRow[]; truncated: boolean };

export type ObjectUsage = { reportIds: Set<string>; visualKeys: Set<string> };
export type EvidenceReport = { name?: string; workspaceName?: string };
export type EvidenceVisual = { key: string; reportId: string; pageName: string; visualName: string; visualType: string };
export type EvidenceIndex = {
  /** Keyed by {@link evidenceKey}: which reports and visuals read one semantic object. */
  byObject: Map<string, ObjectUsage>;
  reports: Map<string, EvidenceReport>;
  visuals: Map<string, EvidenceVisual>;
};

/** Parsed definitions carry each table's and column's physical source; the shared ParsedTable type leaves it out. */
export type SourcedTable = {
  name: string;
  expression?: string | null;
  source_path?: string | null;
  columns: Array<{ name: string; expression?: string | null; source_path?: string | null }>;
  measures: ParsedTable["measures"];
};

export function fetchImpactEvidence(apiOrigin: string, bound: ExplorerReportSelection[]): Promise<EvidenceData> {
  return fetchBatchedExplorer<VisualSourceLookupRow>(apiOrigin, "/api/v1/explorer/visual-source-lookup", bound);
}

/** Query key for one model's visual evidence; `visual-evidence` keeps it apart from the older two-call cache shape. */
export function impactEvidenceKey(page: string, apiOrigin: string, semanticModelId: string, bound: ExplorerReportSelection[]) {
  return [page, "visual-evidence", apiOrigin, semanticModelId, bound.map((report) => report.report_id).join(",")] as const;
}

export function evidenceKey(table: string | null | undefined, name: string) {
  return `${(table ?? "").trim().toLocaleLowerCase()}[${name.trim().toLocaleLowerCase()}]`;
}

export function visualKey(reportId: string, pageId: string, visualId: string) {
  return `${reportId}:${pageId}:${visualId}`;
}

export function buildEvidenceIndex(data: EvidenceData | undefined): EvidenceIndex {
  const index: EvidenceIndex = { byObject: new Map(), reports: new Map(), visuals: new Map() };
  function usage(key: string) {
    if (!index.byObject.has(key)) index.byObject.set(key, { reportIds: new Set(), visualKeys: new Set() });
    return index.byObject.get(key)!;
  }
  function noteReport(row: { report_id: string; report_name?: string | null; workspace_name?: string | null }) {
    const known = index.reports.get(row.report_id);
    index.reports.set(row.report_id, { name: known?.name ?? row.report_name ?? undefined, workspaceName: known?.workspaceName ?? row.workspace_name ?? undefined });
  }
  data?.rows.forEach((row) => {
    if (row.match_status !== "matched" || !row.semantic_object_name) return;
    const key = visualKey(row.report_id, row.page_id, row.visual_id);
    const entry = usage(evidenceKey(row.semantic_table, row.semantic_object_name));
    entry.reportIds.add(row.report_id);
    entry.visualKeys.add(key);
    noteReport(row);
    if (!index.visuals.has(key)) {
      index.visuals.set(key, {
        key,
        reportId: row.report_id,
        pageName: row.page_name ?? row.page_id,
        visualName: row.visual_name ?? row.visual_id,
        visualType: row.visual_type ?? VALUE.notAvailable,
      });
    }
  });
  return index;
}

/** Distinct physical sources behind a semantic table: its own `source_path` plus any per-column ones. */
export function tableSources(table: SourcedTable | null | undefined) {
  const seen = new Map<string, string>();
  [table?.source_path, ...(table?.columns ?? []).map((column) => column.source_path)].forEach((path) => {
    const clean = path?.trim();
    if (clean && !seen.has(clean.toLocaleUpperCase())) seen.set(clean.toLocaleUpperCase(), clean);
  });
  return [...seen.values()];
}

/** Every column, measure, and (for a calculated table) the table itself — the seeds of a whole-table closure. */
export function tableSeeds(table: SourcedTable): DaxReference[] {
  const seeds: DaxReference[] = table.columns.map((column) => ({ object_type: column.expression ? "calculated_column" : "column", table_name: table.name, object_name: column.name, qualified_name: `${table.name}[${column.name}]` }));
  table.measures.forEach((measure) => seeds.push({ object_type: "measure", table_name: table.name, object_name: measure.name, qualified_name: `${table.name}[${measure.name}]` }));
  if (table.expression) seeds.push({ object_type: "calculated_table", table_name: table.name, object_name: table.name, qualified_name: table.name });
  return seeds;
}

/** A semantic object type in sentence case ("Calculated column"), the same wording as every grid. */
export function displayType(value: string) {
  return objectTypeLabel(canonicalType(value));
}

/** The estate body also lists every workspace's reports, which the shared type leaves out. */
export type EstateWithReports = Omit<EstateDiscoveryResponse, "workspaces"> & {
  workspaces: Array<{
    workspace: EstateDiscoveryResponse["workspaces"][number]["workspace"];
    report_bindings: EstateDiscoveryResponse["workspaces"][number]["report_bindings"];
    reports?: Array<{ id: string; name: string }> | null;
  }>;
};

export type ReportDisplayName = { name: string; workspaceName: string };

/** Report names from the estate first, then from evidence rows for any report the estate only knows by id. */
export function buildReportNames(estate: EstateWithReports | undefined, evidence: EvidenceIndex[]) {
  const names = new Map<string, ReportDisplayName>();
  estate?.workspaces.forEach((inventory) => {
    (inventory.reports ?? []).forEach((report) => names.set(report.id, { name: report.name, workspaceName: inventory.workspace.name }));
    inventory.report_bindings.forEach((binding) => {
      if (!names.has(binding.report_id)) names.set(binding.report_id, { name: binding.report_id, workspaceName: inventory.workspace.name });
    });
  });
  evidence.forEach((index) => index.reports.forEach((report, id) => {
    const known = names.get(id);
    if (!known || known.name === id) names.set(id, { name: report.name ?? known?.name ?? id, workspaceName: known?.workspaceName ?? report.workspaceName ?? VALUE.notAvailable });
  }));
  return names;
}
