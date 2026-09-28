import type { ColDef } from "ag-grid-community";

/**
 * The one vocabulary for grid headers, tiles, and values on Explorer, Report
 * lineage, Table impact, and Measure impact — see
 * Docs/07-column-naming-standard.md. Headers are sentence case, name the
 * object before the attribute, and are also the exact column names written to
 * Copy table, CSV, and Excel.
 */
export const COLUMN = {
  workspaceName: "Workspace name",
  workspaceId: "Workspace ID",
  reportName: "Report name",
  reportId: "Report ID",
  reportType: "Report type",
  reportFormat: "Report format",
  semanticModel: "Semantic model",
  semanticModelId: "Semantic model ID",
  semanticTable: "Semantic table",
  measuresSemanticTable: "Measure's semantic table",
  pageOrder: "Page order",
  pageName: "Page name",
  pageId: "Page ID",
  visualName: "Visual name",
  visualType: "Visual type",
  visualId: "Visual ID",
  dashboardName: "Dashboard name",
  dashboardId: "Dashboard ID",
  dashboardTileCount: "Number of dashboard tiles",
  appId: "App ID",
  itemType: "Item type",
  itemName: "Item name",
  itemId: "Item ID",
  createdBy: "Created by",
  lastModifiedBy: "Last modified by",
  configuredBy: "Configured by",
  objectName: "Object name",
  objectType: "Object type",
  dataType: "Data type",
  daxExpression: "DAX expression",
  referencedAs: "Referenced as",
  measureName: "Measure name",
  dataSourceType: "Data source type",
  dataSourceName: "Data source name",
  databaseAccount: "Database account",
  database: "Database",
  schema: "Schema",
  databaseTable: "Database table",
  databaseTables: "Database tables",
  databaseColumn: "Database column",
  databaseColumns: "Database columns",
  reachedThrough: "Reached through",
  ownedByYou: "Owned by you",
  readOnly: "Read-only",
  refreshEnabled: "Refresh enabled",
  gatewayRequired: "Gateway required",
  storageMode: "Storage mode",
  selectedTables: "Selected tables",
  selectedMeasure: "Selected measure",
  howItIsUsed: "How it is used",
  objectsUsed: "Objects used",
  objectsInvolved: "Objects involved",
  connectionToMeasure: "Connection to the measure",
  dependency: "Dependency",
  stepsAway: "Steps away",
  pageCount: "Number of pages",
  visualCount: "Number of visuals",
  reportCount: "Number of reports",
  impactedMeasureCount: "Number of impacted measures",
  impactedCalculatedColumnCount: "Number of impacted calculated columns",
  reportsUsingCount: "Number of reports using it",
  visualsUsingCount: "Number of visuals using it",
  connectedReportCount: "Number of connected reports",
} as const;

/** Standard cell values, including the three ways of saying a value is missing. */
export const VALUE = {
  /** Power BI or the database did not provide it. */
  notAvailable: "Not available",
  /** The app looked but could not trace it. */
  notFound: "Not found",
  /** The value does not exist for this kind of item. */
  notApplicable: "Not applicable",
  yes: "Yes",
  no: "No",
  unknown: "Unknown",
  direct: "Direct",
  indirect: "Indirect",
  usesDirectly: "Uses it directly",
  throughMeasure: "Through a measure",
  directly: "Directly",
} as const;

export function yesNo(value: boolean | null | undefined) {
  return value === true ? VALUE.yes : value === false ? VALUE.no : VALUE.unknown;
}

/** "Direct" one step away, "Indirect" through any other calculation. */
export function dependencyLabel(stepsAway: number) {
  return stepsAway <= 1 ? VALUE.direct : VALUE.indirect;
}

const REPORT_TYPE_LABELS: Record<string, string> = { PowerBIReport: "Power BI report", PaginatedReport: "Paginated report" };
const REPORT_FORMAT_LABELS: Record<string, string> = { PBIRLegacy: "PBIR (legacy)" };
const STORAGE_MODE_LABELS: Record<string, string> = { Abf: "Import", PremiumFiles: "Import (large model)", DirectLake: "Direct Lake" };

export function reportTypeLabel(raw: string | null | undefined) {
  return raw ? REPORT_TYPE_LABELS[raw] ?? raw : VALUE.notAvailable;
}

export function reportFormatLabel(raw: string | null | undefined) {
  return raw ? REPORT_FORMAT_LABELS[raw] ?? raw : VALUE.notAvailable;
}

export function storageModeLabel(raw: string | null | undefined) {
  return raw ? STORAGE_MODE_LABELS[raw] ?? raw : VALUE.notAvailable;
}

/** Semantic object types, sentence case ("Calculated column", never "Calculated Column"). */
export const OBJECT_TYPE_LABELS: Record<string, string> = {
  table: "Semantic table",
  calculated_table: "Calculated table",
  column: "Column",
  calculated_column: "Calculated column",
  measure: "Measure",
  hierarchy: "Hierarchy",
  hierarchy_level: "Hierarchy level",
};

export function objectTypeLabel(raw: string | null | undefined) {
  if (!raw) return VALUE.notAvailable;
  const key = raw.trim().toLocaleLowerCase().replace(/[\s-]+/g, "_");
  return OBJECT_TYPE_LABELS[key] ?? raw;
}

/** "Sales (Finance Model)": a name disambiguated by the thing that holds it. */
export function nameWithParent(name: string, parent: string | null | undefined) {
  return parent ? `${name} (${parent})` : name;
}

/**
 * A grid column whose row key is its header, so screen and export agree without
 * a mapping. `hide: true` makes it export-only (IDs).
 */
export function gridColumn<TData = unknown>(header: string, options: Omit<ColDef<TData>, "field" | "headerName"> = {}): ColDef<TData> {
  return { field: header as ColDef<TData>["field"], headerName: header, ...options };
}

/** An export-only column: in Copy table, CSV, and Excel, never on screen. */
export function exportOnlyColumn<TData = unknown>(field: string, header: string): ColDef<TData> {
  return { field: field as ColDef<TData>["field"], headerName: header, hide: true };
}
