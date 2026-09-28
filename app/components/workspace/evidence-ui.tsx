import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";
import { Boxes, CheckCircle2, ClipboardCopy, Copy, Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "~/components/ui/button";
import { copyText, downloadExportCsv, downloadExportExcel, exportTableToTsv, toExportTable, type ExportColumn } from "~/lib/grid-export";
import { ApiError, isPermissionDenied, isSessionExpired } from "~/lib/lineage-api";
import { COLUMN, OBJECT_TYPE_LABELS, VALUE } from "~/lib/naming";
import { cn } from "~/lib/utils";

ModuleRegistry.registerModules([AllCommunityModule]);

export type ExportValue = string | number | boolean | null | undefined;
export type ExplorerGridRow = { id: string; [key: string]: ExportValue };
export type ExportContext = Record<string, string>;

export type Workspace = {
  id: string;
  name: string;
  is_read_only?: boolean;
  is_on_dedicated_capacity?: boolean;
};

export type Report = {
  id: string;
  name: string;
  dataset_id?: string | null;
  /** Power BI often omits this, so it is never required — but when present it is the only reliable proof of where the bound model actually lives. */
  dataset_workspace_id?: string | null;
  description?: string | null;
  report_type?: string | null;
  format?: string | null;
  is_owned_by_me?: boolean | null;
};

export type SemanticModel = {
  id: string;
  name: string;
  description?: string | null;
  is_refreshable?: boolean | null;
  is_on_prem_gateway_required?: boolean | null;
  target_storage_mode?: string | null;
};

export type ExplorerEvidenceWarning = { code: string; message: string };

/** Semantic object types in the standard vocabulary (Docs/07-column-naming-standard.md). */
export const SEMANTIC_OBJECT_KIND_LABELS: Record<string, string> = OBJECT_TYPE_LABELS;

const explorerTheme = themeQuartz.withParams({
  accentColor: "var(--fabric-primary)",
  backgroundColor: "var(--bg-surface)",
  borderColor: "var(--border-default)",
  foregroundColor: "var(--text-primary)",
  headerBackgroundColor: "var(--bg-subtle)",
  headerTextColor: "var(--text-secondary)",
  rowHoverColor: "var(--bg-subtle)",
  wrapperBorder: false,
});

export function ExplorerGrid({ rowData, columnDefs, onRowClick, emptyMessage, exportFileName, exportContext }: {
  rowData: ExplorerGridRow[];
  columnDefs: ColDef<ExplorerGridRow>[];
  onRowClick?: (row: ExplorerGridRow) => void;
  emptyMessage: string;
  exportFileName: string;
  exportContext: ExportContext;
}) {
  const [tableCopied, setTableCopied] = useState(false);
  // Screen and file share headers: hidden (export-only) columns included, context first, IDs last.
  const exportTable = () => toExportTable(rowData, columnDefs as ExportColumn[], exportContext);

  async function copyTable() {
    await copyText(exportTableToTsv(exportTable()));
    setTableCopied(true);
    window.setTimeout(() => setTableCopied(false), 1800);
  }

  return <div className="mt-4 overflow-x-auto border border-zinc-200"><div className="flex min-w-[720px] items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50 px-3 py-2"><span className="text-xs text-zinc-500">{rowData.length} {rowData.length === 1 ? "row" : "rows"}</span><div className="flex gap-2"><Button type="button" variant="outline" size="sm" title="Copy all table values" disabled={!rowData.length} onClick={() => void copyTable()}>{tableCopied ? <CheckCircle2 className="size-3.5 text-emerald-700" /> : <ClipboardCopy className="size-3.5" />} {tableCopied ? "Copied" : "Copy table"}</Button><Button type="button" variant="outline" size="sm" title="Download CSV" disabled={!rowData.length} onClick={() => downloadExportCsv(exportTable(), exportFileName)}><Download className="size-3.5" /> CSV</Button><Button type="button" variant="outline" size="sm" title="Download Excel-compatible file" disabled={!rowData.length} onClick={() => downloadExportExcel(exportTable(), exportFileName)}><FileSpreadsheet className="size-3.5" /> Excel</Button></div></div><div className="h-[350px] min-w-[720px]"><AgGridReact<ExplorerGridRow> theme={explorerTheme} rowData={rowData} columnDefs={columnDefs} defaultColDef={{ sortable: true, resizable: true, minWidth: 110, cellRenderer: CopyableCell }} rowHeight={42} headerHeight={40} suppressCellFocus={false} enableCellTextSelection ensureDomOrder overlayNoRowsTemplate={`<span class="ag-overlay-no-rows-center">${emptyMessage}</span>`} onRowClicked={(event) => event.data && onRowClick?.(event.data)} /></div></div>;
}

function CopyableCell({ value }: ICellRendererParams<ExplorerGridRow>) {
  const [copied, setCopied] = useState(false);
  const text = String(value ?? VALUE.notAvailable);

  async function copyValue(event: React.MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    await copyText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return <span className="group flex h-full min-w-0 items-center gap-1"><span className="min-w-0 truncate" title={text}>{abbreviate(text, 120)}</span><button type="button" aria-label="Copy cell value" title="Copy value" className="ml-auto hidden shrink-0 rounded-full p-1 text-zinc-400 outline-none transition-[color,background-color,scale] duration-200 ease-apple hover:bg-accent hover:text-teal-700 focus-visible:ring-2 focus-visible:ring-ring/40 active:scale-90 group-hover:inline-flex focus:inline-flex" onClick={(event) => void copyValue(event)}>{copied ? <CheckCircle2 className="size-3.5 text-emerald-700" /> : <Copy className="size-3.5" />}</button></span>;
}

export function daxColumn(field = "daxExpression", headerName = "DAX expression"): ColDef<ExplorerGridRow> {
  return { field, headerName, minWidth: 300, flex: 1.8, tooltipField: field, valueFormatter: (params) => abbreviate(String(params.value ?? "--"), 86) };
}

export function objectKey(tableName: string | null | undefined, objectName: string) {
  return `${tableName ?? ""}[${objectName}]`.toLocaleLowerCase();
}

/** Context columns for an export, in standard names; the export writes the names first and the IDs last. */
export function makeExportContext(workspace: Workspace | null, report?: Report | null, semanticModel?: { id: string; name: string } | null): ExportContext {
  const context: ExportContext = {};
  if (workspace) { context[COLUMN.workspaceName] = workspace.name; context[COLUMN.workspaceId] = workspace.id; }
  if (report) { context[COLUMN.reportName] = report.name; context[COLUMN.reportId] = report.id; }
  if (semanticModel) { context[COLUMN.semanticModel] = semanticModel.name; context[COLUMN.semanticModelId] = semanticModel.id; }
  return context;
}

export function filePart(value: string | undefined) {
  return (value ?? "lineage-export").trim().replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "lineage-export";
}

export function abbreviate(value: string, length: number) {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}...` : clean;
}

export function SectionHeading({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="flex items-start gap-3"><span className="mt-0.5 text-teal-700">{icon}</span><div><h2 className="text-base font-semibold">{title}</h2><p className="mt-1 text-sm leading-6 text-zinc-500">{text}</p></div></div>;
}

export function ExplorerMetric({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return <div className="min-w-0 px-3 py-3 sm:px-4"><div className="flex items-center gap-1.5 text-xs text-zinc-500">{icon}<span className="truncate">{label}</span></div><p className="mt-1 truncate text-sm font-semibold text-zinc-950">{value}</p></div>;
}

export function DetailItem({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 border-b border-zinc-200 px-4 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"><p className="text-xs text-zinc-500">{label}</p><p className="mt-1 truncate text-sm font-semibold text-zinc-950" title={value}>{value}</p></div>;
}

export function AvailabilityNotice({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="border-b border-zinc-200 p-4 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0"><div className="flex items-center gap-2 text-zinc-700">{icon}<h3 className="text-sm font-semibold">{title}</h3></div><p className="mt-2 text-xs leading-5 text-zinc-500">{text}</p></div>;
}

export function ExplorerLoading({ label, compact = false }: { label: string; compact?: boolean }) {
  return <div className={cn("flex items-center justify-center gap-2 border border-zinc-200 bg-zinc-50 text-sm text-zinc-600", compact ? "mt-4 p-4" : "min-h-[340px] p-6")}><Loader2 className="size-4 animate-spin text-teal-700" />{label}</div>;
}

export function ExplorerEmpty({ title, text }: { title: string; text: string }) {
  return <section className="flex min-h-[560px] items-center justify-center border border-zinc-200 bg-white p-6 text-center"><div className="max-w-md"><Boxes className="mx-auto size-8 text-zinc-300" /><h1 className="mt-4 text-lg font-semibold">{title}</h1><p className="mt-2 text-sm leading-6 text-zinc-500">{text}</p></div></section>;
}

export function ExplorerError({ text }: { text: string }) {
  return <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">{text}</div>;
}

export function ExplorerWarnings({ warnings }: { warnings: ExplorerEvidenceWarning[] }) {
  if (!warnings.length) return null;
  return <div className="space-y-1 border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">{warnings.map((warning, index) => <p key={`${warning.code}-${index}`}>{warning.message}</p>)}</div>;
}

/**
 * Explicit opt-in for evidence that costs real upstream API calls (a tenant
 * lineage scan, or gateway admin lookups). Always rendered off by default and
 * never enabled implicitly by navigation.
 */
export function EvidenceOptionToggle({ title, text, label, checked, onChange }: {
  title: string;
  text: string;
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return <div className="flex flex-wrap items-center justify-between gap-3 border-y border-zinc-200 bg-zinc-50 px-4 py-3">
    <div>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-0.5 max-w-2xl text-xs leading-5 text-zinc-500">{text}</p>
    </div>
    <label className="flex shrink-0 items-center gap-2 text-sm font-medium text-zinc-700">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="size-4 accent-teal-700" />
      {label}
    </label>
  </div>;
}

/**
 * Turns a failed query into the most accurate thing we can say about it: a 401
 * means the backend's in-memory session is gone (any backend restart does
 * this), a 403 means the identity is missing a scope or admin right, and
 * anything else keeps the backend's own message plus its request_id.
 */
export function EvidenceError({ error, fallback }: { error: unknown; fallback: string }) {
  if (isSessionExpired(error)) {
    return <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
      Your Power BI session has expired or the backend restarted. <a href="/workspace/power-bi" className="font-semibold underline">Sign in again</a> to continue.
    </div>;
  }

  const apiError = error instanceof ApiError ? error : null;
  const message = isPermissionDenied(error)
    ? `${apiError?.message ?? "This request was denied."} The signed-in identity is missing a Power BI/Fabric scope or admin right for this operation.`
    : apiError?.message ?? fallback;

  return <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
    <p>{message}</p>
    {apiError?.requestId && <p className="mt-1 text-xs text-amber-800">Request ID: <code>{apiError.requestId}</code></p>}
  </div>;
}
