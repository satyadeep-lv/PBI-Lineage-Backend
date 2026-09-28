import { useQuery } from "@tanstack/react-query";
import {
  Boxes,
  FileBarChart2,
  Files,
  Layers3,
  Loader2,
  Network,
  Radar,
  UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { PowerBiAuthRequired } from "~/components/workspace/auth-required";
import {
  AvailabilityNotice,
  ExplorerEmpty,
  ExplorerError,
  ExplorerGrid,
  ExplorerLoading,
  ExplorerMetric,
  filePart,
  makeExportContext,
  SectionHeading,
  type ExplorerGridRow,
  type ExportContext,
  type Report,
  type SemanticModel,
  type Workspace,
} from "~/components/workspace/evidence-ui";
import { ReportEvidence, type ReportBinding, type ReportSection } from "~/components/workspace/report-evidence";
import { requestJson, WORKSPACE_LIST_PATH, workspaceListKey } from "~/lib/lineage-api";
import { COLUMN, exportOnlyColumn, reportFormatLabel, reportTypeLabel, storageModeLabel, VALUE, yesNo } from "~/lib/naming";
import { DEFAULT_SCAN_FLAGS, workspacePayload, type ScannerWorkspace } from "~/lib/scanner-api";
import { useWorkspaceScan } from "~/lib/use-workspace-scan";
import { sectionTabClass } from "~/lib/interaction-styles";
import { useAppStore } from "~/stores/app-store";
import { usePowerAiStore } from "~/stores/power-ai-store";

type ExplorerTab = "assets" | "reports";

type WorkspaceResponse = { workspaces: Workspace[] };
type ReportsResponse = { reports: Report[] };
type SemanticModelsResponse = { semantic_models: SemanticModel[] };

/** Explorer labels from Docs/07-column-naming-standard.md that the shared glossary (~/lib/naming) does not hold yet. */
const LABEL = {
  pageBadge: "Workspace browser",
  workspaceContent: "Workspace content",
  reportDetails: "Report details",
  appsUsingWorkspace: "Apps using this workspace",
} as const;

/** Explorer cell values from the standard that VALUE does not hold yet. */
const EXPLORER_VALUE = {
  /** The report's semantic model lives in a different workspace. */
  inAnotherWorkspace: "In another workspace",
  /** A dashboard that no Power BI app includes. */
  notInAnApp: "Not in an app",
  itemTypeReport: "Report",
  itemTypeSemanticModel: "Semantic model",
} as const;

const tabs: Array<{ id: ExplorerTab; label: string; shortLabel: string }> = [
  { id: "assets", label: "1. Reports, semantic models, dashboards, apps, and owners in the selected workspace", shortLabel: LABEL.workspaceContent },
  { id: "reports", label: "2. Pages, data sources, semantic objects, database mapping, and visual fields of the selected report", shortLabel: LABEL.reportDetails },
];

/** Export file names follow `explorer-<workspace>-<grid>`. */
function explorerFileName(workspaceName: string | undefined, grid: string) {
  return `explorer-${filePart(workspaceName)}-${grid}`;
}

export function Explorer() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  // Deep links from Overview (see explorerHref) seed only the first selection; the selectors own it after that.
  const [searchParams] = useSearchParams();
  const [requestedModelId, setRequestedModelId] = useState(() => searchParams.get("model") ?? "");
  const [activeTab, setActiveTab] = useState<ExplorerTab>(() => (searchParams.get("report") || searchParams.get("model") ? "reports" : "assets"));
  const [activeReportSection, setActiveReportSection] = useState<ReportSection>(() => (searchParams.get("model") ? "semantic-objects" : "report-detail"));
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(() => searchParams.get("workspace") ?? "");
  const [selectedReportId, setSelectedReportId] = useState(() => searchParams.get("report") ?? "");

  const workspacesQuery = useQuery({
    queryKey: workspaceListKey(apiOrigin),
    queryFn: () => requestJson<WorkspaceResponse>(apiOrigin, WORKSPACE_LIST_PATH),
  });
  const workspaces = workspacesQuery.data?.workspaces ?? [];
  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ?? null;
  const scan = useWorkspaceScan(apiOrigin, selectedWorkspace ? [selectedWorkspace.id] : [], DEFAULT_SCAN_FLAGS);

  useEffect(() => {
    usePowerAiStore.getState().mergeContext({
      workspaceId: selectedWorkspace?.id,
      workspaceName: selectedWorkspace?.name,
      reportId: undefined,
      reportName: undefined,
      semanticModelId: undefined,
      semanticModelName: undefined,
      semanticModelWorkspaceId: undefined,
      objectType: undefined,
      objectId: undefined,
      objectName: undefined,
    });
  }, [selectedWorkspace]);

  useEffect(() => {
    if (workspaces.length && !workspaces.some((workspace) => workspace.id === selectedWorkspaceId)) {
      setSelectedWorkspaceId(workspaces[0].id);
    }
  }, [selectedWorkspaceId, workspaces]);

  const reportsQuery = useQuery({
    queryKey: ["explorer", "reports", apiOrigin, selectedWorkspaceId],
    queryFn: () => requestJson<ReportsResponse>(apiOrigin, `/api/v1/workspaces/${selectedWorkspaceId}/reports`),
    enabled: Boolean(selectedWorkspaceId),
  });
  const semanticModelsQuery = useQuery({
    queryKey: ["explorer", "semantic-models", apiOrigin, selectedWorkspaceId],
    queryFn: () => requestJson<SemanticModelsResponse>(apiOrigin, `/api/v1/workspaces/${selectedWorkspaceId}/semantic-models`),
    enabled: Boolean(selectedWorkspaceId),
  });
  const reports = reportsQuery.data?.reports ?? [];
  const semanticModels = semanticModelsQuery.data?.semantic_models ?? [];
  const semanticModelNames = useMemo(() => new Map(semanticModels.map((model) => [model.id, model.name])), [semanticModels]);

  useEffect(() => {
    if (reports.length && !reports.some((report) => report.id === selectedReportId)) {
      setSelectedReportId(reports[0].id);
    }
  }, [reports, selectedReportId]);

  // A semantic-model deep link opens a report connected to that model, exactly like
  // picking the model in Workspace content; with no connected report it stays there.
  useEffect(() => {
    if (!requestedModelId || !reportsQuery.isSuccess) return;
    const boundReport = reports.find((report) => report.dataset_id === requestedModelId);
    if (boundReport) {
      setSelectedReportId(boundReport.id);
    } else {
      setActiveTab("assets");
      setActiveReportSection("report-detail");
    }
    setRequestedModelId("");
  }, [reports, reportsQuery.isSuccess, requestedModelId]);

  const selectedReport = reports.find((report) => report.id === selectedReportId) ?? null;
  const reportSemanticModel = selectedReport?.dataset_id
    ? semanticModels.find((model) => model.id === selectedReport.dataset_id) ?? null
    : null;
  // Explorer resolves the report's model from the workspace it was picked in;
  // `dataset_workspace_id` is the only reliable proof when that model actually
  // lives somewhere else.
  const binding: ReportBinding | null = selectedWorkspace && selectedReport
    ? {
        workspace: selectedWorkspace,
        report: selectedReport,
        semanticModelId: selectedReport.dataset_id ?? null,
        semanticModelName: reportSemanticModel?.name ?? null,
        semanticModelWorkspaceId: selectedReport.dataset_workspace_id ?? selectedWorkspace.id,
      }
    : null;

  if (workspacesQuery.isLoading) return <ExplorerLoading label="Loading Power BI workspaces" />;
  if (workspacesQuery.isError) return <PowerBiAuthRequired returnTo="Explorer" />;
  if (!workspaces.length) return <ExplorerEmpty title="No Power BI workspaces found" text="The authenticated account did not return any workspaces to explore." />;

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-start">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><Network className="size-5" /></span>
            <div>
              <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-semibold uppercase text-fabric">Power BI</span><Badge className="rounded-md border border-fabric/25 bg-accent text-accent-foreground">{LABEL.pageBadge}</Badge></div>
              <h1 className="text-lg font-semibold">Explorer</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-500">Choose a workspace, review its content, then pick a report to see its pages, data sources, semantic objects, database mapping, and visual fields.</p>
            </div>
          </div>
          <NameSelector id="explorer-workspace" label="Workspace" items={workspaces} selectedId={selectedWorkspaceId} onChange={setSelectedWorkspaceId} />
        </div>
        <div className="mt-5 grid grid-cols-2 divide-x divide-zinc-200 border-y border-zinc-200 sm:max-w-sm">
          <ExplorerMetric label="Reports" value={reports.length} icon={<FileBarChart2 className="size-4" />} />
          <ExplorerMetric label="Semantic models" value={semanticModels.length} icon={<Layers3 className="size-4" />} />
        </div>
      </div>

      <ExplorerGuidance />
      <div className="overflow-x-auto border-b border-border bg-subtle">
        <div className="flex min-w-max px-4 sm:px-6" role="tablist" aria-label="Explorer sections">
          {tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} onClick={() => setActiveTab(tab.id)} className={sectionTabClass(activeTab === tab.id, "px-4 py-3 text-left")} title={tab.label}>{tab.shortLabel}</button>)}
        </div>
      </div>

      <div className="p-5 sm:p-6">
        {activeTab === "assets" && <WorkspaceContentTab workspace={selectedWorkspace} reports={reports} semanticModels={semanticModels} isLoading={reportsQuery.isLoading || semanticModelsQuery.isLoading} error={reportsQuery.error ?? semanticModelsQuery.error} scan={scan} onReportSelect={(reportId) => { setSelectedReportId(reportId); setActiveReportSection("report-detail"); setActiveTab("reports"); }} onSemanticModelSelect={(modelId) => {
          const boundReport = reports.find((report) => report.dataset_id === modelId);
          if (!boundReport) return;
          setSelectedReportId(boundReport.id);
          setActiveReportSection("semantic-objects");
          setActiveTab("reports");
        }} />}
        {activeTab === "reports" && <div className="space-y-6">
          <ReportSelector reports={reports} selectedReport={selectedReport} onChange={setSelectedReportId} />
          {!binding
            ? <ExplorerEmpty title="No reports in this workspace" text="Choose another workspace, or check that the authenticated account can see this workspace's reports." />
            : <ReportEvidence binding={binding} modelNames={semanticModelNames} activeSection={activeReportSection} onSectionChange={setActiveReportSection} />}
        </div>}
      </div>
    </section>
  );
}

function ExplorerGuidance() {
  return <div className="grid border-b border-border bg-subtle md:grid-cols-3"><GuidanceStep number="1" title="Choose business context" text="Start with the workspace and report people recognize." /><GuidanceStep number="2" title="Pick a report" text={`Everything in the ${LABEL.reportDetails} tab is about the report selected there.`} /><GuidanceStep number="3" title="Trace the report" text="Work through Pages, Data sources, Semantic objects, Database mapping, and Visual fields." /></div>;
}

function GuidanceStep({ number, title, text }: { number: string; title: string; text: string }) {
  return <div className="flex gap-3 border-b border-border px-5 py-4 last:border-b-0 md:border-b-0 md:border-r md:px-6 md:last:border-r-0"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-fabric text-xs font-semibold text-primary-foreground">{number}</span><div><p className="text-sm font-semibold">{title}</p><p className="mt-0.5 text-xs leading-5 text-muted-foreground">{text}</p></div></div>;
}

function WorkspaceContentTab({ workspace, reports, semanticModels, isLoading, error, scan, onReportSelect, onSemanticModelSelect }: {
  workspace: Workspace | null;
  reports: Report[];
  semanticModels: SemanticModel[];
  isLoading: boolean;
  error: Error | null;
  scan: ReturnType<typeof useWorkspaceScan>;
  onReportSelect: (id: string) => void;
  onSemanticModelSelect: (id: string) => void;
}) {
  const modelNames = new Map(semanticModels.map((model) => [model.id, model.name]));
  const reportRows: ExplorerGridRow[] = reports.map((report) => ({
    id: report.id,
    reportId: report.id,
    name: report.name,
    type: reportTypeLabel(report.report_type),
    semanticModel: report.dataset_id ? modelNames.get(report.dataset_id) ?? (report.dataset_workspace_id ? EXPLORER_VALUE.inAnotherWorkspace : VALUE.notFound) : VALUE.notAvailable,
    format: reportFormatLabel(report.format),
    ownedByYou: yesNo(report.is_owned_by_me),
  }));
  const modelRows: ExplorerGridRow[] = semanticModels.map((model) => ({
    id: model.id,
    semanticModelId: model.id,
    name: model.name,
    storage: storageModeLabel(model.target_storage_mode),
    refresh: yesNo(model.is_refreshable),
    gateway: yesNo(model.is_on_prem_gateway_required),
  }));
  if (isLoading) return <ExplorerLoading label="Loading reports and semantic models" />;
  if (error) return <ExplorerError text="The reports and semantic models for this workspace could not be loaded." />;
  return <div className="space-y-8">
    <div><SectionHeading icon={<Files className="size-5" />} title="Reports" text="Select a report to see its pages, data sources, semantic objects, and visual fields. Report format is how the report file is stored: PBIR, PBIR (legacy), or PBIX." /><ExplorerGrid rowData={reportRows} columnDefs={[{ field: "name", headerName: COLUMN.reportName, minWidth: 230, flex: 1.4 }, { field: "type", headerName: COLUMN.reportType, minWidth: 150 }, { field: "semanticModel", headerName: COLUMN.semanticModel, minWidth: 220, flex: 1.2 }, { field: "format", headerName: COLUMN.reportFormat, minWidth: 140 }, { field: "ownedByYou", headerName: COLUMN.ownedByYou, minWidth: 140 }, exportOnlyColumn<ExplorerGridRow>("reportId", COLUMN.reportId)]} onRowClick={(row) => onReportSelect(row.id)} emptyMessage="No reports were returned for this workspace." exportFileName={explorerFileName(workspace?.name, "reports")} exportContext={makeExportContext(workspace)} /></div>
    <div><SectionHeading icon={<Layers3 className="size-5" />} title="Semantic models" text="Select a semantic model to see its semantic objects through a report connected to it." /><ExplorerGrid rowData={modelRows} columnDefs={[{ field: "name", headerName: COLUMN.semanticModel, minWidth: 260, flex: 1.5 }, { field: "storage", headerName: COLUMN.storageMode, minWidth: 160 }, { field: "refresh", headerName: COLUMN.refreshEnabled, minWidth: 160 }, { field: "gateway", headerName: COLUMN.gatewayRequired, minWidth: 170 }, exportOnlyColumn<ExplorerGridRow>("semanticModelId", COLUMN.semanticModelId)]} onRowClick={(row) => onSemanticModelSelect(row.id)} emptyMessage="No semantic models were returned for this workspace." exportFileName={explorerFileName(workspace?.name, "semantic-models")} exportContext={makeExportContext(workspace)} /></div>
    <ScannerEvidencePanel workspace={workspace} scan={scan} />
  </div>;
}

function ScannerEvidencePanel({ workspace, scan }: { workspace: Workspace | null; scan: ReturnType<typeof useWorkspaceScan> }) {
  const status = scan.status;
  const isRunning = Boolean(scan.scanId) && status !== "Succeeded" && status !== "Failed";
  const payload = status === "Succeeded" && workspace ? workspacePayload(scan.resultQuery.data, workspace.id) : undefined;

  return <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3 border-y border-zinc-200 bg-zinc-50 px-4 py-3">
      <div>
        <p className="text-sm font-semibold">Dashboards, apps, and ownership</p>
        <p className="mt-0.5 text-xs leading-5 text-zinc-500">Runs the Power BI Admin scanner for this workspace only. Subject to the tenant's hourly scan limits — run it deliberately, not repeatedly.</p>
      </div>
      <Button type="button" variant="outline" size="sm" disabled={!workspace || isRunning} onClick={scan.runScan}>
        {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : <Radar className="size-3.5" />} {scan.scanId && status === "Succeeded" ? "Run scan again" : "Run metadata scan"}
      </Button>
    </div>

    {isRunning && <div className="flex items-center gap-2 border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900"><Loader2 className="size-3.5 animate-spin" />Scanning ({status ?? "starting"})...</div>}
    {status === "Failed" && <div className="border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{scan.statusError?.message ?? "The metadata scan failed."}</div>}
    {scan.isStatusUnavailable && <div className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">Scan status could not be checked. Confirm the scanner API is reachable for this session.</div>}

    {!payload
      ? <div className="grid border-y border-zinc-200 md:grid-cols-3">
          <AvailabilityNotice icon={<FileBarChart2 className="size-5" />} title="Dashboards" text="Run a scan above to see this workspace's dashboards." />
          <AvailabilityNotice icon={<Boxes className="size-5" />} title={LABEL.appsUsingWorkspace} text="Run a scan above to see which Power BI apps include this workspace's content." />
          <AvailabilityNotice icon={<UsersRound className="size-5" />} title="Ownership" text="Run a scan above to see report and semantic model owners." />
        </div>
      : <ScannerEvidenceResults workspace={payload} exportContext={makeExportContext(workspace)} />}
  </div>;
}

function ScannerEvidenceResults({ workspace, exportContext }: { workspace: ScannerWorkspace; exportContext: ExportContext }) {
  const dashboardRows: ExplorerGridRow[] = (workspace.dashboards ?? []).map((dashboard) => ({
    id: dashboard.id,
    dashboardId: dashboard.id,
    name: dashboard.displayName,
    tiles: dashboard.tiles?.length ?? 0,
    readOnly: yesNo(dashboard.isReadOnly),
    appId: dashboard.appId ?? EXPLORER_VALUE.notInAnApp,
  }));
  const appIds = Array.from(new Set([...(workspace.reports ?? []).map((report) => report.appId), ...(workspace.dashboards ?? []).map((dashboard) => dashboard.appId)].filter((id): id is string => Boolean(id))));
  // One column per kind of owner: reports carry who created and last modified them,
  // semantic models only who configured them.
  const ownershipRows: ExplorerGridRow[] = [
    ...(workspace.reports ?? []).map((report) => ({
      id: `report-${report.id}`,
      itemId: report.id,
      itemType: EXPLORER_VALUE.itemTypeReport,
      name: report.name,
      lastModifiedBy: report.modifiedBy ?? VALUE.notAvailable,
      createdBy: report.createdBy ?? VALUE.notAvailable,
      configuredBy: VALUE.notApplicable,
    })),
    ...(workspace.datasets ?? []).map((dataset) => ({
      id: `dataset-${dataset.id}`,
      itemId: dataset.id,
      itemType: EXPLORER_VALUE.itemTypeSemanticModel,
      name: dataset.name,
      lastModifiedBy: VALUE.notAvailable,
      createdBy: VALUE.notAvailable,
      configuredBy: dataset.configuredBy ?? VALUE.notAvailable,
    })),
  ];

  return <div className="space-y-8">
    <div>
      <SectionHeading icon={<FileBarChart2 className="size-5" />} title="Dashboards" text="Every dashboard the metadata scan found in this workspace." />
      <ExplorerGrid rowData={dashboardRows} columnDefs={[{ field: "name", headerName: COLUMN.dashboardName, minWidth: 230, flex: 1 }, { field: "tiles", headerName: COLUMN.dashboardTileCount, minWidth: 210 }, { field: "readOnly", headerName: COLUMN.readOnly, minWidth: 120 }, { field: "appId", headerName: COLUMN.appId, minWidth: 320, flex: 1 }, exportOnlyColumn<ExplorerGridRow>("dashboardId", COLUMN.dashboardId)]} emptyMessage="No dashboards were found in this workspace." exportFileName={explorerFileName(workspace.name, "dashboards")} exportContext={exportContext} />
    </div>
    <div>
      <SectionHeading icon={<Boxes className="size-5" />} title={LABEL.appsUsingWorkspace} text="Power BI apps that include this workspace's reports or dashboards, shown by App ID. The metadata scan does not return app names." />
      {appIds.length
        ? <ul className="mt-3 flex flex-wrap gap-2">{appIds.map((id) => <li key={id} className="break-all border border-zinc-200 bg-zinc-50 px-2.5 py-1 font-mono text-xs text-zinc-700">{id}</li>)}</ul>
        : <p className="mt-3 text-sm text-zinc-500">No report or dashboard in this workspace is in an app.</p>}
    </div>
    <div>
      <SectionHeading icon={<UsersRound className="size-5" />} title="Ownership" text="Who last modified and created each report, and who configured each semantic model." />
      <ExplorerGrid rowData={ownershipRows} columnDefs={[{ field: "itemType", headerName: COLUMN.itemType, minWidth: 150 }, { field: "name", headerName: COLUMN.itemName, minWidth: 220, flex: 1 }, { field: "lastModifiedBy", headerName: COLUMN.lastModifiedBy, minWidth: 200, flex: 1 }, { field: "createdBy", headerName: COLUMN.createdBy, minWidth: 200, flex: 1 }, { field: "configuredBy", headerName: COLUMN.configuredBy, minWidth: 200, flex: 1 }, exportOnlyColumn<ExplorerGridRow>("itemId", COLUMN.itemId)]} emptyMessage="No reports or semantic models were found in this workspace." exportFileName={explorerFileName(workspace.name, "owners")} exportContext={exportContext} />
    </div>
  </div>;
}

function NameSelector({ id, label, items, selectedId, onChange }: { id: string; label: string; items: Array<{ id: string; name: string }>; selectedId: string; onChange: (id: string) => void }) {
  const selectedItem = items.find((item) => item.id === selectedId) ?? null;
  return <div className="w-full space-y-1.5 xl:max-w-sm"><label className="text-xs font-semibold text-zinc-600" htmlFor={id}>{label}</label><select id={id} value={selectedId} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none transition-[border-color,box-shadow] duration-200 ease-apple hover:border-zinc-300 focus:border-teal-700 focus:ring-4 focus:ring-teal-100"><option value="" disabled>Select a {label.toLowerCase()}</option>{items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{selectedItem && <p className="break-all text-xs text-zinc-500">{label} ID: <code className="text-zinc-700">{selectedItem.id}</code></p>}</div>;
}

function ReportSelector({ reports, selectedReport, onChange }: { reports: Report[]; selectedReport: Report | null; onChange: (id: string) => void }) {
  return <NameSelector id="explorer-report" label="Report" items={reports} selectedId={selectedReport?.id ?? ""} onChange={onChange} />;
}
