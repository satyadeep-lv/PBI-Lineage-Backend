import { Handle, Position, type NodeProps, type NodeTypes } from "@xyflow/react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { memo } from "react";

import { LINEAGE_NODE_WIDTH } from "./lineage-layout";
import type { LineageFlowNode, LineageNodeKind } from "./lineage-types";
import { cn } from "~/lib/utils";

export const KIND_STYLES: Record<LineageNodeKind, { container: string; accent: string }> = {
  workspace: { container: "border-rose-300 bg-rose-50", accent: "text-rose-800" },
  "database-source": { container: "border-emerald-300 bg-emerald-50", accent: "text-emerald-800" },
  table: { container: "border-sky-300 bg-sky-50", accent: "text-sky-800" },
  "semantic-model": { container: "border-teal-300 bg-teal-50", accent: "text-teal-800" },
  column: { container: "border-sky-200 bg-sky-50", accent: "text-sky-700" },
  "calculated-column": { container: "border-orange-300 bg-orange-50", accent: "text-orange-800" },
  "calculated-table": { container: "border-orange-300 bg-orange-50", accent: "text-orange-800" },
  measure: { container: "border-violet-300 bg-violet-50", accent: "text-violet-800" },
  hierarchy: { container: "border-border bg-subtle", accent: "text-foreground" },
  report: { container: "border-rose-300 bg-rose-50", accent: "text-rose-800" },
  page: { container: "border-amber-300 bg-amber-50", accent: "text-amber-800" },
  visual: { container: "border-border bg-surface", accent: "text-foreground" },
};

function abbreviate(value: string, length: number) {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 3)}...` : clean;
}

const LineageNode = memo(function LineageNode({ id, data }: NodeProps<LineageFlowNode>) {
  const style = KIND_STYLES[data.kind];
  const [targetPosition, sourcePosition] = data.direction === "TB"
    ? data.verticalFlow === "up"
      ? [Position.Bottom, Position.Top]
      : [Position.Top, Position.Bottom]
    : [Position.Left, Position.Right];

  return (
    <div
      style={{ width: LINEAGE_NODE_WIDTH }}
      className={cn("relative cursor-grab rounded-md border p-2.5 active:cursor-grabbing", style.container, data.isFocal && "ring-2 ring-fabric ring-offset-2 ring-offset-background")}
    >
      <Handle type="target" position={targetPosition} />
      <div className="max-w-full text-left" title={data.tooltip ?? `${data.label}\n${data.detail ?? ""}`}>
        <div className={cn("break-words text-xs font-semibold", style.accent)}>{data.label}</div>
        {data.detail && <div className="mt-1 break-words text-[11px] leading-4 text-zinc-600">{abbreviate(data.detail, 130)}</div>}
      </div>
      {data.hasChildren && (
        <button
          type="button"
          className="nodrag nopan absolute -right-2 -top-2 flex h-5 items-center gap-0.5 rounded-full border border-zinc-300 bg-white px-1 text-[10px] text-zinc-700 shadow-sm outline-none transition-[color,background-color,border-color,scale] duration-200 ease-apple hover:border-fabric/50 hover:bg-zinc-50 hover:text-fabric focus-visible:ring-2 focus-visible:ring-ring/40 active:scale-90"
          onClick={(event) => { event.stopPropagation(); data.onToggle(id); }}
          aria-label={data.collapsed ? "Expand descendants" : "Collapse descendants"}
        >
          {data.collapsed ? <ChevronRight className="size-3" /> : <ChevronDown className="size-3" />}
          {data.collapsed && data.descendantCount > 0 && <span>{data.descendantCount}</span>}
        </button>
      )}
      <Handle type="source" position={sourcePosition} />
    </div>
  );
});

export const LINEAGE_NODE_TYPES: NodeTypes = { lineage: LineageNode };
