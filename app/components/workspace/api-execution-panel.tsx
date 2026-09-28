import {
  Braces,
  CheckCircle2,
  ClipboardCopy,
  Clock3,
  Code2,
  Loader2,
  Play,
  ServerCog,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import {
  DEFAULT_REQUEST_BODIES,
  type ApiEndpoint,
  type ApiResult,
  getParameterDefault,
  methodTone,
} from "~/lib/api-catalog";
import type { ExecuteEndpoint } from "~/lib/use-api-executor";
import { cn } from "~/lib/utils";

type ResponseView = "body" | "headers";

export function ApiExecutionPanel({
  endpoint,
  execute,
  result,
  error,
  isRunning,
}: {
  endpoint: ApiEndpoint;
  execute: ExecuteEndpoint;
  result: ApiResult | null;
  error: string | null;
  isRunning: boolean;
}) {
  const [parameters, setParameters] = useState<Record<string, string>>(() => parameterDefaults(endpoint));
  const [bodyText, setBodyText] = useState(() => requestBodyText(endpoint));
  const [requestError, setRequestError] = useState<string | null>(null);
  const [responseView, setResponseView] = useState<ResponseView>("body");
  const [copied, setCopied] = useState(false);
  const endpointResult = result?.endpoint === endpoint.id ? result : null;
  const supportsBody = endpoint.hasBody && endpoint.method !== "get" && endpoint.method !== "delete";
  const visibleParameters = useMemo(
    () => endpoint.parameters.filter((parameter) => parameter.in !== "cookie" && parameter.name.toLowerCase() !== "x-lineage-admin-key"),
    [endpoint.parameters],
  );

  useEffect(() => {
    setParameters(parameterDefaults(endpoint));
    setBodyText(requestBodyText(endpoint));
    setRequestError(null);
    setResponseView("body");
    setCopied(false);
  }, [endpoint]);

  async function runEndpoint() {
    const missing = visibleParameters
      .filter((parameter) => parameter.required && !parameters[parameter.name]?.trim())
      .map((parameter) => parameter.name);
    if (missing.length) {
      setRequestError(`Set required value${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}.`);
      return;
    }

    let body: unknown;
    if (supportsBody) {
      if (endpoint.requestBodyRequired && !bodyText.trim()) {
        setRequestError("Enter the required JSON request body.");
        return;
      }
      try {
        body = bodyText.trim() ? JSON.parse(bodyText) : undefined;
      } catch (caughtError) {
        const message = caughtError instanceof Error ? caughtError.message : String(caughtError);
        setRequestError(`Request body is not valid JSON. ${message}`);
        return;
      }
    }

    setRequestError(null);
    setResponseView("body");
    await execute(endpoint.id, { parameters, body });
    if (body !== undefined && hasSensitiveValues(body)) {
      setBodyText(JSON.stringify(clearSensitiveValues(body), null, 2));
    }
  }

  const output = endpointResult
    ? responseView === "body"
      ? formatOutput(endpointResult.body)
      : formatOutput(endpointResult.headers)
    : "Run this operation to see its response.";

  async function copyOutput() {
    if (!endpointResult) return;
    await copyText(output);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return <div className="mt-4 border-y border-zinc-200 bg-zinc-50">
    <div className="flex flex-col justify-between gap-3 border-b border-zinc-200 px-4 py-3 lg:flex-row lg:items-start">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("inline-flex rounded-[6px] border px-2 py-1 text-xs font-semibold uppercase", methodTone(endpoint.method))}>{endpoint.method}</span>
          <h4 className="text-sm font-semibold text-zinc-950">{endpoint.summary}</h4>
        </div>
        <p className="mt-2 break-all font-mono text-xs text-zinc-500">{endpoint.path}</p>
      </div>
      <Button type="button" size="sm" disabled={isRunning} onClick={() => void runEndpoint()}>
        {isRunning ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
        {isRunning ? "Running" : "Run API"}
      </Button>
    </div>

    <div className="grid lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div className="border-b border-zinc-200 p-4 lg:border-b-0 lg:border-r">
        <div className="mb-4 flex items-start gap-2"><Code2 className="mt-0.5 size-4 text-cyan-800" /><div><h5 className="text-sm font-semibold">Request input</h5><p className="mt-0.5 text-xs text-zinc-500">Session cookies are included automatically.</p></div></div>

        {visibleParameters.length > 0 && <div className="space-y-4">
          {visibleParameters.map((parameter) => {
            const id = `${endpoint.operationId}-${parameter.in}-${parameter.name}`;
            const enumValues = parameter.schema?.enum ?? [];
            return <div key={`${parameter.in}-${parameter.name}`} className="space-y-1.5">
              <label htmlFor={id} className="flex flex-wrap items-center gap-1 text-xs font-semibold text-zinc-700">
                {parameter.name}{parameter.required && <span className="text-rose-600">*</span>}
                <span className="font-normal text-zinc-400">{parameter.in}</span>
              </label>
              {enumValues.length > 0
                ? <select id={id} value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} className="h-9 w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm outline-none transition-[border-color,box-shadow] duration-200 ease-apple hover:border-zinc-300 focus:border-cyan-800 focus:ring-4 focus:ring-cyan-100"><option value="">Select {parameter.name}</option>{enumValues.map((value) => <option key={value} value={value}>{value}</option>)}</select>
                : <Input id={id} value={parameters[parameter.name] ?? ""} onChange={(event) => setParameters((current) => ({ ...current, [parameter.name]: event.target.value }))} placeholder={`${parameter.in} parameter`} />}
              {parameter.description && <p className="text-xs leading-5 text-zinc-500">{parameter.description}</p>}
            </div>;
          })}
        </div>}

        {supportsBody && <div className={cn("space-y-1.5", visibleParameters.length > 0 && "mt-5 border-t border-zinc-200 pt-5")}>
          <label htmlFor={`${endpoint.operationId}-body`} className="flex items-center gap-1 text-xs font-semibold text-zinc-700">JSON request body{endpoint.requestBodyRequired && <span className="text-rose-600">*</span>}</label>
          <Textarea id={`${endpoint.operationId}-body`} value={bodyText} onChange={(event) => setBodyText(event.target.value)} spellCheck={false} className="min-h-56 resize-y bg-white font-mono text-xs leading-5" />
        </div>}

        {visibleParameters.length === 0 && !supportsBody && <div className="border border-zinc-200 bg-white px-3 py-4 text-sm text-zinc-600">This operation uses the current authenticated browser session and needs no additional input.</div>}
        {requestError && <div role="alert" className="mt-4 border border-rose-200 bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-800">{requestError}</div>}
      </div>

      <div className="min-w-0 bg-zinc-950 text-zinc-100">
        <div className="flex flex-col justify-between gap-3 border-b border-zinc-800 px-4 py-3 sm:flex-row sm:items-start">
          <div><div className="flex items-center gap-2"><ServerCog className="size-4 text-cyan-300" /><h5 className="text-sm font-semibold">Response output</h5></div><p className="mt-1 text-xs text-zinc-400">Status, duration, headers, and returned content</p></div>
          <Button type="button" size="sm" variant="outline" disabled={!endpointResult} onClick={() => void copyOutput()} className="border-zinc-700 bg-zinc-900 text-zinc-100 hover:bg-zinc-800 hover:text-white">{copied ? <CheckCircle2 className="size-3.5 text-emerald-400" /> : <ClipboardCopy className="size-3.5" />}{copied ? "Copied" : "Copy output"}</Button>
        </div>

        <div className="grid grid-cols-3 border-b border-zinc-800">
          <ResponseMetric icon={<ServerCog className="size-3.5" />} label="Status" value={endpointResult?.status == null ? "--" : String(endpointResult.status)} tone={endpointResult ? endpointResult.ok ? "success" : "error" : "neutral"} />
          <ResponseMetric icon={<Clock3 className="size-3.5" />} label="Duration" value={endpointResult ? `${endpointResult.durationMs} ms` : "--"} tone="neutral" />
          <ResponseMetric icon={<Braces className="size-3.5" />} label="Method" value={endpoint.method.toUpperCase()} tone="method" />
        </div>

        <div className="flex border-b border-zinc-800 px-3 pt-2" role="tablist" aria-label="API response output">
          {(["body", "headers"] as ResponseView[]).map((view) => <button key={view} type="button" role="tab" aria-selected={responseView === view} onClick={() => setResponseView(view)} className={cn("border-b-2 px-3 py-2 text-xs font-medium capitalize outline-none transition-[color,border-color] duration-300 ease-apple focus-visible:text-cyan-100", responseView === view ? "border-cyan-400 text-cyan-200" : "border-transparent text-zinc-400 hover:text-zinc-200")}>{view}</button>)}
        </div>
        {endpointResult && !endpointResult.ok && error && <div role="alert" className="border-b border-rose-900 bg-rose-950/60 px-4 py-3 text-xs leading-5 text-rose-200">{error}</div>}
        <pre className="min-h-72 max-h-[560px] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-5 text-zinc-200">{output}</pre>
      </div>
    </div>
  </div>;
}

function ResponseMetric({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: "success" | "error" | "neutral" | "method" }) {
  return <div className="min-w-0 border-r border-zinc-800 px-3 py-3 last:border-r-0"><div className="flex items-center gap-1.5 text-[11px] text-zinc-500">{icon}{label}</div><p className={cn("mt-1 truncate text-xs font-semibold", tone === "success" && "text-emerald-400", tone === "error" && "text-rose-400", tone === "neutral" && "text-zinc-300", tone === "method" && "text-amber-300")}>{value}</p></div>;
}

function parameterDefaults(endpoint: ApiEndpoint) {
  return Object.fromEntries(endpoint.parameters.map((parameter) => [parameter.name, getParameterDefault(parameter)]));
}

function requestBodyText(endpoint: ApiEndpoint) {
  return DEFAULT_REQUEST_BODIES[endpoint.id] ?? endpoint.requestBodyTemplate ?? "{}";
}

function formatOutput(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function hasSensitiveValues(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasSensitiveValues);
  if (typeof value !== "object" || value === null) return false;
  return Object.entries(value).some(([key, child]) => isSensitiveKey(key) || hasSensitiveValues(child));
}

function clearSensitiveValues(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(clearSensitiveValues);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, isSensitiveKey(key) ? "" : clearSensitiveValues(child)]));
}

function isSensitiveKey(key: string) {
  return /(^|_)(password|secret|token|private_key|passcode)($|_)/i.test(key);
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}
