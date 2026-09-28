import { useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";
import { Loader2, Radar } from "lucide-react";
import { useState } from "react";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Checkbox } from "~/components/ui/checkbox";
import { PowerBiAuthRequired } from "~/components/workspace/auth-required";
import { ImpactGrid } from "~/components/workspace/impact-grid";
import { WorkspaceScopeSelect } from "~/components/workspace/impact-picker";
import type { GridRow } from "~/lib/grid-export";
import { requestJson, WORKSPACE_LIST_PATH, workspaceListKey } from "~/lib/lineage-api";
import {
  type ScanFlags,
  type ScannerDatasourceInstance,
  type ScannerWorkspace,
} from "~/lib/scanner-api";
import { useWorkspaceScan } from "~/lib/use-workspace-scan";
import { sectionTabClass } from "~/lib/interaction-styles";
import { cn } from "~/lib/utils";
import { useAppStore } from "~/stores/app-store";

type Workspace = { id: string; name: string };
type WorkspaceResponse = { workspaces: Workspace[] };

type ScannerTab =
  | "workspaces"
  | "reports-dashboards"
  | "semantic-models"
  | "dependencies"
  | "datasource-instances";

const SCANNER_TABS: Array<{ id: ScannerTab; label: string }> = [
  { id: "workspaces", label: "Workspaces" },
  { id: "reports-dashboards", label: "Reports & dashboards" },
  { id: "semantic-models", label: "Semantic models" },
  { id: "dependencies", label: "Dependencies" },
  { id: "datasource-instances", label: "Datasource instances" },
];

const WORKSPACE_SCAN_LIMIT = 100;

export function Scanner() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<ScannerTab>("workspaces");
  const [flags, setFlags] = useState<Required<Omit<ScanFlags, "get_artifact_users">>>({
    lineage: true,
    datasource_details: true,
    dataset_schema: true,
    dataset_expressions: true,
  });

  const workspacesQuery = useQuery({
    queryKey: workspaceListKey(apiOrigin),
    queryFn: () => requestJson<WorkspaceResponse>(apiOrigin, WORKSPACE_LIST_PATH),
  });
  const workspaces = workspacesQuery.data?.workspaces ?? [];

  const scan = useWorkspaceScan(apiOrigin, selectedWorkspaceIds, flags);
  const overLimit = selectedWorkspaceIds.length > WORKSPACE_SCAN_LIMIT;
  const isRunning = Boolean(scan.scanId) && scan.status !== "Succeeded" && scan.status !== "Failed";
  const canRun = selectedWorkspaceIds.length > 0 && !overLimit && !scan.isSubmitting && !isRunning;

  const result = scan.resultQuery.data;
  const scannedWorkspaces = result?.payload.workspaces ?? [];
  const datasourceInstances = result?.payload.datasourceInstances ?? [];
  const misconfiguredInstances = result?.payload.misconfiguredDatasourceInstances ?? [];

  if (workspacesQuery.isLoading) return <LoadingState label="Loading Power BI workspaces" />;
  if (workspacesQuery.isError) return <PowerBiAuthRequired returnTo="Scanner" />;
  if (!workspaces.length) return <EmptyState title="No Power BI workspaces found" text="The authenticated account did not return any workspaces to explore." />;

  return <section className="overflow-hidden rounded-lg border border-border bg-surface">
    <div className="border-b border-border px-5 py-5 sm:px-6">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><Radar className="size-5" /></span>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-semibold uppercase text-fabric">Power BI</span><Badge className="rounded-md border border-fabric/25 bg-accent text-accent-foreground">Scanner</Badge></div>
          <h1 className="text-lg font-semibold">Scanner</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">Run the Power BI Admin metadata scanner across one or more workspaces, then browse every data point it returns — workspaces, reports, dashboards, semantic models, dependencies, and datasource instances. Subject to the tenant's hourly scan limits — select only the workspaces you need.</p>
        </div>
      </div>
    </div>

    <div className="space-y-4 border-b border-border bg-subtle px-5 py-4 sm:px-6">
      <div className="grid gap-4 md:grid-cols-2">
        <WorkspaceScopeSelect id="scanner-scope" label="Workspaces to scan" workspaces={workspaces} selectedIds={selectedWorkspaceIds} onChange={setSelectedWorkspaceIds} />
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-zinc-600">Scan options</p>
          <div className="flex flex-wrap gap-4 pt-1.5">
            <FlagToggle label="Lineage" checked={flags.lineage} onChange={(value) => setFlags((previous) => ({ ...previous, lineage: value }))} />
            <FlagToggle label="Datasource details" checked={flags.datasource_details} onChange={(value) => setFlags((previous) => ({ ...previous, datasource_details: value }))} />
            <FlagToggle label="Dataset schema" checked={flags.dataset_schema} onChange={(value) => setFlags((previous) => ({ ...previous, dataset_schema: value }))} />
            <FlagToggle label="Dataset expressions" checked={flags.dataset_expressions} onChange={(value) => setFlags((previous) => ({ ...previous, dataset_expressions: value }))} />
          </div>
        </div>
      </div>
      {overLimit && <StatusBand tone="warning" text={`${selectedWorkspaceIds.length} workspaces selected. The scanner accepts at most ${WORKSPACE_SCAN_LIMIT} per scan — narrow the selection to run it.`} />}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" disabled={!canRun} onClick={scan.runScan}>
          {isRunning || scan.isSubmitting ? <Loader2 className="size-3.5 animate-spin" /> : <Radar className="size-3.5" />} {scan.scanId ? "Run scan again" : "Run scan"}
        </Button>
        {scan.scanId && <span className="text-xs text-zinc-500">Scan ID: <code className="text-zinc-700">{scan.scanId}</code></span>}
      </div>
    </div>

    <div className="space-y-6 p-5 sm:p-6">
      {!scan.scanId && <EmptyState title="No scan run yet" text="Select workspaces above and run a scan to browse every data point it returns." />}
      {isRunning && <div className="flex items-center gap-2 border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900"><Loader2 className="size-3.5 animate-spin" />Scanning ({scan.status ?? "starting"})...</div>}
      {scan.status === "Failed" && <StatusBand tone="warning" text={scan.statusError?.message ?? "The metadata scan failed."} />}
      {scan.submitError && <StatusBand tone="warning" text="The scan could not be started. Confirm the scanner API is reachable for this session." />}

      {result && <>
        <div className="grid grid-cols-3 gap-4 border-y border-zinc-200 py-4 sm:grid-cols-4 lg:grid-cols-8">
          <SummaryStat label="Workspaces" value={result.summary.workspace_count} />
          <SummaryStat label="Reports" value={result.summary.report_count} />
          <SummaryStat label="Dashboards" value={result.summary.dashboard_count} />
          <SummaryStat label="Semantic models" value={result.summary.semantic_model_count} />
          <SummaryStat label="Dataflows" value={result.summary.dataflow_count} />
          <SummaryStat label="Datamarts" value={result.summary.datamart_count} />
          <SummaryStat label="Tables" value={result.summary.table_count} />
          <SummaryStat label="Columns" value={result.summary.column_count} />
          <SummaryStat label="Measures" value={result.summary.measure_count} />
          <SummaryStat label="Relationships" value={result.summary.relationship_count} />
          <SummaryStat label="Roles" value={result.summary.role_count} />
          <SummaryStat label="Dataset expressions" value={result.summary.dataset_expression_count} />
          <SummaryStat label="Table sources" value={result.summary.table_source_expression_count} />
          <SummaryStat label="Datasource instances" value={result.summary.datasource_instance_count} />
          <SummaryStat label="Misconfigured sources" value={result.summary.misconfigured_datasource_instance_count} warnOnValue />
        </div>

        <div className="overflow-x-auto border-b border-border bg-subtle">
          <div className="flex min-w-max" role="tablist" aria-label="Scanner data categories">
            {SCANNER_TABS.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} onClick={() => setActiveTab(tab.id)} className={sectionTabClass(activeTab === tab.id, "px-4 py-3 text-left")}>{tab.label}</button>)}
          </div>
        </div>

        {activeTab === "workspaces" && <div className="space-y-8">
          <GridSection title="Workspaces" description="Every workspace included in this scan.">
            <ImpactGrid rowData={workspaceRows(scannedWorkspaces)} columnDefs={workspaceColumnDefs} emptyMessage="No workspaces were returned." exportFileName="scanner-workspaces" exportContext={{}} />
          </GridSection>
          <GridSection title="Tags" description="Tag IDs applied across every scanned item. The scanner returns tag IDs only, never display names.">
            <ImpactGrid rowData={tagRows(scannedWorkspaces)} columnDefs={tagColumnDefs} emptyMessage="No tags were returned." exportFileName="scanner-tags" exportContext={{}} />
          </GridSection>
        </div>}

        {activeTab === "reports-dashboards" && <div className="space-y-8">
          <GridSection title="Reports">
            <ImpactGrid rowData={reportRows(scannedWorkspaces)} columnDefs={reportColumnDefs} emptyMessage="No reports were returned." exportFileName="scanner-reports" exportContext={{}} />
          </GridSection>
          <GridSection title="Dashboards">
            <ImpactGrid rowData={dashboardRows(scannedWorkspaces)} columnDefs={dashboardColumnDefs} emptyMessage="No dashboards were returned." exportFileName="scanner-dashboards" exportContext={{}} />
          </GridSection>
          <GridSection title="Dashboard tiles">
            <ImpactGrid rowData={tileRows(scannedWorkspaces)} columnDefs={tileColumnDefs} emptyMessage="No dashboard tiles were returned." exportFileName="scanner-dashboard-tiles" exportContext={{}} />
          </GridSection>
        </div>}

        {activeTab === "semantic-models" && <div className="space-y-8">
          <GridSection title="Semantic models">
            <ImpactGrid rowData={datasetRows(scannedWorkspaces)} columnDefs={datasetColumnDefs} emptyMessage="No semantic models were returned." exportFileName="scanner-semantic-models" exportContext={{}} />
          </GridSection>
          <GridSection title="Tables">
            <ImpactGrid rowData={tableRows(scannedWorkspaces)} columnDefs={tableColumnDefs} emptyMessage="No tables were returned." exportFileName="scanner-tables" exportContext={{}} />
          </GridSection>
          <GridSection title="Columns">
            <ImpactGrid rowData={columnRows(scannedWorkspaces)} columnDefs={columnColumnDefs} emptyMessage="No columns were returned." exportFileName="scanner-columns" exportContext={{}} />
          </GridSection>
          <GridSection title="Measures">
            <ImpactGrid rowData={measureRows(scannedWorkspaces)} columnDefs={measureColumnDefs} emptyMessage="No measures were returned." exportFileName="scanner-measures" exportContext={{}} />
          </GridSection>
          <GridSection title="Table sources (M-query)">
            <ImpactGrid rowData={tableSourceRows(scannedWorkspaces)} columnDefs={tableSourceColumnDefs} emptyMessage="No table source expressions were returned." exportFileName="scanner-table-sources" exportContext={{}} />
          </GridSection>
          <GridSection title="Dataset expressions" description="Shared/parameter M-queries declared on the semantic model, distinct from each table's own source expression.">
            <ImpactGrid rowData={datasetExpressionRows(scannedWorkspaces)} columnDefs={datasetExpressionColumnDefs} emptyMessage="No dataset expressions were returned." exportFileName="scanner-dataset-expressions" exportContext={{}} />
          </GridSection>
        </div>}

        {activeTab === "dependencies" && <div className="space-y-8">
          <GridSection title="Dependencies" description="Every report-to-semantic-model link plus each item's declared upstream dataflows, datamarts, and semantic models.">
            <ImpactGrid rowData={dependencyRows(scannedWorkspaces)} columnDefs={dependencyColumnDefs} emptyMessage="No dependencies were returned." exportFileName="scanner-dependencies" exportContext={{}} />
          </GridSection>
        </div>}

        {activeTab === "datasource-instances" && <div className="space-y-8">
          {misconfiguredInstances.length > 0 && <GridSection title="Misconfigured datasource instances">
            <div className="mb-2"><StatusBand tone="warning" text={`${misconfiguredInstances.length} misconfigured datasource ${misconfiguredInstances.length === 1 ? "instance was" : "instances were"} found.`} /></div>
            <ImpactGrid rowData={datasourceRows(misconfiguredInstances, scannedWorkspaces)} columnDefs={datasourceColumnDefs} emptyMessage="No misconfigured datasource instances." exportFileName="scanner-misconfigured-datasources" exportContext={{}} />
          </GridSection>}
          <GridSection title="Datasource instances">
            <ImpactGrid rowData={datasourceRows(datasourceInstances, scannedWorkspaces)} columnDefs={datasourceColumnDefs} emptyMessage="No datasource instances were returned." exportFileName="scanner-datasource-instances" exportContext={{}} />
          </GridSection>
        </div>}
      </>}
    </div>
  </section>;
}

function GridSection({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return <div>
    <h2 className="text-sm font-semibold">{title}</h2>
    {description && <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-500">{description}</p>}
    <div className="mt-3">{children}</div>
  </div>;
}

const workspaceColumnDefs: ColDef<GridRow>[] = [
  { field: "name", headerName: "Workspace", minWidth: 200, flex: 1 },
  { field: "workspaceId", headerName: "Workspace ID", minWidth: 240 },
  { field: "type", headerName: "Type", minWidth: 110 },
  { field: "state", headerName: "State", minWidth: 100 },
  { field: "capacity", headerName: "Capacity", minWidth: 100 },
  { field: "capacityId", headerName: "Capacity ID", minWidth: 240 },
  { field: "storageFormat", headerName: "Storage format", minWidth: 130 },
  { field: "dataRetrievalState", headerName: "Data retrieval state", minWidth: 150 },
  { field: "description", headerName: "Description", minWidth: 200, flex: 1 },
  { field: "reports", headerName: "Reports", minWidth: 100 },
  { field: "dashboards", headerName: "Dashboards", minWidth: 110 },
  { field: "datasets", headerName: "Semantic models", minWidth: 140 },
  { field: "dataflows", headerName: "Dataflows", minWidth: 110 },
  { field: "datamarts", headerName: "Datamarts", minWidth: 110 },
  { field: "tags", headerName: "Tags", minWidth: 90 },
  { field: "users", headerName: "Users", minWidth: 90 },
];

const tagColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 160 },
  { field: "scope", headerName: "Scope", minWidth: 140 },
  { field: "item", headerName: "Item", minWidth: 220, flex: 1 },
  { field: "tagId", headerName: "Tag ID", minWidth: 260 },
];

const reportColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "name", headerName: "Report", minWidth: 200, flex: 1 },
  { field: "reportId", headerName: "Report ID", minWidth: 240 },
  { field: "reportType", headerName: "Type", minWidth: 130 },
  { field: "format", headerName: "Format", minWidth: 110 },
  { field: "appId", headerName: "App ID", minWidth: 220 },
  { field: "datasetId", headerName: "Dataset ID", minWidth: 220 },
  { field: "datasetWorkspaceId", headerName: "Dataset workspace ID", minWidth: 220 },
  { field: "description", headerName: "Description", minWidth: 180 },
  { field: "createdBy", headerName: "Created by", minWidth: 180 },
  { field: "createdById", headerName: "Created by ID", minWidth: 240 },
  { field: "createdDateTime", headerName: "Created", minWidth: 170 },
  { field: "modifiedBy", headerName: "Modified by", minWidth: 180 },
  { field: "modifiedById", headerName: "Modified by ID", minWidth: 240 },
  { field: "modifiedDateTime", headerName: "Modified", minWidth: 170 },
  { field: "isOwnedByMe", headerName: "Owned by me", minWidth: 120 },
  { field: "originalReportId", headerName: "Original report ID (app)", minWidth: 220 },
  { field: "endorsement", headerName: "Endorsement", minWidth: 130 },
  { field: "certifiedBy", headerName: "Certified by", minWidth: 180 },
  { field: "sensitivityLabel", headerName: "Sensitivity label ID", minWidth: 220 },
];

const dashboardColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "name", headerName: "Dashboard", minWidth: 200, flex: 1 },
  { field: "dashboardId", headerName: "Dashboard ID", minWidth: 240 },
  { field: "appId", headerName: "App ID", minWidth: 220 },
  { field: "isReadOnly", headerName: "Access", minWidth: 110 },
  { field: "dataClassification", headerName: "Data classification", minWidth: 160 },
  { field: "sensitivityLabel", headerName: "Sensitivity label ID", minWidth: 220 },
  { field: "tiles", headerName: "Tiles", minWidth: 90 },
];

const tileColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "dashboard", headerName: "Dashboard", minWidth: 180 },
  { field: "title", headerName: "Tile", minWidth: 200, flex: 1 },
  { field: "tileId", headerName: "Tile ID", minWidth: 240 },
  { field: "datasetId", headerName: "Dataset ID", minWidth: 220 },
  { field: "datasetWorkspaceId", headerName: "Dataset workspace ID", minWidth: 220 },
  { field: "reportId", headerName: "Report ID", minWidth: 220 },
];

const datasetColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "name", headerName: "Semantic model", minWidth: 200, flex: 1 },
  { field: "semanticModelId", headerName: "Semantic model ID", minWidth: 240 },
  { field: "description", headerName: "Description", minWidth: 180 },
  { field: "configuredBy", headerName: "Configured by", minWidth: 180 },
  { field: "createdDate", headerName: "Created", minWidth: 170 },
  { field: "storageMode", headerName: "Storage mode", minWidth: 150 },
  { field: "contentProvider", headerName: "Content provider", minWidth: 180 },
  { field: "schemaMayNotBeUpToDate", headerName: "Schema may be stale", minWidth: 150 },
  { field: "schemaRetrievalError", headerName: "Schema retrieval error", minWidth: 200 },
  { field: "endorsement", headerName: "Endorsement", minWidth: 130 },
  { field: "certifiedBy", headerName: "Certified by", minWidth: 180 },
  { field: "sensitivityLabel", headerName: "Sensitivity label ID", minWidth: 220 },
  { field: "tables", headerName: "Tables", minWidth: 90 },
  { field: "expressions", headerName: "Expressions", minWidth: 110 },
  { field: "roles", headerName: "Roles", minWidth: 90 },
  { field: "relationships", headerName: "Relationships", minWidth: 120 },
];

const tableColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "dataset", headerName: "Semantic model", minWidth: 180 },
  { field: "table", headerName: "Table", minWidth: 200, flex: 1 },
  { field: "description", headerName: "Description", minWidth: 200 },
  { field: "isHidden", headerName: "Visibility", minWidth: 110 },
  { field: "columns", headerName: "Columns", minWidth: 100 },
  { field: "measures", headerName: "Measures", minWidth: 100 },
  { field: "rows", headerName: "Rows", minWidth: 90 },
];

const columnColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "dataset", headerName: "Semantic model", minWidth: 170 },
  { field: "table", headerName: "Table", minWidth: 170 },
  { field: "column", headerName: "Column", minWidth: 190, flex: 1 },
  { field: "dataType", headerName: "Data type", minWidth: 120 },
  { field: "dataCategory", headerName: "Data category", minWidth: 140 },
  { field: "formatString", headerName: "Format string", minWidth: 150 },
  { field: "isHidden", headerName: "Visibility", minWidth: 110 },
  { field: "sortByColumn", headerName: "Sort by column", minWidth: 150 },
  { field: "summarizeBy", headerName: "Summarize by", minWidth: 140 },
];

const measureColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "dataset", headerName: "Semantic model", minWidth: 170 },
  { field: "table", headerName: "Table", minWidth: 170 },
  { field: "measure", headerName: "Measure", minWidth: 190 },
  { field: "expression", headerName: "DAX expression", minWidth: 320, flex: 2 },
  { field: "description", headerName: "Description", minWidth: 180 },
  { field: "formatString", headerName: "Format string", minWidth: 150 },
  { field: "isHidden", headerName: "Visibility", minWidth: 110 },
];

const tableSourceColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 160 },
  { field: "dataset", headerName: "Semantic model", minWidth: 200 },
  { field: "table", headerName: "Table", minWidth: 200 },
  { field: "expression", headerName: "M-query expression", minWidth: 320, flex: 2 },
];

const datasetExpressionColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 160 },
  { field: "dataset", headerName: "Semantic model", minWidth: 200 },
  { field: "name", headerName: "Expression name", minWidth: 200 },
  { field: "description", headerName: "Description", minWidth: 220 },
  { field: "expression", headerName: "M-query expression", minWidth: 320, flex: 2 },
];

const dependencyColumnDefs: ColDef<GridRow>[] = [
  { field: "workspace", headerName: "Workspace", minWidth: 150 },
  { field: "sourceType", headerName: "Source type", minWidth: 140 },
  { field: "source", headerName: "Source", minWidth: 200, flex: 1 },
  { field: "dependsOnType", headerName: "Depends on type", minWidth: 150 },
  { field: "targetId", headerName: "Target ID", minWidth: 240 },
  { field: "targetScopeId", headerName: "Target workspace/group ID", minWidth: 240 },
];

const datasourceColumnDefs: ColDef<GridRow>[] = [
  { field: "datasourceType", headerName: "Type", minWidth: 130 },
  { field: "datasourceId", headerName: "Datasource ID", minWidth: 240 },
  { field: "gatewayId", headerName: "Gateway ID", minWidth: 240 },
  { field: "server", headerName: "Server", minWidth: 180 },
  { field: "database", headerName: "Database", minWidth: 160 },
  { field: "domain", headerName: "Domain", minWidth: 140 },
  { field: "account", headerName: "Account", minWidth: 140 },
  { field: "kind", headerName: "Kind", minWidth: 120 },
  { field: "classInfo", headerName: "Class info", minWidth: 140 },
  { field: "connectionEmail", headerName: "Connection email", minWidth: 200 },
  { field: "loginServer", headerName: "Login server", minWidth: 160 },
  { field: "path", headerName: "Path", minWidth: 160 },
  { field: "url", headerName: "URL", minWidth: 200 },
  { field: "name", headerName: "Name (deprecated)", minWidth: 160 },
  { field: "connectionString", headerName: "Connection string (deprecated)", minWidth: 220 },
  { field: "usedBy", headerName: "Used by", minWidth: 260, flex: 1 },
];

function workspaceRows(workspaces: ScannerWorkspace[]): GridRow[] {
  return workspaces.map((workspace) => ({
    id: workspace.id,
    workspaceId: workspace.id,
    name: workspace.name,
    type: workspace.type ?? "--",
    state: workspace.state ?? "--",
    capacity: workspace.isOnDedicatedCapacity ? "Dedicated" : "Shared",
    capacityId: workspace.capacityId ?? "--",
    storageFormat: workspace.defaultDatasetStorageFormat ?? "--",
    dataRetrievalState: workspace.dataRetrievalState ?? "--",
    description: workspace.description ?? "--",
    reports: workspace.reports?.length ?? 0,
    dashboards: workspace.dashboards?.length ?? 0,
    datasets: workspace.datasets?.length ?? 0,
    dataflows: workspace.dataflows?.length ?? 0,
    datamarts: workspace.datamarts?.length ?? 0,
    tags: workspace.tags?.length ?? 0,
    users: workspace.users?.length ?? 0,
  }));
}

function tagRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => {
    (workspace.tags ?? []).forEach((tag) => rows.push({ id: `workspace-${workspace.id}-${tag.id}`, workspace: workspace.name, scope: "Workspace", item: workspace.name, tagId: tag.id }));
    (workspace.reports ?? []).forEach((report) => (report.tags ?? []).forEach((tagId, index) => rows.push({ id: `report-${report.id}-${index}`, workspace: workspace.name, scope: "Report", item: report.name, tagId })));
    (workspace.dashboards ?? []).forEach((dashboard) => (dashboard.tags ?? []).forEach((tagId, index) => rows.push({ id: `dashboard-${dashboard.id}-${index}`, workspace: workspace.name, scope: "Dashboard", item: dashboard.displayName, tagId })));
    (workspace.datasets ?? []).forEach((dataset) => (dataset.tags ?? []).forEach((tagId, index) => rows.push({ id: `dataset-${dataset.id}-${index}`, workspace: workspace.name, scope: "Semantic model", item: dataset.name, tagId })));
    (workspace.dataflows ?? []).forEach((dataflow) => (dataflow.tags ?? []).forEach((tagId, index) => rows.push({ id: `dataflow-${dataflow.objectId}-${index}`, workspace: workspace.name, scope: "Dataflow", item: dataflow.name, tagId })));
    (workspace.datamarts ?? []).forEach((datamart) => (datamart.tags ?? []).forEach((tagId, index) => rows.push({ id: `datamart-${datamart.id}-${index}`, workspace: workspace.name, scope: "Datamart", item: datamart.name, tagId })));
  });
  return rows;
}

function reportRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.reports ?? []).forEach((report) => rows.push({
    id: report.id,
    reportId: report.id,
    workspace: workspace.name,
    name: report.name,
    appId: report.appId ?? "--",
    datasetId: report.datasetId ?? "--",
    datasetWorkspaceId: report.datasetWorkspaceId ?? "--",
    description: report.description ?? "--",
    format: report.format ?? "--",
    reportType: report.reportType ?? "--",
    createdBy: report.createdBy ?? "--",
    createdById: report.createdById ?? "--",
    createdDateTime: report.createdDateTime ?? "--",
    modifiedBy: report.modifiedBy ?? "--",
    modifiedById: report.modifiedById ?? "--",
    modifiedDateTime: report.modifiedDateTime ?? "--",
    isOwnedByMe: report.isOwnedByMe ? "Yes" : "No",
    originalReportId: report.originalReportId ?? "--",
    endorsement: report.endorsementDetails?.endorsement ?? "--",
    certifiedBy: report.endorsementDetails?.certifiedBy ?? "--",
    sensitivityLabel: report.sensitivityLabel?.labelId ?? "--",
  })));
  return rows;
}

function dashboardRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.dashboards ?? []).forEach((dashboard) => rows.push({
    id: dashboard.id,
    dashboardId: dashboard.id,
    workspace: workspace.name,
    name: dashboard.displayName,
    appId: dashboard.appId ?? "--",
    isReadOnly: dashboard.isReadOnly ? "Read-only" : "Editable",
    dataClassification: dashboard.dataClassification ?? "--",
    sensitivityLabel: dashboard.sensitivityLabel?.labelId ?? "--",
    tiles: dashboard.tiles?.length ?? 0,
  })));
  return rows;
}

function tileRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.dashboards ?? []).forEach((dashboard) => (dashboard.tiles ?? []).forEach((tile) => rows.push({
    id: tile.id,
    tileId: tile.id,
    workspace: workspace.name,
    dashboard: dashboard.displayName,
    title: tile.title ?? "--",
    datasetId: tile.datasetId ?? "--",
    datasetWorkspaceId: tile.datasetWorkspaceId ?? "--",
    reportId: tile.reportId ?? "--",
  }))));
  return rows;
}

function datasetRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.datasets ?? []).forEach((dataset) => rows.push({
    id: dataset.id,
    semanticModelId: dataset.id,
    workspace: workspace.name,
    name: dataset.name,
    description: dataset.description ?? "--",
    configuredBy: dataset.configuredBy ?? "--",
    createdDate: dataset.createdDate ?? "--",
    storageMode: dataset.targetStorageMode ?? "--",
    contentProvider: dataset.contentProviderType ?? "--",
    schemaMayNotBeUpToDate: dataset.schemaMayNotBeUpToDate ? "Yes" : "No",
    schemaRetrievalError: dataset.schemaRetrievalError ?? "--",
    endorsement: dataset.endorsementDetails?.endorsement ?? "--",
    certifiedBy: dataset.endorsementDetails?.certifiedBy ?? "--",
    sensitivityLabel: dataset.sensitivityLabel?.labelId ?? "--",
    tables: dataset.tables?.length ?? 0,
    expressions: dataset.expressions?.length ?? 0,
    roles: dataset.roles?.length ?? 0,
    relationships: dataset.relationships?.length ?? 0,
  })));
  return rows;
}

/** Table.rows (raw data rows) is intentionally shown only as a count below, never listed row by
 * row: the admin scan API essentially never populates it, and if it ever did, dumping full data
 * rows into a metadata browser would be well outside this page's scope. */
function tableRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.datasets ?? []).forEach((dataset) => (dataset.tables ?? []).forEach((table) => rows.push({
    id: `${dataset.id}-${table.name}`,
    workspace: workspace.name,
    dataset: dataset.name,
    table: table.name,
    description: table.description ?? "--",
    isHidden: table.isHidden ? "Hidden" : "Visible",
    columns: table.columns?.length ?? 0,
    measures: table.measures?.length ?? 0,
    rows: table.rows?.length ?? 0,
  }))));
  return rows;
}

function columnRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.datasets ?? []).forEach((dataset) => (dataset.tables ?? []).forEach((table) => (table.columns ?? []).forEach((column) => rows.push({
    id: `${dataset.id}-${table.name}-${column.name}`,
    workspace: workspace.name,
    dataset: dataset.name,
    table: table.name,
    column: column.name,
    dataType: column.dataType ?? "--",
    dataCategory: column.dataCategory ?? "--",
    formatString: column.formatString ?? "--",
    isHidden: column.isHidden ? "Hidden" : "Visible",
    sortByColumn: column.sortByColumn ?? "--",
    summarizeBy: column.summarizeBy ?? "--",
  })))));
  return rows;
}

function measureRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.datasets ?? []).forEach((dataset) => (dataset.tables ?? []).forEach((table) => (table.measures ?? []).forEach((measure) => rows.push({
    id: `${dataset.id}-${table.name}-${measure.name}`,
    workspace: workspace.name,
    dataset: dataset.name,
    table: table.name,
    measure: measure.name,
    expression: measure.expression ?? "--",
    description: measure.description ?? "--",
    formatString: measure.formatString ?? "--",
    isHidden: measure.isHidden ? "Hidden" : "Visible",
  })))));
  return rows;
}

function tableSourceRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => {
    (workspace.datasets ?? []).forEach((dataset) => {
      (dataset.tables ?? []).forEach((table) => {
        (table.source ?? []).forEach((source, index) => {
          if (!source.expression) return;
          rows.push({ id: `${workspace.id}-${dataset.id}-${table.name}-${index}`, workspace: workspace.name, dataset: dataset.name, table: table.name, expression: source.expression });
        });
      });
    });
  });
  return rows;
}

function datasetExpressionRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => (workspace.datasets ?? []).forEach((dataset) => (dataset.expressions ?? []).forEach((expression, index) => rows.push({
    id: `${dataset.id}-expr-${index}`,
    workspace: workspace.name,
    dataset: dataset.name,
    name: expression.name ?? "--",
    description: expression.description ?? "--",
    expression: expression.expression ?? "--",
  }))));
  return rows;
}

function dependencyRows(workspaces: ScannerWorkspace[]): GridRow[] {
  const rows: GridRow[] = [];
  workspaces.forEach((workspace) => {
    (workspace.reports ?? []).forEach((report) => {
      if (report.datasetId) rows.push({ id: `report-${report.id}-dataset`, workspace: workspace.name, sourceType: "Report", source: report.name, dependsOnType: "Semantic model", targetId: report.datasetId, targetScopeId: report.datasetWorkspaceId ?? "--" });
    });
    (workspace.datasets ?? []).forEach((dataset) => {
      (dataset.upstreamDataflows ?? []).forEach((dependency, index) => rows.push({ id: `dataset-${dataset.id}-udf-${index}`, workspace: workspace.name, sourceType: "Semantic model", source: dataset.name, dependsOnType: "Dataflow", targetId: dependency.targetDataflowId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
      (dataset.upstreamDatamarts ?? []).forEach((dependency, index) => rows.push({ id: `dataset-${dataset.id}-udm-${index}`, workspace: workspace.name, sourceType: "Semantic model", source: dataset.name, dependsOnType: "Datamart", targetId: dependency.targetDatamartId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
      (dataset.upstreamDatasets ?? []).forEach((dependency, index) => rows.push({ id: `dataset-${dataset.id}-uds-${index}`, workspace: workspace.name, sourceType: "Semantic model", source: dataset.name, dependsOnType: "Semantic model", targetId: dependency.targetDatasetId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
    });
    (workspace.dataflows ?? []).forEach((dataflow) => {
      (dataflow.upstreamDataflows ?? []).forEach((dependency, index) => rows.push({ id: `dataflow-${dataflow.objectId}-udf-${index}`, workspace: workspace.name, sourceType: "Dataflow", source: dataflow.name, dependsOnType: "Dataflow", targetId: dependency.targetDataflowId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
      (dataflow.upstreamDatamarts ?? []).forEach((dependency, index) => rows.push({ id: `dataflow-${dataflow.objectId}-udm-${index}`, workspace: workspace.name, sourceType: "Dataflow", source: dataflow.name, dependsOnType: "Datamart", targetId: dependency.targetDatamartId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
    });
    (workspace.datamarts ?? []).forEach((datamart) => {
      (datamart.upstreamDataflows ?? []).forEach((dependency, index) => rows.push({ id: `datamart-${datamart.id}-udf-${index}`, workspace: workspace.name, sourceType: "Datamart", source: datamart.name, dependsOnType: "Dataflow", targetId: dependency.targetDataflowId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
      (datamart.upstreamDatamarts ?? []).forEach((dependency, index) => rows.push({ id: `datamart-${datamart.id}-udm-${index}`, workspace: workspace.name, sourceType: "Datamart", source: datamart.name, dependsOnType: "Datamart", targetId: dependency.targetDatamartId ?? "--", targetScopeId: dependency.groupId ?? "--" }));
    });
  });
  return rows;
}

function usedByLabel(workspaces: ScannerWorkspace[], datasourceId: string | undefined): string {
  if (!datasourceId) return "--";
  const usedBy: string[] = [];
  workspaces.forEach((workspace) => {
    (workspace.datasets ?? []).forEach((dataset) => {
      const uses = [...(dataset.datasourceUsages ?? []), ...(dataset.misconfiguredDatasourceUsages ?? [])];
      if (uses.some((usage) => usage.datasourceInstanceId === datasourceId)) usedBy.push(`${dataset.name} (semantic model)`);
    });
    (workspace.dataflows ?? []).forEach((dataflow) => {
      const uses = [...(dataflow.datasourceUsages ?? []), ...(dataflow.misconfiguredDatasourceUsages ?? [])];
      if (uses.some((usage) => usage.datasourceInstanceId === datasourceId)) usedBy.push(`${dataflow.name} (dataflow)`);
    });
    (workspace.datamarts ?? []).forEach((datamart) => {
      if ((datamart.datasourceUsages ?? []).some((usage) => usage.datasourceInstanceId === datasourceId)) usedBy.push(`${datamart.name} (datamart)`);
    });
  });
  return usedBy.length ? usedBy.join(", ") : "--";
}

function datasourceRows(instances: ScannerDatasourceInstance[] | undefined, workspaces: ScannerWorkspace[]): GridRow[] {
  return (instances ?? []).map((instance, index) => ({
    id: `${instance.datasourceId ?? instance.gatewayId ?? "datasource"}-${index}`,
    datasourceType: instance.datasourceType ?? "--",
    datasourceId: instance.datasourceId ?? "--",
    gatewayId: instance.gatewayId ?? "--",
    server: instance.connectionDetails?.server ?? "--",
    database: instance.connectionDetails?.database ?? "--",
    domain: instance.connectionDetails?.domain ?? "--",
    account: instance.connectionDetails?.account ?? "--",
    kind: instance.connectionDetails?.kind ?? "--",
    classInfo: instance.connectionDetails?.classInfo ?? "--",
    connectionEmail: instance.connectionDetails?.emailAddress ?? "--",
    loginServer: instance.connectionDetails?.loginServer ?? "--",
    path: instance.connectionDetails?.path ?? "--",
    url: instance.connectionDetails?.url ?? "--",
    name: instance.name ?? "--",
    connectionString: instance.connectionString ?? "--",
    usedBy: usedByLabel(workspaces, instance.datasourceId),
  }));
}

function SummaryStat({ label, value, warnOnValue }: { label: string; value: number; warnOnValue?: boolean }) {
  return <div><p className="text-xs text-zinc-500">{label}</p><p className={cn("mt-1 text-lg font-semibold", warnOnValue && value > 0 ? "text-amber-700" : "text-zinc-950")}>{value}</p></div>;
}

function FlagToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-center gap-2 text-sm text-zinc-700"><Checkbox checked={checked} onCheckedChange={(value) => onChange(value)} />{label}</label>;
}

function StatusBand({ tone, text }: { tone: "success" | "warning"; text: string }) {
  return <div className={cn("border px-3 py-2 text-xs", tone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900")}>{text}</div>;
}

function LoadingState({ label }: { label: string }) {
  return <div className="flex min-h-[320px] items-center justify-center gap-2 text-sm text-zinc-500"><Loader2 className="size-4 animate-spin" />{label}</div>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="rounded-md border border-border bg-surface p-10 text-center"><p className="text-sm font-semibold">{title}</p><p className="mt-1 text-sm text-muted-foreground">{text}</p></div>;
}
