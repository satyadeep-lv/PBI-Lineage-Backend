import { Lock, PowerOff, ShieldAlert } from "lucide-react";

import type { AiUnavailableReason } from "~/lib/power-ai-api";

const UNAVAILABLE_COPY: Partial<Record<AiUnavailableReason, string>> = {
  disabled: "Power AI is not enabled for this environment.",
  not_configured: "Power AI hasn't been configured yet.",
  provider_unavailable: "The AI backend is temporarily unavailable. Try again shortly.",
  rate_limited: "Power AI is receiving too many requests right now. Try again shortly.",
  timeout: "The AI backend didn't respond in time. Try again shortly.",
};

/**
 * Shown in place of the chat UI whenever Power AI isn't usable yet. This is a
 * UX affordance only — the backend enforces the real authorization on every
 * /api/v1/ai/* call regardless of what this component shows.
 */
export function PowerAiLocked({ reason }: { reason: AiUnavailableReason }) {
  if (reason === "auth_required") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
        <Lock className="size-6 text-zinc-400" />
        <div>
          <p className="text-sm font-semibold text-zinc-900">Power AI</p>
          <p className="mt-1.5 max-w-[240px] text-xs leading-5 text-zinc-500">
            Complete Power BI setup with a device code or a service principal to unlock the AI assistant.
          </p>
        </div>
        <a href="/workspace/power-bi" className="mt-1 inline-flex h-8 text-xs items-center rounded-full bg-fabric px-4 font-medium text-primary-foreground outline-none transition-[background-color,scale] duration-200 ease-apple hover:bg-fabric-hover focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]">
          Open Power BI setup
        </a>
      </div>
    );
  }

  if (reason === "insufficient_permissions") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
        <ShieldAlert className="size-6 text-zinc-400" />
        <div>
          <p className="text-sm font-semibold text-zinc-900">Power AI</p>
          <p className="mt-1.5 max-w-[240px] text-xs leading-5 text-zinc-500">
            Your account doesn't have permission to use Power AI. Contact your workspace admin.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <PowerOff className="size-6 text-zinc-400" />
      <div>
        <p className="text-sm font-semibold text-zinc-900">Power AI is unavailable</p>
        <p className="mt-1.5 max-w-[240px] text-xs leading-5 text-zinc-500">
          {UNAVAILABLE_COPY[reason] ?? "The AI backend is temporarily unavailable. Try again shortly."}
        </p>
      </div>
    </div>
  );
}
