import {
  Braces,
  ChartColumn,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  Info,
  Layers,
  Lightbulb,
  ListChecks,
  Network,
  Table2,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useId, useMemo, useState, type ReactNode } from "react";

import { CopyButton } from "~/components/power-ai/copy-button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import { highlightDax, type DaxTokenType } from "~/lib/dax-highlight";
import type { EvidenceItem } from "~/lib/power-ai-api";
import { answerLineCount, parseAnswer, type AnswerBlock, type AnswerSection, type AnswerSectionKind } from "~/lib/power-ai-answer";
import { buildEntityIndex, entityQuestion, linkify, type AnswerEntity, type EntityIndex } from "~/lib/power-ai-entities";
import { cn } from "~/lib/utils";

/**
 * The one interactive renderer for a Power AI answer, shared by the chat and
 * the measure panel. It lays the answer out as cards and turns names the
 * evidence backs into chips. It never changes the answer: copy and download
 * still use the stored text.
 */

const SECTION_ICON: Record<AnswerSectionKind, LucideIcon> = {
  lead: Info,
  plain: Lightbulb,
  dax: Braces,
  semantic: Network,
  database: Database,
  dependents: Layers,
  tables: Table2,
  visuals: ChartColumn,
  report: FileText,
  coverage: ListChecks,
  other: Info,
};

/** A chat answer longer than this many lines starts with its later sections collapsed. */
const LONG_ANSWER_LINES = 12;
/** How many cards stay open in a long chat answer. */
const OPEN_CARDS = 2;

export type AnswerViewProps = {
  text: string;
  evidence?: EvidenceItem[];
  variant: "chat" | "panel";
  /** Called when a chip with a question is activated. Without it, chips only show their tooltip. */
  onEntity?: (entity: AnswerEntity) => void;
  /** Disables chip clicks, e.g. while an answer is still arriving. */
  entitiesDisabled?: boolean;
  /** Lets the measure panel's tabs scroll to a card. */
  sectionRef?: (sectionId: string, element: HTMLElement | null) => void;
  highlightedSectionId?: string | null;
};

export function AnswerView({ text, evidence = [], variant, onEntity, entitiesDisabled = false, sectionRef, highlightedSectionId }: AnswerViewProps) {
  const sections = useMemo(() => parseAnswer(text), [text]);
  const index = useMemo(() => buildEntityIndex(evidence), [evidence]);
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const [expandAll, setExpandAll] = useState(false);
  const descriptionPrefix = useId();

  const leading = sections.filter((section) => section.kind === "lead" || section.kind === "plain");
  const cards = sections.filter((section) => section.kind !== "lead" && section.kind !== "plain");
  const long = variant === "chat" && answerLineCount(text) > LONG_ANSWER_LINES;
  const isCollapsed = (section: AnswerSection, position: number) =>
    overrides[section.id] ?? (!expandAll && long && position >= OPEN_CARDS);
  const hiddenCount = cards.filter((section, position) => isCollapsed(section, position)).length;

  const chips: ChipContext = { index, onEntity, disabled: entitiesDisabled, descriptionPrefix };

  return (
    <TooltipProvider delay={150}>
      <div className="space-y-3 break-words" data-answer-view={variant}>
        {leading.map((section) => (
          <section key={section.id} ref={(element) => sectionRef?.(section.id, element)} className={cn("scroll-mt-32 rounded-md transition-shadow", highlightedSectionId === section.id && "ring-2 ring-teal-500 ring-offset-2")}>
            {section.displayTitle && (
              <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                <Lightbulb className="size-3.5 text-amber-500" aria-hidden /> {section.displayTitle}
              </h3>
            )}
            <Blocks blocks={section.blocks} chips={chips} />
          </section>
        ))}

        {cards.map((section, position) => (
          <SectionCard
            key={section.id}
            section={section}
            collapsed={isCollapsed(section, position)}
            onToggle={() => setOverrides((current) => ({ ...current, [section.id]: !isCollapsed(section, position) }))}
            chips={chips}
            sectionRef={sectionRef}
            highlighted={highlightedSectionId === section.id}
          />
        ))}

        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => {
              setOverrides({});
              setExpandAll(true);
            }}
            className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-teal-800 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:text-teal-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
          >
            <ChevronDown className="size-3.5" aria-hidden /> Show full answer ({hiddenCount} more {hiddenCount === 1 ? "section" : "sections"})
          </button>
        )}

        {/* Referenced by each chip's aria-describedby, so its tooltip fact is announced too. */}
        <div hidden>
          {index.entries.map((entity) => (
            <span key={entity.text} id={describedBy(descriptionPrefix, entity)}>{entity.typeLabel}{entity.detail ? `: ${entity.detail}` : ""}</span>
          ))}
        </div>
      </div>
    </TooltipProvider>
  );
}

type ChipContext = {
  index: EntityIndex;
  onEntity?: (entity: AnswerEntity) => void;
  disabled: boolean;
  descriptionPrefix: string;
};

function describedBy(prefix: string, entity: AnswerEntity) {
  return `${prefix}-entity-${entity.text.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

function SectionCard({ section, collapsed, onToggle, chips, sectionRef, highlighted }: {
  section: AnswerSection;
  collapsed: boolean;
  onToggle: () => void;
  chips: ChipContext;
  sectionRef?: AnswerViewProps["sectionRef"];
  highlighted: boolean;
}) {
  const Icon = SECTION_ICON[section.kind];
  const bodyId = useId();
  return (
    <section
      ref={(element) => sectionRef?.(section.id, element)}
      data-section-kind={section.kind}
      className={cn("scroll-mt-32 rounded-lg border border-zinc-200 bg-white transition-shadow", highlighted && "ring-2 ring-teal-500 ring-offset-2")}
    >
      <h3 className="text-sm font-semibold text-zinc-950">
        <button
          type="button"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          onClick={onToggle}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
        >
          <Icon className="size-4 shrink-0 text-teal-700" aria-hidden />
          <span className="min-w-0 flex-1">{section.displayTitle}</span>
          {collapsed ? <ChevronRight className="size-4 shrink-0 text-zinc-400" aria-hidden /> : <ChevronDown className="size-4 shrink-0 text-zinc-400" aria-hidden />}
        </button>
      </h3>
      {!collapsed && (
        <div id={bodyId} className="border-t border-zinc-100 px-3 py-2.5">
          <Blocks blocks={section.blocks} chips={chips} />
        </div>
      )}
    </section>
  );
}

function Blocks({ blocks, chips }: { blocks: AnswerBlock[]; chips: ChipContext }) {
  return (
    <div className="space-y-2">
      {blocks.map((block, position) => {
        switch (block.kind) {
          case "items":
            return (
              <ul key={position} className="divide-y divide-zinc-100">
                {block.items.map((item, itemPosition) => (
                  <li key={itemPosition} className="flex gap-2 py-1 first:pt-0 last:pb-0">
                    <span aria-hidden className="mt-[0.6rem] size-1.5 shrink-0 rounded-full bg-teal-600/60" />
                    <span className="min-w-0 whitespace-pre-wrap">
                      <Linked text={item} chips={chips} />
                    </span>
                  </li>
                ))}
              </ul>
            );
          case "code":
            return <DaxBlock key={position} lines={block.lines} />;
          case "note":
            return <p key={position} className="pl-3 font-mono text-[11px] text-zinc-400">{block.text}</p>;
          default:
            return (
              <p key={position} className="whitespace-pre-wrap">
                <Linked text={block.lines.join("\n")} chips={chips} />
              </p>
            );
        }
      })}
    </div>
  );
}

function Linked({ text, chips }: { text: string; chips: ChipContext }) {
  const segments = linkify(text, chips.index);
  return (
    <>
      {segments.map((segment, position) =>
        typeof segment === "string" ? (
          <Fragment key={position}>{segment}</Fragment>
        ) : (
          <EntityChip
            key={position}
            entity={segment.entity}
            onEntity={chips.onEntity}
            disabled={chips.disabled}
            describedById={describedBy(chips.descriptionPrefix, segment.entity)}
          >
            {segment.text}
          </EntityChip>
        ),
      )}
    </>
  );
}

/**
 * A name the evidence backs: its fact in a tooltip, and a follow-up question
 * when clicked. Keeps the exact original text. `describedById` points at an
 * element holding the same fact, so it is announced as well as hovered.
 */
export function EntityChip({ entity, onEntity, disabled = false, describedById, children, className }: {
  entity: AnswerEntity;
  onEntity?: (entity: AnswerEntity) => void;
  disabled?: boolean;
  describedById?: string;
  children: ReactNode;
  className?: string;
}) {
  const question = entityQuestion(entity);
  const actionable = Boolean(question && onEntity);
  const tone = entity.kind === "database"
    ? "bg-sky-50 text-sky-900 decoration-sky-300"
    : entity.kind === "visual" || entity.kind === "report" || entity.kind === "page"
      ? "bg-violet-50 text-violet-900 decoration-violet-300"
      : "bg-teal-50 text-teal-900 decoration-teal-300";
  const shared = cn(
    "rounded-sm px-0.5 font-semibold underline decoration-dotted underline-offset-2 [box-decoration-break:clone] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600",
    tone,
    className,
  );
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          actionable ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onEntity?.(entity)}
              aria-describedby={describedById}
              data-entity-kind={entity.kind}
              className={cn(shared, "inline cursor-pointer text-left hover:brightness-95 disabled:cursor-default")}
            />
          ) : (
            <span tabIndex={0} aria-describedby={describedById} data-entity-kind={entity.kind} className={cn(shared, "cursor-help")} />
          )
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-sm">
        <span className="flex flex-col gap-0.5 text-left">
          <span className="font-semibold">{entity.typeLabel}{entity.qualifiedName && entity.qualifiedName !== entity.text ? ` · ${entity.qualifiedName}` : ""}</span>
          {entity.detail && <span className="font-normal opacity-90">{entity.detail}</span>}
          {actionable && <span className="text-[11px] opacity-70">Click to ask: {question}</span>}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}

const TOKEN_CLASS: Record<DaxTokenType, string> = {
  plain: "",
  function: "text-sky-700 font-semibold",
  reference: "text-teal-800 font-semibold",
  string: "text-amber-700 font-semibold",
  number: "text-violet-700 font-semibold",
  comment: "text-zinc-500 font-semibold italic",
};

/** DAX as sent, coloured by a tokenizer that never changes a character. The copy button copies these exact lines. */
export function DaxBlock({ lines }: { lines: string[] }) {
  const code = lines.join("\n");
  const tokens = useMemo(() => highlightDax(code), [code]);
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 py-2 pr-16 pl-3 font-mono text-[12px] leading-5 text-zinc-800">
        <code>
          {tokens.map((token, position) => (token.type === "plain" ? token.text : <span key={position} className={TOKEN_CLASS[token.type]}>{token.text}</span>))}
        </code>
      </pre>
      <CopyButton text={code} label="Copy DAX" className="absolute top-1.5 right-1.5 rounded border border-zinc-200 bg-white px-1.5 py-0.5">
        <span>Copy</span>
      </CopyButton>
    </div>
  );
}
