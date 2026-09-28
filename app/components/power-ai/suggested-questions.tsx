import { suggestedQuestionsFor } from "~/lib/power-ai-suggestions";
import { usePowerAiChat } from "~/lib/use-power-ai-chat";
import { usePowerAiStore } from "~/stores/power-ai-store";

export function SuggestedQuestions() {
  const context = usePowerAiStore((state) => state.context);
  const messages = usePowerAiStore((state) => state.messages);
  const loading = usePowerAiStore((state) => state.loading);
  const { send } = usePowerAiChat();

  if (messages.length) return null;
  const questions = suggestedQuestionsFor(context);

  return (
    <div className="border-t border-zinc-200 px-4 py-3">
      <p className="mb-2 text-[11px] font-semibold uppercase text-zinc-400">Suggested questions</p>
      <div className="flex flex-wrap gap-1.5">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            disabled={loading}
            onClick={() => void send(question)}
            className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:border-fabric hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97] disabled:opacity-50"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
