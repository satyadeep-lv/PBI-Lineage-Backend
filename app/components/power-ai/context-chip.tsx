import { File, History as HistoryIcon, MessageCircleQuestionMark, X, type LucideIcon } from "lucide-react";

import type { AiFocus, PowerAIContext } from "~/lib/power-ai-api";
import { objectTypeLabel } from "~/lib/power-ai-entities";
import { usePowerAiStore, type ChatMessage } from "~/stores/power-ai-store";

type Shown = { source: AiFocus["source"]; parts: string[] };

const SOURCE: Record<AiFocus["source"], { icon: LucideIcon; label: string }> = {
  page: { icon: File, label: "From this page" },
  question: { icon: MessageCircleQuestionMark, label: "Named in your question" },
  conversation: { icon: HistoryIcon, label: "From earlier in this conversation" },
};

function describe(parts: { objectType?: string | null; objectName?: string | null; reportName?: string | null; modelName?: string | null; workspaceName?: string | null }) {
  const shown: string[] = [];
  const type = parts.objectType ?? undefined;
  // A report or model selected as the object is already named by its own part below.
  if (parts.objectName && type && type !== "report" && type !== "semantic_model") shown.push(`${objectTypeLabel(type)}: ${parts.objectName}`);
  if (parts.reportName) shown.push(`Report: ${parts.reportName}`);
  if (parts.modelName) shown.push(`Model: ${parts.modelName}`);
  if (!shown.length && parts.workspaceName) shown.push(`Workspace: ${parts.workspaceName}`);
  return shown;
}

function fromFocus(focus: AiFocus): Shown {
  return {
    source: focus.source,
    parts: describe({ objectType: focus.object_type, objectName: focus.object_name, reportName: focus.report_name, modelName: focus.semantic_model_name, workspaceName: focus.workspace_name }),
  };
}

function fromContext(context: PowerAIContext): Shown {
  return {
    source: "page",
    parts: describe({ objectType: context.objectType, objectName: context.objectName, reportName: context.reportName, modelName: context.semanticModelName, workspaceName: context.workspaceName }),
  };
}

/** The last reply's focus, unless the page's context changed after it arrived. */
export function shownContext(messages: ChatMessage[], context: PowerAIContext, contextChangedAt: number): Shown {
  const last = [...messages].reverse().find((message) => message.role === "assistant" && message.answeredAt);
  if (last?.focus && (last.answeredAt ?? 0) >= contextChangedAt) {
    const focused = fromFocus(last.focus);
    if (focused.parts.length) return focused;
  }
  return fromContext(context);
}

/**
 * What Power AI will answer about, under the header. It makes a lost or
 * stale context visible before a question is asked, and lets it be cleared.
 */
export function ContextChip() {
  const messages = usePowerAiStore((state) => state.messages);
  const context = usePowerAiStore((state) => state.context);
  const contextChangedAt = usePowerAiStore((state) => state.contextChangedAt);
  const clearPageContext = usePowerAiStore((state) => state.clearPageContext);
  const shown = shownContext(messages, context, contextChangedAt);

  if (!shown.parts.length) {
    return (
      <div className="border-b border-zinc-100 px-4 py-2 text-xs text-zinc-400" data-testid="power-ai-context">
        Nothing selected - ask about a report or measure by name
      </div>
    );
  }

  const source = SOURCE[shown.source];
  return (
    <div className="flex items-center gap-2 border-b border-zinc-100 px-4 py-2" data-testid="power-ai-context">
      <span className="flex min-w-0 flex-1 items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 py-0.5 pr-1 pl-2 text-xs text-teal-900">
        <span role="img" aria-label={source.label} title={source.label} data-source={shown.source} className="shrink-0">
          <source.icon className="size-3.5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1 truncate" title={shown.parts.join(" · ")}>{shown.parts.join(" · ")}</span>
        <button
          type="button"
          onClick={clearPageContext}
          aria-label="Clear context for the next question"
          title="Clear context for the next question"
          className="flex size-5 shrink-0 items-center justify-center rounded-full text-teal-700 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:bg-teal-100 hover:text-teal-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 active:scale-90"
        >
          <X className="size-3" aria-hidden />
        </button>
      </span>
    </div>
  );
}
