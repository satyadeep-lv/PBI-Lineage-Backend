import { Lock, Sparkles } from "lucide-react";

import { isUnlocked } from "~/lib/power-ai-api";
import { usePowerAiStatus } from "~/lib/use-power-ai-status";
import { cn } from "~/lib/utils";

/**
 * The one lock/unlock-aware trigger button for opening Power AI — a white
 * pill with the app's teal accent (matching every icon badge elsewhere) and
 * a restrained availability accent while unlocked.
 * `className` is for the caller's positioning only (e.g. fixed placement) —
 * this component owns all of its own visual styling.
 */
export function PowerAiTrigger({ onClick, className }: { onClick: () => void; className?: string }) {
  const statusQuery = usePowerAiStatus();
  const unlocked = isUnlocked(statusQuery.data);

  return (
    <span className={cn("relative inline-flex", className)}>
      <button
        type="button"
        onClick={onClick}
        aria-label={unlocked ? "Open Power AI" : "Power AI is locked"}
        title="Power AI"
        className="relative flex items-center justify-center gap-2 rounded-full border border-fabric/60 bg-surface px-4 py-2.5 text-sm font-semibold text-fabric shadow-lg transition-[background-color,box-shadow,translate,scale] duration-300 ease-apple hover:-translate-y-0.5 hover:bg-accent hover:shadow-xl focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]"
      >
        {unlocked ? <Sparkles className="size-4 shrink-0" /> : <Lock className="size-4 shrink-0" />}
        <span>Power AI</span>
      </button>
    </span>
  );
}
