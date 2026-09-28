import { Loader2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "~/lib/utils";

/** Presentational pieces shared by Table impact and Measure impact. */

export function SummaryTile({ icon: Icon, label, value, caption, pending }: { icon: LucideIcon; label: string; value: number; caption: string; pending: boolean }) {
  return <div className="rounded-lg border border-border bg-subtle px-4 py-3.5">
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs font-semibold uppercase text-muted-foreground">{label}</span>
      <span className="flex size-7 items-center justify-center rounded-md border border-fabric/20 bg-surface text-fabric"><Icon className="size-3.5" /></span>
    </div>
    <p className="mt-1.5 flex items-center gap-2 text-2xl font-semibold tabular-nums text-foreground">
      {value}
      {pending && <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Still checking" />}
    </p>
    <p className="mt-0.5 text-xs text-muted-foreground">{caption}</p>
  </div>;
}

export function ImpactSection({ icon: Icon, title, text, children }: { icon: LucideIcon; title: string; text: string; children: ReactNode }) {
  return <section className="space-y-3">
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 size-5 shrink-0 text-fabric" />
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-0.5 text-sm leading-6 text-muted-foreground">{text}</p>
      </div>
    </div>
    {children}
  </section>;
}

export function StatusBand({ tone, text, loading = false }: { tone: "success" | "warning" | "info"; text: string; loading?: boolean }) {
  return <div className={cn(
    "flex items-center gap-2 border px-3 py-2 text-xs",
    tone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : tone === "warning" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-sky-200 bg-sky-50 text-sky-900",
  )}>
    {loading && <Loader2 className="size-3.5 shrink-0 animate-spin" />}
    {text}
  </div>;
}

export function LoadingState({ label }: { label: string }) {
  return <div className="flex min-h-[320px] items-center justify-center gap-2 text-sm text-zinc-500"><Loader2 className="size-4 animate-spin" />{label}</div>;
}

export function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="border border-zinc-200 bg-white p-10 text-center"><p className="text-sm font-semibold">{title}</p><p className="mt-1 text-sm text-zinc-500">{text}</p></div>;
}

/** Shown on both grids' pages when the list of reports could not be loaded, so no report or visual usage exists. */
export const REPORT_LIST_FAILED_TEXT = "Report usage is not available because the list of reports could not be loaded.";

const reportsWord = (count: number) => (count === 1 ? "report" : "reports");

/**
 * Report-usage band shared by both pages: first whether the list of reports
 * loaded, then the check of the visuals in the reports connected to the
 * semantic models (wording from Docs/07-column-naming-standard.md).
 */
export function EvidenceStatus({ estateLoading, estateError, boundCount, loading, truncated, noBoundText }: {
  estateLoading: boolean;
  estateError: boolean;
  boundCount: number;
  loading: boolean;
  truncated: boolean;
  noBoundText: string;
}) {
  if (estateError) return <StatusBand tone="warning" text="The list of reports could not be loaded for your account. Report and visual usage cannot be shown; the dependency results remain accurate." />;
  if (estateLoading) return <StatusBand tone="info" loading text="Finding the reports connected to these semantic models..." />;
  if (!boundCount) return <StatusBand tone="warning" text={noBoundText} />;
  if (loading) return <StatusBand tone="info" loading text={`Checking the visuals in ${boundCount} connected ${reportsWord(boundCount)}`} />;
  if (truncated) return <StatusBand tone="warning" text="Report usage was checked in the first 300 connected reports of at least one semantic model." />;
  return <StatusBand tone="success" text={`Checked the visuals in ${boundCount} connected ${reportsWord(boundCount)}.`} />;
}
