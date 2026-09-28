import { cn } from "~/lib/utils";

/**
 * Hand-rolled controls (section tabs, segmented toggles, list rows) share the
 * motion of ~/components/ui/button: colours eased with `ease-apple`, a slight
 * press-in, and the same soft focus ring, so every clickable thing feels alike.
 */

/** An underlined section tab, as in Explorer, Report lineage, and Scanner. */
export function sectionTabClass(active: boolean, className?: string) {
  return cn(
    "relative border-b-2 text-sm outline-none transition-[color,border-color,background-color] duration-300 ease-apple focus-visible:rounded-t-md focus-visible:bg-accent/50 focus-visible:text-foreground active:bg-accent/40",
    active
      ? "border-fabric font-semibold text-fabric"
      : "border-transparent text-muted-foreground hover:border-foreground/20 hover:text-foreground",
    className,
  );
}

/** The track of an apple.com-style segmented control. */
export const segmentGroupClass = "inline-flex rounded-full border border-border bg-subtle p-1";

/** One option of a segmented control; the chosen one lifts onto a raised pill. */
export function segmentClass(active: boolean, className?: string) {
  return cn(
    "inline-flex items-center gap-2 rounded-full px-3.5 text-sm font-medium whitespace-nowrap outline-none transition-[color,background-color,box-shadow,scale] duration-300 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]",
    active
      ? "bg-surface text-foreground shadow-[0_1px_2px_rgb(0_0_0/0.06),0_4px_14px_-4px_rgb(0_0_0/0.14)]"
      : "text-muted-foreground hover:bg-surface/60 hover:text-foreground",
    className,
  );
}

/** A small text action inside a panel ("Select all", "Clear", "Done"). */
export const textActionClass =
  "rounded-full px-2 py-0.5 text-xs font-medium outline-none transition-[color,background-color,scale] duration-200 ease-apple hover:bg-muted focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-95 disabled:pointer-events-none disabled:opacity-45";

/** A compact icon-only action (copy, remove, collapse). */
export const iconActionClass =
  "inline-flex items-center justify-center rounded-full outline-none transition-[color,background-color,scale] duration-200 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-90";
