import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { BookOpenCheck, Database, FileBarChart2, TableProperties } from "lucide-react";
import { useMemo, useState } from "react";

import { MeasureAiDefinition, type MeasureDefinitionTarget } from "~/components/workspace/measure-ai-definition";
import { SnowflakeColumnLineage, SnowflakeObjectLineage, type SnowflakeColumnTarget, type SnowflakeTraceTarget } from "~/components/workspace/snowflake-object-lineage";
import {
  daxColumn,
  DetailItem,
  EvidenceError,
  EvidenceOptionToggle,
  ExplorerGrid,
  ExplorerLoading,
  ExplorerWarnings,
  filePart,
  makeExportContext,
  objectKey,
  SectionHeading,
  type ExplorerEvidenceWarning,
  type ExplorerGridRow,
  type ExportValue,
  type Report,
  type Workspace,
} from "~/components/workspace/evidence-ui";
import { requestJson } from "~/lib/lineage-api";
import { COLUMN, exportOnlyColumn, OBJECT_TYPE_LABELS, objectTypeLabel, reportFormatLabel, reportTypeLabel, VALUE } from "~/lib/naming";
import { cn } from "~/lib/utils";
import { useAppStore } from "~/stores/app-store";

/** Every view here works against the one report the caller selected, so the picker lives above these rather than inside each of them. */
export type ReportSection = "report-detail" | "source-db-lineage" | "semantic-objects" | "semantic-db-mapping" | "report-semantic";

/**
 * Tab (`shortLabel`) and section heading (`label`) of each report section, as
 * Docs/07-column-naming-standard.md names them. The ids stay as they are:
 * deep links and other screens use them.
 */
export const REPORT_SECTIONS: Array<{ id: ReportSection; label: string; shortLabel: string }> = [
  { id: "report-detail", label: "Report pages", shortLabel: "Pages" },
  { id: "source-db-lineage", label: "Data sources behind this report", shortLabel: "Data sources" },
  { id: "semantic-objects", label: "Semantic model objects", shortLabel: "Semantic objects" },
  { id: "semantic-db-mapping", label: "Semantic objects mapped to database columns", shortLabel: "Database mapping" },
  { id: "report-semantic", label: "Visual fields traced to the database", shortLabel: "Visual fields" },
];

const SECTION_HEADING = Object.fromEntries(REPORT_SECTIONS.map((section) => [section.id, section.label])) as Record<ReportSection, string>;

/** Summary, note, and value labels in these sections that are not grid headers (Docs/07-column-naming-standard.md). */
const LABEL = {
  semanticModels: "Semantic models",
  semanticTables: "Semantic tables",
  columns: "Columns",
  measures: "Measures",
  pages: "Pages",
  visuals: "Visuals",
  reportDefinitionFiles: "Report definition files",
  fieldsInVisuals: "Fields in visuals",
  fullyTraced: "Fully traced",
  partlyTraced: "Partly traced",
  notTraced: "Not traced",
  liveModelCheck: "Live model check",
  inDefinitionAndLiveModel: "In definition and live model",
  onlyInDefinition: "Only in definition",
  onlyInLiveModel: "Only in live model",
  untitledVisual: "Untitled visual",
} as const;

/** Files from these sections are named the same on Explorer and Report lineage, because their content is identical. */
function reportFileName(report: Report | null, grid: string) {
  return `report-${filePart(report?.name)}-${grid}`;
}

/**
 * One report and everything already known about where its model lives.
 *
 * Explorer resolves this from a workspace's own report and model lists;
 * Report lineage resolves it from estate discovery, where the bound model can
 * sit in a different workspace entirely. Either way the evidence below is
 * scoped to exactly one report, which is what keeps both screens at report
 * granularity.
 */
export type ReportBinding = {
  workspace: Workspace;
  report: Report;
  semanticModelId: string | null;
  semanticModelName: string | null;
  semanticModelWorkspaceId: string | null;
};

type ReportPage = { name: string; display_name: string; order: number };
type ReportPagesResponse = { pages: ReportPage[] };

type NormalizedReport = {
  semantic_model?: { semantic_model_id?: string | null; path?: string | null } | null;
  page_count: number;
  visual_count: number;
  source_part_count: number;
  warnings: string[];
};

type ReportVisualSourceColumnRow = {
  page_name: string;
  page_id?: string | null;
  visual_id?: string | null;
  visual_title?: string | null;
  visual_type?: string | null;
  field_role?: string | null;
  semantic_table?: string | null;
  semantic_object_name?: string | null;
  semantic_object_type?: "column" | "measure" | "calculated_column" | null;
  dax_expression?: string | null;
  source_columns: string[];
  source_tables: string[];
  via_workspace_name?: string | null;
  resolution_status: "resolved" | "partial" | "unresolved";
  resolution_note?: string | null;
};

type ReportVisualSourceColumnsResponse = {
  workspace_id: string;
  workspace_name: string;
  report_id: string;
  report_name: string;
  semantic_model_id?: string | null;
  semantic_model_name?: string | null;
  semantic_model_workspace_id?: string | null;
  rows: ReportVisualSourceColumnRow[];
  total_field_reference_count: number;
  resolved_count: number;
  partial_count: number;
  unresolved_count: number;
  warnings: ExplorerEvidenceWarning[];
};

type ReportSourceTableRow = {
  workspace_name: string;
  report_name: string;
  report_id: string;
  semantic_model_id: string;
  source_account?: string | null;
  source_database?: string | null;
  source_schema?: string | null;
  table_name?: string | null;
  source_object_type: string;
  /** Non-null only when this table was reached through another workspace's semantic model. */
  via_workspace_name?: string | null;
  via_semantic_model_name?: string | null;
  via_semantic_table?: string | null;
};
type ReportSourceTablesResponse = { rows: ReportSourceTableRow[]; count: number; warnings: ExplorerEvidenceWarning[] };

/** One parsed semantic object, already carrying its own workspace/report/model context. */
type SemanticModelObjectRow = {
  workspace_id: string;
  workspace_name: string;
  report_id: string;
  report_name: string;
  semantic_model_id: string;
  semantic_table: string;
  semantic_object_type: string;
  semantic_object_name: string;
  semantic_data_type?: string | null;
  semantic_source_column?: string | null;
  semantic_dax_expression?: string | null;
};
type SemanticModelObjectsResponse = { rows: SemanticModelObjectRow[]; count: number; warnings: ExplorerEvidenceWarning[] };

/** A DAX dependency traced all the way down to the physical column it reads. */
type MeasureSourceLineageRow = {
  semantic_table?: string | null;
  semantic_object_name: string;
  source_column_name?: string | null;
  source_fully_qualified_name?: string | null;
};

type SnapshotSourceRow = { semantic_table: string; source_fully_qualified_name?: string | null };

/**
 * `/explorer/snapshot` returns every explorer dataset from one request. The
 * mapping grid needs three of them, and fetching them separately would repeat
 * the expensive part — the workspace, report and TMDL definition fetches —
 * once per dataset.
 */
type ExplorerSnapshot = {
  warnings: ExplorerEvidenceWarning[];
  semantic_model_objects: { rows: SemanticModelObjectRow[]; count: number };
  measure_source_lineage: { rows: MeasureSourceLineageRow[]; count: number };
  source_database_lineage: { rows: SnapshotSourceRow[]; count: number };
};

type MetadataResponse = { reconciliation: { matched_count: number; definition_only_count: number; xmla_only_count: number } };

/**
 * One selection is always enough here because both screens work a single
 * report at a time; `semantic_model_id` is deliberately omitted so the backend
 * infers the binding itself (which is also what makes a model in another
 * workspace work). Both `include_*` flags cost real upstream API calls, so
 * they default to off.
 */
function explorerReportsBody(workspaceId: string, reportId: string, options?: { includeCrossModelMatching?: boolean; includeGatewaySources?: boolean }) {
  return {
    reports: [{ workspace_id: workspaceId, report_id: reportId }],
    include_gateway_sources: options?.includeGatewaySources ?? false,
    include_cross_model_matching: options?.includeCrossModelMatching ?? false,
    // Ordinary resolution, not an expensive scan: it only costs anything when a
    // composite model is actually present, and it is what makes a cross-workspace
    // table report its real database instead of stopping at the Power BI boundary.
    resolve_cross_workspace_sources: true,
    report_definition_format: "PBIR",
    semantic_model_definition_format: "TMDL",
  };
}

/**
 * The five report-scoped evidence views, with their section tabs and every
 * call behind them.
 *
 * Both Explorer and Report lineage render this, so the two screens show the
 * same tabs against the same endpoints; they differ only in how the report
 * reaches them — Explorer picks one inside a workspace, Report lineage picks
 * one from anywhere in the estate.
 */
export function ReportEvidence({ binding, modelNames, activeSection, onSectionChange }: {
  binding: ReportBinding;
  /** Workspace model names, when the caller has them, so a multi-model grid can label each row. */
  modelNames?: Map<string, string>;
  activeSection: ReportSection;
  onSectionChange: (section: ReportSection) => void;
}) {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [gatewaySourcesEnabled, setGatewaySourcesEnabled] = useState(false);

  const { workspace, report } = binding;
  const workspaceId = workspace.id;
  const reportId = report.id;
  // Drive semantic evidence from the report's own binding rather than from a
  // model that happens to be listed in this workspace: a report can be bound to
  // a model in another workspace, and the caller's resolution (or Power BI's
  // `dataset_workspace_id`) is the only reliable proof of where that model lives.
  const boundModelId = binding.semanticModelId ?? report.dataset_id ?? null;
  const boundModelWorkspaceId = binding.semanticModelWorkspaceId ?? report.dataset_workspace_id ?? workspaceId;
  const boundModelName = binding.semanticModelName ?? (boundModelId ? modelNames?.get(boundModelId) ?? null : null);
  const boundModel = boundModelId && boundModelName ? { id: boundModelId, name: boundModelName } : null;

  // A section's evidence is only worth fetching once that section is on screen.
  // The session cache serves it from memory afterwards, so moving between
  // sections stays instant while never paying for one left unopened.
  const reportDetailQuery = useQuery({
    queryKey: ["explorer", "report", apiOrigin, workspaceId, reportId],
    queryFn: () => requestJson<Report>(apiOrigin, `/api/v1/workspaces/${workspaceId}/reports/${reportId}`),
    enabled: activeSection === "report-detail",
  });
  const reportPagesQuery = useQuery({
    queryKey: ["explorer", "report-pages", apiOrigin, workspaceId, reportId],
    queryFn: () => requestJson<ReportPagesResponse>(apiOrigin, `/api/v1/workspaces/${workspaceId}/reports/${reportId}/pages`),
    enabled: activeSection === "report-detail",
  });
  const normalizedReportQuery = useQuery({
    queryKey: ["explorer", "normalized-report", apiOrigin, workspaceId, reportId],
    queryFn: () => requestJson<NormalizedReport>(apiOrigin, `/api/v1/workspaces/${workspaceId}/reports/${reportId}/definition/normalized?format=PBIR`, { method: "POST" }),
    enabled: activeSection === "report-semantic",
  });
  const reportVisualSourceColumnsQuery = useQuery({
    queryKey: ["explorer", "report-visual-source-columns", apiOrigin, workspaceId, reportId],
    queryFn: () => requestJson<ReportVisualSourceColumnsResponse>(apiOrigin, "/api/v1/explorer/report-visual-source-columns", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, report_id: reportId, include_gateway_sources: false }),
    }),
    enabled: activeSection === "report-semantic",
  });
  const semanticMetadataQuery = useQuery({
    queryKey: ["explorer", "semantic-metadata", apiOrigin, boundModelWorkspaceId, boundModelId],
    queryFn: () => requestJson<MetadataResponse>(apiOrigin, `/api/v1/workspaces/${boundModelWorkspaceId}/semantic-models/${boundModelId}/metadata?format=TMDL`),
    enabled: Boolean(boundModelId) && activeSection === "semantic-objects",
  });
  const reportSourceTablesQuery = useQuery({
    queryKey: ["explorer", "report-source-tables", apiOrigin, workspaceId, reportId, gatewaySourcesEnabled],
    queryFn: () => requestJson<ReportSourceTablesResponse>(apiOrigin, "/api/v1/explorer/report-source-tables", { method: "POST", body: JSON.stringify(explorerReportsBody(workspaceId, reportId, { includeGatewaySources: gatewaySourcesEnabled })) }),
    enabled: activeSection === "source-db-lineage",
  });
  const semanticModelObjectsQuery = useQuery({
    queryKey: ["explorer", "semantic-model-objects", apiOrigin, workspaceId, reportId],
    queryFn: () => requestJson<SemanticModelObjectsResponse>(apiOrigin, "/api/v1/explorer/semantic-model-objects", { method: "POST", body: JSON.stringify(explorerReportsBody(workspaceId, reportId)) }),
    enabled: activeSection === "semantic-objects",
  });
  const explorerSnapshotQuery = useQuery({
    queryKey: ["explorer", "snapshot", apiOrigin, workspaceId, reportId, gatewaySourcesEnabled],
    queryFn: () => requestJson<ExplorerSnapshot>(apiOrigin, "/api/v1/explorer/snapshot", { method: "POST", body: JSON.stringify(explorerReportsBody(workspaceId, reportId, { includeGatewaySources: gatewaySourcesEnabled })) }),
    enabled: activeSection === "semantic-db-mapping",
  });

  return <>
    <div className="overflow-x-auto border-b border-zinc-200">
      <div className="flex min-w-max gap-1" role="tablist" aria-label="Report sections">
        {REPORT_SECTIONS.map((section) => <button key={section.id} type="button" role="tab" aria-selected={activeSection === section.id} onClick={() => onSectionChange(section.id)} className={cn("border-b-2 px-3 py-2 text-sm transition", activeSection === section.id ? "border-teal-700 font-semibold text-teal-800" : "border-transparent text-zinc-500 hover:text-zinc-950")} title={section.label}>{section.shortLabel}</button>)}
      </div>
    </div>
    {activeSection === "report-detail" && <ReportDetailTab workspace={workspace} selectedReport={report} reportSemanticModel={boundModel} semanticModelId={boundModelId} detailQuery={reportDetailQuery} pagesQuery={reportPagesQuery} />}
    {activeSection === "source-db-lineage" && <SourceDbLineageTab workspace={workspace} selectedReport={report} query={reportSourceTablesQuery} gatewaySourcesEnabled={gatewaySourcesEnabled} onGatewaySourcesChange={setGatewaySourcesEnabled} />}
    {activeSection === "semantic-objects" && <SemanticObjectsTab workspace={workspace} selectedReport={report} reportSemanticModel={boundModel} modelNames={modelNames} query={semanticModelObjectsQuery} metadataQuery={semanticMetadataQuery} />}
    {activeSection === "semantic-db-mapping" && <SemanticDbMappingTab workspace={workspace} selectedReport={report} semanticModelId={boundModelId} semanticModelName={boundModelName} semanticModelWorkspaceId={boundModelWorkspaceId} query={explorerSnapshotQuery} gatewaySourcesEnabled={gatewaySourcesEnabled} onGatewaySourcesChange={setGatewaySourcesEnabled} />}
    {activeSection === "report-semantic" && <ReportSemanticTab workspace={workspace} selectedReport={report} reportSemanticModel={boundModel} normalizedQuery={normalizedReportQuery} visualSourcesQuery={reportVisualSourceColumnsQuery} />}
  </>;
}

function ReportDetailTab({ workspace, selectedReport, reportSemanticModel, semanticModelId, detailQuery, pagesQuery }: {
  workspace: Workspace | null;
  selectedReport: Report | null;
  reportSemanticModel: { id: string; name: string } | null;
  /** Set when Power BI named a semantic model, even if its name could not be found. */
  semanticModelId: string | null;
  detailQuery: UseQueryResult<Report, Error>;
  pagesQuery: UseQueryResult<ReportPagesResponse, Error>;
}) {
  const pages = pagesQuery.data?.pages ?? [];
  const pageRows: ExplorerGridRow[] = pages.map((page) => ({ id: page.name, pageOrder: page.order + 1, pageName: page.display_name, pageId: page.name }));
  const context = makeExportContext(workspace, selectedReport, reportSemanticModel);
  const semanticModelValue = reportSemanticModel?.name ?? (semanticModelId ? VALUE.notFound : VALUE.notAvailable);
  return <div className="space-y-6">
    <SectionHeading icon={<FileBarChart2 className="size-5" />} title={SECTION_HEADING["report-detail"]} text="The pages of the selected report, in the order they appear. Each report is read on its own, so its pages are ready before you look at its semantic model and data sources." />
    {detailQuery.isLoading || pagesQuery.isLoading ? <ExplorerLoading label="Loading the selected report and its pages" /> : null}
    {detailQuery.isError || pagesQuery.isError ? <EvidenceError error={detailQuery.error ?? pagesQuery.error} fallback="The selected report's details are not available for this workspace." /> : null}
    {detailQuery.data && <div className="grid border-y border-zinc-200 md:grid-cols-4"><DetailItem label={COLUMN.reportType} value={reportTypeLabel(detailQuery.data.report_type)} /><DetailItem label={COLUMN.reportFormat} value={reportFormatLabel(detailQuery.data.format)} /><DetailItem label={COLUMN.semanticModel} value={semanticModelValue} /><DetailItem label={COLUMN.pageCount} value={String(pages.length)} /></div>}
    {!pagesQuery.isLoading && !pagesQuery.isError && <ExplorerGrid rowData={pageRows} columnDefs={[{ field: "pageOrder", headerName: COLUMN.pageOrder, minWidth: 130 }, { field: "pageName", headerName: COLUMN.pageName, minWidth: 280, flex: 1 }, exportOnlyColumn<ExplorerGridRow>("pageId", COLUMN.pageId)]} emptyMessage="No pages were returned for this report." exportFileName={reportFileName(selectedReport, "pages")} exportContext={context} />}
  </div>;
}

function SourceDbLineageTab({ workspace, selectedReport, query, gatewaySourcesEnabled, onGatewaySourcesChange }: {
  workspace: Workspace | null;
  selectedReport: Report | null;
  query: UseQueryResult<ReportSourceTablesResponse, Error>;
  gatewaySourcesEnabled: boolean;
  onGatewaySourcesChange: (value: boolean) => void;
}) {
  // The workspace and report are the export's context columns, so they are not repeated per row.
  const rows: ExplorerGridRow[] = (query.data?.rows ?? []).map((row, index) => {
    const absent = absentSourceValue(row.source_object_type);
    return {
      id: `${row.semantic_model_id}-${row.table_name ?? "unknown"}-${index}`,
      dataSourceType: dataSourceType(row.source_object_type),
      databaseAccount: row.source_account ?? absent,
      database: row.source_database ?? absent,
      schema: row.source_schema ?? absent,
      dataSourceName: row.table_name ?? (row.source_object_type === "unknown" ? VALUE.notFound : VALUE.notAvailable),
      // The hop is detail about how the row was reached, not what it is.
      reachedThrough: reachedThrough(row),
      reportId: row.report_id,
      semanticModelId: row.semantic_model_id,
    };
  });

  const traceTargets: SnowflakeTraceTarget[] = useMemo(() => {
    const seen = new Map<string, SnowflakeTraceTarget>();
    (query.data?.rows ?? []).forEach((row) => {
      const traceable = row.source_object_type === "table" || row.source_object_type === "view";
      if (!traceable || !row.source_database || !row.source_schema || !row.table_name) return;
      const qualifiedName = `${row.source_database}.${row.source_schema}.${row.table_name}`;
      if (!seen.has(qualifiedName)) seen.set(qualifiedName, { qualifiedName, label: qualifiedName });
    });
    return Array.from(seen.values()).sort((a, b) => a.qualifiedName.localeCompare(b.qualifiedName));
  }, [query.data]);

  return <div className="space-y-6">
    <SectionHeading icon={<Database className="size-5" />} title={SECTION_HEADING["source-db-lineage"]} text="Every database table, view, native query, file, or URL this report's semantic model loads data from, read from its partition queries. A data source reached through another workspace's semantic model still shows its real database, with the path under Reached through. Data sources that could not be traced are listed as Not found rather than hidden." />
    <EvidenceOptionToggle
      title="Gateway data sources"
      text="Adds on-premises gateway lookups, so partitions that load through a gateway show their data source. Needs gateway admin rights; without them the call still succeeds and returns a warning instead of data."
      label="Include gateway sources"
      checked={gatewaySourcesEnabled}
      onChange={onGatewaySourcesChange}
    />
    {query.isLoading ? <ExplorerLoading label="Reading the data sources" /> : null}
    {query.isError ? <EvidenceError error={query.error} fallback="Data sources need Fabric access to the selected report's semantic model." /> : null}
    {query.data && <>
      <ExplorerWarnings warnings={query.data.warnings} />
      <ExplorerGrid
        rowData={rows}
        columnDefs={[
          { field: "dataSourceType", headerName: COLUMN.dataSourceType, minWidth: 170 },
          { field: "databaseAccount", headerName: COLUMN.databaseAccount, minWidth: 200 },
          { field: "database", headerName: COLUMN.database, minWidth: 150 },
          { field: "schema", headerName: COLUMN.schema, minWidth: 130 },
          { field: "dataSourceName", headerName: COLUMN.dataSourceName, minWidth: 200, flex: 1 },
          { field: "reachedThrough", headerName: COLUMN.reachedThrough, minWidth: 230 },
          { field: "reportId", headerName: COLUMN.reportId, minWidth: 220 },
          { field: "semanticModelId", headerName: COLUMN.semanticModelId, minWidth: 220 },
        ]}
        emptyMessage="No data sources were found for this report's semantic model."
        exportFileName={reportFileName(selectedReport, "data-sources")}
        exportContext={makeExportContext(workspace, selectedReport)}
      />
      <SnowflakeObjectLineage targets={traceTargets} />
    </>}
  </div>;
}

/**
 * Semantic objects for whichever model(s) the selected report actually uses.
 * There is deliberately no model picker: the report's own binding is the
 * answer, and a picker could only list models in the current workspace, so a
 * report bound across workspaces would show an unrelated model's objects.
 * Rows are tagged with `semantic_model_id`, so however many models the
 * response covers, they render together in one grid.
 */
function SemanticObjectsTab({ workspace, selectedReport, reportSemanticModel, modelNames, query, metadataQuery }: {
  workspace: Workspace | null;
  selectedReport: Report | null;
  reportSemanticModel: { id: string; name: string } | null;
  modelNames?: Map<string, string>;
  query: UseQueryResult<SemanticModelObjectsResponse, Error>;
  metadataQuery: UseQueryResult<MetadataResponse, Error>;
}) {
  const rows = useMemo(() => semanticObjectRows(query.data, modelNames, reportSemanticModel), [query.data, modelNames, reportSemanticModel]);
  const sourceRows = query.data?.rows ?? [];
  const modelCount = useMemo(() => new Set(sourceRows.map((row) => row.semantic_model_id)).size, [sourceRows]);
  const tableCount = useMemo(() => new Set(sourceRows.map((row) => `${row.semantic_model_id}:${row.semantic_table}`)).size, [sourceRows]);

  return <div className="space-y-6">
    <SectionHeading icon={<TableProperties className="size-5" />} title={SECTION_HEADING["semantic-objects"]} text="Semantic tables, columns, measures, and hierarchies in the semantic model this report reads from, with their DAX expressions. The date tables Power BI creates automatically (Auto date/time) are left out." />
    {query.isLoading ? <ExplorerLoading label="Loading semantic model objects" /> : null}
    {query.isError ? <EvidenceError error={query.error} fallback="Semantic model objects need Fabric access to this report's semantic model." /> : null}
    {query.data && <>
      <ExplorerWarnings warnings={query.data.warnings} />
      {modelCount > 1 && <div className="border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-950">This report reads from <strong>{modelCount}</strong> semantic models. Their objects are listed together below — sort by the Semantic model column to separate them.</div>}
      <div className="grid border-y border-zinc-200 sm:grid-cols-4">
        <DetailItem label={LABEL.semanticModels} value={String(modelCount)} />
        <DetailItem label={LABEL.semanticTables} value={String(tableCount)} />
        <DetailItem label={LABEL.columns} value={String(rows.filter((row) => row.objectType === OBJECT_TYPE_LABELS.column || row.objectType === OBJECT_TYPE_LABELS.calculated_column).length)} />
        <DetailItem label={LABEL.measures} value={String(rows.filter((row) => row.objectType === OBJECT_TYPE_LABELS.measure).length)} />
      </div>
      <ExplorerGrid
        rowData={rows}
        columnDefs={[
          { field: "semanticModel", headerName: COLUMN.semanticModel, minWidth: 200 },
          { field: "semanticTable", headerName: COLUMN.semanticTable, minWidth: 190 },
          { field: "objectName", headerName: COLUMN.objectName, minWidth: 220, flex: 1 },
          { field: "objectType", headerName: COLUMN.objectType, minWidth: 160 },
          { field: "dataType", headerName: COLUMN.dataType, minWidth: 140 },
          { field: "databaseColumn", headerName: COLUMN.databaseColumn, minWidth: 180 },
          daxColumn("daxExpression", COLUMN.daxExpression),
        ]}
        emptyMessage="No semantic objects were returned for this report's semantic model."
        exportFileName={reportFileName(selectedReport, "semantic-objects")}
        exportContext={makeExportContext(workspace, selectedReport, reportSemanticModel)}
      />
      <MetadataSummary query={metadataQuery} modelName={reportSemanticModel?.name ?? null} />
    </>}
  </div>;
}

function SemanticDbMappingTab({ workspace, selectedReport, semanticModelId, semanticModelName, semanticModelWorkspaceId, query, gatewaySourcesEnabled, onGatewaySourcesChange }: {
  workspace: Workspace | null;
  selectedReport: Report | null;
  semanticModelId: string | null;
  semanticModelName: string | null;
  /** Where the bound model actually lives, which can differ from the report's workspace. */
  semanticModelWorkspaceId: string | null;
  query: UseQueryResult<ExplorerSnapshot, Error>;
  gatewaySourcesEnabled: boolean;
  onGatewaySourcesChange: (value: boolean) => void;
}) {
  const rows = useMemo(() => (query.data ? semanticDbMappingRows(query.data, semanticModelName) : []), [query.data, semanticModelName]);
  const columnTargets: SnowflakeColumnTarget[] = useMemo(() => {
    const byTable = new Map<string, Set<string>>();
    rows.forEach((row) => {
      const tables = splitNames(row.databaseTables);
      const columns = splitNames(row.databaseColumns);
      if (!tables.length || !columns.length) return;
      tables.forEach((table) => {
        const set = byTable.get(table) ?? new Set<string>();
        columns.forEach((column) => set.add(column));
        byTable.set(table, set);
      });
    });
    return Array.from(byTable.entries())
      .map(([qualifiedName, columns]) => ({ qualifiedName, columns: Array.from(columns).sort((a, b) => a.localeCompare(b)) }))
      .sort((a, b) => a.qualifiedName.localeCompare(b.qualifiedName));
  }, [rows]);

  const measures: MeasureDefinitionTarget[] = useMemo(
    () => rows
      .filter((row) => row.objectType === OBJECT_TYPE_LABELS.measure)
      .map((row) => ({
        key: String(row.id),
        table: String(row.semanticTable ?? ""),
        name: String(row.objectName ?? ""),
        daxExpression: String(row.daxExpression ?? VALUE.notAvailable),
        databaseColumns: String(row.databaseColumns ?? VALUE.notFound),
        databaseTables: String(row.databaseTables ?? VALUE.notFound),
      })),
    [rows],
  );
  return <div className="space-y-6">
    <SectionHeading icon={<Database className="size-5" />} title={SECTION_HEADING["semantic-db-mapping"]} text="Every semantic object next to the database columns and database tables it reads. A column maps through the database column it loads from; measures and calculated columns map through the columns their DAX reads." />
    <EvidenceOptionToggle
      title="Gateway data sources"
      text="Adds on-premises gateway lookups, so partitions that load through a gateway show their data source. Needs gateway admin rights; without them the call still succeeds and returns a warning instead of data."
      label="Include gateway sources"
      checked={gatewaySourcesEnabled}
      onChange={onGatewaySourcesChange}
    />
    {query.isLoading ? <ExplorerLoading label="Reading semantic objects and database columns" /> : null}
    {query.isError ? <EvidenceError error={query.error} fallback="The database mapping needs Fabric access to the selected report's semantic model." /> : null}
    {query.data && <>
      <ExplorerWarnings warnings={query.data.warnings} />
      <ExplorerGrid
        rowData={rows}
        columnDefs={[
          { field: "semanticTable", headerName: COLUMN.semanticTable, minWidth: 170 },
          { field: "objectName", headerName: COLUMN.objectName, minWidth: 200, flex: 1 },
          { field: "objectType", headerName: COLUMN.objectType, minWidth: 160 },
          { field: "dataType", headerName: COLUMN.dataType, minWidth: 140 },
          { field: "databaseColumns", headerName: COLUMN.databaseColumns, minWidth: 200 },
          { field: "databaseTables", headerName: COLUMN.databaseTables, minWidth: 280, flex: 1 },
          daxColumn("daxExpression", COLUMN.daxExpression),
          { field: "workspaceName", headerName: COLUMN.workspaceName, minWidth: 180 },
          { field: "reportName", headerName: COLUMN.reportName, minWidth: 200 },
          { field: "semanticModel", headerName: COLUMN.semanticModel, minWidth: 200 },
          { field: "workspaceId", headerName: COLUMN.workspaceId, minWidth: 220 },
          { field: "reportId", headerName: COLUMN.reportId, minWidth: 220 },
          { field: "semanticModelId", headerName: COLUMN.semanticModelId, minWidth: 220 },
        ]}
        emptyMessage="No semantic objects were returned for this report's semantic model."
        exportFileName={reportFileName(selectedReport, "database-mapping")}
        exportContext={{}}
      />
      <MeasureAiDefinition
        measures={measures}
        context={{
          workspaceId: workspace?.id,
          workspaceName: workspace?.name,
          reportId: selectedReport?.id,
          reportName: selectedReport?.name,
          semanticModelId: semanticModelId ?? undefined,
          semanticModelName: semanticModelName ?? undefined,
          semanticModelWorkspaceId: semanticModelWorkspaceId ?? undefined,
          route: "/workspace/explorer",
        }}
      />
      <SnowflakeColumnLineage targets={columnTargets} />
    </>}
  </div>;
}

function ReportSemanticTab({ workspace, selectedReport, reportSemanticModel, normalizedQuery, visualSourcesQuery }: {
  workspace: Workspace | null;
  selectedReport: Report | null;
  reportSemanticModel: { id: string; name: string } | null;
  normalizedQuery: UseQueryResult<NormalizedReport, Error>;
  visualSourcesQuery: UseQueryResult<ReportVisualSourceColumnsResponse, Error>;
}) {
  const result = visualSourcesQuery.data;
  const fieldRows: ExplorerGridRow[] = (result?.rows ?? []).map((row, index) => {
    const objectType = row.semantic_object_type ? objectTypeLabel(row.semantic_object_type) : row.semantic_object_name ? VALUE.notAvailable : VALUE.notFound;
    return {
      id: `${row.page_id ?? row.page_name}-${row.visual_id ?? row.visual_title ?? index}-${row.field_role ?? "field"}-${row.semantic_table ?? "unresolved"}-${row.semantic_object_name ?? index}`,
      pageName: row.page_name,
      visualName: row.visual_title ?? row.visual_type ?? LABEL.untitledVisual,
      semanticTable: row.semantic_table ?? VALUE.notFound,
      objectName: row.semantic_object_name ?? VALUE.notFound,
      objectType,
      daxExpression: row.dax_expression ?? (row.semantic_object_name ? missingDaxExpression(row.semantic_object_type ?? "") : VALUE.notFound),
      databaseColumns: joinNames(row.source_columns),
      databaseTables: joinNames(row.source_tables),
    };
  });
  const semanticModel = result?.semantic_model_id && result.semantic_model_name
    ? { id: result.semantic_model_id, name: result.semantic_model_name }
    : reportSemanticModel;
  // The response names the workspace and report it actually traced; prefer those for the export's context.
  const exportContext = makeExportContext(
    result ? { id: result.workspace_id, name: result.workspace_name } : workspace,
    result ? { id: result.report_id, name: result.report_name } : selectedReport,
    semanticModel,
  );

  return <div className="space-y-6">
    <SectionHeading icon={<BookOpenCheck className="size-5" />} title={SECTION_HEADING["report-semantic"]} text="Each field used in a visual is matched to its semantic object and followed through DAX to the database columns and database tables it reads." />
    {semanticModel && <div className="border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">{COLUMN.semanticModel}: <strong>{semanticModel.name}</strong></div>}
    {normalizedQuery.isLoading || visualSourcesQuery.isLoading ? <ExplorerLoading label="Tracing visual fields to the database" /> : null}
    {normalizedQuery.isError ? <EvidenceError error={normalizedQuery.error} fallback="The report definition files are not available." /> : null}
    {visualSourcesQuery.isError ? <EvidenceError error={visualSourcesQuery.error} fallback="Visual fields need access to the report and its semantic model." /> : null}
    {normalizedQuery.data && <div className="grid border-y border-zinc-200 sm:grid-cols-3"><DetailItem label={LABEL.pages} value={String(normalizedQuery.data.page_count)} /><DetailItem label={LABEL.visuals} value={String(normalizedQuery.data.visual_count)} /><DetailItem label={LABEL.reportDefinitionFiles} value={String(normalizedQuery.data.source_part_count)} /></div>}
    {result && <>
      <ExplorerWarnings warnings={result.warnings} />
      <div className="grid border-y border-zinc-200 sm:grid-cols-4"><DetailItem label={LABEL.fieldsInVisuals} value={String(result.total_field_reference_count)} /><DetailItem label={LABEL.fullyTraced} value={String(result.resolved_count)} /><DetailItem label={LABEL.partlyTraced} value={String(result.partial_count)} /><DetailItem label={LABEL.notTraced} value={String(result.unresolved_count)} /></div>
      <ExplorerGrid
        rowData={fieldRows}
        columnDefs={[
          { field: "pageName", headerName: COLUMN.pageName, minWidth: 160 },
          { field: "visualName", headerName: COLUMN.visualName, minWidth: 190, flex: 1 },
          { field: "semanticTable", headerName: COLUMN.semanticTable, minWidth: 170 },
          { field: "objectName", headerName: COLUMN.objectName, minWidth: 180 },
          { field: "objectType", headerName: COLUMN.objectType, minWidth: 160 },
          daxColumn("daxExpression", COLUMN.daxExpression),
          { field: "databaseColumns", headerName: COLUMN.databaseColumns, minWidth: 220 },
          { field: "databaseTables", headerName: COLUMN.databaseTables, minWidth: 280, flex: 1 },
        ]}
        emptyMessage="No fields in visuals were returned for this report."
        exportFileName={reportFileName(selectedReport, "visual-fields")}
        exportContext={exportContext}
      />
    </>}
  </div>;
}

function MetadataSummary({ query, modelName }: { query: UseQueryResult<MetadataResponse, Error>; modelName: string | null }) {
  if (query.isLoading) return <ExplorerLoading label="Running the live model check" compact />;
  // The reconciled metadata route needs a live XMLA/MSOLAP connection, which
  // only exists on a Windows deployment. `/health/ready` reports no platform
  // capability, so there is nothing to feature-gate on up front — the call is
  // made and a failure degrades to this note instead of a hard error.
  if (query.isError) return <div className="mt-6 border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-600"><p className="font-semibold text-zinc-700">{LABEL.liveModelCheck}</p><p className="mt-1">The live model check is not available here. It needs a live connection to the semantic model, which is only possible on a Windows deployment and for a capacity that allows it. Every object above is still read from the semantic model definition.</p></div>;
  if (!query.data) return null;
  const reconciliation = query.data.reconciliation;
  return <div className="mt-6">
    <p className="mb-2 text-xs text-zinc-500"><span className="font-semibold text-zinc-700">{LABEL.liveModelCheck}</span> for {modelName ?? "this report's semantic model"}: the objects in its definition compared with the live model.</p>
    <div className="grid border-y border-zinc-200 sm:grid-cols-3"><DetailItem label={LABEL.inDefinitionAndLiveModel} value={String(reconciliation.matched_count)} /><DetailItem label={LABEL.onlyInDefinition} value={String(reconciliation.definition_only_count)} /><DetailItem label={LABEL.onlyInLiveModel} value={String(reconciliation.xmla_only_count)} /></div>
  </div>;
}

/** One row per semantic object, tagged with the model it belongs to so several models can share one grid. */
function semanticObjectRows(response: SemanticModelObjectsResponse | undefined, modelNames: Map<string, string> | undefined, boundModel: { id: string; name: string } | null): ExplorerGridRow[] {
  if (!response) return [];
  return response.rows.map((row, index) => ({
    id: `${row.semantic_model_id}-${row.semantic_table}-${row.semantic_object_type}-${row.semantic_object_name}-${index}`,
    semanticModel: modelNames?.get(row.semantic_model_id) ?? (boundModel?.id === row.semantic_model_id ? boundModel.name : row.semantic_model_id),
    semanticTable: row.semantic_table,
    objectName: row.semantic_object_name,
    objectType: objectTypeLabel(row.semantic_object_type),
    dataType: row.semantic_data_type ?? VALUE.notAvailable,
    databaseColumn: row.semantic_source_column ?? missingDatabaseColumn(row.semantic_object_type),
    daxExpression: row.semantic_dax_expression ?? missingDaxExpression(row.semantic_object_type),
  }));
}

/**
 * Joins the three snapshot datasets into one row per semantic object.
 *
 * A plain column declares its database column directly in TMDL. A measure or
 * calculated column does not — its physical columns are only knowable by
 * following its DAX dependencies, which is what `measure_source_lineage`
 * already did, so those are read from there and listed together. The fully
 * qualified table falls back to the semantic table's own physical source when
 * an object has no traced dependency of its own.
 */
function semanticDbMappingRows(snapshot: ExplorerSnapshot, semanticModelName: string | null): ExplorerGridRow[] {
  const traced = new Map<string, { columns: Set<string>; qualified: Set<string> }>();
  snapshot.measure_source_lineage.rows.forEach((row) => {
    const key = objectKey(row.semantic_table, row.semantic_object_name);
    const entry = traced.get(key) ?? { columns: new Set<string>(), qualified: new Set<string>() };
    if (row.source_column_name) entry.columns.add(row.source_column_name);
    if (row.source_fully_qualified_name) entry.qualified.add(row.source_fully_qualified_name);
    traced.set(key, entry);
  });

  const qualifiedByTable = new Map<string, string>();
  snapshot.source_database_lineage.rows.forEach((row) => {
    if (row.source_fully_qualified_name) qualifiedByTable.set(row.semantic_table, row.source_fully_qualified_name);
  });

  return snapshot.semantic_model_objects.rows.map((row, index) => {
    const trace = traced.get(objectKey(row.semantic_table, row.semantic_object_name));
    const dbColumns = row.semantic_source_column ? [row.semantic_source_column] : Array.from(trace?.columns ?? []);
    const tableFallback = qualifiedByTable.get(row.semantic_table);
    const qualified = trace?.qualified.size ? Array.from(trace.qualified) : tableFallback ? [tableFallback] : [];
    return {
      id: `${row.semantic_model_id}-${row.semantic_table}-${row.semantic_object_type}-${row.semantic_object_name}-${index}`,
      semanticTable: row.semantic_table,
      objectName: row.semantic_object_name,
      objectType: objectTypeLabel(row.semantic_object_type),
      dataType: row.semantic_data_type ?? VALUE.notAvailable,
      databaseColumns: joinNames(dbColumns),
      databaseTables: joinNames(qualified),
      daxExpression: row.semantic_dax_expression ?? missingDaxExpression(row.semantic_object_type),
      workspaceName: row.workspace_name,
      reportName: row.report_name,
      semanticModel: semanticModelName ?? VALUE.notAvailable,
      workspaceId: row.workspace_id,
      reportId: row.report_id,
      semanticModelId: row.semantic_model_id,
    };
  });
}

/** The three standard "missing" values; never offered as a name to trace. */
const MISSING_VALUES = new Set<string>([VALUE.notAvailable, VALUE.notFound, VALUE.notApplicable]);

/** Splits a joined cell back into names, dropping a missing-value placeholder rather than offering it as a name. */
function splitNames(value: ExportValue): string[] {
  const text = typeof value === "string" ? value : "";
  return text.split(",").map((part) => part.trim()).filter((part) => part && !MISSING_VALUES.has(part));
}

/** Database columns or tables, joined; "Not found" when the trace reached none. */
function joinNames(values: string[]) {
  return values.length ? values.join(", ") : VALUE.notFound;
}

function normalizedObjectType(raw: string) {
  return raw.trim().toLocaleLowerCase().replace(/[\s-]+/g, "_");
}

const CALCULATED_OBJECT_TYPES = new Set(["measure", "calculated_column", "calculated_table"]);

/** Only a plain column loads from a database column; for every other object type there is none to show. */
function missingDatabaseColumn(objectType: string) {
  return normalizedObjectType(objectType) === "column" ? VALUE.notAvailable : VALUE.notApplicable;
}

/** A calculation always has DAX, so a missing one was not provided; a plain column or hierarchy never has any. */
function missingDaxExpression(objectType: string) {
  return CALCULATED_OBJECT_TYPES.has(normalizedObjectType(objectType)) ? VALUE.notAvailable : VALUE.notApplicable;
}

/**
 * Short, readable classification of where a table's data actually comes from.
 *
 * A composite-model table is no longer a category here. The backend now
 * follows the link into the other workspace and reports the real database, so
 * such a row is an ordinary database row; that it arrived via another model is
 * shown separately, under Reached through.
 */
function dataSourceType(objectType: string): string {
  switch (objectType) {
    case "table": return "Database table";
    case "view": return "Database view";
    case "query": return "Native query";
    case "file": return "File";
    case "url": return "Web URL";
    case "endpoint": return "Endpoint";
    case "unknown": return VALUE.notFound;
    default: return objectType || VALUE.notFound;
  }
}

/** "Workspace › Semantic model › Semantic table" for a composite-model hop; "Directly" when there is none. */
function reachedThrough(row: ReportSourceTableRow): string {
  if (!row.via_workspace_name) return VALUE.directly;
  return [row.via_workspace_name, row.via_semantic_model_name ?? VALUE.notAvailable, row.via_semantic_table].filter(Boolean).join(" › ");
}

/**
 * Account/database/schema do not exist for file, URL and endpoint rows, and
 * could not be traced for unknown ones — say which, rather than rendering a
 * row of identical blanks.
 */
function absentSourceValue(objectType: string): string {
  if (objectType === "unknown") return VALUE.notFound;
  if (objectType === "file" || objectType === "url" || objectType === "endpoint") return VALUE.notApplicable;
  return VALUE.notAvailable;
}
