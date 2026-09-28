import { cn } from "~/lib/utils";
import { usePowerAiStore, type PowerAiAudience } from "~/stores/power-ai-store";

const PERSONAS: Array<{ value: PowerAiAudience; label: string; hint: string }> = [
  { value: "general", label: "General", hint: "Plain-language answers" },
  { value: "business", label: "Business", hint: "Light technical detail" },
  { value: "developer", label: "Developer", hint: "Full technical detail" },
];

export function PersonaSelector() {
  const audience = usePowerAiStore((state) => state.audience);
  const setAudience = usePowerAiStore((state) => state.setAudience);

  return (
    <div className="border-b border-zinc-200 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase text-zinc-400">Persona</p>
        <span className="text-[11px] text-zinc-400">{PERSONAS.find((persona) => persona.value === audience)?.hint}</span>
      </div>
      <div role="radiogroup" aria-label="Power AI audience" className="inline-flex w-full rounded-full border border-zinc-200 bg-zinc-50 p-0.5">
        {PERSONAS.map((persona) => (
          <button
            key={persona.value}
            type="button"
            role="radio"
            aria-checked={audience === persona.value}
            onClick={() => setAudience(persona.value)}
            className={cn(
              "flex-1 rounded-full px-2 py-1.5 text-xs font-medium transition-[color,background-color,border-color,box-shadow,scale] duration-200 ease-apple focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]",
              audience === persona.value ? "bg-white text-zinc-950 shadow-[0_1px_2px_rgb(0_0_0/0.06),0_4px_14px_-4px_rgb(0_0_0/0.14)]" : "text-zinc-500 hover:text-zinc-950",
            )}
          >
            {persona.label}
          </button>
        ))}
      </div>
    </div>
  );
}
