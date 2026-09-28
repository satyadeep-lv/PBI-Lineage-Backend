import { AlertCircle } from "lucide-react";

/** Shown in place of a page's content whenever its first Power BI-backed query fails — the most
 * common cause by far is that Power BI setup (device code or service principal) hasn't been
 * completed yet for this session. Consistent across every workspace page. */
export function PowerBiAuthRequired({ returnTo }: { returnTo: string }) {
  return <section className="flex min-h-[560px] items-center justify-center border border-zinc-200 bg-white p-6 text-center">
    <div className="max-w-md">
      <AlertCircle className="mx-auto size-8 text-amber-500" />
      <h1 className="mt-4 text-lg font-semibold">Power BI authentication is required</h1>
      <p className="mt-2 text-sm leading-6 text-zinc-500">Complete Power BI setup with device code or a service principal, then return to {returnTo}.</p>
      <a href="/workspace/power-bi" className="mt-5 inline-flex h-9 text-sm items-center rounded-full bg-fabric px-4 font-medium text-primary-foreground outline-none transition-[background-color,scale] duration-200 ease-apple hover:bg-fabric-hover focus-visible:ring-4 focus-visible:ring-ring/25 active:scale-[0.97]">Open Power BI setup</a>
    </div>
  </section>;
}
