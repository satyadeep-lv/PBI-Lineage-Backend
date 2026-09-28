import { useQuery } from "@tanstack/react-query";
import {
  ChevronRight,
  FileBarChart2,
  FolderKanban,
  Layers3,
  LayoutDashboard,
  Search,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { Input } from "~/components/ui/input";
import { Skeleton } from "~/components/ui/skeleton";
import { PowerBiAuthRequired } from "~/components/workspace/auth-required";
import { ExplorerEmpty, ExplorerLoading, type Report, type SemanticModel, type Workspace } from "~/components/workspace/evidence-ui";
import { ESTATE_DISCOVER_PATH, estateDiscoveryKey, requestJson, WORKSPACE_LIST_PATH, workspaceListKey } from "~/lib/lineage-api";
import { cn } from "~/lib/utils";
import { explorerHref } from "~/lib/workspace-routes";
import { useAppStore } from "~/stores/app-store";

type WorkspaceResponse = { workspaces: Workspace[] };
/** The part of estate/discover this page reads — the cached value is the full body Report lineage and both impact pages share. */
type EstateResponse = {
  workspaces: Array<{ workspace: Workspace; reports?: Report[] | null; semantic_models?: SemanticModel[] | null }>;
};

type WorkspaceContent = { workspace: Workspace; reports: Report[]; semanticModels: SemanticModel[] };
type InventoryState = "loading" | "error" | "ready";
type ListItem = { id: string; name: string; to: string; meta?: ReactNode; label?: string };
type ListGroup = { id: string; name: string; items: ListItem[] };

/** Entrance motion shared by every block; each block staggers it with its own delay. */
const ENTER_CLASS = "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:fill-mode-both motion-safe:ease-apple";

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" });

/**
 * Totals, then every workspace, report, and semantic model the signed-in
 * account can open — each one a link into Explorer with that item selected.
 *
 * Reads only the workspace list and estate discovery entries other pages
 * already share, so opening it never fans out per workspace.
 */
export function Overview() {
  const apiOrigin = useAppStore((state) => state.apiOrigin);

  const workspacesQuery = useQuery({
    queryKey: workspaceListKey(apiOrigin),
    queryFn: () => requestJson<WorkspaceResponse>(apiOrigin, WORKSPACE_LIST_PATH),
  });
  const estateQuery = useQuery({
    queryKey: estateDiscoveryKey(apiOrigin),
    queryFn: () => requestJson<EstateResponse>(apiOrigin, ESTATE_DISCOVER_PATH),
    enabled: workspacesQuery.isSuccess,
  });

  // Explorer can only open workspaces from this same list, so it is the page's universe.
  const content = useMemo<WorkspaceContent[]>(() => {
    const inventories = new Map((estateQuery.data?.workspaces ?? []).map((inventory) => [inventory.workspace.id, inventory]));
    return [...(workspacesQuery.data?.workspaces ?? [])].sort(byName).map((workspace) => ({
      workspace,
      reports: [...(inventories.get(workspace.id)?.reports ?? [])].sort(byName),
      semanticModels: [...(inventories.get(workspace.id)?.semantic_models ?? [])].sort(byName),
    }));
  }, [estateQuery.data, workspacesQuery.data]);

  if (workspacesQuery.isLoading) return <ExplorerLoading label="Loading your Power BI access" />;
  if (workspacesQuery.isError) return <PowerBiAuthRequired returnTo="Overview" />;
  if (!content.length) return <ExplorerEmpty title="No Power BI workspaces found" text="The authenticated account did not return any workspaces, so there is nothing to show yet." />;

  const inventoryState: InventoryState = estateQuery.isError ? "error" : estateQuery.isSuccess ? "ready" : "loading";
  const reportCount = content.reduce((total, entry) => total + entry.reports.length, 0);
  const semanticModelCount = content.reduce((total, entry) => total + entry.semanticModels.length, 0);
  const workspaceCaption = `${content.length === 1 ? "Workspace" : "Workspaces"} your account can open`;
  const acrossCaption = `Across ${content.length} ${content.length === 1 ? "workspace" : "workspaces"}`;

  const workspaceItems: ListItem[] = content.map(({ workspace, reports, semanticModels }) => ({
    id: workspace.id,
    name: workspace.name,
    to: explorerHref({ workspaceId: workspace.id }),
    meta:
      inventoryState === "ready" ? `${plural(reports.length, "report")} · ${plural(semanticModels.length, "semantic model")}`
      : inventoryState === "loading" ? <Skeleton className="h-3 w-28" />
      : undefined,
  }));
  const reportGroups: ListGroup[] = content.map(({ workspace, reports }) => ({
    id: workspace.id,
    name: workspace.name,
    items: reports.map((report) => ({
      id: report.id,
      name: report.name,
      to: explorerHref({ workspaceId: workspace.id, reportId: report.id }),
      label: `${report.name}, in ${workspace.name}`,
    })),
  }));
  const semanticModelGroups: ListGroup[] = content.map(({ workspace, semanticModels }) => ({
    id: workspace.id,
    name: workspace.name,
    items: semanticModels.map((model) => ({
      id: model.id,
      name: model.name,
      to: explorerHref({ workspaceId: workspace.id, semanticModelId: model.id }),
      label: `${model.name}, in ${workspace.name}`,
    })),
  }));

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-5 sm:px-6">
        <div className={cn("flex items-start gap-3", ENTER_CLASS)} style={{ animationDuration: "700ms" }}>
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground">
            <LayoutDashboard className="size-5" />
          </span>
          <div>
            <span className="text-xs font-semibold uppercase text-fabric">Power BI</span>
            <h1 className="text-lg font-semibold">Overview</h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
              Everything your signed-in account can open. Select any workspace, report, or semantic model to see it in Explorer.
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <TotalTile icon={FolderKanban} label="Workspaces" value={content.length} caption={workspaceCaption} state="ready" delay={60} />
          <TotalTile icon={FileBarChart2} label="Reports" value={reportCount} caption={acrossCaption} state={inventoryState} delay={120} />
          <TotalTile icon={Layers3} label="Semantic models" value={semanticModelCount} caption={acrossCaption} state={inventoryState} delay={180} />
        </div>
      </div>

      <div className="grid items-start gap-4 p-4 sm:p-6 lg:grid-cols-3">
        <OverviewColumn
          id="overview-workspaces"
          icon={FolderKanban}
          title="Workspaces"
          description="Opens Explorer on the workspace's reports and semantic models."
          groups={[{ id: "all", name: "", items: workspaceItems }]}
          flat
          state="ready"
          emptyText="No workspaces were returned for your account."
          delay={200}
        />
        <OverviewColumn
          id="overview-reports"
          icon={FileBarChart2}
          title="Reports"
          description="Grouped by workspace. Opens the report's pages, sources, and visuals."
          groups={reportGroups}
          state={inventoryState}
          error={estateQuery.error}
          emptyText="No reports were returned for your workspaces."
          delay={260}
        />
        <OverviewColumn
          id="overview-semantic-models"
          icon={Layers3}
          title="Semantic models"
          description="Grouped by workspace. Opens the model's tables, columns, and measures."
          groups={semanticModelGroups}
          state={inventoryState}
          error={estateQuery.error}
          emptyText="No semantic models were returned for your workspaces."
          delay={320}
        />
      </div>
    </section>
  );
}

function TotalTile({ icon: Icon, label, value, caption, state, delay }: {
  icon: LucideIcon;
  label: string;
  value: number;
  caption: string;
  state: InventoryState;
  delay: number;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-subtle px-4 py-4", ENTER_CLASS)} style={{ animationDelay: `${delay}ms`, animationDuration: "800ms" }}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase text-muted-foreground">{label}</span>
        <span className="flex size-8 items-center justify-center rounded-md border border-fabric/20 bg-surface text-fabric">
          <Icon className="size-4" />
        </span>
      </div>
      <div className="mt-2 h-9">
        {state === "loading" ? <Skeleton className="h-8 w-16" />
          : state === "error" ? <span className="text-3xl font-semibold text-muted-foreground" title="Unavailable">—</span>
          : <CountUp value={value} className="text-3xl font-semibold tabular-nums text-foreground" />}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
    </div>
  );
}

/** Rolls a total up from zero once; the settled value is what assistive technology reads. */
function CountUp({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? value : 0));

  useEffect(() => {
    if (prefersReducedMotion() || value === 0) {
      setShown(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 700);
      setShown(Math.round(value * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <span className={className}>
      <span aria-hidden="true">{shown}</span>
      <span className="sr-only">{value}</span>
    </span>
  );
}

function OverviewColumn({ id, icon: Icon, title, description, groups, flat = false, state, error, emptyText, delay }: {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  groups: ListGroup[];
  /** One unlabeled group: no workspace headings. */
  flat?: boolean;
  state: InventoryState;
  error?: Error | null;
  emptyText: string;
  delay: number;
}) {
  const [filter, setFilter] = useState("");
  const total = groups.reduce((count, group) => count + group.items.length, 0);
  const visibleGroups = useMemo(() => filterGroups(groups, filter), [groups, filter]);
  const shown = visibleGroups.reduce((count, group) => count + group.items.length, 0);
  const filtering = filter.trim().length > 0;

  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className={cn("flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface", ENTER_CLASS)}
      style={{ animationDelay: `${delay}ms`, animationDuration: "800ms" }}
    >
      <div className="border-b border-border bg-subtle px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
            <Icon className="size-4" />
          </span>
          <h2 id={`${id}-heading`} className="text-sm font-semibold">{title}</h2>
          {state === "ready" && (
            <span className="ml-auto rounded-full border border-border bg-surface px-2 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
              {filtering ? `${shown} of ${total}` : total}
            </span>
          )}
        </div>
        <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{description}</p>
        {state === "ready" && total > 0 && (
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label={`Filter ${title.toLowerCase()}`}
              placeholder={flat ? "Filter by name" : "Filter by name or workspace"}
              className="h-8 pl-8 md:text-xs"
            />
          </div>
        )}
      </div>

      <div className="max-h-80 min-h-32 overflow-y-auto lg:max-h-[28rem]">
        {state === "loading" ? (
          <ColumnSkeleton />
        ) : state === "error" ? (
          <div role="status" className="flex gap-2.5 px-4 py-4 text-xs leading-5 text-muted-foreground">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
            <div>
              <p className="font-medium text-foreground">{title} could not be loaded</p>
              <p className="mt-0.5">{error?.message || "Estate discovery is unavailable."} Open a workspace to list them in Explorer.</p>
            </div>
          </div>
        ) : total === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">{emptyText}</p>
        ) : shown === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">Nothing matches “{filter.trim()}”.</p>
        ) : (
          visibleGroups.map((group) => (
            <div key={group.id} role="group" aria-label={flat ? undefined : group.name}>
              {!flat && (
                <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 py-1.5 text-[11px] font-semibold uppercase text-muted-foreground backdrop-blur-sm">
                  <span className="truncate" title={group.name}>{group.name}</span>
                  <span className="shrink-0 tabular-nums">{group.items.length}</span>
                </div>
              )}
              <ul className="py-1">
                {group.items.map((item) => (
                  <li key={item.id}>
                    <OverviewLink item={item} />
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function OverviewLink({ item }: { item: ListItem }) {
  return (
    <Link
      to={item.to}
      aria-label={item.label}
      title={item.name}
      className="group flex items-center gap-3 px-4 py-2 text-sm transition-colors duration-300 ease-apple outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-inset active:bg-accent"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{item.name}</span>
        {item.meta ? <span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.meta}</span> : null}
      </span>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-[translate,color] duration-300 ease-apple group-hover:translate-x-0.5 group-hover:text-fabric group-focus-visible:text-fabric" />
    </Link>
  );
}

function ColumnSkeleton() {
  return (
    <div className="space-y-3 px-4 py-4" aria-hidden="true">
      {[72, 56, 64, 48, 60, 52].map((width, index) => (
        <Skeleton key={index} className="h-4" style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}

/** A workspace-name match keeps its whole group; otherwise only the items whose own name matches. */
function filterGroups(groups: ListGroup[], filter: string): ListGroup[] {
  const needle = filter.trim().toLowerCase();
  return groups
    .map((group) =>
      !needle || group.name.toLowerCase().includes(needle)
        ? group
        : { ...group, items: group.items.filter((item) => item.name.toLowerCase().includes(needle)) },
    )
    .filter((group) => group.items.length > 0);
}

function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
