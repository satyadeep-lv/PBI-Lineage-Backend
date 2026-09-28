import { ChevronsRight, Circle, Loader2, Maximize2, Minimize2, RotateCcw, Sparkles } from "lucide-react";

import { isUnlocked } from "~/lib/power-ai-api";
import { usePowerAiStatus } from "~/lib/use-power-ai-status";
import { usePowerAiStore } from "~/stores/power-ai-store";

const ICON_BUTTON = "flex size-8 items-center justify-center rounded-full text-muted-foreground transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-90";

export function PowerAiHeader({ onCollapse }: { onCollapse?: () => void }) {
  const hasMessages = usePowerAiStore((state) => state.messages.length > 0);
  const resetConversation = usePowerAiStore((state) => state.resetConversation);
  const expanded = usePowerAiStore((state) => state.expanded);
  const setExpanded = usePowerAiStore((state) => state.setExpanded);
  const statusQuery = usePowerAiStatus();
  const available = isUnlocked(statusQuery.data);

  return (
    <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <div className="flex min-w-0 items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground">
          <Sparkles className="size-4" />
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-foreground">Power AI</h2>
          <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
            {statusQuery.isLoading ? <Loader2 className="size-2.5 animate-spin" /> : <Circle className={available ? "size-2.5 fill-success text-success" : "size-2.5 fill-muted-foreground text-muted-foreground"} />}
            {statusQuery.isLoading ? "Checking" : available ? "Available" : "Unavailable"}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {hasMessages && (
          <button type="button" onClick={resetConversation} aria-label="Start a new conversation" title="Start a new conversation" className={ICON_BUTTON}>
            <RotateCcw className="size-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-pressed={expanded}
          aria-label={expanded ? "Narrow Power AI" : "Widen Power AI"}
          title={expanded ? "Narrow Power AI" : "Widen Power AI for long answers"}
          className={ICON_BUTTON}
        >
          {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
        </button>
        {onCollapse && (
          <button type="button" onClick={onCollapse} aria-label="Collapse Power AI" title="Collapse Power AI" className={ICON_BUTTON}>
            <ChevronsRight className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
