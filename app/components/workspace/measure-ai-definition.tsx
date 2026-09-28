import { Download, FileText, Loader2, MessageCircleQuestionMark, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AnswerView } from "~/components/power-ai/answer-view";
import { CopyButton } from "~/components/power-ai/copy-button";
import { Button } from "~/components/ui/button";
import {
  buildChatRequest,
  explainObject,
  type AiChatResponse,
  type PowerAiApiError,
  type PowerAiAudience,
  type PowerAIContext,
} from "~/lib/power-ai-api";
import { parseAnswer, sectionTabs } from "~/lib/power-ai-answer";
import { contextForEntity, entityQuestion, type AnswerEntity } from "~/lib/power-ai-entities";
import { evidenceLine, groupBySection, isContextItem } from "~/lib/power-ai-evidence";
import { COLUMN, VALUE } from "~/lib/naming";
import { AI_ERROR_COPY } from "~/lib/use-power-ai-chat";
import { prefersReducedMotion } from "~/lib/use-revealed-text";
import { cn } from "~/lib/utils";
import { useAppStore } from "~/stores/app-store";
import { usePowerAiStore } from "~/stores/power-ai-store";

/** One selectable measure, carrying the mapping already on screen for it. */
export type MeasureDefinitionTarget = {
  key: string;
  table: string;
  name: string;
  daxExpression: string;
  /** The Database columns cell of the mapping grid: names joined with ", ", or a standard missing value. */
  databaseColumns: string;
  /** The Database tables cell of the mapping grid: full names joined with ", ", or a standard missing value. */
  databaseTables: string;
};

/** Field labels of the downloaded definition that are not grid headers (Docs/07-column-naming-standard.md). */
const LABEL = {
  answerStatus: "Answer status",
  writtenBy: "Written by",
} as const;

/** The answer status in plain words, never the raw API code. */
const ANSWER_STATUS_LABELS: Record<AiChatResponse["status"], string> = {
  answered: "Answered",
  insufficient_evidence: "Not enough evidence",
  ambiguous: "Ambiguous",
  conflicting_evidence: "Conflicting evidence",
  out_of_scope: "Out of scope",
};

/**
 * Always the most detailed reader. This panel exists to show the DAX, its
 * sources and its dependencies in full, so there is nothing to choose.
 */
const AUDIENCE: PowerAiAudience = "developer";

const STATUS_NOTE: Partial<Record<AiChatResponse["status"], string>> = {
  insufficient_evidence: "Power AI did not have enough verified evidence to define this measure fully. What it could ground is below.",
  ambiguous: "Power AI found more than one possible reading of this measure. Narrow the selection and try again.",
  conflicting_evidence: "Power AI found conflicting evidence for this measure. Treat the definition below as unconfirmed.",
  out_of_scope: "Power AI treated this as outside what it can answer from this model's evidence.",
};

/** The staged wait text. Cosmetic: the request reports no progress, so these only say what usually takes the time. */
const LOADING_STAGES: Array<{ after: number; text: string }> = [
  { after: 4_000, text: "Reading DAX and lineage..." },
  { after: 12_000, text: "Checking reports for visual impact..." },
];

/** How long a card stays highlighted after its tab is used. */
const HIGHLIGHT_MS = 1_600;

/** The panel's tabs. Any other section (e.g. "What was checked") is still shown, as a card without a tab. */
const PANEL_TABS = new Set(["Overview", "DAX", "Semantic lineage", "Database", "Impact", "Visuals"]);

/**
 * The numbered structure steers how a model writes the answer up. The
 * evidence itself doesn't depend on the wording: for a selected measure the
 * backend gathers the same complete set whatever the question says.
 */
function questionFor(target: MeasureDefinitionTarget): string {
  return [
    `Explain the measure '${target.name}' in table '${target.table}'.`,
    "Cover five things, in this order:",
    "1. A plain-language definition of what this measure calculates.",
    "2. The DAX expression it uses, and what each part of that expression does.",
    "3. The sources that DAX reads - name the semantic tables, and the database tables and columns behind them.",
    "4. Which objects it reads, and which other measures or visuals build on it, including references that cross into another table or model.",
    "5. Which report visuals would change if it changed, and whether they use it directly or through another measure.",
  ].join(" ");
}

/** The response's evidence in answer-section order, without the context line the answer already opens with. */
function evidenceSections(response: AiChatResponse) {
  return groupBySection(response.evidence.filter((item) => !isContextItem(item)));
}

/**
 * A self-contained document, so a downloaded answer still says what it was
 * about and what backed it. The answer itself goes in verbatim in both formats,
 * followed by every evidence item — the screen shows less than this, the
 * download never does.
 */
function toDocument(target: MeasureDefinitionTarget, response: AiChatResponse, context: PowerAIContext, format: "md" | "txt"): string {
  const md = format === "md";
  const heading = (level: 1 | 2, text: string) => (md ? `${"#".repeat(level)} ${text}` : text);
  const field = (label: string, value: string) => (md ? `**${label}:** ${value}` : `${label}: ${value}`);
  const lines = [
    heading(1, target.name),
    "",
    field(COLUMN.semanticTable, target.table),
    field(COLUMN.workspaceName, context.workspaceName ?? VALUE.notAvailable),
    field(COLUMN.reportName, context.reportName ?? VALUE.notAvailable),
    field(COLUMN.semanticModel, context.semanticModelName ?? VALUE.notAvailable),
    field(COLUMN.databaseColumns, target.databaseColumns),
    field(COLUMN.databaseTables, target.databaseTables),
    field(LABEL.answerStatus, ANSWER_STATUS_LABELS[response.status] ?? response.status),
    field(LABEL.writtenBy, response.usage ? `Power AI (${response.usage.model})` : "Lineage evidence"),
    "",
    heading(2, "Definition"),
    "",
    response.answer || "Power AI returned no answer text.",
    "",
    heading(2, "DAX expression"),
    "",
    ...(md ? ["```dax", target.daxExpression, "```"] : [target.daxExpression]),
  ];
  evidenceSections(response).forEach(({ section, items }) => {
    lines.push("", heading(2, section.title), "");
    items.forEach((item) => lines.push(`- ${evidenceLine(item)} (${item.object_type}, ${item.source_type}, ${item.verification_status})`));
  });
  return `${lines.join("\n")}\n`;
}

function download(content: string, type: string, fileName: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

/** Says who wrote the answer up: a model (named in the tooltip) or the backend straight from the evidence. */
function AuthorBadge({ usage }: { usage: AiChatResponse["usage"] }) {
  return usage
    ? <span title={`Model: ${usage.model}`} className="inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-800"><Sparkles className="size-3" /> Written by Power AI</span>
    : <span className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] font-medium text-zinc-600">From lineage evidence</span>;
}

function fileStem(target: MeasureDefinitionTarget) {
  return `${target.table}-${target.name}`.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "measure-definition";
}

function qualified(target: MeasureDefinitionTarget) {
  return `${target.table}[${target.name}]`;
}

/**
 * Generates a full, reader-appropriate definition of one measure through the
 * backend's evidence-grounded Power AI route, inline beneath the mapping grid.
 * Unlike `AskPowerAiButton`, which hands its question to the shared chat
 * widget, this keeps the answer on the page so it can be explored and
 * downloaded. Only the definition is shown: the evidence behind it goes into
 * the downloads rather than being listed again under the answer.
 */
export function MeasureAiDefinition({ measures, context }: { measures: MeasureDefinitionTarget[]; context: PowerAIContext }) {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const [selectedKey, setSelectedKey] = useState("");
  const [generatingSince, setGeneratingSince] = useState<number | null>(null);
  const [result, setResult] = useState<{ target: MeasureDefinitionTarget; response: AiChatResponse } | null>(null);
  const [error, setError] = useState<PowerAiApiError | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const sectionElements = useRef(new Map<string, HTMLElement>());
  const request = useRef(0);

  const selected = useMemo(
    () => measures.find((measure) => measure.key === selectedKey) ?? measures[0] ?? null,
    [measures, selectedKey],
  );

  useEffect(() => {
    if (!highlighted) return;
    const timer = setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [highlighted]);

  const measureContext = (target: MeasureDefinitionTarget): PowerAIContext => ({ ...context, objectType: "measure", objectId: undefined, objectName: qualified(target) });

  async function generate(target = selected) {
    if (!target) return;
    const attempt = ++request.current;
    setGeneratingSince(Date.now());
    setError(null);
    setResult(null);
    try {
      const response = await explainObject(apiOrigin, buildChatRequest(questionFor(target), AUDIENCE, measureContext(target)));
      if (attempt === request.current) setResult({ target, response });
    } catch (caught) {
      if (attempt === request.current) setError(caught as PowerAiApiError);
    } finally {
      if (attempt === request.current) setGeneratingSince(null);
    }
  }

  /** A measure in this panel is defined here; anything else is asked in the chat, seeded but not sent. */
  function onEntity(entity: AnswerEntity) {
    const measure = entity.kind === "measure"
      ? measures.find((candidate) => (entity.qualifiedName ? qualified(candidate) === entity.qualifiedName : candidate.name === entity.name))
      : undefined;
    if (measure) {
      setSelectedKey(measure.key);
      void generate(measure);
      return;
    }
    const question = entityQuestion(entity);
    if (!question) return;
    const store = usePowerAiStore.getState();
    store.mergeContext(contextForEntity(result ? measureContext(result.target) : context, entity));
    store.setPendingQuestion(question);
    store.setWidgetOpen(true);
  }

  /** A follow-up goes to the chat with this measure as its context, and is sent straight away. */
  function followUp(question: string) {
    if (!result) return;
    const store = usePowerAiStore.getState();
    store.mergeContext(measureContext(result.target));
    store.queueQuestion(question);
    store.setWidgetOpen(true);
  }

  function goToSection(sectionId: string) {
    const element = sectionElements.current.get(sectionId);
    if (!element) return;
    element.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    element.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
    setHighlighted(sectionId);
  }

  const response = result?.response ?? null;
  const target = result?.target ?? null;
  const sections = useMemo(() => parseAnswer(response?.answer ?? ""), [response]);
  const tabs = useMemo(() => sectionTabs(sections).filter((tab) => PANEL_TABS.has(tab.label)), [sections]);
  const generating = generatingSince !== null;

  return <section className="border border-zinc-200">
    <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-3">
      <p className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-teal-700" /> Measure definition with Power AI</p>
      <p className="mt-0.5 max-w-3xl text-xs leading-5 text-zinc-500">Select a measure for its full definition: what it calculates, its DAX, the semantic tables and database columns that DAX reads, what builds on it, and which report visuals would change with it. Power AI writes this from verified lineage evidence when AI is enabled, and shows the evidence directly when it is not, so it works either way. Click a name to explore it; the downloads include every fact behind the answer.</p>
    </div>

    {!measures.length
      ? <p className="px-4 py-6 text-sm text-zinc-500">This semantic model returned no measures to define.</p>
      : <div className="space-y-5 p-4">
            <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_auto] md:items-end">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-600" htmlFor="measure-ai-measure">Measure</label>
                <select id="measure-ai-measure" value={selected?.key ?? ""} onChange={(event) => setSelectedKey(event.target.value)} className="h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100">
                  {measures.map((measure) => <option key={measure.key} value={measure.key}>{measure.table} · {measure.name}</option>)}
                </select>
              </div>
              <Button type="button" disabled={!selected || generating} onClick={() => void generate()} className="h-10">
                {generating ? <Loader2 className="size-4 motion-safe:animate-spin" /> : <Sparkles className="size-4" />}
                {generating ? "Generating" : "Power AI definition"}
              </Button>
            </div>

            {/* Always the vetted copy for the reason, never the raw backend message. */}
            {error && <div role="alert" className="border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-900">{AI_ERROR_COPY[error.reason] ?? AI_ERROR_COPY.unknown}</div>}

            {generating && <DefinitionSkeleton since={generatingSince} />}

            {response && target && <div className="space-y-4" data-testid="measure-definition">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200 pb-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-zinc-950">{target.name}</h3>
                    <AuthorBadge usage={response.usage} />
                  </div>
                  <p className="text-xs text-zinc-500">
                    {COLUMN.semanticTable} <span className="font-medium text-zinc-700">{target.table}</span>
                    {context.semanticModelName && <> · {COLUMN.semanticModel} <span className="font-medium text-zinc-700">{context.semanticModelName}</span></>}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <CopyButton text={response.answer} label="Copy answer" className="h-7 rounded-md border border-zinc-200 bg-white px-2.5">
                    <span>Copy</span>
                  </CopyButton>
                  <Button type="button" variant="outline" size="sm" title="Download as plain text" onClick={() => download(toDocument(target, response, context, "txt"), "text/plain;charset=utf-8", `${fileStem(target)}-definition.txt`)}><FileText className="size-3.5" /> .txt</Button>
                  <Button type="button" variant="outline" size="sm" title="Download as Markdown" onClick={() => download(toDocument(target, response, context, "md"), "text/markdown;charset=utf-8", `${fileStem(target)}-definition.md`)}><Download className="size-3.5" /> .md</Button>
                </div>
              </div>

              {STATUS_NOTE[response.status] && <p className="flex items-start gap-1.5 rounded-md bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-900"><MessageCircleQuestionMark className="mt-0.5 size-3.5 shrink-0" aria-hidden />{STATUS_NOTE[response.status]}</p>}

              <div className="space-y-3">
                {tabs.length > 1 && (
                  <nav aria-label="Answer sections" className="sticky top-16 z-10 -mx-1 flex flex-wrap gap-1 border-b border-zinc-200 bg-white/95 px-1 py-2 backdrop-blur-sm">
                    {tabs.map((tab) => (
                      <button
                        key={tab.label}
                        type="button"
                        onClick={() => goToSection(tab.sectionId)}
                        aria-current={highlighted === tab.sectionId ? "true" : undefined}
                        className={cn(
                          "rounded-full border px-3 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600",
                          highlighted === tab.sectionId ? "border-teal-700 bg-teal-700 text-white" : "border-zinc-200 text-zinc-700 hover:border-teal-700 hover:text-teal-900",
                        )}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </nav>
                )}
                <div className="text-sm leading-6 text-zinc-800">
                  {response.answer
                    ? <AnswerView
                        text={response.answer}
                        evidence={response.evidence}
                        variant="panel"
                        onEntity={onEntity}
                        entitiesDisabled={generating}
                        sectionRef={(sectionId, element) => {
                          if (element) sectionElements.current.set(sectionId, element);
                          else sectionElements.current.delete(sectionId);
                        }}
                        highlightedSectionId={highlighted}
                      />
                    : "Power AI returned no answer text."}
                </div>
              </div>

              {response.suggested_questions.length > 0 && (
                <div className="space-y-1.5 border-t border-zinc-200 pt-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Ask Power AI next</p>
                  <div className="flex flex-wrap gap-1.5">
                    {response.suggested_questions.map((question) => (
                      <button
                        key={question}
                        type="button"
                        onClick={() => followUp(question)}
                        className="rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-left text-xs text-teal-900 hover:border-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {response.evidence.length > 0 && <p className="text-xs text-zinc-500">Grounded in {response.evidence.length} verified {response.evidence.length === 1 ? "fact" : "facts"}{response.claims.length ? ` across ${response.claims.length} ${response.claims.length === 1 ? "claim" : "claims"}` : ""}. All of it is included in the downloads.</p>}
            </div>}
          </div>}
  </section>;
}

/** The shape of the answer while it is generated, with a line about what usually takes the time. */
function DefinitionSkeleton({ since }: { since: number | null }) {
  const [stage, setStage] = useState(-1);

  useEffect(() => {
    if (since === null) return;
    setStage(-1);
    const timers = LOADING_STAGES.map((entry, position) => setTimeout(() => setStage(position), Math.max(0, entry.after - (Date.now() - since))));
    return () => timers.forEach(clearTimeout);
  }, [since]);

  const bar = "rounded bg-zinc-200/80 motion-safe:animate-pulse";
  return (
    <div aria-busy="true" className="space-y-4" data-testid="measure-definition-loading">
      <div className="space-y-2 border-b border-zinc-200 pb-3">
        <div className={cn(bar, "h-5 w-48")} />
        <div className={cn(bar, "h-3 w-64")} />
      </div>
      <div className="flex gap-1.5">
        {[64, 44, 104, 72].map((width) => <div key={width} className={cn(bar, "h-6 rounded-full")} style={{ width }} />)}
      </div>
      {[0, 1, 2].map((card) => (
        <div key={card} className="space-y-2 rounded-lg border border-zinc-200 p-3">
          <div className={cn(bar, "h-4 w-40")} />
          <div className={cn(bar, "h-3 w-full")} />
          <div className={cn(bar, "h-3 w-5/6")} />
        </div>
      ))}
      <p aria-live="polite" className="flex items-center gap-2 text-xs text-zinc-500">
        <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden />
        {stage >= 0 ? LOADING_STAGES[stage].text : "Generating the definition"}
      </p>
    </div>
  );
}
