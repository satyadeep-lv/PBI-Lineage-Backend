import { Calculator, CheckCircle2, Columns3, Copy, GitBranch, Loader2, Network } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LineageDiagram } from "~/components/workspace/lineage/lineage-diagram";
import type { LineageGraph } from "~/components/workspace/lineage/lineage-types";
import { Button } from "~/components/ui/button";
import { canonicalType, closureToLineageGraph, computeDependencyClosure, referenceKey, type DaxDependency, type DaxReference } from "~/lib/dependency-graph";
import { COLUMN, objectTypeLabel, VALUE } from "~/lib/naming";
import { cn } from "~/lib/utils";

type ReportChoice = {
  workspaceId: string;
  workspaceName: string;
  report: { id: string; name: string };
  semanticModelId: string | null;
  semanticModelWorkspaceId: string | null;
  semanticModelName: string | null;
};
type SourceRow = { semantic_table: string; source_id: string; source_provider: string; source_object_type: string; source_fully_qualified_name: string };
type SemanticObjectRow = { semantic_table: string; semantic_object_type: string; semantic_object_name: string; semantic_data_type?: string | null; semantic_source_column?: string | null; semantic_dax_expression?: string | null; source_path?: string | null };
type MeasureSourceRow = { semantic_table?: string | null; semantic_object_type: string; semantic_object_name: string; semantic_dax_expression?: string | null; source_semantic_table?: string | null; source_semantic_object_type?: string | null; source_semantic_object_name?: string | null; source_column_name?: string | null; dependency_depth?: number | null; is_direct_dependency?: boolean | null };
type ReportLayoutRow = { page_id: string; page_name: string; page_order?: number | null; visual_id: string; visual_name: string; visual_type?: string | null; table_name?: string | null; column_measure_name?: string | null };
type VisualSourceRow = { page_id: string; page_name: string; visual_id: string; visual_name: string; visual_type?: string | null; semantic_table?: string | null };
type ExplorerSnapshot = {
  source_database_lineage: { rows: SourceRow[]; count: number };
  semantic_model_objects: { rows: SemanticObjectRow[]; count: number };
  measure_source_lineage: { rows: MeasureSourceRow[]; count: number };
  report_layout: { rows: ReportLayoutRow[]; count: number };
  visual_source_lookup: { rows: VisualSourceRow[]; count: number };
};
type ParsedColumn = { name: string; source_path?: string | null; source_column?: string | null; data_type?: string | null; expression?: string | null };
type ParsedTable = { name: string; source_path?: string | null; expression?: string | null; columns: ParsedColumn[]; measures: Array<{ name: string; expression?: string | null }> };
type ParsedSemanticModel = { tables: ParsedTable[] };
type DaxAnalysis = { dependencies: DaxDependency[]; dependency_count: number };
type LineageMode = "report" | "column" | "calculation";
type LineageObject = { key: string; table: string; name: string; objectType: string; expression: string | null; sourceColumn: string | null; sourcePath: string | null; dataType: string | null };
type SelectOption = { value: string; label: string };

const SUMMARY_SCOPE = "__report_summary__";
const modeOptions: Array<{ id: LineageMode; label: string; icon: typeof GitBranch }> = [
  { id: "report", label: "Report and database", icon: Network },
  { id: "column", label: "Column lineage", icon: Columns3 },
  { id: "calculation", label: "Measures and calculated columns", icon: Calculator },
];

/** Diagram metric and selector labels that are not grid headers (Docs/07-column-naming-standard.md). */
const LABEL = {
  dataSources: "Data sources",
  semanticObjects: "Semantic objects",
  pages: "Pages",
  visuals: "Visuals",
  diagramScope: "Diagram scope",
  column: "Column",
  calculation: "Calculation",
} as const;

export function ReportLineageDiagrams({ report, snapshot, parsed, dax, exactLineageLoading, exactLineageError }: {
  report: ReportChoice;
  snapshot: ExplorerSnapshot;
  parsed: ParsedSemanticModel | undefined;
  dax: DaxAnalysis | undefined;
  exactLineageLoading: boolean;
  exactLineageError: boolean;
}) {
  const [mode, setMode] = useState<LineageMode>("report");

  return <div className="space-y-5">
    <div className="flex items-start gap-3">
      <span className="mt-0.5 text-cyan-800"><GitBranch className="size-5" /></span>
      <div><h2 className="text-base font-semibold">Lineage diagrams</h2><p className="mt-1 text-sm leading-6 text-zinc-500">Trace the selected report from its data sources through its semantic model, calculations, pages, and visuals.</p></div>
    </div>

    <div className="overflow-x-auto border-y border-zinc-200 bg-zinc-50 p-1">
      <div className="flex min-w-max" role="tablist" aria-label="Lineage diagram type">
        {modeOptions.map((option) => {
          const Icon = option.icon;
          return <button key={option.id} type="button" role="tab" aria-selected={mode === option.id} onClick={() => setMode(option.id)} className={cn("inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm", mode === option.id ? "bg-white font-semibold text-cyan-900 shadow-sm ring-1 ring-zinc-200" : "text-zinc-600 hover:text-zinc-950")}><Icon className="size-4" />{option.label}</button>;
        })}
      </div>
    </div>

    {mode !== "report" && <ExactLineageStatus loading={exactLineageLoading} error={exactLineageError} dax={dax} hasModel={Boolean(report.semanticModelId && report.semanticModelWorkspaceId)} />}
    {mode === "report" && <ReportDatabaseLineage report={report} snapshot={snapshot} />}
    {mode === "column" && <ColumnLineage snapshot={snapshot} parsed={parsed} dax={dax} />}
    {mode === "calculation" && <CalculationLineage snapshot={snapshot} parsed={parsed} dax={dax} />}
  </div>;
}

function ExactLineageStatus({ loading, error, dax, hasModel }: { loading: boolean; error: boolean; dax: DaxAnalysis | undefined; hasModel: boolean }) {
  if (!hasModel) return <StatusBand tone="warning" text="The report's semantic model was not found. The mapping of semantic objects to data sources is still available." />;
  if (loading) return <div className="flex items-center gap-2 border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900"><Loader2 className="size-3.5 animate-spin" />Finding calculation links in the background</div>;
  if (error) return <StatusBand tone="warning" text="DAX analysis is not available for your account. The diagram uses the report's mapping of semantic objects to data sources instead." />;
  if (dax) return <StatusBand tone="success" text={`${dax.dependency_count} calculation ${dax.dependency_count === 1 ? "link" : "links"} found in this semantic model`} />;
  return null;
}

function ReportDatabaseLineage({ report, snapshot }: { report: ReportChoice; snapshot: ExplorerSnapshot }) {
  const pages = useMemo(() => uniquePages(snapshot.report_layout.rows), [snapshot.report_layout.rows]);
  const [pageScope, setPageScope] = useState(SUMMARY_SCOPE);
  useEffect(() => {
    if (pageScope !== SUMMARY_SCOPE && !pages.some((page) => page.value === pageScope)) setPageScope(SUMMARY_SCOPE);
  }, [pageScope, pages]);
  const graph = useMemo(() => buildReportGraph(report, snapshot, pageScope), [pageScope, report, snapshot]);
  const selectedPage = pages.find((page) => page.value === pageScope)?.label;

  return <div className="space-y-4">
    <div className="grid gap-4 border-y border-zinc-200 py-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <LineageSelect id="report-lineage-page" label={LABEL.diagramScope} value={pageScope} options={[{ value: SUMMARY_SCOPE, label: "Whole report summary" }, ...pages]} onChange={setPageScope} />
      <div className="grid grid-cols-3 border border-zinc-200 bg-zinc-50"><Metric label={LABEL.dataSources} value={snapshot.source_database_lineage.count} /><Metric label={LABEL.semanticObjects} value={snapshot.semantic_model_objects.count} /><Metric label={pageScope === SUMMARY_SCOPE ? LABEL.pages : LABEL.visuals} value={pageScope === SUMMARY_SCOPE ? pages.length : uniqueVisuals(snapshot.report_layout.rows.filter((row) => row.page_id === pageScope)).length} /></div>
    </div>
    <LineageDiagram direction="LR" graph={graph} title={selectedPage ? `${selectedPage} lineage` : `${report.report.name} lineage`} description={selectedPage ? "Data sources and semantic tables used by the selected page, followed by its visuals." : "Data sources flow into semantic tables, the semantic model, the report, and its pages."} emptyText="No verified lineage data available." />
  </div>;
}

function ColumnLineage({ snapshot, parsed, dax }: { snapshot: ExplorerSnapshot; parsed: ParsedSemanticModel | undefined; dax: DaxAnalysis | undefined }) {
  const objects = useMemo(() => collectSemanticObjects(snapshot, parsed), [parsed, snapshot]);
  const columns = useMemo(() => objects.filter((object) => isColumnType(object.objectType)), [objects]);
  const tableNames = useMemo(() => uniqueStrings(columns.map((column) => column.table)), [columns]);
  const [tableName, setTableName] = useState("");
  const [columnKey, setColumnKey] = useState("");

  useEffect(() => {
    if (!tableNames.includes(tableName)) setTableName(tableNames[0] ?? "");
  }, [tableName, tableNames]);
  const tableColumns = columns.filter((column) => column.table === tableName);
  useEffect(() => {
    if (!tableColumns.some((column) => column.key === columnKey)) setColumnKey(tableColumns[0]?.key ?? "");
  }, [columnKey, tableColumns]);
  const selected = tableColumns.find((column) => column.key === columnKey) ?? null;
  const graph = useMemo(() => selected ? buildColumnGraph(snapshot, parsed, dax, selected) : emptyGraph(), [dax, parsed, selected, snapshot]);
  const focusNodeId = selected ? dependencyObjectKey(selected.objectType, selected.table, selected.name) : undefined;

  if (!columns.length) return <EmptyDiagram text="No semantic columns were returned for this report." />;
  return <div className="space-y-4">
    <div className="grid gap-4 border-y border-zinc-200 py-4 md:grid-cols-2">
      <LineageSelect id="column-lineage-table" label={COLUMN.semanticTable} value={tableName} options={tableNames.map(asOption)} onChange={setTableName} />
      <LineageSelect id="column-lineage-column" label={LABEL.column} value={columnKey} options={tableColumns.map((column) => ({ value: column.key, label: `${column.name}${canonicalType(column.objectType) === "calculated_column" ? " (calculated)" : ""}` }))} onChange={setColumnKey} />
    </div>
    {selected && <ObjectEvidence object={selected} />}
    <LineageDiagram direction="TB" graph={graph} focusNodeId={focusNodeId} title="Column lineage" description={selected ? `${selected.table}[${selected.name}] from its data source through the calculations that use this column.` : "Column lineage"} emptyText="No verified lineage data available." />
  </div>;
}

function CalculationLineage({ snapshot, parsed, dax }: { snapshot: ExplorerSnapshot; parsed: ParsedSemanticModel | undefined; dax: DaxAnalysis | undefined }) {
  const objects = useMemo(() => collectSemanticObjects(snapshot, parsed), [parsed, snapshot]);
  const calculations = useMemo(() => objects.filter((object) => isCalculationType(object.objectType)), [objects]);
  const tableNames = useMemo(() => uniqueStrings(calculations.map((object) => object.table)), [calculations]);
  const [tableName, setTableName] = useState("");
  const [targetKey, setTargetKey] = useState("");

  useEffect(() => {
    if (!tableNames.includes(tableName)) setTableName(tableNames[0] ?? "");
  }, [tableName, tableNames]);
  const tableCalculations = calculations.filter((object) => object.table === tableName);
  useEffect(() => {
    if (!tableCalculations.some((object) => object.key === targetKey)) setTargetKey(tableCalculations[0]?.key ?? "");
  }, [tableCalculations, targetKey]);
  const selected = tableCalculations.find((object) => object.key === targetKey) ?? null;
  const graph = useMemo(() => selected ? buildCalculationGraph(snapshot, parsed, dax, selected) : emptyGraph(), [dax, parsed, selected, snapshot]);
  const focusNodeId = selected ? dependencyObjectKey(selected.objectType, selected.table, selected.name) : undefined;

  if (!calculations.length) return <EmptyDiagram text="No measures or calculated columns were returned for this report." />;
  return <div className="space-y-4">
    <div className="grid gap-4 border-y border-zinc-200 py-4 md:grid-cols-2">
      <LineageSelect id="calculation-lineage-table" label={COLUMN.semanticTable} value={tableName} options={tableNames.map(asOption)} onChange={setTableName} />
      <LineageSelect id="calculation-lineage-target" label={LABEL.calculation} value={targetKey} options={tableCalculations.map((object) => ({ value: object.key, label: `${object.name} (${displayType(object.objectType)})` }))} onChange={setTargetKey} />
    </div>
    {selected && <ObjectEvidence object={selected} />}
    <LineageDiagram direction="LR" graph={graph} focusNodeId={focusNodeId} title={`${selected ? displayType(selected.objectType) : "Calculation"} lineage`} description={selected ? `${selected.table}[${selected.name}] is the focal calculation. Inputs flow in from the left; dependent calculations flow out to the right.` : "Calculation lineage"} emptyText="No DAX dependencies were found for the selected calculation." />
  </div>;
}

function ObjectEvidence({ object }: { object: LineageObject }) {
  const [copied, setCopied] = useState(false);
  const hasExpression = Boolean(object.expression?.trim());
  const evidence = object.expression?.trim() || object.sourcePath || object.sourceColumn || "No DAX expression or data source is declared for this object.";
  async function copyExpression() {
    await copyText(evidence);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }
  return <div className="border border-zinc-200 bg-zinc-50">
    <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-3 py-2"><div className="min-w-0"><p className="truncate text-sm font-semibold" title={`${object.table}[${object.name}]`}>{object.table}[{object.name}]</p><p className="mt-0.5 text-xs text-zinc-500">{displayType(object.objectType)}{object.sourceColumn ? ` · ${COLUMN.databaseColumn} ${object.sourceColumn}` : ""}</p></div><Button type="button" variant="outline" size="sm" onClick={() => void copyExpression()}>{copied ? <CheckCircle2 className="size-3.5 text-emerald-700" /> : <Copy className="size-3.5" />}{copied ? "Copied" : hasExpression ? "Copy DAX" : "Copy source"}</Button></div>
    <pre className="max-h-36 overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-5 text-zinc-700">{evidence}</pre>
  </div>;
}

function LineageSelect({ id, label, value, options, onChange }: { id: string; label: string; value: string; options: SelectOption[]; onChange: (value: string) => void }) {
  return <div className="min-w-0 space-y-1.5"><label className="text-xs font-semibold text-zinc-600" htmlFor={id}>{label}</label><select id={id} value={value} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-cyan-800 focus:ring-2 focus:ring-cyan-100">{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>;
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="min-w-0 border-r border-zinc-200 px-3 py-2 last:border-r-0"><p className="truncate text-[11px] text-zinc-500">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div>; }
function EmptyDiagram({ text }: { text: string }) { return <div className="flex min-h-[440px] items-center justify-center border border-zinc-200 bg-zinc-50 p-6 text-center"><div><GitBranch className="mx-auto size-7 text-zinc-300" /><p className="mt-3 text-sm text-zinc-500">{text}</p></div></div>; }
function StatusBand({ tone, text }: { tone: "success" | "warning"; text: string }) { return <div className={cn("border px-3 py-2 text-xs", tone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900")}>{text}</div>; }

function buildReportGraph(report: ReportChoice, snapshot: ExplorerSnapshot, pageScope: string): LineageGraph {
  const selectedPage = pageScope === SUMMARY_SCOPE ? null : pageScope;
  const pageLayout = selectedPage ? snapshot.report_layout.rows.filter((row) => row.page_id === selectedPage) : snapshot.report_layout.rows;
  const pageMappings = selectedPage ? snapshot.visual_source_lookup.rows.filter((row) => row.page_id === selectedPage) : snapshot.visual_source_lookup.rows;
  const usedTables = new Set(pageMappings.map((row) => row.semantic_table).filter((value): value is string => Boolean(value)));
  pageLayout.forEach((row) => { if (row.table_name) usedTables.add(row.table_name); });
  const tableNames = uniqueStrings((usedTables.size ? [...usedTables] : snapshot.source_database_lineage.rows.map((row) => row.semantic_table)).filter(Boolean));
  const sourceRows = snapshot.source_database_lineage.rows.filter((row) => !tableNames.length || tableNames.includes(row.semantic_table));
  const sources = uniqueBy(sourceRows, (row) => row.source_id);
  const pages = selectedPage ? uniquePages(pageLayout) : uniquePages(snapshot.report_layout.rows);
  const visuals = selectedPage ? uniqueVisuals(pageLayout) : [];
  const nodes: LineageGraph["nodes"] = [];
  const edges: LineageGraph["edges"] = [];
  const sourceIds = new Map<string, string>();
  const tableIds = new Map<string, string>();

  sources.forEach((source) => {
    const id = `database-${lineageId(source.source_id)}`;
    sourceIds.set(source.source_id, id);
    nodes.push({ id, kind: "database-source", label: source.source_fully_qualified_name, detail: `${source.source_provider} · ${source.source_object_type}` });
  });
  tableNames.forEach((table) => {
    const id = `table-${lineageId(table)}`;
    tableIds.set(table, id);
    const objectCount = snapshot.semantic_model_objects.rows.filter((row) => row.semantic_table === table).length;
    nodes.push({ id, kind: "table", label: table, detail: `${objectCount} semantic ${objectCount === 1 ? "object" : "objects"}` });
  });
  sourceRows.forEach((row, index) => {
    const source = sourceIds.get(row.source_id);
    const target = tableIds.get(row.semantic_table);
    if (source && target) edges.push({ id: `source-table-${index}`, source, target, label: "feeds" });
  });

  const modelId = "selected-semantic-model";
  const reportId = "selected-report";
  nodes.push({ id: modelId, kind: "semantic-model", label: report.semanticModelName ?? COLUMN.semanticModel, detail: report.semanticModelId ?? `${COLUMN.semanticModelId}: ${VALUE.notFound}` });
  nodes.push({ id: reportId, kind: "report", label: report.report.name, detail: report.workspaceName });
  tableIds.forEach((id, table) => edges.push({ id: `table-model-${lineageId(table)}`, source: id, target: modelId, label: "belongs to" }));
  edges.push({ id: "model-report", source: modelId, target: reportId, label: "powers" });

  pages.forEach((page) => {
    const id = `page-${lineageId(page.value)}`;
    const visualCount = uniqueVisuals(snapshot.report_layout.rows.filter((row) => row.page_id === page.value)).length;
    nodes.push({ id, kind: "page", label: page.label, detail: `${visualCount} ${visualCount === 1 ? "visual" : "visuals"}` });
    edges.push({ id: `report-page-${lineageId(page.value)}`, source: reportId, target: id, label: "contains" });
  });
  if (selectedPage) {
    visuals.forEach((visual) => {
      const id = `visual-${lineageId(visual.value)}`;
      const rows = pageLayout.filter((row) => `${row.page_id}:${row.visual_id}` === visual.value);
      const type = rows.find((row) => row.visual_type)?.visual_type ?? "Visual";
      const fields = uniqueStrings(rows.map((row) => row.column_measure_name).filter((value): value is string => Boolean(value)));
      nodes.push({ id, kind: "visual", label: visual.label, detail: `${type} · ${fields.length} referenced ${fields.length === 1 ? "field" : "fields"}` });
      edges.push({ id: `page-visual-${lineageId(visual.value)}`, source: `page-${lineageId(selectedPage)}`, target: id, label: "renders" });
    });
  }
  return dedupeGraph({ nodes, edges });
}

function buildColumnGraph(snapshot: ExplorerSnapshot, parsed: ParsedSemanticModel | undefined, dax: DaxAnalysis | undefined, selected: LineageObject): LineageGraph {
  const dependencies = collectDependencies(snapshot, dax);
  const expressionIndex = buildExpressionIndex(snapshot, parsed);
  const seed: DaxReference = { object_type: selected.objectType, table_name: selected.table, object_name: selected.name, qualified_name: `${selected.table}[${selected.name}]` };
  const rootId = referenceKey(seed);
  const closure = computeDependencyClosure(dependencies, [seed]);
  const graph = closureToLineageGraph({ seeds: [seed], upstream: [], downstream: closure.downstream }, dependencies);
  graph.nodes.forEach((node) => {
    node.detail = node.id === rootId ? (selected.expression ?? selected.sourcePath ?? objectTypeLabel(selected.objectType)) : (expressionIndex.get(node.id) ?? node.detail);
  });

  const sourceRows = snapshot.source_database_lineage.rows.filter((row) => row.semantic_table === selected.table);
  const sources = uniqueBy(sourceRows, (row) => row.source_id);
  const sourceItems = sources.length ? sources : [{ source_id: `declared-${selected.key}`, source_provider: "Definition", source_object_type: "column", source_fully_qualified_name: selected.sourcePath ?? `${COLUMN.databaseTable}: ${VALUE.notAvailable}` }];
  sourceItems.forEach((source) => {
    const id = `source-${lineageId(source.source_id)}`;
    const columnDetail = `${COLUMN.databaseColumn} ${selected.sourceColumn ?? VALUE.notAvailable.toLocaleLowerCase()}`;
    graph.nodes.push({ id, kind: "database-source", label: source.source_fully_qualified_name, detail: `${source.source_provider} · ${columnDetail}` });
    graph.edges.push({ id: `source-root-${lineageId(source.source_id)}`, source: id, target: rootId, label: "maps to" });
  });
  return graph;
}

function buildCalculationGraph(snapshot: ExplorerSnapshot, parsed: ParsedSemanticModel | undefined, dax: DaxAnalysis | undefined, selected: LineageObject): LineageGraph {
  const dependencies = collectDependencies(snapshot, dax);
  const expressionIndex = buildExpressionIndex(snapshot, parsed);
  const seed: DaxReference = { object_type: selected.objectType, table_name: selected.table, object_name: selected.name, qualified_name: `${selected.table}[${selected.name}]` };
  const rootId = referenceKey(seed);
  const closure = computeDependencyClosure(dependencies, [seed]);
  const graph = closureToLineageGraph(closure, dependencies);
  graph.nodes.forEach((node) => {
    node.detail = node.id === rootId ? (selected.expression ?? LABEL.calculation) : (expressionIndex.get(node.id) ?? node.detail);
  });
  return graph;
}

function collectSemanticObjects(snapshot: ExplorerSnapshot, parsed: ParsedSemanticModel | undefined) {
  const objects = new Map<string, LineageObject>();
  snapshot.semantic_model_objects.rows.forEach((row) => {
    const type = canonicalType(row.semantic_object_type);
    const key = selectionKey(type, row.semantic_table, row.semantic_object_name);
    objects.set(key, { key, table: row.semantic_table, name: row.semantic_object_name, objectType: type, expression: row.semantic_dax_expression ?? null, sourceColumn: row.semantic_source_column ?? null, sourcePath: row.source_path ?? null, dataType: row.semantic_data_type ?? null });
  });
  parsed?.tables.forEach((table) => {
    if (table.expression) addObject(objects, { table: table.name, name: table.name, objectType: "calculated_table", expression: table.expression, sourceColumn: null, sourcePath: table.source_path ?? null, dataType: null });
    table.columns.forEach((column) => addObject(objects, { table: table.name, name: column.name, objectType: column.expression ? "calculated_column" : "column", expression: column.expression ?? null, sourceColumn: column.source_column ?? null, sourcePath: column.source_path ?? table.source_path ?? null, dataType: column.data_type ?? null }));
    table.measures.forEach((measure) => addObject(objects, { table: table.name, name: measure.name, objectType: "measure", expression: measure.expression ?? null, sourceColumn: null, sourcePath: table.source_path ?? null, dataType: null }));
  });
  return [...objects.values()].sort((first, second) => first.table.localeCompare(second.table) || first.name.localeCompare(second.name));
}

function addObject(objects: Map<string, LineageObject>, object: Omit<LineageObject, "key">) {
  const key = selectionKey(object.objectType, object.table, object.name);
  const existing = objects.get(key);
  objects.set(key, { key, ...object, expression: existing?.expression ?? object.expression, sourceColumn: existing?.sourceColumn ?? object.sourceColumn, sourcePath: existing?.sourcePath ?? object.sourcePath, dataType: existing?.dataType ?? object.dataType });
}

function collectDependencies(snapshot: ExplorerSnapshot, dax: DaxAnalysis | undefined): DaxDependency[] {
  if (dax) return uniqueBy(dax.dependencies, (dependency) => `${referenceKey(dependency.source)}>${referenceKey(dependency.target)}:${dependency.reference_text}`);
  const dependencies = snapshot.measure_source_lineage.rows.flatMap((row): DaxDependency[] => {
    const sourceName = row.source_semantic_object_name ?? row.source_column_name;
    if (!sourceName || !row.source_semantic_table) return [];
    const sourceType = canonicalType(row.source_semantic_object_type ?? "column");
    const targetType = canonicalType(row.semantic_object_type);
    return [{
      source: makeReference(sourceType, row.source_semantic_table, sourceName),
      target: makeReference(targetType, row.semantic_table ?? "", row.semantic_object_name),
      reference_text: row.is_direct_dependency ? "direct" : `indirect${row.dependency_depth ? ` · ${row.dependency_depth} steps away` : ""}`,
    }];
  });
  return uniqueBy(dependencies, (dependency) => `${referenceKey(dependency.source)}>${referenceKey(dependency.target)}`);
}

function buildExpressionIndex(snapshot: ExplorerSnapshot, parsed: ParsedSemanticModel | undefined) {
  const index = new Map<string, string>();
  collectSemanticObjects(snapshot, parsed).forEach((object) => { if (object.expression) index.set(dependencyObjectKey(object.objectType, object.table, object.name), object.expression); });
  return index;
}

function dependencyObjectKey(objectType: string, table: string, name: string) {
  return referenceKey({ object_type: objectType, table_name: table, object_name: name, qualified_name: "" });
}

function makeReference(objectType: string, tableName: string, objectName: string): DaxReference { return { object_type: objectType, table_name: tableName, object_name: objectName, qualified_name: tableName ? `${tableName}[${objectName}]` : objectName }; }
function selectionKey(objectType: string, table: string, name: string) { return `${canonicalType(objectType)}${table}${name}`; }
function isColumnType(value: string) { const type = canonicalType(value); return type === "column" || type === "calculated_column"; }
function isCalculationType(value: string) { const type = canonicalType(value); return type === "measure" || type === "calculated_column" || type === "calculated_table"; }
function displayType(value: string) { return objectTypeLabel(canonicalType(value)); }

function uniquePages(rows: ReportLayoutRow[]): SelectOption[] { return uniqueBy(rows, (row) => row.page_id).sort((first, second) => (first.page_order ?? Number.MAX_SAFE_INTEGER) - (second.page_order ?? Number.MAX_SAFE_INTEGER) || first.page_name.localeCompare(second.page_name)).map((row) => ({ value: row.page_id, label: row.page_name })); }
function uniqueVisuals(rows: ReportLayoutRow[]): SelectOption[] { return uniqueBy(rows, (row) => `${row.page_id}:${row.visual_id}`).map((row) => ({ value: `${row.page_id}:${row.visual_id}`, label: row.visual_name })); }
function uniqueStrings(values: string[]) { return [...new Set(values)].sort((first, second) => first.localeCompare(second)); }
function uniqueBy<T>(items: T[], key: (item: T) => string) { const seen = new Set<string>(); return items.filter((item) => { const value = key(item); if (seen.has(value)) return false; seen.add(value); return true; }); }
function dedupeGraph(graph: LineageGraph): LineageGraph { return { nodes: uniqueBy(graph.nodes, (node) => node.id), edges: uniqueBy(graph.edges, (edge) => `${edge.source}>${edge.target}:${String(edge.label ?? "")}`) }; }
function emptyGraph(): LineageGraph { return { nodes: [], edges: [] }; }
function asOption(value: string): SelectOption { return { value, label: value }; }
function lineageId(value: string) { return value.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLocaleLowerCase(); }
async function copyText(text: string) { try { await navigator.clipboard.writeText(text); } catch { const textarea = document.createElement("textarea"); textarea.value = text; textarea.style.position = "fixed"; textarea.style.opacity = "0"; document.body.appendChild(textarea); textarea.select(); document.execCommand("copy"); textarea.remove(); } }
