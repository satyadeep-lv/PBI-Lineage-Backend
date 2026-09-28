import { Braces, Loader2, Play, Search, ServerCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiOutputPanel } from "~/components/workspace/api-output-panel";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Textarea } from "~/components/ui/textarea";
import {
  type ApiEndpoint,
  type ApiResult,
  DEFAULT_REQUEST_BODIES,
  getParameterDefault,
  methodTone,
} from "~/lib/api-catalog";
import type { ExecuteEndpoint } from "~/lib/use-api-executor";
import { cn } from "~/lib/utils";

export function ApiDomainCanvas({
  domainName,
  endpoints,
  execute,
  result,
  error,
  isRunning,
}: {
  domainName: string;
  endpoints: ApiEndpoint[];
  execute: ExecuteEndpoint;
  result: ApiResult | null;
  error: string | null;
  isRunning: boolean;
}) {
  const [filter, setFilter] = useState("");
  const [selectedEndpointId, setSelectedEndpointId] = useState("");
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({});
  const [requestBody, setRequestBody] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const selectedEndpoint = endpoints.find((endpoint) => endpoint.id === selectedEndpointId) ?? null;
  const filteredEndpoints = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    if (!normalizedFilter) return endpoints;

    return endpoints.filter((endpoint) =>
      [endpoint.summary, endpoint.path, endpoint.operationId, endpoint.method].some((value) =>
        value.toLowerCase().includes(normalizedFilter),
      ),
    );
  }, [endpoints, filter]);

  useEffect(() => {
    if (!endpoints.some((endpoint) => endpoint.id === selectedEndpointId)) {
      setSelectedEndpointId(endpoints[0]?.id ?? "");
    }
  }, [endpoints, selectedEndpointId]);

  useEffect(() => {
    if (!selectedEndpoint) {
      setParameterValues({});
      setRequestBody("");
      return;
    }

    const defaults: Record<string, string> = {};
    selectedEndpoint.parameters
      .filter((parameter) => parameter.in !== "cookie" && parameter.name !== "X-Lineage-Admin-Key")
      .forEach((parameter) => {
        defaults[parameter.name] = getParameterDefault(parameter);
      });
    setParameterValues(defaults);
    setRequestBody(
      DEFAULT_REQUEST_BODIES[selectedEndpoint.id] ??
        (selectedEndpoint.hasBody ? "{\n  \n}" : ""),
    );
    setValidationError(null);
  }, [selectedEndpoint]);

  async function runSelectedEndpoint() {
    if (!selectedEndpoint) {
      setValidationError("Choose an API operation first.");
      return;
    }

    const missingRequired = selectedEndpoint.parameters
      .filter(
        (parameter) =>
          parameter.required &&
          parameter.in !== "cookie" &&
          parameter.name !== "X-Lineage-Admin-Key" &&
          !parameterValues[parameter.name]?.trim(),
      )
      .map((parameter) => parameter.name);

    if (missingRequired.length > 0) {
      setValidationError(`Set required values: ${missingRequired.join(", ")}`);
      return;
    }

    if (selectedEndpoint.hasBody) {
      try {
        JSON.parse(requestBody);
      } catch {
        setValidationError("Request body must be valid JSON.");
        return;
      }
    }

    setValidationError(null);
    await execute(selectedEndpoint.id, {
      parameters: parameterValues,
      body: selectedEndpoint.hasBody ? requestBody : undefined,
    });
  }

  return (
    <section className="overflow-hidden border border-zinc-200 bg-white">
      <div className="flex flex-col justify-between gap-3 border-b border-zinc-200 px-5 py-4 sm:flex-row sm:items-center sm:px-6">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-[8px] bg-zinc-950 text-white">
            <ServerCog className="size-5" />
          </span>
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-semibold uppercase text-zinc-500">API domain</span>
              <Badge className="rounded-[8px] border border-zinc-200 bg-zinc-50 text-zinc-700">{endpoints.length} operations</Badge>
            </div>
            <h1 className="text-lg font-semibold">{domainName}</h1>
            <p className="mt-1 text-sm text-zinc-500">Choose an operation, set its input, and run it against the connected backend.</p>
          </div>
        </div>
      </div>

      {endpoints.length === 0 ? (
        <div className="flex min-h-[560px] items-center justify-center p-6 text-center">
          <div>
            <Braces className="mx-auto size-8 text-zinc-300" />
            <p className="mt-4 text-sm text-zinc-500">No API operations are available for this domain.</p>
          </div>
        </div>
      ) : (
        <div className="grid xl:grid-cols-[290px_minmax(0,1fr)]">
          <aside className="border-b border-border bg-subtle p-4 xl:border-b-0 xl:border-r">
            <div className="relative mb-3">
              <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-zinc-400" />
              <Input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter operations"
                className="pl-9"
              />
            </div>
            <div className="max-h-[660px] space-y-1.5 overflow-y-auto pr-1">
              {filteredEndpoints.map((endpoint) => (
                <button
                  key={endpoint.id}
                  type="button"
                  onClick={() => setSelectedEndpointId(endpoint.id)}
                  className={cn(
                    "w-full rounded-lg border px-3 py-2.5 text-left outline-none transition-[background-color,border-color,box-shadow] duration-200 ease-apple focus-visible:ring-4 focus-visible:ring-ring/25",
                    selectedEndpointId === endpoint.id
                      ? "border-zinc-950 bg-white shadow-sm"
                      : "border-transparent hover:border-zinc-200 hover:bg-white",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className={cn("rounded-[6px] border px-1.5 py-0.5 text-[10px] font-semibold uppercase", methodTone(endpoint.method))}>{endpoint.method}</span>
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-zinc-800">{endpoint.summary}</span>
                  </div>
                  <div className="mt-1.5 truncate font-mono text-[11px] text-zinc-400">{endpoint.path}</div>
                </button>
              ))}
              {filteredEndpoints.length === 0 && (
                <p className="px-3 py-5 text-center text-xs text-zinc-500">No matching operations.</p>
              )}
            </div>
          </aside>

          <div className="min-w-0">
            <div className="border-b border-zinc-200 px-5 py-4">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedEndpoint && (
                      <span className={cn("rounded-[6px] border px-2 py-0.5 text-xs font-semibold uppercase", methodTone(selectedEndpoint.method))}>{selectedEndpoint.method}</span>
                    )}
                    <h2 className="text-base font-semibold">{selectedEndpoint?.summary ?? "Choose an operation"}</h2>
                  </div>
                  <p className="mt-1 break-all font-mono text-xs text-zinc-500">{selectedEndpoint?.path}</p>
                </div>
                <Button type="button" disabled={!selectedEndpoint || isRunning} onClick={() => void runSelectedEndpoint()}>
                  {isRunning ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                  Run API
                </Button>
              </div>
            </div>

            <div className="grid lg:grid-cols-2">
              <div className="min-w-0 p-5">
                <h3 className="text-sm font-semibold">Request input</h3>
                <p className="mt-1 text-xs text-zinc-500">Path, query, and header parameters come from OpenAPI.</p>

                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  {selectedEndpoint?.parameters
                    .filter((parameter) => parameter.in !== "cookie" && parameter.name !== "X-Lineage-Admin-Key")
                    .map((parameter) => (
                      <div key={`${parameter.in}-${parameter.name}`} className="space-y-1.5">
                        <Label htmlFor={`parameter-${parameter.in}-${parameter.name}`}>
                          {parameter.name}{parameter.required ? " *" : ""}
                        </Label>
                        <Input
                          id={`parameter-${parameter.in}-${parameter.name}`}
                          value={parameterValues[parameter.name] ?? ""}
                          onChange={(event) =>
                            setParameterValues((current) => ({ ...current, [parameter.name]: event.target.value }))
                          }
                          placeholder={`${parameter.in} parameter`}
                        />
                        <p className="text-[11px] text-zinc-400">{parameter.in}</p>
                      </div>
                    ))}
                </div>

                {selectedEndpoint?.hasBody && (
                  <div className="mt-5 space-y-1.5">
                    <Label htmlFor="request-body">JSON request body</Label>
                    <Textarea
                      id="request-body"
                      value={requestBody}
                      onChange={(event) => setRequestBody(event.target.value)}
                      className="min-h-72 resize-y font-mono text-xs leading-5"
                      spellCheck={false}
                    />
                  </div>
                )}

                {selectedEndpoint && !selectedEndpoint.hasBody && selectedEndpoint.parameters.filter((parameter) => parameter.in !== "cookie").length === 0 && (
                  <div className="mt-5 border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-600">This operation needs no request input. Browser session cookies are included automatically.</div>
                )}

                {validationError && (
                  <div className="mt-4 border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{validationError}</div>
                )}
              </div>

              <ApiOutputPanel result={result} error={error} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
