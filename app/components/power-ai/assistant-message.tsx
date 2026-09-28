import { ChevronDown, ChevronRight, Loader2, MessageCircleQuestionMark, RotateCw, ShieldAlert, type LucideIcon } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { AnswerView } from "~/components/power-ai/answer-view";
import { CopyButton } from "~/components/power-ai/copy-button";
import { EvidenceView, listedEvidence } from "~/components/power-ai/evidence-view";
import type { AiChatResponseStatus } from "~/lib/power-ai-api";
import { contextForEntity, entityQuestion, type AnswerEntity } from "~/lib/power-ai-entities";
import { useRevealedText } from "~/lib/use-revealed-text";
import { cn } from "~/lib/utils";
import { usePowerAiStore, type ChatMessage, type PowerAiAudience } from "~/stores/power-ai-store";

/**
 * The first question about an object can take ~25 seconds while the backend
 * loads every report on the model for visual impact, so a wait that long says
 * what is happening. Timed from the message itself, so a remount (e.g. a
 * responsive layout switch) doesn't restart it.
 */
const SLOW_AFTER_MS = 6_000;

function PendingLabel({ createdAt }: { createdAt: number }) {
  const [slow, setSlow] = useState(() => Date.now() - createdAt >= SLOW_AFTER_MS);

  useEffect(() => {
    if (slow) return;
    const timer = setTimeout(() => setSlow(true), Math.max(0, SLOW_AFTER_MS - (Date.now() - createdAt)));
    return () => clearTimeout(timer);
  }, [createdAt, slow]);

  return (
    <span className="flex items-center gap-2 text-zinc-500">
      <Loader2 className="size-3.5 motion-safe:animate-spin" /> {slow ? "Gathering lineage evidence..." : "Thinking"}
    </span>
  );
}

/**
 * How a reply that isn't a full answer opens. It keeps the backend's status
 * and says what it means in a sentence, instead of a warning box; the
 * suggestions under it are the way forward.
 */
const STATUS_NOTE: Partial<Record<AiChatResponseStatus, { text: string; icon: LucideIcon; tone: string }>> = {
  insufficient_evidence: { text: "I need a bit more to go on", icon: MessageCircleQuestionMark, tone: "text-sky-900" },
  ambiguous: { text: "More than one thing matches. Which did you mean?", icon: MessageCircleQuestionMark, tone: "text-sky-900" },
  out_of_scope: { text: "That's outside what I can check from lineage metadata", icon: MessageCircleQuestionMark, tone: "text-zinc-700" },
  conflicting_evidence: { text: "Conflicting evidence found. Both sides are shown in Sources", icon: ShieldAlert, tone: "text-rose-900" },
};

export function AssistantMessage({ message, latest, busy, audience, onSend }: {
  message: ChatMessage;
  latest: boolean;
  busy: boolean;
  audience: PowerAiAudience;
  onSend: (question: string) => void;
}) {
  const text = useRevealedText(message.id, message.text, { enabled: Boolean(message.streamed), pending: Boolean(message.pending) });
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sourcesId = useId();

  const note = message.status ? STATUS_NOTE[message.status] : undefined;
  const nonAnswer = Boolean(note) && message.status !== "conflicting_evidence";
  const suggestions = message.suggestedQuestions ?? [];
  const sourceCount = listedEvidence(message.evidence ?? []).length;
  const hasSources = sourceCount > 0 || Boolean(message.claims?.length);
  const done = !message.pending && text.length === message.text.length;

  function askAbout(entity: AnswerEntity) {
    const question = entityQuestion(entity);
    if (!question) return;
    const store = usePowerAiStore.getState();
    store.mergeContext(contextForEntity(store.context, entity));
    onSend(question);
  }

  if (message.pending && !text) {
    return <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"><PendingLabel createdAt={message.createdAt} /></div>;
  }

  return (
    <div
      className="space-y-2.5 rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-sm leading-6 text-zinc-900"
      data-revealed={text.length}
      data-total={message.text.length}
    >
      {note && (
        <p className={cn("flex items-center gap-1.5 font-medium", note.tone)}>
          <note.icon className="size-4 shrink-0" aria-hidden /> {note.text}
        </p>
      )}

      {text && (
        <div className={cn(nonAnswer && "text-zinc-600")}>
          <AnswerView text={text} evidence={message.evidence} variant="chat" onEntity={askAbout} entitiesDisabled={busy || !done} />
        </div>
      )}

      {latest && done && suggestions.length > 0 && (
        <div className={cn("flex flex-wrap gap-1.5", nonAnswer && "rounded-md bg-sky-50 p-2")}>
          {nonAnswer && <p className="w-full text-xs font-medium text-sky-900">Try one of these:</p>}
          {suggestions.map((question) => (
            <button
              key={question}
              type="button"
              disabled={busy}
              onClick={() => onSend(question)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-left text-xs transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 active:scale-[0.97]",
                nonAnswer
                  ? "border-sky-300 bg-white font-medium text-sky-900 hover:border-sky-700"
                  : "border-zinc-200 text-zinc-700 hover:border-zinc-950 hover:text-zinc-950",
              )}
            >
              {question}
            </button>
          ))}
        </div>
      )}

      {done && message.text && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-zinc-100 pt-2">
          <CopyButton text={message.text} label="Copy answer"><span>Copy answer</span></CopyButton>
          {message.question && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onSend(message.question!)}
              className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-zinc-500 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:text-zinc-950 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 active:scale-95"
            >
              <RotateCw className="size-3.5" aria-hidden /> Ask again
            </button>
          )}
          {hasSources && (
            <button
              type="button"
              aria-expanded={sourcesOpen}
              aria-controls={sourcesId}
              onClick={() => setSourcesOpen((open) => !open)}
              className="ml-auto inline-flex items-center gap-1 rounded-md text-xs font-medium text-zinc-500 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:text-zinc-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 active:scale-95"
            >
              {sourcesOpen ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
              Sources ({sourceCount})
            </button>
          )}
        </div>
      )}

      {sourcesOpen && <EvidenceView id={sourcesId} evidence={message.evidence ?? []} claims={message.claims} status={message.status} audience={audience} />}
    </div>
  );
}
