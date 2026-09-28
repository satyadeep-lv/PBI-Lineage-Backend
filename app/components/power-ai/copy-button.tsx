import { Check, Copy } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { cn } from "~/lib/utils";

/** Copies `text` exactly as given and confirms for a moment. `label` names what is copied, for screen readers too. */
export function CopyButton({ text, label, children, className }: { text: string; label: string; children?: ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard access can be refused; the text is still selectable on screen.
    }
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center gap-1 rounded-md text-xs font-medium text-zinc-500 transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple hover:text-zinc-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 active:scale-95",
        className,
      )}
    >
      {copied ? <Check className="size-3.5 text-emerald-600" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      {children}
      <span aria-live="polite" className="sr-only">{copied ? "Copied" : ""}</span>
    </button>
  );
}
