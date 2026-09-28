import { Sparkles } from "lucide-react";

import { usePowerAiStore, type PowerAIContext } from "~/stores/power-ai-store";

/**
 * Reusable action wired onto pages with one clear focal object (a selected
 * report, table, or measure): merges that object into Power AI's shared
 * context, seeds a starting question, and opens Power AI — without coupling
 * the page to the chat implementation itself.
 */
export function AskPowerAiButton({ context, question, label = "Ask Power AI" }: { context: PowerAIContext; question: string; label?: string }) {
  function open() {
    usePowerAiStore.getState().mergeContext(context);
    usePowerAiStore.getState().setPendingQuestion(question);
    usePowerAiStore.getState().setWidgetOpen(true);
  }

  return (
    <button
      type="button"
      onClick={open}
      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-3 text-xs font-medium text-teal-800 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:border-teal-300 hover:bg-teal-100 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]"
    >
      <Sparkles className="size-3.5" />
      {label}
    </button>
  );
}
