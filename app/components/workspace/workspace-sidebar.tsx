import {
  Database,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  SearchCheck,
  Sigma,
  TableProperties,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Separator } from "~/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import { cn } from "~/lib/utils";

export type ApiGroupSummary = {
  tag: string;
  slug: string;
  count: number;
};

/**
 * The one nav-content implementation reused as the desktop `<aside>` (full or
 * collapsed to an icon rail), the tablet icon rail, and inside the mobile Sheet
 * — only `collapsed` changes, never the nav logic or item list. API reference
 * lives under the header's Documents menu, so it has no entry here.
 */
export function WorkspaceSidebar({
  activeSection,
  onNavigate,
  collapsed = false,
}: {
  activeSection: string;
  onNavigate: (section: string) => void;
  collapsed?: boolean;
}) {
  return (
    <TooltipProvider delay={200}>
      <nav aria-label="Workspace navigation" className="flex h-full min-h-0 flex-col bg-sidebar text-sidebar-foreground">
        <div className={cn("min-h-0 flex-1 overflow-y-auto overflow-x-hidden", collapsed ? "p-2" : "p-4")}>
          <SidebarLabel collapsed={collapsed}>Setup</SidebarLabel>
          <div className="space-y-1">
            <NavigationItem collapsed={collapsed} active={activeSection === "power-bi"} icon={KeyRound} label="Power BI" meta="Step 1" onClick={() => onNavigate("power-bi")} />
            <NavigationItem collapsed={collapsed} active={activeSection === "database"} icon={Database} label="Database" meta="Step 2" onClick={() => onNavigate("database")} />
          </div>

          <Separator className="my-5" />

          <div className="space-y-1">
            <NavigationItem collapsed={collapsed} active={activeSection === "overview"} icon={LayoutDashboard} label="Overview" meta="Access" onClick={() => onNavigate("overview")} />
            <NavigationItem collapsed={collapsed} active={activeSection === "explorer"} icon={SearchCheck} label="Explorer" meta="Inventory" onClick={() => onNavigate("explorer")} />
            <NavigationItem collapsed={collapsed} active={activeSection === "report-lineage"} icon={GitBranch} label="Report lineage" meta="Reports" onClick={() => onNavigate("report-lineage")} />
            <NavigationItem collapsed={collapsed} active={activeSection === "table-impact"} icon={TableProperties} label="Table impact" meta="Impact" onClick={() => onNavigate("table-impact")} />
            <NavigationItem collapsed={collapsed} active={activeSection === "measure-impact"} icon={Sigma} label="Measure impact" meta="Impact" onClick={() => onNavigate("measure-impact")} />
          </div>
        </div>
      </nav>
    </TooltipProvider>
  );
}

function SidebarLabel({ children, collapsed }: { children: string; collapsed: boolean }) {
  if (collapsed) return null;
  return <div className="mb-2 px-3 text-[11px] font-semibold uppercase text-muted-foreground">{children}</div>;
}

function NavigationItem({
  active,
  icon: Icon,
  label,
  meta,
  onClick,
  collapsed,
}: {
  active: boolean;
  icon: LucideIcon;
  label: string;
  meta: string;
  onClick: () => void;
  collapsed: boolean;
}) {
  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              onClick={onClick}
              aria-label={label}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex w-full items-center justify-center rounded-xl py-2.5 outline-none transition-[color,background-color,scale] duration-300 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-95",
                active ? "bg-sidebar-accent text-fabric" : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
              )}
            />
          }
        >
          <Icon className="size-4.5 shrink-0" />
        </TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        // The brand marker on the left grows in when an item becomes current.
        "group relative flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm outline-none transition-[color,background-color,scale] duration-300 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.98] before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:origin-center before:rounded-full before:bg-fabric before:transition-transform before:duration-300 before:ease-apple",
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground before:scale-y-100"
          : "text-muted-foreground before:scale-y-0 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
      )}
    >
      <Icon className={cn("size-4 shrink-0 transition-colors duration-300 ease-apple", active ? "text-fabric" : "group-hover:text-fabric")} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {meta && <span className="shrink-0 text-[11px] text-muted-foreground">{meta}</span>}
    </button>
  );
}
