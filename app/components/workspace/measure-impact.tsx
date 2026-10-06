import { useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";
import { ArrowUpToLine, CheckCircle2, Code2, Copy, FileBarChart2, Layers3, Loader2, MonitorPlay, RefreshCw, Sigma, TableProperties } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { TableSearchHeader } from "~/components/ui/table-search-header";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { AskPowerAiButton } from "~/components/power-ai/ask-power-ai-button";
import { PowerBiAuthRequired } from "~/components/workspace/auth-required";
import { ImpactGrid } from "~/components/workspace/impact-grid";
import { buildImpactGraph, ImpactLineageDiagram } from "~/components/workspace/impact-lineage";
import { ObjectSearchSelect, WorkspaceScopeSelect, type SearchEntry } from "~/components/workspace/impact-picker";
import { EmptyState, EvidenceStatus, ImpactSection, LoadingState, REPORT_LIST_FAILED_TEXT, StatusBand, SummaryTile } from "~/components/workspace/impact-ui";
import { canonicalType, computeDependencyClosure, referenceKey, referenceLabel, type ClosureHop, type DaxDependency, type DaxReference } from "~/lib/dependency-graph";
import { copyText, filePart, type ExportContext, type GridRow } from "~/lib/grid-export";
import {
  buildEvidenceIndex,
  buildReportNames,
  displayType,
  evidenceKey,
  fetchImpactEvidence,
  impactEvidenceKey,
  tableSources,
  type EstateWithReports,
  type EvidenceIndex,
  type ReportDisplayName,
  type SourcedTable,
} from "~/lib/impact-analysis";
import {
  boundReportsForModel,
  daxAnalysisKey,
  estateDiscoveryKey,
  ESTATE_DISCOVER_PATH,
  estateInventoryKey,
  fetchEstateInventory,
  modelKey,
  requestJson,
  WORKSPACE_LIST_PATH,
  workspaceListKey,
  type InventoryEntry,
  type ParsedSemanticModel,
} from "~/lib/lineage-api";
import { COLUMN, dependencyLabel, gridColumn, VALUE } from "~/lib/naming";
import { useAppStore } from "~/stores/app-store";
import { usePowerAiStore } from "~/stores/power-ai-store";

type Workspace = { id: string; name: string };
type WorkspaceResponse = { workspaces: Workspace[] };
type DaxAnalysis = { dependencies: DaxDependency[]; dependency_count: number };

/** "Connection to the measure" values in the Semantic tables grid (Docs/07-column-naming-standard.md). */
const CONNECTION = {
  holdsMeasure: "Holds the measure",
  readByMeasure: "Read by the measure",
  holdsImpactedMeasures: "Holds impacted measures",
  holdsImpactedCalculations: "Holds impacted calculations",
} as const;

const plural = (count: number, one: string, many: string) => (count === 1 ? one : many);

/**
 * Pick a measure and see everything it touches: the tables it reads and the
 * tables holding calculations built on it, the other measures it impacts, its
 * semantic model, and every report and visual that shows it or an impacted
 * measure.
 */
export function MeasureImpact() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[] | null>(null);
  const [selectedMeasureKey, setSelectedMeasureKey] = useState("");

  // Search states for each of the 6 table sections
  const [tableSearch, setTableSearch] = useState("");
  const [impactedMeasureSearch, setImpactedMeasureSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [visualSearch, setVisualSearch] = useState("");
  const [inputSearch, setInputSearch] = useState("");

  const workspacesQuery = useQuery({
    queryKey: workspaceListKey(apiOrigin),
    queryFn: () => requestJson<WorkspaceResponse>(apiOrigin, WORKSPACE_LIST_PATH),
  });
  const workspaces = useMemo(() => workspacesQuery.data?.workspaces ?? [], [workspacesQuery.data]);
  useEffect(() => {
    if (workspaces.length && selectedWorkspaceIds === null) setSelectedWorkspaceIds(workspaces.map((workspace) => workspace.id));
  }, [workspaces, selectedWorkspaceIds]);
  const scopeIds = useMemo(() => selectedWorkspaceIds ?? [], [selectedWorkspaceIds]);
  const scopedWorkspaces = useMemo(() => workspaces.filter((workspace) => scopeIds.includes(workspace.id)), [workspaces, scopeIds]);

  const inventoryQuery = useQuery({
    queryKey: estateInventoryKey(apiOrigin, scopeIds),
    queryFn: () => fetchEstateInventory(apiOrigin, scopedWorkspaces),
    enabled: scopeIds.length > 0,
  });
  const measures = useMemo(() => inventoryQuery.data?.measures ?? [], [inventoryQuery.data]);
  
  const measureEntries: SearchEntry[] = useMemo(() => measures.map((entry) => ({
    key: entry.key,
    searchValue: `${entry.measureName} ${entry.tableName} ${entry.semanticModelName} ${entry.workspaceName}`,
    primary: entry.measureName ?? "",
    secondary: `${entry.tableName} · ${entry.semanticModelName} · ${entry.workspaceName}`,
  })), [measures]);
  useEffect(() => {
    if (measures.length && !measures.some((entry) => entry.key === selectedMeasureKey)) setSelectedMeasureKey(measures[0].key);
  }, [measures, selectedMeasureKey]);
  const selectedEntry = measures.find((entry) => entry.key === selectedMeasureKey) ?? null;
  const selectedModelKey = selectedEntry ? modelKey(selectedEntry.workspaceId, selectedEntry.semanticModelId) : "";
  const parsedModel = selectedEntry ? inventoryQuery.data?.parsedByModel.get(selectedModelKey) : undefined;

  const daxQuery = useQuery({
    queryKey: daxAnalysisKey(apiOrigin, selectedEntry?.workspaceId ?? "", selectedEntry?.semanticModelId ?? ""),
    queryFn: () => requestJson<DaxAnalysis>(apiOrigin, "/api/v1/lineage/dax/analyze", { method: "POST", body: JSON.stringify(parsedModel) }),
    enabled: Boolean(parsedModel),
  });

  const estateQuery = useQuery({
    queryKey: estateDiscoveryKey(apiOrigin),
    queryFn: () => requestJson<EstateWithReports>(apiOrigin, ESTATE_DISCOVER_PATH),
    enabled: Boolean(selectedEntry),
  });
  const boundReports = useMemo(() => boundReportsForModel(estateQuery.data, selectedEntry?.semanticModelId ?? ""), [estateQuery.data, selectedEntry]);
  const evidenceQuery = useQuery({
    queryKey: impactEvidenceKey("measure-impact", apiOrigin, selectedEntry?.semanticModelId ?? "", boundReports),
    queryFn: () => fetchImpactEvidence(apiOrigin, boundReports),
    enabled: boundReports.length > 0,
  });

  const selectedMeasureExpression = useMemo(() => {
    if (selectedEntry?.expression) return selectedEntry.expression;
    if (!parsedModel || !selectedEntry?.measureName) return null;
    const targetName = selectedEntry.measureName.trim().toLowerCase();
    const targetTable = selectedEntry.tableName.trim().toLowerCase();
    for (const table of parsedModel.tables) {
      if (!targetTable || table.name.trim().toLowerCase() === targetTable) {
        const found = table.measures.find((m) => m.name.trim().toLowerCase() === targetName);
        if (found?.expression) return found.expression;
      }
    }
    for (const table of parsedModel.tables) {
      const found = table.measures.find((m) => m.name.trim().toLowerCase() === targetName);
      if (found?.expression) return found.expression;
    }
    return null;
  }, [selectedEntry, parsedModel]);

  const seed = useMemo<DaxReference | null>(
    () => (selectedEntry?.measureName ? {
      object_type: "measure",
      table_name: selectedEntry.tableName,
      object_name: selectedEntry.measureName,
      qualified_name: `${selectedEntry.tableName}[${selectedEntry.measureName}]`,
      expression: selectedMeasureExpression,
    } : null),
    [selectedEntry, selectedMeasureExpression],
  );
  const dependencies = useMemo(() => daxQuery.data?.dependencies ?? [], [daxQuery.data]);
  const closure = useMemo(() => computeDependencyClosure(dependencies, seed ? [seed] : []), [dependencies, seed]);
  const evidence = useMemo(() => buildEvidenceIndex(evidenceQuery.data), [evidenceQuery.data]);
  const reportNames = useMemo(() => buildReportNames(estateQuery.data, [evidence]), [estateQuery.data, evidence]);
  const sourcesByTable = useMemo(() => new Map((parsedModel?.tables ?? []).map((table) => [table.name, tableSources(table as SourcedTable)] as const)), [parsedModel]);
  const analysis = useMemo(
    () => (selectedEntry && seed ? analyzeMeasure(selectedEntry, seed, closure.upstream, closure.downstream, evidence, reportNames, sourcesByTable, parsedModel, boundReports.length) : null),
    [selectedEntry, seed, closure, evidence, reportNames, sourcesByTable, parsedModel, boundReports.length],
  );
  const impactGraph = useMemo(() => (selectedEntry && seed
    ? buildImpactGraph([{
      model: { key: selectedModelKey, name: selectedEntry.semanticModelName, workspaceName: selectedEntry.workspaceName },
      focal: [seed],
      members: [...closure.upstream, ...closure.downstream].map((hop) => hop.reference),
      dependencies,
      evidence,
      tableSources: sourcesByTable,
    }], reportNames)
    : null), [selectedEntry, seed, selectedModelKey, closure, dependencies, evidence, sourcesByTable, reportNames]);

  // Dynamic row filtering for each table section
  const filteredTableRows = useMemo(() => {
    if (!analysis?.tableRows) return [];
    if (!tableSearch.trim()) return analysis.tableRows;
    const q = tableSearch.toLowerCase();
    return analysis.tableRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.tableRows, tableSearch]);

  const filteredImpactedMeasureRows = useMemo(() => {
    if (!analysis?.impactedMeasureRows) return [];
    if (!impactedMeasureSearch.trim()) return analysis.impactedMeasureRows;
    const q = impactedMeasureSearch.toLowerCase();
    return analysis.impactedMeasureRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.impactedMeasureRows, impactedMeasureSearch]);

  const filteredModelRows = useMemo(() => {
    if (!analysis?.modelRows) return [];
    if (!modelSearch.trim()) return analysis.modelRows;
    const q = modelSearch.toLowerCase();
    return analysis.modelRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.modelRows, modelSearch]);

  const filteredReportRows = useMemo(() => {
    if (!analysis?.reportRows) return [];
    if (!reportSearch.trim()) return analysis.reportRows;
    const q = reportSearch.toLowerCase();
    return analysis.reportRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.reportRows, reportSearch]);

  const filteredVisualRows = useMemo(() => {
    if (!analysis?.visualRows) return [];
    if (!visualSearch.trim()) return analysis.visualRows;
    const q = visualSearch.toLowerCase();
    return analysis.visualRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.visualRows, visualSearch]);

  const filteredInputRows = useMemo(() => {
    if (!analysis?.inputRows) return [];
    if (!inputSearch.trim()) return analysis.inputRows;
    const q = inputSearch.toLowerCase();
    return analysis.inputRows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(q))
    );
  }, [analysis?.inputRows, inputSearch]);

  const measureLabel = selectedEntry?.measureName ?? "";
  const qualifiedMeasure = selectedEntry ? `${selectedEntry.tableName}[${selectedEntry.measureName}]` : "";
  const exportContext: ExportContext = {
    [COLUMN.workspaceName]: selectedEntry?.workspaceName ?? "",
    [COLUMN.semanticModel]: selectedEntry?.semanticModelName ?? "",
    [COLUMN.selectedMeasure]: measureLabel,
    [COLUMN.daxExpression]: selectedMeasureExpression ?? VALUE.notAvailable,
    [COLUMN.workspaceId]: selectedEntry?.workspaceId ?? "",
    [COLUMN.semanticModelId]: selectedEntry?.semanticModelId ?? "",
  };

  const usageExportContext: ExportContext = {
    [COLUMN.semanticModel]: selectedEntry?.semanticModelName ?? "",
    [COLUMN.selectedMeasure]: measureLabel,
    [COLUMN.daxExpression]: selectedMeasureExpression ?? VALUE.notAvailable,
    [COLUMN.semanticModelId]: selectedEntry?.semanticModelId ?? "",
  };
  const filePrefix = `measure-impact-${filePart(selectedEntry?.measureName)}`;

  useEffect(() => {
    usePowerAiStore.getState().mergeContext({
      workspaceId: selectedEntry?.workspaceId,
      workspaceName: selectedEntry?.workspaceName,
      semanticModelId: selectedEntry?.semanticModelId,
      semanticModelName: selectedEntry?.semanticModelName,
      semanticModelWorkspaceId: selectedEntry?.workspaceId,
      reportId: undefined,
      reportName: undefined,
      objectType: selectedEntry ? "measure" : undefined,
      objectId: selectedEntry?.key,
      objectName: selectedEntry ? `${selectedEntry.tableName}[${selectedEntry.measureName}]` : undefined,
    });
  }, [selectedEntry]);

  if (workspacesQuery.isLoading) return <LoadingState label="Loading Power BI workspaces" />;
  if (workspacesQuery.isError) return <PowerBiAuthRequired returnTo="Measure impact" />;
  if (!workspaces.length) return <EmptyState title="No Power BI workspaces found" text="The authenticated account did not return any workspaces to explore." />;

  const usagePending = evidenceQuery.isLoading || estateQuery.isLoading;
  const usageEmpty = estateQuery.isError ? REPORT_LIST_FAILED_TEXT : usagePending || daxQuery.isLoading ? "Checking reports..." : undefined;
  const daxEmpty = daxQuery.isLoading ? "Finding calculation links..." : daxQuery.isError ? "Calculation links could not be loaded for your account." : undefined;

  return <section className="overflow-hidden rounded-lg border border-border bg-surface">
    <div className="border-b border-border px-5 py-5 sm:px-6">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><Sigma className="size-5" /></span>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-semibold uppercase text-fabric">Power BI</span><Badge className="rounded-md border border-fabric/25 bg-accent text-accent-foreground">Measure impact</Badge></div>
          <h1 className="text-lg font-semibold">Measure impact</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">Pick a measure to see the semantic tables it reads and affects, the other measures it impacts, its semantic model, and every report and visual that shows it.</p>
        </div>
      </div>
    </div>

    <InventoryStatus selectedWorkspaceCount={scopeIds.length} isLoading={inventoryQuery.isFetching} isError={inventoryQuery.isError} entryCount={measures.length} skippedCount={inventoryQuery.data?.skipped.length ?? 0} onRefresh={() => void inventoryQuery.refetch()} />

    <div className="grid gap-4 border-b border-border bg-subtle px-5 py-4 sm:px-6 md:grid-cols-2">
      <WorkspaceScopeSelect id="measure-impact-scope" label="Workspace scope" workspaces={workspaces} selectedIds={scopeIds} onChange={setSelectedWorkspaceIds} />
      <ObjectSearchSelect id="measure-impact-measure" label="Measure" placeholder="Search a measure by name..." entries={measureEntries} selectedKey={selectedMeasureKey} onChange={setSelectedMeasureKey} emptyText="No measures indexed for the selected workspace scope yet." />
    </div>

    <div className="space-y-6 p-5 sm:p-6">
      {!selectedEntry && <EmptyState title="No measure selected" text="Choose a workspace scope and search for a measure above to run impact analysis." />}
      {selectedEntry && analysis && impactGraph && <>
        <div className="space-y-2">
          <ExactLineageStatus loading={daxQuery.isLoading} error={daxQuery.isError} dax={daxQuery.data} />
          <EvidenceStatus estateLoading={estateQuery.isLoading} estateError={estateQuery.isError} boundCount={boundReports.length} loading={evidenceQuery.isLoading} truncated={Boolean(evidenceQuery.data?.truncated)} noBoundText="No report you can open is connected to this semantic model." />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <SummaryTile icon={TableProperties} label="Semantic tables" value={analysis.tableRows.length} caption="Read by it or holding calculations on it" pending={daxQuery.isLoading} />
          <SummaryTile icon={Sigma} label="Impacted measures" value={analysis.impactedMeasureRows.length} caption="Depending on it, directly or indirectly" pending={daxQuery.isLoading} />
          <SummaryTile icon={Layers3} label="Semantic models" value={analysis.modelRows.length} caption={selectedEntry.semanticModelName} pending={false} />
          <SummaryTile icon={FileBarChart2} label="Reports" value={analysis.reportRows.length} caption="With a visual showing it or an impacted measure" pending={usagePending} />
          <SummaryTile icon={MonitorPlay} label="Visuals" value={analysis.visualRows.length} caption="Showing it or an impacted measure" pending={usagePending} />
        </div>

        <div className="flex justify-end">
          <AskPowerAiButton
            context={{
              workspaceId: selectedEntry.workspaceId,
              workspaceName: selectedEntry.workspaceName,
              semanticModelId: selectedEntry.semanticModelId,
              semanticModelName: selectedEntry.semanticModelName,
              semanticModelWorkspaceId: selectedEntry.workspaceId,
              objectType: "measure",
              objectId: selectedEntry.key,
              objectName: qualifiedMeasure,
            }}
            question="Explain this measure"
          />
        </div>

        <ImpactLineageDiagram
          graph={impactGraph.graph}
          focusNodeId={`${selectedModelKey}|${referenceKey(seed!)}`}
          title={`${measureLabel} impact`}
          description="Database tables and the semantic model feed the tables and columns the measure reads; the measure flows down through the measures that depend on it to the reports and visuals that show them."
          emptyText="No DAX dependencies or report usage were found for the selected measure."
          hiddenReports={impactGraph.hiddenReports}
          hiddenVisuals={impactGraph.hiddenVisuals}
        />

        {/* 1. SEMANTIC TABLES SECTION */}
        <ImpactSection icon={TableProperties} title="Semantic tables" text="The semantic table holding the measure, the semantic tables whose columns and measures it reads, and the ones holding measures or calculated columns that depend on it.">
          <TableSearchHeader
            searchTerm={tableSearch}
            onSearchChange={setTableSearch}
            placeholder="Search semantic tables..."
          />
          <ImpactGrid rowData={filteredTableRows} columnDefs={tableColumnDefs} emptyMessage={daxEmpty ?? "No semantic tables are connected to this measure."} exportFileName={`${filePrefix}-semantic-tables`} exportContext={exportContext} fitRows />
        </ImpactSection>

        {/* 2. IMPACTED MEASURES SECTION */}
        <ImpactSection icon={Sigma} title={`Measures impacted by ${measureLabel}`} text="Every measure that reads this measure, directly or through another calculation — each one changes when this measure changes.">
          <TableSearchHeader
            searchTerm={impactedMeasureSearch}
            onSearchChange={setImpactedMeasureSearch}
            placeholder="Search measures, DAX expressions, or dependencies..."
          />
          <ImpactGrid rowData={filteredImpactedMeasureRows} columnDefs={impactedMeasureColumnDefs} emptyMessage={daxEmpty ?? "No other measure depends on this measure."} exportFileName={`${filePrefix}-impacted-measures`} exportContext={exportContext} fitRows />
        </ImpactSection>

        {/* 3. SEMANTIC MODEL SECTION */}
        <ImpactSection icon={Layers3} title="Semantic model" text="The semantic model holding the measure, with how much of it the measure impacts and how many connected reports show it.">
          <TableSearchHeader
            searchTerm={modelSearch}
            onSearchChange={setModelSearch}
            placeholder="Search semantic models or workspaces..."
          />
          <ImpactGrid rowData={filteredModelRows} columnDefs={modelColumnDefs} emptyMessage="The semantic model was not found." exportFileName={`${filePrefix}-semantic-model`} exportContext={exportContext} fitRows />
        </ImpactSection>

        {/* 4. REPORTS SECTION */}
        <ImpactSection icon={FileBarChart2} title="Reports" text="Reports with at least one visual that shows this measure directly, or shows a measure or calculation that depends on it.">
          <TableSearchHeader
            searchTerm={reportSearch}
            onSearchChange={setReportSearch}
            placeholder="Search reports or workspaces..."
          />
          <ImpactGrid rowData={filteredReportRows} columnDefs={reportColumnDefs} emptyMessage={usageEmpty ?? "No report visual shows this measure or anything depending on it."} exportFileName={`${filePrefix}-reports`} exportContext={usageExportContext} fitRows />
        </ImpactSection>

        {/* 5. VISUALS SECTION */}
        <ImpactSection icon={MonitorPlay} title="Visuals" text="Every visual showing this measure or an impacted measure, with its page and report.">
          <TableSearchHeader
            searchTerm={visualSearch}
            onSearchChange={setVisualSearch}
            placeholder="Search visuals, page names, or visual types..."
          />
          <ImpactGrid rowData={filteredVisualRows} columnDefs={visualColumnDefs} emptyMessage={usageEmpty ?? "No visual shows this measure or anything depending on it."} exportFileName={`${filePrefix}-visuals`} exportContext={usageExportContext} fitRows />
        </ImpactSection>

        {/* 6. INPUTS READ SECTION */}
        <ImpactSection icon={ArrowUpToLine} title={`Inputs ${measureLabel} reads`} text="Columns and measures this measure depends on, directly or indirectly, with the database table behind each column.">
          <TableSearchHeader
            searchTerm={inputSearch}
            onSearchChange={setInputSearch}
            placeholder="Search input objects, tables, or DAX expressions..."
          />
          <ImpactGrid rowData={filteredInputRows} columnDefs={inputColumnDefs} emptyMessage={daxEmpty ?? "This measure reads no other semantic objects."} exportFileName={`${filePrefix}-inputs`} exportContext={exportContext} fitRows />
        </ImpactSection>
      </>}
    </div>
  </section>;
}

const tableColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.semanticTable, { minWidth: 170 }),
  gridColumn(COLUMN.connectionToMeasure, { minWidth: 240, flex: 1 }),
  gridColumn(COLUMN.objectsInvolved, { minWidth: 240, flex: 1 }),
  gridColumn(COLUMN.databaseTables, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.semanticModel, { minWidth: 170 }),
  gridColumn(COLUMN.workspaceName, { hide: true }),
];

const impactedMeasureColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.measureName, { minWidth: 200, flex: 1 }),
  gridColumn(COLUMN.semanticTable, { minWidth: 160 }),
  gridColumn(COLUMN.dependency, { minWidth: 130 }),
  gridColumn(COLUMN.stepsAway, { minWidth: 120 }),
  gridColumn(COLUMN.referencedAs, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.daxExpression, { minWidth: 300, flex: 2 }),
  gridColumn(COLUMN.reportCount, { minWidth: 170 }),
  gridColumn(COLUMN.visualCount, { minWidth: 170 }),
];

const modelColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.semanticModel, { minWidth: 190, flex: 1 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.measuresSemanticTable, { minWidth: 230 }),
  gridColumn(COLUMN.impactedMeasureCount, { minWidth: 250 }),
  gridColumn(COLUMN.impactedCalculatedColumnCount, { minWidth: 320 }),
  gridColumn(COLUMN.reportsUsingCount, { minWidth: 240 }),
  gridColumn(COLUMN.visualsUsingCount, { minWidth: 240 }),
  gridColumn(COLUMN.connectedReportCount, { minWidth: 250 }),
  gridColumn(COLUMN.semanticModelId, { hide: true }),
  gridColumn(COLUMN.workspaceId, { hide: true }),
];

const reportColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.reportName, { minWidth: 200, flex: 1.2 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.howItIsUsed, { minWidth: 170 }),
  gridColumn(COLUMN.pageCount, { minWidth: 160 }),
  gridColumn(COLUMN.visualCount, { minWidth: 170 }),
  gridColumn(COLUMN.objectsUsed, { minWidth: 240, flex: 1 }),
  gridColumn(COLUMN.reportId, { hide: true }),
];

const visualColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.visualName, { minWidth: 190, flex: 1 }),
  gridColumn(COLUMN.visualType, { minWidth: 140 }),
  gridColumn(COLUMN.pageName, { minWidth: 150 }),
  gridColumn(COLUMN.reportName, { minWidth: 180 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.howItIsUsed, { minWidth: 170 }),
  gridColumn(COLUMN.objectsUsed, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.reportId, { hide: true }),
  gridColumn(COLUMN.visualId, { hide: true }),
];

const inputColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.objectName, { minWidth: 200, flex: 1 }),
  gridColumn(COLUMN.semanticTable, { minWidth: 160 }),
  gridColumn(COLUMN.objectType, { minWidth: 150 }),
  gridColumn(COLUMN.daxExpression, { minWidth: 300, flex: 2 }),
  gridColumn(COLUMN.dependency, { minWidth: 130 }),
  gridColumn(COLUMN.stepsAway, { minWidth: 120 }),
  gridColumn(COLUMN.referencedAs, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.databaseTable, { minWidth: 220 }),
];

type TableAccumulator = { roles: Set<string>; objects: Set<string> };

const howItIsUsed = (direct: boolean) => (direct ? VALUE.usesDirectly : VALUE.throughMeasure);
const byStepsThenName = (a: ClosureHop, b: ClosureHop) => a.depth - b.depth || referenceLabel(a.reference).localeCompare(referenceLabel(b.reference));

function analyzeMeasure(
  entry: InventoryEntry,
  seed: DaxReference,
  upstream: ClosureHop[],
  downstream: ClosureHop[],
  evidence: EvidenceIndex,
  reportNames: Map<string, ReportDisplayName>,
  sourcesByTable: Map<string, string[]>,
  parsedModel: ParsedSemanticModel | undefined,
  boundCount: number,
) {
  const usageOf = (reference: DaxReference) => evidence.byObject.get(evidenceKey(reference.table_name, reference.object_name));
  const measureName = referenceLabel(seed);

  const expressionFor = (tableName: string | null | undefined, objectName: string, objectType: string): string => {
    if (!parsedModel || !tableName || !objectName) return VALUE.notAvailable;
    const type = canonicalType(objectType);
    const tableNameLower = tableName.trim().toLowerCase();
    const objectNameLower = objectName.trim().toLowerCase();
    for (const table of parsedModel.tables) {
      if (table.name.trim().toLowerCase() !== tableNameLower) continue;
      if (type === "measure") {
        const found = table.measures.find((m) => m.name.trim().toLowerCase() === objectNameLower);
        if (found?.expression) return found.expression;
      } else if (type === "calculated_column") {
        const found = table.columns.find((c) => c.name.trim().toLowerCase() === objectNameLower);
        if (found?.expression) return found.expression;
      }
    }
    return VALUE.notAvailable;
  };

  const tables = new Map<string, TableAccumulator>();
  const noteTable = (name: string | null | undefined, role: string, object?: string) => {
    if (!name) return;
    const table = tables.get(name) ?? { roles: new Set<string>(), objects: new Set<string>() };
    table.roles.add(role);
    if (object) table.objects.add(object);
    tables.set(name, table);
  };
  noteTable(entry.tableName, CONNECTION.holdsMeasure, measureName);
  upstream.forEach((hop) => noteTable(hop.reference.table_name, CONNECTION.readByMeasure, referenceLabel(hop.reference)));
  downstream.forEach((hop) => {
    const type = canonicalType(hop.reference.object_type);
    noteTable(hop.reference.table_name, type === "measure" ? CONNECTION.holdsImpactedMeasures : CONNECTION.holdsImpactedCalculations, referenceLabel(hop.reference));
  });
  const tableRows: GridRow[] = [...tables.entries()].map(([name, table]) => ({
    id: `table-${name}`,
    [COLUMN.semanticTable]: name,
    [COLUMN.connectionToMeasure]: [...table.roles].join(", "),
    [COLUMN.objectsInvolved]: [...table.objects].join(", "),
    [COLUMN.databaseTables]: (sourcesByTable.get(name) ?? []).join(", ") || (parsedModel?.tables.some((candidate) => candidate.name === name) ? VALUE.notAvailable : VALUE.notFound),
    [COLUMN.semanticModel]: entry.semanticModelName,
    [COLUMN.workspaceName]: entry.workspaceName,
  }));

  const impactedMeasureRows: GridRow[] = downstream
    .filter((hop) => canonicalType(hop.reference.object_type) === "measure")
    .sort(byStepsThenName)
    .map((hop) => {
      const usage = usageOf(hop.reference);
      return {
        id: `impacted-${referenceKey(hop.reference)}`,
        [COLUMN.measureName]: hop.reference.object_name,
        [COLUMN.semanticTable]: hop.reference.table_name || VALUE.notAvailable,
        [COLUMN.daxExpression]: expressionFor(hop.reference.table_name, hop.reference.object_name, hop.reference.object_type),
        [COLUMN.dependency]: dependencyLabel(hop.depth),
        [COLUMN.stepsAway]: hop.depth,
        [COLUMN.referencedAs]: hop.referenceText,
        [COLUMN.reportCount]: usage?.reportIds.size ?? 0,
        [COLUMN.visualCount]: usage?.visualKeys.size ?? 0,
      };
    });

  const inputRows: GridRow[] = [...upstream]
    .sort(byStepsThenName)
    .map((hop) => {
      const type = canonicalType(hop.reference.object_type);
      const daxExpr = (type === "measure" || type === "calculated_column")
        ? expressionFor(hop.reference.table_name, hop.reference.object_name, hop.reference.object_type)
        : VALUE.notApplicable;
      return {
        id: `input-${referenceKey(hop.reference)}`,
        [COLUMN.objectName]: hop.reference.object_name,
        [COLUMN.semanticTable]: hop.reference.table_name || VALUE.notAvailable,
        [COLUMN.objectType]: displayType(hop.reference.object_type),
        [COLUMN.daxExpression]: daxExpr,
        [COLUMN.dependency]: dependencyLabel(hop.depth),
        [COLUMN.stepsAway]: hop.depth,
        [COLUMN.referencedAs]: hop.referenceText,
        [COLUMN.databaseTable]: type === "column" ? (sourcesByTable.get(hop.reference.table_name ?? "") ?? []).join(", ") || VALUE.notAvailable : VALUE.notApplicable,
      };
    });

  type Usage = { direct: boolean; objects: Set<string>; visuals: Set<string>; pages: Set<string> };
  const reports = new Map<string, Usage>();
  const visuals = new Map<string, { direct: boolean; objects: Set<string> }>();
  const collect = (reference: DaxReference, direct: boolean) => {
    usageOf(reference)?.visualKeys.forEach((key) => {
      const visual = evidence.visuals.get(key);
      if (!visual) return;
      const visualUse = visuals.get(key) ?? { direct: false, objects: new Set<string>() };
      visualUse.direct ||= direct;
      visualUse.objects.add(referenceLabel(reference));
      visuals.set(key, visualUse);
      const report = reports.get(visual.reportId) ?? { direct: false, objects: new Set<string>(), visuals: new Set<string>(), pages: new Set<string> };
      report.direct ||= direct;
      report.objects.add(referenceLabel(reference));
      report.visuals.add(key);
      report.pages.add(visual.pageName);
      reports.set(visual.reportId, report);
    });
  };
  collect(seed, true);
  downstream.forEach((hop) => collect(hop.reference, false));

  const reportRows: GridRow[] = [...reports.entries()]
    .map(([reportId, report]) => ({
      id: reportId,
      [COLUMN.reportName]: reportNames.get(reportId)?.name ?? reportId,
      [COLUMN.workspaceName]: reportNames.get(reportId)?.workspaceName ?? VALUE.notAvailable,
      [COLUMN.howItIsUsed]: howItIsUsed(report.direct),
      [COLUMN.pageCount]: report.pages.size,
      [COLUMN.visualCount]: report.visuals.size,
      [COLUMN.objectsUsed]: [...report.objects].join(", "),
      [COLUMN.reportId]: reportId,
    }))
    .sort((a, b) => String(a[COLUMN.reportName]).localeCompare(String(b[COLUMN.reportName])));

  const visualRows: GridRow[] = [...visuals.entries()]
    .map(([key, use]) => {
      const info = evidence.visuals.get(key);
      const reportId = info?.reportId ?? key.split(":")[0];
      return {
        id: key,
        [COLUMN.visualName]: info?.visualName ?? key,
        [COLUMN.visualType]: info?.visualType ?? VALUE.notAvailable,
        [COLUMN.pageName]: info?.pageName ?? VALUE.notAvailable,
        [COLUMN.reportName]: reportNames.get(reportId)?.name ?? reportId,
        [COLUMN.workspaceName]: reportNames.get(reportId)?.workspaceName ?? VALUE.notAvailable,
        [COLUMN.howItIsUsed]: howItIsUsed(use.direct),
        [COLUMN.objectsUsed]: [...use.objects].join(", "),
        [COLUMN.reportId]: reportId,
        [COLUMN.visualId]: key,
      };
    })
    .sort((a, b) => String(a[COLUMN.reportName]).localeCompare(String(b[COLUMN.reportName])) || String(a[COLUMN.pageName]).localeCompare(String(b[COLUMN.pageName])) || String(a[COLUMN.visualName]).localeCompare(String(b[COLUMN.visualName])));

  const modelRows: GridRow[] = [{
    id: modelKey(entry.workspaceId, entry.semanticModelId),
    [COLUMN.semanticModel]: entry.semanticModelName,
    [COLUMN.workspaceName]: entry.workspaceName,
    [COLUMN.measuresSemanticTable]: entry.tableName,
    [COLUMN.impactedMeasureCount]: impactedMeasureRows.length,
    [COLUMN.impactedCalculatedColumnCount]: downstream.filter((hop) => canonicalType(hop.reference.object_type) === "calculated_column").length,
    [COLUMN.reportsUsingCount]: reportRows.length,
    [COLUMN.visualsUsingCount]: visualRows.length,
    [COLUMN.connectedReportCount]: boundCount,
    [COLUMN.semanticModelId]: entry.semanticModelId,
    [COLUMN.workspaceId]: entry.workspaceId,
  }];

  return { tableRows, impactedMeasureRows, inputRows, modelRows, reportRows, visualRows };
}

function InventoryStatus({ selectedWorkspaceCount, isLoading, isError, entryCount, skippedCount, onRefresh }: { selectedWorkspaceCount: number; isLoading: boolean; isError: boolean; entryCount: number; skippedCount: number; onRefresh: () => void }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-subtle px-5 py-2.5 text-xs sm:px-6">
    <span className="text-muted-foreground">
      {!selectedWorkspaceCount
        ? "Select at least one workspace to build the measure inventory."
        : isLoading
          ? "Building measure inventory across the selected workspaces..."
          : isError
            ? "The measure inventory could not be loaded for your account."
            : `${entryCount} ${plural(entryCount, "measure", "measures")} indexed across ${selectedWorkspaceCount} ${plural(selectedWorkspaceCount, "workspace", "workspaces")}.${skippedCount ? ` ${skippedCount} semantic${plural(skippedCount, "model", "models")} skipped (no access).` : ""}`}
    </span>
    <Button type="button" variant="outline" size="sm" disabled={!selectedWorkspaceCount || isLoading} onClick={onRefresh}>{isLoading ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Refresh inventory</Button>
  </div>;
}

function ExactLineageStatus({ loading, error, dax }: { loading: boolean; error: boolean; dax: DaxAnalysis | undefined }) {
  if (loading) return <StatusBand tone="info" loading text="Finding calculation links in the background" />;
  if (error) return <StatusBand tone="warning" text="Calculation links could not be loaded for your account. Measure impact needs elevated backend access to find them." />;
  if (dax) return <StatusBand tone="success" text={`${dax.dependency_count} calculation ${plural(dax.dependency_count, "link", "links")} found`} />;
  return null;
}