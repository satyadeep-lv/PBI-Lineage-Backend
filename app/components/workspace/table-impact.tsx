import { useQueries, useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";
import { FileBarChart2, Layers3, Loader2, MonitorPlay, RefreshCw, Sigma, TableProperties } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { AskPowerAiButton } from "~/components/power-ai/ask-power-ai-button";
import { PowerBiAuthRequired } from "~/components/workspace/auth-required";
import { ImpactGrid } from "~/components/workspace/impact-grid";
import { buildImpactGraph, ImpactLineageDiagram, type ImpactGraphScope, type ReportName } from "~/components/workspace/impact-lineage";
import { MultiObjectSearch, type SearchGroup } from "~/components/workspace/impact-picker";
import { EmptyState, EvidenceStatus, ImpactSection, LoadingState, REPORT_LIST_FAILED_TEXT, StatusBand, SummaryTile } from "~/components/workspace/impact-ui";
import { canonicalType, computeDependencyClosure, referenceKey, referenceLabel, type DaxDependency, type DaxReference } from "~/lib/dependency-graph";
import { filePart, type GridRow } from "~/lib/grid-export";
import {
  buildEvidenceIndex,
  buildReportNames,
  evidenceKey,
  fetchImpactEvidence,
  impactEvidenceKey,
  tableSeeds,
  tableSources,
  type EstateWithReports,
  type EvidenceIndex,
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
  type ExplorerReportSelection,
  type InventoryEntry,
  type ParsedSemanticModel,
} from "~/lib/lineage-api";
import { COLUMN, dependencyLabel, gridColumn, nameWithParent, VALUE } from "~/lib/naming";
import { useAppStore } from "~/stores/app-store";
import { usePowerAiStore } from "~/stores/power-ai-store";

type Workspace = { id: string; name: string };
type WorkspaceResponse = { workspaces: Workspace[] };
type DaxAnalysis = { dependencies: DaxDependency[]; dependency_count: number };
/** A physical table behind one or more semantic tables, found through their `source_path`. */
type DatabaseTable = { key: string; name: string; semanticKeys: string[] };
type ModelRef = { key: string; workspaceId: string; workspaceName: string; semanticModelId: string; semanticModelName: string };
/** One semantic table to analyze, with every search selection that led to it (itself, or a database table behind it). */
type ImpactTarget = { entry: InventoryEntry; table: SourcedTable; model: ModelRef; selectedAs: string[]; sources: string[] };

const DATABASE_KEY_PREFIX = "db:";
/** Export file subject when more than one table is selected (Docs/07-column-naming-standard.md, "Export file names"). */
const MULTIPLE_TABLES_FILE_SUBJECT = "multiple-tables";

const plural = (count: number, one: string, many: string) => (count === 1 ? one : many);

/**
 * Pick semantic tables, or the database tables behind them, and see every
 * report, visual, semantic model, and measure that uses them.
 *
 * Built from the same calls the page always made — the workspace inventory,
 * each touched model's exact DAX analysis, estate bindings, and bound-report
 * visual evidence — per model, so a selection may span several models.
 */
export function TableImpact() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  const workspacesQuery = useQuery({
    queryKey: workspaceListKey(apiOrigin),
    queryFn: () => requestJson<WorkspaceResponse>(apiOrigin, WORKSPACE_LIST_PATH),
  });
  const workspaces = useMemo(() => workspacesQuery.data?.workspaces ?? [], [workspacesQuery.data]);
  const scopeIds = useMemo(() => workspaces.map((workspace) => workspace.id), [workspaces]);

  const inventoryQuery = useQuery({
    queryKey: estateInventoryKey(apiOrigin, scopeIds),
    queryFn: () => fetchEstateInventory(apiOrigin, workspaces),
    enabled: scopeIds.length > 0,
  });
  const inventory = inventoryQuery.data;
  const tables = useMemo(() => inventory?.tables ?? [], [inventory]);
  const tablesByKey = useMemo(() => new Map(tables.map((entry) => [entry.key, entry])), [tables]);
  const databaseTables = useMemo(() => (inventory ? buildDatabaseTables(tables, inventory.parsedByModel) : []), [inventory, tables]);
  const databaseByKey = useMemo(() => new Map(databaseTables.map((table) => [table.key, table])), [databaseTables]);
  const searchGroups = useMemo(() => buildSearchGroups(tables, databaseTables, tablesByKey, inventory?.parsedByModel), [tables, databaseTables, tablesByKey, inventory]);

  // A refreshed inventory can drop tables; keep only selections that still exist.
  useEffect(() => {
    if (!inventory) return;
    setSelectedKeys((keys) => {
      const kept = keys.filter((key) => tablesByKey.has(key) || databaseByKey.has(key));
      return kept.length === keys.length ? keys : kept;
    });
  }, [inventory, tablesByKey, databaseByKey]);

  const targets = useMemo(
    () => (inventory ? resolveTargets(selectedKeys, tablesByKey, databaseByKey, inventory.parsedByModel) : []),
    [inventory, selectedKeys, tablesByKey, databaseByKey],
  );
  const models = useMemo(() => uniqueModels(targets), [targets]);

  const daxQueries = useQueries({
    queries: models.map((model) => ({
      queryKey: daxAnalysisKey(apiOrigin, model.workspaceId, model.semanticModelId),
      queryFn: () => requestJson<DaxAnalysis>(apiOrigin, "/api/v1/lineage/dax/analyze", { method: "POST", body: JSON.stringify(inventory?.parsedByModel.get(model.key)) }),
    })),
  });

  const estateQuery = useQuery({
    queryKey: estateDiscoveryKey(apiOrigin),
    queryFn: () => requestJson<EstateWithReports>(apiOrigin, ESTATE_DISCOVER_PATH),
    enabled: models.length > 0,
  });
  const boundByModel = useMemo(
    () => new Map(models.map((model) => [model.key, boundReportsForModel(estateQuery.data, model.semanticModelId)] as const)),
    [models, estateQuery.data],
  );
  const evidenceQueries = useQueries({
    queries: models.map((model) => {
      const bound = boundByModel.get(model.key) ?? [];
      return {
        queryKey: impactEvidenceKey("table-impact", apiOrigin, model.semanticModelId, bound),
        queryFn: () => fetchImpactEvidence(apiOrigin, bound),
        enabled: bound.length > 0,
      };
    }),
  });

  // useQueries returns a new array every render; its per-query data stamps say when anything actually changed.
  const daxStamp = daxQueries.map((query) => query.dataUpdatedAt).join(",");
  const evidenceStamp = evidenceQueries.map((query) => query.dataUpdatedAt).join(",");
  const daxByModel = useMemo(() => new Map(models.map((model, index) => [model.key, daxQueries[index]?.data?.dependencies] as const)), [models, daxStamp]);
  const evidenceByModel = useMemo(() => new Map(models.map((model, index) => [model.key, buildEvidenceIndex(evidenceQueries[index]?.data)] as const)), [models, evidenceStamp]);
  const reportNames = useMemo(() => buildReportNames(estateQuery.data, [...evidenceByModel.values()]), [estateQuery.data, evidenceByModel]);
  const analysis = useMemo(
    () => analyzeImpact(targets, models, daxByModel, evidenceByModel, boundByModel, reportNames),
    [targets, models, daxByModel, evidenceByModel, boundByModel, reportNames],
  );
  const impactGraph = useMemo(
    () => buildImpactGraph(graphScopes(targets, models, daxByModel, evidenceByModel, inventory?.parsedByModel), reportNames),
    [targets, models, daxByModel, evidenceByModel, inventory, reportNames],
  );

  const singleTarget = targets.length === 1 ? targets[0] : null;
  const selectedLabels = [...new Set(targets.flatMap((target) => target.selectedAs))];
  const exportContext = { [COLUMN.selectedTables]: selectedLabels.join("; ") };
  // Files are named after the one table picked in the search (semantic or database), or "multiple-tables".
  const pickedNames = selectedKeys.flatMap((key) => {
    const name = tablesByKey.get(key)?.tableName ?? databaseByKey.get(key)?.name;
    return name ? [name] : [];
  });
  const filePrefix = `table-impact-${pickedNames.length === 1 ? filePart(pickedNames[0]) : MULTIPLE_TABLES_FILE_SUBJECT}`;

  useEffect(() => {
    const entry = singleTarget?.entry;
    usePowerAiStore.getState().mergeContext({
      workspaceId: entry?.workspaceId,
      workspaceName: entry?.workspaceName,
      semanticModelId: entry?.semanticModelId,
      semanticModelName: entry?.semanticModelName,
      // An inventory entry is indexed under the workspace its model lives in.
      semanticModelWorkspaceId: entry?.workspaceId,
      reportId: undefined,
      reportName: undefined,
      objectType: entry ? "table" : undefined,
      objectId: entry?.key,
      objectName: entry?.tableName,
    });
  }, [singleTarget]);

  if (workspacesQuery.isLoading) return <LoadingState label="Loading Power BI workspaces" />;
  if (workspacesQuery.isError) return <PowerBiAuthRequired returnTo="Table impact" />;
  if (!workspaces.length) return <EmptyState title="No Power BI workspaces found" text="The authenticated account did not return any workspaces to explore." />;

  const daxLoading = daxQueries.some((query) => query.isLoading);
  const daxFailedModels = models.filter((_, index) => daxQueries[index]?.isError);
  const dependencyCount = daxQueries.reduce((count, query) => count + (query.data?.dependency_count ?? 0), 0);
  const boundTotal = [...boundByModel.values()].reduce((count, reports) => count + reports.length, 0);
  const evidenceLoading = evidenceQueries.some((query) => query.isLoading);
  const evidenceTruncated = evidenceQueries.some((query) => query.data?.truncated);
  const usagePending = evidenceLoading || estateQuery.isLoading;
  const usageEmpty = estateQuery.isError ? REPORT_LIST_FAILED_TEXT : usagePending || daxLoading ? "Checking reports..." : undefined;

  return <section className="overflow-hidden rounded-lg border border-border bg-surface">
    <div className="border-b border-border px-5 py-5 sm:px-6">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><TableProperties className="size-5" /></span>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-semibold uppercase text-fabric">Power BI</span><Badge className="rounded-md border border-fabric/25 bg-accent text-accent-foreground">Table impact</Badge></div>
          <h1 className="text-lg font-semibold">Table impact</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">Search semantic tables or the database tables behind them, pick one or several, and see every report, visual, semantic model, and measure that uses them.</p>
        </div>
      </div>
    </div>

    <InventoryStatus workspaceCount={scopeIds.length} isLoading={inventoryQuery.isFetching} isError={inventoryQuery.isError} tableCount={tables.length} databaseCount={databaseTables.length} skippedCount={inventory?.skipped.length ?? 0} onRefresh={() => void inventoryQuery.refetch()} />

    <div className="border-b border-border bg-subtle px-5 py-4 sm:px-6">
      <div className="max-w-5xl">
        <MultiObjectSearch
          id="table-impact-tables"
          label="Tables"
          placeholder="Search semantic tables or database tables..."
          groups={searchGroups}
          selectedKeys={selectedKeys}
          onChange={setSelectedKeys}
          emptyText={inventoryQuery.isFetching ? "Building the table inventory..." : "No tables are indexed yet."}
        />
      </div>
    </div>

    <div className="space-y-6 p-5 sm:p-6">
      {!targets.length && <EmptyState title="No tables selected" text="Search above and pick one or more semantic tables or database tables to see the reports, visuals, semantic models, and measures that use them." />}
      {targets.length > 0 && <>
        <div className="space-y-2">
          <ExactLineageStatus loading={daxLoading} failedModels={daxFailedModels} dependencyCount={dependencyCount} modelCount={models.length} />
          <EvidenceStatus estateLoading={estateQuery.isLoading} estateError={estateQuery.isError} boundCount={boundTotal} loading={evidenceLoading} truncated={evidenceTruncated} noBoundText="No report you can open is connected to the semantic models holding these tables." />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryTile icon={FileBarChart2} label="Reports" value={analysis.reportRows.length} caption="With a visual that uses the tables" pending={usagePending} />
          <SummaryTile icon={MonitorPlay} label="Visuals" value={analysis.visualRows.length} caption="Reading the tables or their measures" pending={usagePending} />
          <SummaryTile icon={Layers3} label="Semantic models" value={analysis.modelRows.length} caption={`${targets.length} semantic ${plural(targets.length, "table", "tables")} selected`} pending={false} />
          <SummaryTile icon={Sigma} label="Impacted measures" value={analysis.measureRows.length} caption="Depending on them, directly or indirectly" pending={daxLoading} />
        </div>

        {singleTarget && <div className="flex justify-end">
          <AskPowerAiButton
            context={{
              workspaceId: singleTarget.entry.workspaceId,
              workspaceName: singleTarget.entry.workspaceName,
              semanticModelId: singleTarget.entry.semanticModelId,
              semanticModelName: singleTarget.entry.semanticModelName,
              semanticModelWorkspaceId: singleTarget.entry.workspaceId,
              objectType: "table",
              objectId: singleTarget.entry.key,
              objectName: singleTarget.entry.tableName,
            }}
            question={`Explain the ${singleTarget.entry.tableName} table`}
          />
        </div>}

        <ImpactLineageDiagram
          graph={impactGraph.graph}
          focusNodeId={singleTarget ? `${singleTarget.model.key}|table|${singleTarget.entry.tableName.toLocaleLowerCase()}` : undefined}
          title={singleTarget ? `${singleTarget.entry.tableName} impact` : `Impact of ${targets.length} semantic tables`}
          description="Database tables and semantic models feed the selected tables; their columns and measures flow down through dependent measures to the reports and visuals that use them."
          emptyText="Nothing depends on the selected tables."
          hiddenReports={impactGraph.hiddenReports}
          hiddenVisuals={impactGraph.hiddenVisuals}
        />

        <ImpactSection icon={FileBarChart2} title="Reports using the selected tables" text="Reports with at least one visual that uses a selected table directly, or uses a measure built on it.">
          <ImpactGrid rowData={analysis.reportRows} columnDefs={reportColumnDefs} emptyMessage={usageEmpty ?? "No report visual uses the selected tables."} exportFileName={`${filePrefix}-reports`} exportContext={exportContext} fitRows />
        </ImpactSection>

        <ImpactSection icon={MonitorPlay} title="Visuals using the selected tables" text="Every visual that uses a selected table's columns or measures, or a measure depending on them, with the page it sits on.">
          <ImpactGrid rowData={analysis.visualRows} columnDefs={visualColumnDefs} emptyMessage={usageEmpty ?? "No visual uses the selected tables."} exportFileName={`${filePrefix}-visuals`} exportContext={exportContext} fitRows />
        </ImpactSection>

        <ImpactSection icon={Layers3} title="Semantic models" text="Every semantic model holding a selected table, with the database tables behind it and how much depends on it.">
          <ImpactGrid rowData={analysis.modelRows} columnDefs={modelColumnDefs} emptyMessage="No semantic models hold the selected tables." exportFileName={`${filePrefix}-semantic-models`} exportContext={exportContext} fitRows />
        </ImpactSection>

        <ImpactSection icon={Sigma} title="Measures using the selected tables" text="Measures that read a selected table, directly or through another calculation, with the reports and visuals that show them.">
          <ImpactGrid rowData={analysis.measureRows} columnDefs={measureColumnDefs} emptyMessage={daxLoading ? "Finding calculation links..." : "No measure depends on the selected tables."} exportFileName={`${filePrefix}-measures`} exportContext={exportContext} fitRows />
        </ImpactSection>
      </>}
    </div>
  </section>;
}

// Row keys are the standard headers (Docs/07-column-naming-standard.md), so screen and export always agree;
// hidden columns are export-only IDs, written last.
const reportColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.reportName, { minWidth: 200, flex: 1.2 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.semanticModel, { minWidth: 170 }),
  gridColumn(COLUMN.selectedTables, { minWidth: 190 }),
  gridColumn(COLUMN.howItIsUsed, { minWidth: 170 }),
  gridColumn(COLUMN.pageCount, { minWidth: 160 }),
  gridColumn(COLUMN.visualCount, { minWidth: 170 }),
  gridColumn(COLUMN.objectsUsed, { minWidth: 240, flex: 1 }),
  gridColumn(COLUMN.reportId, { hide: true }),
  gridColumn(COLUMN.semanticModelId, { hide: true }),
];

const visualColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.visualName, { minWidth: 190, flex: 1 }),
  gridColumn(COLUMN.visualType, { minWidth: 140 }),
  gridColumn(COLUMN.pageName, { minWidth: 150 }),
  gridColumn(COLUMN.reportName, { minWidth: 180 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.howItIsUsed, { minWidth: 170 }),
  gridColumn(COLUMN.objectsUsed, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.selectedTables, { minWidth: 190 }),
  gridColumn(COLUMN.reportId, { hide: true }),
  gridColumn(COLUMN.visualId, { hide: true }),
];

const modelColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.semanticModel, { minWidth: 190, flex: 1 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.selectedTables, { minWidth: 180 }),
  gridColumn(COLUMN.databaseTables, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.impactedMeasureCount, { minWidth: 250 }),
  gridColumn(COLUMN.reportsUsingCount, { minWidth: 240 }),
  gridColumn(COLUMN.connectedReportCount, { minWidth: 250 }),
  gridColumn(COLUMN.semanticModelId, { hide: true }),
  gridColumn(COLUMN.workspaceId, { hide: true }),
];

const measureColumnDefs: ColDef<GridRow>[] = [
  gridColumn(COLUMN.measureName, { minWidth: 200, flex: 1 }),
  gridColumn(COLUMN.semanticTable, { minWidth: 160 }),
  gridColumn(COLUMN.semanticModel, { minWidth: 170 }),
  gridColumn(COLUMN.workspaceName, { minWidth: 160 }),
  gridColumn(COLUMN.selectedTables, { minWidth: 190 }),
  gridColumn(COLUMN.dependency, { minWidth: 130 }),
  gridColumn(COLUMN.stepsAway, { minWidth: 120 }),
  gridColumn(COLUMN.referencedAs, { minWidth: 220, flex: 1 }),
  gridColumn(COLUMN.reportCount, { minWidth: 170 }),
  gridColumn(COLUMN.visualCount, { minWidth: 170 }),
  gridColumn(COLUMN.semanticModelId, { hide: true }),
];

function findParsedTable(parsedByModel: Map<string, ParsedSemanticModel>, entry: InventoryEntry) {
  return (parsedByModel.get(modelKey(entry.workspaceId, entry.semanticModelId))?.tables.find((table) => table.name === entry.tableName) ?? null) as SourcedTable | null;
}

/** "Sales (Finance Model)": the chip and "Selected tables" text for a semantic table. */
function semanticLabel(entry: InventoryEntry) {
  return nameWithParent(entry.tableName, entry.semanticModelName);
}

function buildDatabaseTables(tables: InventoryEntry[], parsedByModel: Map<string, ParsedSemanticModel>): DatabaseTable[] {
  const byKey = new Map<string, DatabaseTable>();
  tables.forEach((entry) => {
    tableSources(findParsedTable(parsedByModel, entry)).forEach((path) => {
      const key = `${DATABASE_KEY_PREFIX}${path.toLocaleUpperCase()}`;
      const table = byKey.get(key) ?? { key, name: path, semanticKeys: [] };
      if (!table.semanticKeys.includes(entry.key)) table.semanticKeys.push(entry.key);
      byKey.set(key, table);
    });
  });
  return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function buildSearchGroups(tables: InventoryEntry[], databaseTables: DatabaseTable[], tablesByKey: Map<string, InventoryEntry>, parsedByModel: Map<string, ParsedSemanticModel> | undefined): SearchGroup[] {
  return [
    {
      id: "semantic",
      heading: "Semantic tables",
      chipLabel: "Semantic",
      entries: [...tables].sort((a, b) => a.tableName.localeCompare(b.tableName)).map((entry) => {
        const sources = parsedByModel ? tableSources(findParsedTable(parsedByModel, entry)) : [];
        return {
          key: entry.key,
          searchValue: `${entry.tableName} ${entry.semanticModelName} ${entry.workspaceName} ${sources.join(" ")}`,
          primary: entry.tableName,
          secondary: `${entry.semanticModelName} · ${entry.workspaceName}${sources.length ? ` · from ${sources.join(", ")}` : ""}`,
          chipText: semanticLabel(entry),
        };
      }),
    },
    {
      id: "database",
      heading: "Database tables",
      chipLabel: "Database",
      entries: databaseTables.map((table) => {
        const users = table.semanticKeys.flatMap((key) => {
          const entry = tablesByKey.get(key);
          return entry ? [semanticLabel(entry)] : [];
        });
        return {
          key: table.key,
          searchValue: `${table.name} ${users.join(" ")}`,
          primary: table.name,
          secondary: `Behind ${users.length} semantic ${plural(users.length, "table", "tables")}: ${users.join(", ")}`,
        };
      }),
    },
  ];
}

function resolveTargets(selectedKeys: string[], tablesByKey: Map<string, InventoryEntry>, databaseByKey: Map<string, DatabaseTable>, parsedByModel: Map<string, ParsedSemanticModel>): ImpactTarget[] {
  const targets = new Map<string, ImpactTarget>();
  function add(entry: InventoryEntry | undefined, selectedAs: string) {
    if (!entry) return;
    const table = findParsedTable(parsedByModel, entry);
    if (!table) return;
    const target = targets.get(entry.key) ?? {
      entry,
      table,
      model: { key: modelKey(entry.workspaceId, entry.semanticModelId), workspaceId: entry.workspaceId, workspaceName: entry.workspaceName, semanticModelId: entry.semanticModelId, semanticModelName: entry.semanticModelName },
      selectedAs: [],
      sources: tableSources(table),
    };
    if (!target.selectedAs.includes(selectedAs)) target.selectedAs.push(selectedAs);
    targets.set(entry.key, target);
  }
  selectedKeys.forEach((key) => {
    const databaseTable = databaseByKey.get(key);
    if (databaseTable) databaseTable.semanticKeys.forEach((semanticKey) => add(tablesByKey.get(semanticKey), databaseTable.name));
    else {
      const entry = tablesByKey.get(key);
      if (entry) add(entry, semanticLabel(entry));
    }
  });
  return [...targets.values()];
}

function uniqueModels(targets: ImpactTarget[]): ModelRef[] {
  return [...new Map(targets.map((target) => [target.model.key, target.model])).values()];
}

function graphScopes(
  targets: ImpactTarget[],
  models: ModelRef[],
  daxByModel: Map<string, DaxDependency[] | undefined>,
  evidenceByModel: Map<string, EvidenceIndex>,
  parsedByModel: Map<string, ParsedSemanticModel> | undefined,
): ImpactGraphScope[] {
  return models.map((model) => {
    const dependencies = daxByModel.get(model.key) ?? [];
    const modelTargets = targets.filter((target) => target.model.key === model.key);
    const focal = modelTargets.flatMap((target) => tableSeeds(target.table));
    const members = computeDependencyClosure(dependencies, focal).downstream.map((hop) => hop.reference);
    const sources = new Map((parsedByModel?.get(model.key)?.tables ?? []).map((table) => [table.name, tableSources(table as SourcedTable)] as const));
    return {
      model: { key: model.key, name: model.semanticModelName, workspaceName: model.workspaceName },
      focal,
      members,
      dependencies,
      evidence: evidenceByModel.get(model.key),
      tableSources: sources,
      focalTables: modelTargets.map((target) => target.entry.tableName),
    };
  });
}

type MeasureAccumulator = { model: ModelRef; reference: DaxReference; depth: number; referenceText: string; selectedAs: Set<string>; reportIds: Set<string>; visualKeys: Set<string> };
type ReportAccumulator = { reportId: string; model: ModelRef; direct: boolean; objects: Set<string>; visuals: Set<string>; pages: Set<string>; selectedAs: Set<string> };
type VisualAccumulator = { key: string; reportId: string; model: ModelRef; direct: boolean; objects: Set<string>; selectedAs: Set<string> };

const howItIsUsed = (direct: boolean) => (direct ? VALUE.usesDirectly : VALUE.throughMeasure);

/**
 * Walks each target's downstream DAX closure inside its own model (reference
 * keys are only unique within one model), then joins the closure to that
 * model's visual evidence: a report or visual uses a table when a visual reads
 * one of its columns or measures, or a measure depending on them.
 */
function analyzeImpact(
  targets: ImpactTarget[],
  models: ModelRef[],
  daxByModel: Map<string, DaxDependency[] | undefined>,
  evidenceByModel: Map<string, EvidenceIndex>,
  boundByModel: Map<string, ExplorerReportSelection[]>,
  reportNames: Map<string, ReportName>,
) {
  const measures = new Map<string, MeasureAccumulator>();
  const reports = new Map<string, ReportAccumulator>();
  const visuals = new Map<string, VisualAccumulator>();

  targets.forEach((target) => {
    const dependencies = daxByModel.get(target.model.key) ?? [];
    const evidence = evidenceByModel.get(target.model.key);
    const seeds = tableSeeds(target.table);
    const downstream = computeDependencyClosure(dependencies, seeds).downstream;
    const usageOf = (reference: DaxReference) => evidence?.byObject.get(evidenceKey(reference.table_name, reference.object_name));

    downstream.forEach((hop) => {
      if (canonicalType(hop.reference.object_type) !== "measure") return;
      const key = `${target.model.key}|${referenceKey(hop.reference)}`;
      const usage = usageOf(hop.reference);
      const measure = measures.get(key) ?? { model: target.model, reference: hop.reference, depth: hop.depth, referenceText: hop.referenceText, selectedAs: new Set<string>(), reportIds: new Set(usage?.reportIds), visualKeys: new Set(usage?.visualKeys) };
      if (hop.depth < measure.depth) Object.assign(measure, { depth: hop.depth, referenceText: hop.referenceText });
      target.selectedAs.forEach((label) => measure.selectedAs.add(label));
      measures.set(key, measure);
    });

    function collect(reference: DaxReference, direct: boolean) {
      const usage = usageOf(reference);
      if (!usage) return;
      usage.visualKeys.forEach((key) => {
        const visual = evidence?.visuals.get(key);
        if (!visual) return;
        const entry = visuals.get(key) ?? { key, reportId: visual.reportId, model: target.model, direct: false, objects: new Set<string>(), selectedAs: new Set<string>() };
        entry.direct ||= direct;
        entry.objects.add(referenceLabel(reference));
        target.selectedAs.forEach((label) => entry.selectedAs.add(label));
        visuals.set(key, entry);

        const report = reports.get(visual.reportId) ?? { reportId: visual.reportId, model: target.model, direct: false, objects: new Set<string>(), visuals: new Set<string>(), pages: new Set<string>(), selectedAs: new Set<string>() };
        report.direct ||= direct;
        report.objects.add(referenceLabel(reference));
        report.visuals.add(key);
        report.pages.add(visual.pageName);
        target.selectedAs.forEach((label) => report.selectedAs.add(label));
        reports.set(visual.reportId, report);
      });
    }
    seeds.forEach((seed) => collect(seed, true));
    downstream.forEach((hop) => collect(hop.reference, false));
  });

  const reportRows: GridRow[] = [...reports.values()]
    .map((report) => ({
      id: report.reportId,
      [COLUMN.reportName]: reportNames.get(report.reportId)?.name ?? report.reportId,
      [COLUMN.workspaceName]: reportNames.get(report.reportId)?.workspaceName ?? VALUE.notAvailable,
      [COLUMN.semanticModel]: report.model.semanticModelName,
      [COLUMN.selectedTables]: [...report.selectedAs].join(", "),
      [COLUMN.howItIsUsed]: howItIsUsed(report.direct),
      [COLUMN.pageCount]: report.pages.size,
      [COLUMN.visualCount]: report.visuals.size,
      [COLUMN.objectsUsed]: [...report.objects].join(", "),
      [COLUMN.reportId]: report.reportId,
      [COLUMN.semanticModelId]: report.model.semanticModelId,
    }))
    .sort((a, b) => String(a[COLUMN.reportName]).localeCompare(String(b[COLUMN.reportName])));

  const visualRows: GridRow[] = [...visuals.values()]
    .map((visual) => {
      const info = evidenceByModel.get(visual.model.key)?.visuals.get(visual.key);
      return {
        id: visual.key,
        [COLUMN.visualName]: info?.visualName ?? visual.key,
        [COLUMN.visualType]: info?.visualType ?? VALUE.notAvailable,
        [COLUMN.pageName]: info?.pageName ?? VALUE.notAvailable,
        [COLUMN.reportName]: reportNames.get(visual.reportId)?.name ?? visual.reportId,
        [COLUMN.workspaceName]: reportNames.get(visual.reportId)?.workspaceName ?? VALUE.notAvailable,
        [COLUMN.howItIsUsed]: howItIsUsed(visual.direct),
        [COLUMN.objectsUsed]: [...visual.objects].join(", "),
        [COLUMN.selectedTables]: [...visual.selectedAs].join(", "),
        [COLUMN.reportId]: visual.reportId,
        [COLUMN.visualId]: visual.key,
      };
    })
    .sort((a, b) => String(a[COLUMN.reportName]).localeCompare(String(b[COLUMN.reportName])) || String(a[COLUMN.pageName]).localeCompare(String(b[COLUMN.pageName])) || String(a[COLUMN.visualName]).localeCompare(String(b[COLUMN.visualName])));

  // Same order as before the split into Measure name + Semantic table: steps away, then Table[Measure].
  const measureRows: GridRow[] = [...measures.entries()]
    .sort(([, a], [, b]) => a.depth - b.depth || referenceLabel(a.reference).localeCompare(referenceLabel(b.reference)))
    .map(([key, measure]) => ({
      id: key,
      [COLUMN.measureName]: measure.reference.object_name,
      [COLUMN.semanticTable]: measure.reference.table_name || VALUE.notAvailable,
      [COLUMN.semanticModel]: measure.model.semanticModelName,
      [COLUMN.workspaceName]: measure.model.workspaceName,
      [COLUMN.selectedTables]: [...measure.selectedAs].join(", "),
      [COLUMN.dependency]: dependencyLabel(measure.depth),
      [COLUMN.stepsAway]: measure.depth,
      [COLUMN.referencedAs]: measure.referenceText,
      [COLUMN.reportCount]: measure.reportIds.size,
      [COLUMN.visualCount]: measure.visualKeys.size,
      [COLUMN.semanticModelId]: measure.model.semanticModelId,
    }));

  const modelRows: GridRow[] = models.map((model) => {
    const modelTargets = targets.filter((target) => target.model.key === model.key);
    return {
      id: model.key,
      [COLUMN.semanticModel]: model.semanticModelName,
      [COLUMN.workspaceName]: model.workspaceName,
      [COLUMN.selectedTables]: modelTargets.map((target) => target.entry.tableName).join(", "),
      [COLUMN.databaseTables]: [...new Set(modelTargets.flatMap((target) => target.sources))].join(", ") || VALUE.notAvailable,
      [COLUMN.impactedMeasureCount]: measureRows.filter((row) => row[COLUMN.semanticModelId] === model.semanticModelId).length,
      [COLUMN.reportsUsingCount]: reportRows.filter((row) => row[COLUMN.semanticModelId] === model.semanticModelId).length,
      [COLUMN.connectedReportCount]: boundByModel.get(model.key)?.length ?? 0,
      [COLUMN.semanticModelId]: model.semanticModelId,
      [COLUMN.workspaceId]: model.workspaceId,
    };
  });

  return { reportRows, visualRows, measureRows, modelRows };
}

function InventoryStatus({ workspaceCount, isLoading, isError, tableCount, databaseCount, skippedCount, onRefresh }: { workspaceCount: number; isLoading: boolean; isError: boolean; tableCount: number; databaseCount: number; skippedCount: number; onRefresh: () => void }) {
  const workspacesText = `${workspaceCount} ${plural(workspaceCount, "workspace", "workspaces")}`;
  return <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-subtle px-5 py-2.5 text-xs sm:px-6">
    <span className="text-muted-foreground">
      {isLoading
        ? `Building the table inventory across ${workspacesText}...`
        : isError
          ? "The table inventory could not be loaded for your account."
          : `${tableCount} semantic ${plural(tableCount, "table", "tables")} and ${databaseCount} database ${plural(databaseCount, "table", "tables")} indexed across ${workspacesText}.${skippedCount ? ` ${skippedCount} semantic ${plural(skippedCount, "model", "models")} skipped (no access).` : ""}`}
    </span>
    <Button type="button" variant="outline" size="sm" disabled={!workspaceCount || isLoading} onClick={onRefresh}>{isLoading ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Refresh inventory</Button>
  </div>;
}

function ExactLineageStatus({ loading, failedModels, dependencyCount, modelCount }: { loading: boolean; failedModels: ModelRef[]; dependencyCount: number; modelCount: number }) {
  if (loading) return <StatusBand tone="info" loading text="Finding calculation links in the background" />;
  if (failedModels.length) return <StatusBand tone="warning" text={`Calculation links could not be loaded for ${failedModels.map((model) => model.semanticModelName).join(", ")}. Table impact needs elevated backend access to find them.`} />;
  return <StatusBand tone="success" text={`${dependencyCount} calculation ${plural(dependencyCount, "link", "links")} found in ${modelCount} semantic ${plural(modelCount, "model", "models")}`} />;
}
