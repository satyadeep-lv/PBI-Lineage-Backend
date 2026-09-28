import { BookOpenText, ChevronUp, FileText, Play, Search, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { ApiExecutionPanel } from "~/components/workspace/api-execution-panel";
import { type ApiEndpoint, type ApiResult, methodTone, tagSlug } from "~/lib/api-catalog";
import type { ExecuteEndpoint } from "~/lib/use-api-executor";
import { cn } from "~/lib/utils";

export function ApiDocumentation({
  endpoints,
  selectedGroupSlug,
  execute,
  result,
  error,
  isRunning,
}: {
  endpoints: ApiEndpoint[];
  selectedGroupSlug?: string;
  execute: ExecuteEndpoint;
  result: ApiResult | null;
  error: string | null;
  isRunning: boolean;
}) {
  const [filter, setFilter] = useState("");
  const [activeGroup, setActiveGroup] = useState(selectedGroupSlug ?? "all");
  const [activeEndpointId, setActiveEndpointId] = useState<string | null>(null);
  const groups = useMemo(
    () =>
      Array.from(
        endpoints.reduce<Map<string, { name: string; count: number }>>((allGroups, endpoint) => {
          const slug = tagSlug(endpoint.tag);
          const current = allGroups.get(slug);
          allGroups.set(slug, { name: endpoint.tag, count: (current?.count ?? 0) + 1 });
          return allGroups;
        }, new Map()),
        ([slug, value]) => ({ slug, ...value }),
      ),
    [endpoints],
  );

  useEffect(() => {
    setActiveGroup(selectedGroupSlug ?? "all");
    setActiveEndpointId(null);
  }, [selectedGroupSlug]);

  useEffect(() => {
    if (activeEndpointId && !endpoints.some((endpoint) => endpoint.id === activeEndpointId)) {
      setActiveEndpointId(null);
    }
  }, [activeEndpointId, endpoints]);

  const filteredEndpoints = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();

    return endpoints.filter((endpoint) => {
      const isInActiveGroup = activeGroup === "all" || tagSlug(endpoint.tag) === activeGroup;
      const matchesFilter =
        !normalizedFilter ||
        [endpoint.summary, endpoint.description, endpoint.path, endpoint.method, endpoint.tag]
          .join(" ")
          .toLowerCase()
          .includes(normalizedFilter);

      return isInActiveGroup && matchesFilter;
    });
  }, [activeGroup, endpoints, filter]);

  const groupedEndpoints = useMemo(
    () =>
      filteredEndpoints.reduce<Record<string, ApiEndpoint[]>>((allGroups, endpoint) => {
        allGroups[endpoint.tag] ??= [];
        allGroups[endpoint.tag].push(endpoint);
        return allGroups;
      }, {}),
    [filteredEndpoints],
  );

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground">
              <BookOpenText className="size-5" />
            </span>
            <div>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase text-fabric">Reference</span>
                <Badge className="rounded-md border border-border bg-subtle text-foreground">
                  {endpoints.length} operations
                </Badge>
                <Badge className="rounded-md border border-success/30 bg-success/10 text-success">
                  <Zap className="size-3" /> Execution enabled
                </Badge>
              </div>
              <h1 className="text-lg font-semibold">API documentation</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                Browse grouped service operations, set request values, and execute them against the connected PBI Lineage backend.
              </p>
            </div>
          </div>

          <div className="relative w-full lg:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-zinc-400" />
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Search methods and descriptions"
              className="pl-9"
            />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <GroupButton active={activeGroup === "all"} label="All groups" count={endpoints.length} onClick={() => setActiveGroup("all")} />
          {groups.map((group) => (
            <GroupButton
              key={group.slug}
              active={activeGroup === group.slug}
              label={group.name}
              count={group.count}
              onClick={() => setActiveGroup(group.slug)}
            />
          ))}
        </div>
      </div>

      <div className="divide-y divide-zinc-200">
        {Object.entries(groupedEndpoints).map(([groupName, groupEndpoints]) => (
          <div key={groupName} className="px-5 py-5 sm:px-6">
            <div className="mb-4 flex items-center gap-2">
              <FileText className="size-4 text-zinc-500" />
              <h2 className="text-sm font-semibold">{groupName}</h2>
              <span className="text-xs text-zinc-500">{groupEndpoints.length} methods</span>
            </div>
            <div className="divide-y divide-zinc-100 border-y border-zinc-200">
              {groupEndpoints.map((endpoint) => (
                <article key={endpoint.id} className="grid gap-3 py-4 md:grid-cols-[90px_minmax(0,1fr)_minmax(220px,0.9fr)_auto] md:gap-5">
                  <div>
                    <span className={cn("inline-flex rounded-[6px] border px-2 py-1 text-xs font-semibold uppercase", methodTone(endpoint.method))}>
                      {endpoint.method}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-zinc-950">{endpoint.summary}</h3>
                    <p className="mt-1 break-all font-mono text-xs text-zinc-500">{endpoint.path}</p>
                  </div>
                  <p className="text-sm leading-6 text-zinc-600">{endpointDescription(endpoint)}</p>
                  <div className="md:text-right">
                    <Button type="button" variant={activeEndpointId === endpoint.id ? "secondary" : "outline"} size="sm" onClick={() => setActiveEndpointId((current) => current === endpoint.id ? null : endpoint.id)}>
                      {activeEndpointId === endpoint.id ? <ChevronUp className="size-3.5" /> : <Play className="size-3.5" />}
                      {activeEndpointId === endpoint.id ? "Close" : "Execute"}
                    </Button>
                  </div>
                  {activeEndpointId === endpoint.id && <div className="min-w-0 md:col-span-4">
                    <ApiExecutionPanel endpoint={endpoint} execute={execute} result={result} error={result?.endpoint === endpoint.id ? error : null} isRunning={isRunning} />
                  </div>}
                </article>
              ))}
            </div>
          </div>
        ))}

        {filteredEndpoints.length === 0 && (
          <div className="px-5 py-20 text-center sm:px-6">
            <Search className="mx-auto size-7 text-zinc-300" />
            <p className="mt-4 text-sm text-zinc-500">No documented methods match this filter.</p>
          </div>
        )}
      </div>
    </section>
  );
}

function GroupButton({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-2 rounded-full border px-3.5 text-xs font-medium outline-none transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]",
        active
          ? "border-fabric bg-fabric text-primary-foreground"
          : "border-border bg-surface text-muted-foreground hover:border-fabric/50 hover:text-foreground",
      )}
    >
      {label}
      <span className={cn("text-[11px]", active ? "text-primary-foreground/75" : "text-muted-foreground")}>{count}</span>
    </button>
  );
}

function endpointDescription(endpoint: ApiEndpoint) {
  if (endpoint.description.trim()) {
    return endpoint.description.trim();
  }

  const action = endpoint.summary.replace(/^[A-Z]\w*\s+/, "").replace(/\.$/, "").toLowerCase();
  return `Use this operation to ${action || "retrieve application data"}.`;
}
