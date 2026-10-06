import { Columns3, GitBranch, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "~/components/ui/button";
import { LineageDiagram } from "~/components/workspace/lineage/lineage-diagram";
import type { LineageGraph } from "~/components/workspace/lineage/lineage-types";
import { ApiError, isSessionExpired, requestJson } from "~/lib/lineage-api";
import { COLUMN, VALUE } from "~/lib/naming";
import { useAppStore } from "~/stores/app-store";

type SnowflakeObjectReference = {
  object_id: string;
  database: string;
  schema_name: string;
  object_name: string;
  object_domain: string;
  qualified_name: string;
  column_name?: string | null;
  status?: string | null;
};

type SnowflakeDependency = {
  source: SnowflakeObjectReference;
  target: SnowflakeObjectReference;
  dependency_type: string;
  distance?: number | null;
  process?: unknown;
};

type SnowflakeLineageWarning = { code: string; message: string; root_object_name?: string | null };

type SnowflakeTraceResponse = {
  account_identifier: string;
  starting_object_name: string;
  starting_column_name?: string | null;
  object_domain: "TABLE" | "COLUMN";
  direction: "UPSTREAM" | "DOWNSTREAM";
  max_depth: number;
  query_count: number;
  truncated: boolean;
  snapshot: {
    account_identifier: string;
    objects: SnowflakeObjectReference[];
    dependencies: SnowflakeDependency[];
    warnings: SnowflakeLineageWarning[];
    object_count: number;
    dependency_count: number;
  };
  warnings: SnowflakeLineageWarning[];
};

/**
 * The backend's own defaults for a deep trace, sent explicitly so the request
 * this page makes is the request you can read here — `include_process` is
 * singular, which is easy to get wrong because the API catalog's body template
 * spells it `include_processes` (Pydantic silently ignores the misspelling and
 * falls back to its default).
 */
const TRACE_LIMITS = {
  max_depth: 50,
  max_concurrency: 8,
  max_nodes: 5000,
  max_edges: 10000,
  max_queries: 2000,
  include_process: true,
};

export type SnowflakeTraceTarget = { qualifiedName: string; label: string };
export type SnowflakeColumnTarget = { qualifiedName: string; columns: string[] };

/** Trace metric and result-table labels that are not shared grid headers (Docs/07-column-naming-standard.md). */
const LABEL = {
  objectsTraced: "Objects traced",
  dependenciesFound: "Dependencies found",
  queriesRead: "Queries read",
  fromObject: "From object",
  toObject: "To object",
  objectLevel: "Object level",
  dependencyType: "Dependency type",
  process: "Process",
} as const;

/** Snowflake's object level (`TABLE`, `COLUMN` …) in sentence case: "Table", "Column". */
function objectLevelLabel(domain: string | null | undefined): string {
  const value = (domain ?? "").trim().replace(/_/g, " ").toLocaleLowerCase();
  return value ? value.charAt(0).toLocaleUpperCase() + value.slice(1) : VALUE.notAvailable;
}

function processSummary(process: unknown): string {
  if (process == null) return VALUE.notAvailable;
  if (typeof process === "string") return process;
  if (Array.isArray(process)) return process.length ? `${process.length} steps` : VALUE.notAvailable;
  if (typeof process === "object") {
    const record = process as Record<string, unknown>;
    const name = record.name ?? record.query_id ?? record.id;
    return typeof name === "string" && name ? name : "Reported";
  }
  return String(process);
}

/** Shared trace call. Both panels hit the same route with the same limits; only the object identity differs. */
function useSnowflakeTrace() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [isTracing, setIsTracing] = useState(false);
  const [result, setResult] = useState<SnowflakeTraceResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function trace(body: Record<string, unknown>) {
    setIsTracing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await requestJson<SnowflakeTraceResponse>(apiOrigin, "/api/v1/lineage/snowflake/trace", {
        method: "POST",
        body: JSON.stringify({ ...body, ...TRACE_LIMITS }),
      }));
    } catch (caught) {
      setError(caught);
    } finally {
      setIsTracing(false);
    }
  }

  return { isTracing, result, error, trace };
}

/**
 * Traces one physical table's lineage inside Snowflake, starting from a fully
 * qualified name taken straight from the source-database evidence above. This
 * needs the Snowflake session, not the Power BI one — the two are separate
 * cookies, so a signed-in Power BI user can still be unauthenticated here.
 */
export function SnowflakeObjectLineage({ targets }: { targets: SnowflakeTraceTarget[] }) {
  const [selectedName, setSelectedName] = useState("");
  const { isTracing, result, error, trace } = useSnowflakeTrace();

  const selected = useMemo(
    () => targets.find((target) => target.qualifiedName === selectedName) ?? targets[0] ?? null,
    [selectedName, targets],
  );

  return <section className="border border-zinc-200">
    <SnowflakeTraceHeading
      icon={<GitBranch className="size-4 text-teal-700" />}
      title="Snowflake object lineage"
      text="Pick a database table from the data sources above and trace it upstream inside Snowflake, to see what feeds it. This uses the Snowflake connection, which is separate from Power BI sign-in."
    />

    {!targets.length
      ? <p className="px-4 py-6 text-sm text-zinc-500">No database tables were found for this report, so there is nothing to trace. Data sources that were not found, and data sources that are not databases, such as files or URLs, cannot be traced.</p>
      : <div className="space-y-5 p-4">
          <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_auto] md:items-end">
            <SelectField id="snowflake-trace-object" label={COLUMN.databaseTable} value={selected?.qualifiedName ?? ""} onChange={setSelectedName} mono>
              {targets.map((target) => <option key={target.qualifiedName} value={target.qualifiedName}>{target.label}</option>)}
            </SelectField>
            <Button type="button" disabled={!selected || isTracing} onClick={() => selected && void trace({ object_name: selected.qualifiedName, object_domain: "TABLE", direction: "UPSTREAM" })} className="h-10">
              {isTracing ? <Loader2 className="size-4 animate-spin" /> : <GitBranch className="size-4" />}
              {isTracing ? "Tracing" : "Trace lineage"}
            </Button>
          </div>
          <SnowflakeTraceOutcome result={result} error={error} diagram="table" />
        </div>}
  </section>;
}

/**
 * The same trace narrowed to a single database column. Direction and domain are
 * fixed here by design — a column trace only makes sense upstream, so they are
 * sent as constants rather than offered as choices.
 */
export function SnowflakeColumnLineage({ targets }: { targets: SnowflakeColumnTarget[] }) {
  const [selectedName, setSelectedName] = useState("");
  const [selectedColumn, setSelectedColumn] = useState("");
  const { isTracing, result, error, trace } = useSnowflakeTrace();

  const selectedTable = useMemo(
    () => targets.find((target) => target.qualifiedName === selectedName) ?? targets[0] ?? null,
    [selectedName, targets],
  );
  const column = selectedTable?.columns.includes(selectedColumn) ? selectedColumn : selectedTable?.columns[0] ?? "";

  return <section className="border border-zinc-200">
    <SnowflakeTraceHeading
      icon={<Columns3 className="size-4 text-teal-700" />}
      title="Snowflake column lineage"
      text="Trace one database column upstream inside Snowflake, to see which columns and tables it is derived from. Uses the Snowflake connection, which is separate from Power BI sign-in."
    />

    {!targets.length
      ? <p className="px-4 py-6 text-sm text-zinc-500">No database columns were found for this report's semantic objects, so there is nothing to trace.</p>
      : <div className="space-y-5 p-4">
          <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] md:items-end">
            <SelectField id="snowflake-column-object" label={COLUMN.databaseTable} value={selectedTable?.qualifiedName ?? ""} onChange={(value) => { setSelectedName(value); setSelectedColumn(""); }} mono>
              {targets.map((target) => <option key={target.qualifiedName} value={target.qualifiedName}>{target.qualifiedName}</option>)}
            </SelectField>
            <SelectField id="snowflake-column-name" label={COLUMN.databaseColumn} value={column} onChange={setSelectedColumn} mono>
              {(selectedTable?.columns ?? []).map((name) => <option key={name} value={name}>{name}</option>)}
            </SelectField>
            <Button type="button" disabled={!selectedTable || !column || isTracing} onClick={() => selectedTable && column && void trace({ object_name: selectedTable.qualifiedName, column_name: column, object_domain: "COLUMN", direction: "UPSTREAM" })} className="h-10">
              {isTracing ? <Loader2 className="size-4 animate-spin" /> : <Columns3 className="size-4" />}
              {isTracing ? "Tracing" : "Trace column"}
            </Button>
          </div>
          <SnowflakeTraceOutcome result={result} error={error} diagram="column" />
        </div>}
  </section>;
}

function SnowflakeTraceHeading({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-3">
    <p className="flex items-center gap-2 text-sm font-semibold">{icon} {title}</p>
    <p className="mt-0.5 max-w-3xl text-xs leading-5 text-zinc-500">{text}</p>
  </div>;
}

function SelectField({ id, label, value, onChange, mono = false, children }: { id: string; label: string; value: string; onChange: (value: string) => void; mono?: boolean; children: React.ReactNode }) {
  return <div className="space-y-1.5">
    <label className="text-xs font-semibold text-zinc-600" htmlFor={id}>{label}</label>
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)} className={`h-10 w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none transition-[border-color,box-shadow] duration-200 ease-apple hover:border-zinc-300 focus:border-teal-700 focus:ring-4 focus:ring-teal-100${mono ? " font-mono" : ""}`}>
      {children}
    </select>
  </div>;
}

function SnowflakeTraceOutcome({ result, error, diagram }: { result: SnowflakeTraceResponse | null; error: unknown; diagram?: "table" | "column" }) {
  if (error != null) return <SnowflakeTraceError error={error} />;
  if (!result) return null;

  const dependencies = result.snapshot.dependencies;
  const allWarnings = [...result.warnings, ...result.snapshot.warnings];
  const startedFrom = result.starting_column_name
    ? `${result.starting_object_name}.${result.starting_column_name}`
    : result.starting_object_name;

  return <div className="space-y-4">
    <div className="grid border-y border-zinc-200 sm:grid-cols-4">
      <TraceMetric label={LABEL.objectsTraced} value={String(result.snapshot.object_count)} />
      <TraceMetric label={LABEL.dependenciesFound} value={String(result.snapshot.dependency_count)} />
      <TraceMetric label={LABEL.queriesRead} value={String(result.query_count)} />
      <TraceMetric label={COLUMN.databaseAccount} value={result.account_identifier} />
    </div>

    {result.truncated && <div className="border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">This trace hit a limit before it was complete, so only part of the lineage is shown. It stops at {result.max_depth} steps away.</div>}
    {allWarnings.length > 0 && <div className="space-y-1 border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">{allWarnings.map((warning, index) => <p key={`${warning.code}-${index}`}>{warning.message}</p>)}</div>}

    <p className="text-xs text-zinc-500">{result.direction === "UPSTREAM" ? "Upstream of" : "Downstream of"} <span className="font-mono text-zinc-700">{startedFrom}</span></p>

    {dependencies.length === 0
      ? <p className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-600">Snowflake reported no {result.direction.toLowerCase()} dependencies for this {objectLevelLabel(result.object_domain).toLowerCase()}. That is an answer, not a failure — a column loaded straight from an ingested table genuinely has none.</p>
      : <>
          <div className="overflow-x-auto border border-zinc-200">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold text-zinc-600">
                <tr>
                  <th className="border-b border-zinc-200 px-3 py-2">{LABEL.fromObject}</th>
                  <th className="border-b border-zinc-200 px-3 py-2">{LABEL.toObject}</th>
                  <th className="border-b border-zinc-200 px-3 py-2">{LABEL.objectLevel}</th>
                  <th className="border-b border-zinc-200 px-3 py-2">{LABEL.dependencyType}</th>
                  <th className="border-b border-zinc-200 px-3 py-2">{COLUMN.stepsAway}</th>
                  <th className="border-b border-zinc-200 px-3 py-2">{LABEL.process}</th>
                </tr>
              </thead>
              <tbody>
                {dependencies.map((dependency, index) => <tr key={`${dependency.source.object_id}-${dependency.target.object_id}-${index}`} className="align-top hover:bg-zinc-50">
                  <td className="border-b border-zinc-100 px-3 py-2 font-mono text-xs">{qualify(dependency.source)}</td>
                  <td className="border-b border-zinc-100 px-3 py-2 font-mono text-xs">{qualify(dependency.target)}</td>
                  <td className="border-b border-zinc-100 px-3 py-2 text-xs">{objectLevelLabel(dependency.target.object_domain)}</td>
                  <td className="border-b border-zinc-100 px-3 py-2 text-xs">{dependency.dependency_type}</td>
                  <td className="border-b border-zinc-100 px-3 py-2 text-xs">{dependency.distance ?? VALUE.notAvailable}</td>
                  <td className="border-b border-zinc-100 px-3 py-2 text-xs">
                    {processSummary(
                      dependency.process || 
                      (dependency as any).COLUMN_TRANSFORMATION || 
                      (dependency as any).column_transformation || 
                      (dependency as any).MODIFICATION_SQL || 
                      (dependency as any).modification_sql
                    )}
                </td>
                </tr>)}
              </tbody>
            </table>
          </div>
          {diagram && result.object_domain === diagram.toUpperCase() && <SnowflakeDirectedLineageDiagram result={result} level={diagram} />}
        </>}
  </div>;
}

function SnowflakeDirectedLineageDiagram({ result, level }: { result: SnowflakeTraceResponse; level: "table" | "column" }) {
  const { graph, focusNodeId } = useMemo(() => buildSnowflakeGraph(result, level), [result, level]);
  const isColumn = level === "column";

  return <LineageDiagram
    graph={graph}
    direction="TB"
    verticalFlow="up"
    collapseDirection="upstream"
    focusNodeId={focusNodeId}
    title={isColumn ? "Snowflake column lineage" : "Snowflake table lineage"}
    emptyText={isColumn ? "No Snowflake column dependencies were returned." : "No Snowflake table dependencies were returned."}
    canvasClassName={isColumn ? "h-[680px] min-h-[520px]" : "h-[840px] min-h-[560px]"}
    nodeSeparation={20}
    rankSeparation={44}
    animatedEdges
    edgeColor="var(--fabric-primary)"
  />;
}

function buildSnowflakeGraph(result: SnowflakeTraceResponse, level: "table" | "column"): { graph: LineageGraph; focusNodeId?: string } {
  const names = new Map<string, { qualifiedName: string; label: string; detail?: string }>();
  const pairs: Array<{ source: string; target: string }> = [];
  const seenPairs = new Set<string>();
  const isColumn = level === "column";

  const register = (qualifiedName: string, label: string, detail?: string) => {
    const displayName = qualifiedName.trim();
    const key = identityKey(displayName);
    if (displayName && !names.has(key)) names.set(key, { qualifiedName: displayName, label: label || displayName, detail });
    return key;
  };

  const nearest = new Map<string, number>();
  result.snapshot.dependencies.forEach((dependency) => {
    const source = register(referenceName(dependency.source, isColumn), tableName(dependency.source), isColumn ? dependency.source.column_name ?? undefined : undefined);
    const target = register(referenceName(dependency.target, isColumn), tableName(dependency.target), isColumn ? dependency.target.column_name ?? undefined : undefined);
    if (!source || !target || source === target) return;
    // The traced object sits at the near end of the closest hop: the target upstream, the source downstream.
    const near = result.direction === "DOWNSTREAM" ? source : target;
    const distance = dependency.distance ?? Number.MAX_SAFE_INTEGER;
    if (distance < (nearest.get(near) ?? Number.MAX_SAFE_INTEGER)) nearest.set(near, distance);
    const pairKey = `${source}\u0000${target}`;
    if (seenPairs.has(pairKey)) return;
    seenPairs.add(pairKey);
    pairs.push({ source, target });
  });

  // The traced object is always one of the dependency ends. It is found among them rather than
  // added on its own, so a naming difference can never leave it as a second, unconnected node.
  const startingName = result.starting_column_name && isColumn
    ? `${result.starting_object_name}.${result.starting_column_name}`
    : result.starting_object_name;
  const nearestKey = [...nearest].sort((a, b) => a[1] - b[1])[0]?.[0];
  const focusKey = names.has(identityKey(startingName))
    ? identityKey(startingName)
    : nearestKey ?? register(startingName, result.starting_object_name, isColumn ? result.starting_column_name ?? undefined : undefined);

  const idByKey = new Map(Array.from(names.keys()).map((key, index) => [key, `snowflake-${level}-${index}`]));
  const nodes = Array.from(names, ([key, name]) => ({
    id: idByKey.get(key)!,
    kind: isColumn ? "column" as const : "table" as const,
    label: name.label,
    detail: name.detail,
    tooltip: name.qualifiedName,
    isFocal: key === focusKey,
  }));
  const edges = pairs.map((pair, index) => ({
    id: `snowflake-${level}-dependency-${index}`,
    source: idByKey.get(pair.source)!,
    target: idByKey.get(pair.target)!,
  }));

  return { graph: { nodes, edges }, focusNodeId: idByKey.get(focusKey) };
}

/** One key per Snowflake object: unquoted Snowflake names are case-insensitive, and quoting varies between the root and the rows. */
function identityKey(name: string): string {
  return name.replace(/"/g, "").trim().toUpperCase();
}

function referenceName(reference: SnowflakeObjectReference, includeColumn: boolean): string {
  const table = tableName(reference);
  return includeColumn && reference.column_name ? `${table}.${reference.column_name}` : table;
}

/**
 * The table (or view) itself, without the column. Built from the name parts, because a
 * column reference's `qualified_name` already ends in the column ("DB.SCHEMA.TABLE.COLUMN").
 */
function tableName(reference: SnowflakeObjectReference): string {
  const parts = [reference.database, reference.schema_name, reference.object_name].map((part) => part?.trim()).filter(Boolean);
  if (parts.length) return parts.join(".");
  const qualifiedName = reference.qualified_name?.trim() ?? "";
  const column = reference.column_name?.trim();
  return column && identityKey(qualifiedName).endsWith(`.${identityKey(column)}`) ? qualifiedName.slice(0, qualifiedName.length - column.length - 1) : qualifiedName;
}

/** A column trace returns column-level references, so the column is part of the name, once. */
function qualify(reference: SnowflakeObjectReference): string {
  return referenceName(reference, true);
}

function TraceMetric({ label, value }: { label: string; value: string }) {
  return <div className="border-r border-zinc-200 px-4 py-3 last:border-r-0">
    <p className="text-xs text-zinc-500">{label}</p>
    <p className="mt-0.5 break-all text-sm font-semibold">{value}</p>
  </div>;
}

/** A 401 here means the Snowflake session specifically, not Power BI — say which, and link to the right setup. */
function SnowflakeTraceError({ error }: { error: unknown }) {
  if (isSessionExpired(error)) {
    return <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
      <p>No active Snowflake connection. This trace runs against Snowflake directly, so connecting Power BI is not enough.</p>
      <a href="/workspace/database" className="mt-3 inline-flex h-8 text-xs items-center rounded-full bg-fabric px-4 font-medium text-primary-foreground outline-none transition-[background-color,scale] duration-200 ease-apple hover:bg-fabric-hover focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]">Open database setup</a>
    </div>;
  }
  const apiError = error instanceof ApiError ? error : null;
  return <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900">
    <p>{apiError?.message ?? "The Snowflake lineage trace could not be completed."}</p>
    {apiError?.requestId && <p className="mt-1 text-xs text-rose-800">Request ID: <span className="font-mono">{apiError.requestId}</span></p>}
  </div>;
}
