import { ArrowDown, ArrowRight } from "lucide-react";
import { Fragment, useId, useState } from "react";

import { EntityChip } from "~/components/power-ai/answer-view";
import { TooltipProvider } from "~/components/ui/tooltip";
import type { AnswerEntity } from "~/lib/power-ai-entities";
import type { LineageCard, LineageLayer } from "~/lib/power-ai-lineage";
import { cn } from "~/lib/utils";

/** Cards shown per layer before "more"; a measure can reach dozens of visuals. */
const VISIBLE_CARDS = 6;

type CardProps = { onEntity: (entity: AnswerEntity) => void; disabled?: boolean; descriptionId: (layer: LineageLayer["id"], card: LineageCard) => string };

/**
 * The measure's evidence as layers, database to visuals, with one arrow
 * between neighbouring layers. It shows which layer each item is in and
 * nothing more: the evidence doesn't say which input feeds which dependent,
 * so no card is joined to another.
 */
export function LineageStrip({ layers, onEntity, disabled }: { layers: LineageLayer[]; onEntity: (entity: AnswerEntity) => void; disabled?: boolean }) {
  const headingId = useId();
  const descriptionId: CardProps["descriptionId"] = (layer, card) => `${headingId}-${layer}-${card.key}`;
  return (
    <TooltipProvider delay={150}>
      <section aria-labelledby={headingId} className="rounded-lg border border-zinc-200 bg-zinc-50/70 p-3">
        <h3 id={headingId} className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Lineage</h3>
        <div role="list" className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
          {layers.map((layer, position) => (
            <Fragment key={layer.id}>
              {position > 0 && (
                <div aria-hidden className="flex items-center justify-center text-zinc-400">
                  <ArrowDown className="size-4 lg:hidden" />
                  <ArrowRight className="hidden size-4 lg:block" />
                </div>
              )}
              <LayerColumn layer={layer} onEntity={onEntity} disabled={disabled} descriptionId={descriptionId} />
            </Fragment>
          ))}
        </div>
        {/* Each card's fact, referenced by its chip's aria-describedby. */}
        <div hidden>
          {layers.flatMap((layer) => layer.cards.filter((card) => card.entity?.detail).map((card) => (
            <span key={`${layer.id}-${card.key}`} id={descriptionId(layer.id, card)}>{card.entity!.detail}</span>
          )))}
        </div>
      </section>
    </TooltipProvider>
  );
}

function LayerColumn({ layer, ...props }: { layer: LineageLayer } & CardProps) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? layer.cards : layer.cards.slice(0, VISIBLE_CARDS);
  const hidden = layer.cards.length - shown.length;
  return (
    <div role="listitem" data-layer={layer.id} className="min-w-0 flex-1 lg:max-w-[20%]">
      <p className="mb-1 text-[11px] font-semibold text-zinc-600">
        {layer.title}
        {layer.cards.length > 0 && layer.id !== "measure" && <span className="ml-1 font-normal text-zinc-400">{layer.cards.length}</span>}
      </p>
      {layer.cards.length ? (
        <ul className="space-y-1">
          {shown.map((card) => (
            <li key={card.key}>
              <CardView layer={layer.id} card={card} primary={layer.id === "measure"} {...props} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-md border border-dashed border-zinc-200 px-2 py-1 text-xs text-zinc-400">none found</p>
      )}
      {layer.cards.length > VISIBLE_CARDS && (
        <button
          type="button"
          onClick={() => setShowAll((value) => !value)}
          className="mt-1 rounded-sm text-[11px] font-medium text-teal-800 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:text-teal-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
        >
          {showAll ? "Show fewer" : `+${hidden} more`}
        </button>
      )}
    </div>
  );
}

function CardView({ layer, card, primary, onEntity, disabled, descriptionId }: { layer: LineageLayer["id"]; card: LineageCard; primary: boolean } & CardProps) {
  return (
    <div className={cn("rounded-md border bg-white px-2 py-1 text-xs leading-5", primary ? "border-teal-300 bg-teal-50/60 font-semibold" : "border-zinc-200")}>
      <span className="block break-words">
        {card.entity && !primary ? (
          <EntityChip entity={card.entity} onEntity={onEntity} disabled={disabled} describedById={card.entity.detail ? descriptionId(layer, card) : undefined}>
            {card.label}
          </EntityChip>
        ) : (
          card.label
        )}
      </span>
      {card.caption && <span className="block truncate text-[11px] font-normal text-zinc-500" title={card.caption}>{card.caption}</span>}
    </div>
  );
}
