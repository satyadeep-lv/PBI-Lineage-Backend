export type GridValue = string | number | boolean | null | undefined;
export type GridRow = { id: string; [key: string]: GridValue };
export type ExportContext = Record<string, string>;

function csvCell(value: GridValue) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function downloadBlob(content: string, type: string, fileName: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export function filePart(value: string | undefined) {
  return (value ?? "lineage-export").trim().replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "lineage-export";
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}

/** A column as the export sees it: its row key and the header shown on screen. */
export type ExportColumn = { field?: string; headerName?: string };
export type ExportTable = { headers: string[]; rows: string[][] };

const isIdHeader = (header: string) => header === "ID" || header.endsWith(" ID");

function exportCell(value: GridValue) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/**
 * The table Copy table, CSV, and Excel all write: the grid's own headers (hidden
 * export-only columns included) so screen and file always match, the context
 * columns (workspace, report, selection …) first, and every "… ID" column last.
 */
export function toExportTable(rows: Array<Record<string, GridValue>>, columns: ExportColumn[], context: ExportContext = {}): ExportTable {
  const gridColumns = columns
    .filter((column): column is ExportColumn & { field: string } => Boolean(column.field))
    .map((column) => ({ header: column.headerName ?? column.field, read: (row: Record<string, GridValue>) => row[column.field] }));
  const gridHeaders = new Set(gridColumns.map((column) => column.header));
  const contextColumns = Object.entries(context)
    .filter(([header]) => !gridHeaders.has(header))
    .map(([header, value]) => ({ header, read: () => value as GridValue }));
  const ordered = [
    ...contextColumns.filter((column) => !isIdHeader(column.header)),
    ...gridColumns.filter((column) => !isIdHeader(column.header)),
    ...gridColumns.filter((column) => isIdHeader(column.header)),
    ...contextColumns.filter((column) => isIdHeader(column.header)),
  ];
  return { headers: ordered.map((column) => column.header), rows: rows.map((row) => ordered.map((column) => exportCell(column.read(row)))) };
}

export function exportTableToTsv(table: ExportTable) {
  const line = (cells: string[]) => cells.map((cell) => cell.replace(/[\t\r\n]+/g, " ")).join("\t");
  return [line(table.headers), ...table.rows.map(line)].join("\n");
}

export function downloadExportCsv(table: ExportTable, baseName: string) {
  const line = (cells: string[]) => cells.map((cell) => csvCell(cell)).join(",");
  downloadBlob(`${String.fromCharCode(0xfeff)}${[line(table.headers), ...table.rows.map(line)].join("\r\n")}`, "text/csv;charset=utf-8", `${filePart(baseName)}.csv`);
}

export function downloadExportExcel(table: ExportTable, baseName: string) {
  const cells = (tag: "th" | "td", values: string[]) => values.map((value) => `<${tag}>${escapeHtml(value)}</${tag}>`).join("");
  const html = `<table><thead><tr>${cells("th", table.headers)}</tr></thead><tbody>${table.rows.map((row) => `<tr>${cells("td", row)}</tr>`).join("")}</tbody></table>`;
  downloadBlob(`<!doctype html><html><head><meta charset="utf-8"></head><body>${html}</body></html>`, "application/vnd.ms-excel;charset=utf-8", `${filePart(baseName)}.xls`);
}
