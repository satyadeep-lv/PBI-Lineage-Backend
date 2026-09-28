import { zodResolver } from "@hookform/resolvers/zod";
import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Copy,
  ExternalLink,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { type ApiResult, SETUP_ENDPOINTS } from "~/lib/api-catalog";
import { segmentClass, segmentGroupClass } from "~/lib/interaction-styles";
import type { ExecuteEndpoint } from "~/lib/use-api-executor";

const powerBiSchema = z.object({
  authenticationMethod: z.enum(["device_code", "client_secret"]),
  tenantId: z.string().trim().min(1, "Tenant ID is required."),
  clientId: z.string().trim().min(1, "Client ID is required."),
  clientSecret: z.string(),
}).superRefine((values, context) => {
  if (values.authenticationMethod === "client_secret" && !values.clientSecret.trim()) {
    context.addIssue({ code: "custom", path: ["clientSecret"], message: "Client secret is required for service-principal sign-in." });
  }
});

type PowerBiFormValues = z.infer<typeof powerBiSchema>;

type DeviceDetails = {
  sessionId: string;
  verificationUri: string;
  userCode: string;
  expiresIn: number | null;
};

export function PowerBiSetup({
  execute,
  result,
  error,
  isRunning,
  catalogReady,
  onExplore,
}: {
  execute: ExecuteEndpoint;
  result: ApiResult | null;
  error: string | null;
  isRunning: boolean;
  catalogReady: boolean;
  onExplore: () => void;
}) {
  const queryClient = useQueryClient();
  const [deviceDetails, setDeviceDetails] = useState<DeviceDetails | null>(null);
  const form = useForm<PowerBiFormValues>({
    resolver: zodResolver(powerBiSchema),
    defaultValues: { authenticationMethod: "device_code", tenantId: "", clientId: "", clientSecret: "" },
  });
  const authenticationMethod = form.watch("authenticationMethod");
  const isPowerBiResult = result?.endpoint.includes("/api/v1/auth/microsoft/device") ?? false;
  const responseStatus = isPowerBiResult ? getStringProperty(result?.body, "status") : null;
  const isAuthenticated = result?.ok && responseStatus === "authenticated";
  const isPartial = result?.ok && responseStatus === "partial";
  const isPending = result?.ok && responseStatus === "pending";
  const powerBi = getRecordProperty(result?.body, "powerbi");
  const fabric = getRecordProperty(result?.body, "fabric");

  async function startAuthentication(values: PowerBiFormValues) {
    if (values.authenticationMethod === "client_secret") {
      setDeviceDetails(null);
      const nextResult = await execute(SETUP_ENDPOINTS.powerBiServicePrincipalConnect, {
        body: {
          tenant_id: values.tenantId.trim(),
          client_id: values.clientId.trim(),
          client_secret: values.clientSecret,
        },
      });
      form.setValue("clientSecret", "");
      if (nextResult?.ok) await revalidateLineageQueries(queryClient);
      return;
    }

    const nextResult = await execute(SETUP_ENDPOINTS.powerBiStart, {
      body: {
        tenant_id: values.tenantId.trim(),
        client_id: values.clientId.trim(),
      },
    });
    const sessionId = getStringProperty(nextResult?.body, "session_id");
    const verificationUri = getStringProperty(nextResult?.body, "verification_uri");
    const userCode = getStringProperty(nextResult?.body, "user_code");
    const expiresIn = getNumberProperty(nextResult?.body, "expires_in");

    if (nextResult?.ok && sessionId && verificationUri && userCode) {
      setDeviceDetails({ sessionId, verificationUri, userCode, expiresIn });
    }
  }

  async function checkStatus() {
    if (authenticationMethod === "client_secret") {
      const nextResult = await execute(SETUP_ENDPOINTS.powerBiServicePrincipalStatus);
      if (nextResult?.ok) await revalidateLineageQueries(queryClient);
      return;
    }
    if (deviceDetails?.sessionId) {
      const nextResult = await execute(SETUP_ENDPOINTS.powerBiSessionStatus, { parameters: { session_id: deviceDetails.sessionId } });
      if (nextResult?.ok && getStringProperty(nextResult.body, "status") === "authenticated") await revalidateLineageQueries(queryClient);
      return;
    }
    const nextResult = await execute(SETUP_ENDPOINTS.powerBiStatus);
    if (nextResult?.ok && getStringProperty(nextResult.body, "status") === "authenticated") await revalidateLineageQueries(queryClient);
  }

  async function logout() {
    await execute(authenticationMethod === "client_secret" ? SETUP_ENDPOINTS.powerBiServicePrincipalLogout : SETUP_ENDPOINTS.powerBiLogout);
    setDeviceDetails(null);
    queryClient.removeQueries({ queryKey: ["explorer"] });
    queryClient.removeQueries({ queryKey: ["report-lineage"] });
  }

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-4 sm:px-6">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><KeyRound className="size-5" /></span>
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase text-fabric">Step 1 of 2</span>
              {isAuthenticated && <ConnectedBadge label="Ready" />}
              {isPartial && <Badge className="rounded-[8px] border border-amber-200 bg-amber-50 text-amber-800">Power BI ready, Fabric unavailable</Badge>}
              {isPending && <Badge className="rounded-[8px] border border-amber-200 bg-amber-50 text-amber-800">Approval pending</Badge>}
            </div>
            <h1 className="text-lg font-semibold">Connect Power BI and Fabric</h1>
            <p className="mt-1 text-sm text-muted-foreground">Enter the Microsoft application details, approve the device code, then check that both services are ready for discovery.</p>
          </div>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <ol className="mb-6 grid border-y border-zinc-200 sm:grid-cols-3">
          {authenticationMethod === "device_code" ? <><FlowStep number="1" title="Start sign-in" text="Enter the tenant and application IDs." /><FlowStep number="2" title="Approve access" text="Open Microsoft and enter the code." /><FlowStep number="3" title="Check readiness" text="Confirm Power BI and Fabric access." /></> : <><FlowStep number="1" title="Application details" text="Enter the tenant, client ID, and secret." /><FlowStep number="2" title="Acquire tokens" text="Request application access for both services." /><FlowStep number="3" title="Check readiness" text="Confirm Power BI and Fabric token status." /></>}
        </ol>

        <form onSubmit={form.handleSubmit(startAuthentication)}>
          <div className={`mb-5 ${segmentGroupClass}`} role="group" aria-label="Microsoft authentication method">
            <button type="button" onClick={() => { form.setValue("authenticationMethod", "device_code"); form.clearErrors("clientSecret"); }} className={segmentClass(authenticationMethod === "device_code", "h-8")}><KeyRound className="size-4" /> Device code</button>
            <button type="button" onClick={() => form.setValue("authenticationMethod", "client_secret")} className={segmentClass(authenticationMethod === "client_secret", "h-8")}><Building2 className="size-4" /> Service principal</button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tenant-id">Microsoft tenant ID</Label>
              <Input id="tenant-id" placeholder="Directory (tenant) ID" aria-invalid={Boolean(form.formState.errors.tenantId)} {...form.register("tenantId")} />
              <FieldError message={form.formState.errors.tenantId?.message} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="client-id">Application client ID</Label>
              <Input id="client-id" placeholder="Application (client) ID" aria-invalid={Boolean(form.formState.errors.clientId)} {...form.register("clientId")} />
              <FieldError message={form.formState.errors.clientId?.message} />
            </div>
            {authenticationMethod === "client_secret" && <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="client-secret">Application client secret</Label><Input id="client-secret" type="password" autoComplete="new-password" placeholder="Client secret value" aria-invalid={Boolean(form.formState.errors.clientSecret)} {...form.register("clientSecret")} /><FieldError message={form.formState.errors.clientSecret?.message} /><p className="text-xs leading-5 text-zinc-500">The secret is sent only to FastAPI for token acquisition and is cleared from this form after submission.</p></div>}
          </div>
          <Button type="submit" className="mt-5" disabled={isRunning || !catalogReady}>
            {isRunning ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
            {authenticationMethod === "device_code" ? "Start Microsoft sign-in" : "Connect service principal"}
          </Button>
        </form>

        {authenticationMethod === "device_code" && deviceDetails && (
          <div className="mt-6 border border-sky-200 bg-sky-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-sky-950"><BadgeCheck className="size-4" /> Device code is ready</div>
            <p className="mt-2 text-sm leading-6 text-sky-900">Open the Microsoft verification page and enter this code to continue.</p>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              <code className="border border-sky-200 bg-white px-4 py-2 text-lg font-semibold tracking-normal text-sky-950">{deviceDetails.userCode}</code>
              <Button type="button" variant="outline" size="icon" aria-label="Copy device code" title="Copy device code" onClick={() => void navigator.clipboard.writeText(deviceDetails.userCode)}><Copy className="size-4" /></Button>
              <Button type="button" onClick={() => window.open(deviceDetails.verificationUri, "_blank", "noreferrer") }>
                Open Microsoft <ExternalLink data-icon="inline-end" className="size-4" />
              </Button>
            </div>
            {deviceDetails.expiresIn != null && <p className="mt-3 text-xs text-sky-800">The code expires in about {Math.max(1, Math.round(deviceDetails.expiresIn / 60))} minutes.</p>}
          </div>
        )}

        <ConnectionStatus
          error={isPowerBiResult ? error : null}
          status={responseStatus}
          powerBi={powerBi}
          fabric={fabric}
          authenticationMethod={authenticationMethod}
          isRunning={isRunning}
          catalogReady={catalogReady}
          onCheck={() => void checkStatus()}
          onLogout={() => void logout()}
        />
        <div className="mt-6 flex justify-end border-t border-zinc-200 pt-5"><Button type="button" variant="outline" onClick={onExplore}>Continue to database <ArrowRight data-icon="inline-end" className="size-4" /></Button></div>
      </div>
    </section>
  );
}

function ConnectionStatus({ error, status, powerBi, fabric, authenticationMethod, isRunning, catalogReady, onCheck, onLogout }: {
  error: string | null;
  status: string | null;
  powerBi: Record<string, unknown> | null;
  fabric: Record<string, unknown> | null;
  authenticationMethod: PowerBiFormValues["authenticationMethod"];
  isRunning: boolean;
  catalogReady: boolean;
  onCheck: () => void;
  onLogout: () => void;
}) {
  const connected = status === "authenticated";
  const pending = status === "pending";
  const partial = status === "partial";
  return (
    <div className="mt-6 border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            {connected ? <CheckCircle2 className="size-4 text-emerald-700" /> : pending || partial ? <Clock3 className="size-4 text-amber-600" /> : <ShieldCheck className="size-4 text-zinc-500" />}
            <h2 className="text-sm font-semibold">Connection status</h2>
          </div>
          <p className="mt-1 text-sm leading-6 text-zinc-600">{connected ? "Microsoft access is ready. You can continue to database setup or open Explorer." : partial ? "Power BI application access is ready, but Fabric access needs attention before report definitions and semantic models can load." : pending ? "Microsoft approval is still pending. Finish approval, then check status." : authenticationMethod === "client_secret" ? "No application-token session has been verified yet. Connect the service principal, then check status." : "No connection has been verified yet. Start sign-in, complete approval, then check status."}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={isRunning || !catalogReady} onClick={onCheck}>{isRunning ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCcw className="size-3.5" />} Check status</Button>
          <Button type="button" variant="outline" size="sm" disabled={isRunning || !catalogReady} onClick={onLogout}><LogOut className="size-3.5" /> Sign out</Button>
        </div>
      </div>
      {error && <ConnectionAlert text={`Microsoft sign-in could not complete: ${error}`} />}
      {(powerBi || fabric) && <div className="mt-4 grid gap-3 sm:grid-cols-2"><ProviderStatus label="Power BI" details={powerBi} /><ProviderStatus label="Fabric" details={fabric} /></div>}
    </div>
  );
}

function ProviderStatus({ label, details }: { label: string; details: Record<string, unknown> | null }) {
  const isConnected = details?.connected === true || details?.token_acquired === true;
  const message = getStringProperty(details, "message") ?? (isConnected ? "Connected" : "Needs attention");
  const missingScopes = getStringArrayProperty(details, "missing_scopes");
  const grantedRoles = getStringArrayProperty(details, "granted_roles");
  return (
    <div className="border border-zinc-200 bg-white p-3">
      <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{label}</span>{isConnected ? <ConnectedBadge label="Connected" /> : <Badge className="rounded-[8px] border border-amber-200 bg-amber-50 text-amber-800">Review access</Badge>}</div>
      <p className="mt-2 text-xs leading-5 text-zinc-600">{message}</p>
      {missingScopes.length > 0 && <p className="mt-2 text-xs leading-5 text-amber-800">Missing access: {missingScopes.join(", ")}</p>}
      {grantedRoles.length > 0 && <p className="mt-2 text-xs leading-5 text-zinc-500">Granted application roles: {grantedRoles.join(", ")}</p>}
    </div>
  );
}

function ConnectedBadge({ label }: { label: string }) {
  return <Badge className="rounded-[8px] border border-emerald-200 bg-emerald-50 text-emerald-800"><CheckCircle2 className="mr-1 size-3" /> {label}</Badge>;
}

function ConnectionAlert({ text }: { text: string }) {
  return <div className="mt-4 flex gap-2 border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900"><CircleAlert className="mt-0.5 size-4 shrink-0" />{text}</div>;
}

function FlowStep({ number, title, text }: { number: string; title: string; text: string }) {
  return <li className="flex gap-3 border-b border-border py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:px-4 sm:first:pl-0 sm:last:border-r-0"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-fabric text-xs font-semibold text-primary-foreground">{number}</span><span><span className="block text-sm font-semibold">{title}</span><span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{text}</span></span></li>;
}

function getRecordProperty(value: unknown, key: string) {
  if (typeof value !== "object" || value === null || !(key in value)) return null;
  const property = (value as Record<string, unknown>)[key];
  return typeof property === "object" && property !== null ? property as Record<string, unknown> : null;
}

function getStringProperty(value: unknown, key: string) {
  if (typeof value !== "object" || value === null || !(key in value)) return null;
  const property = (value as Record<string, unknown>)[key];
  return typeof property === "string" ? property : null;
}

function getStringArrayProperty(value: unknown, key: string) {
  if (typeof value !== "object" || value === null || !(key in value)) return [];
  const property = (value as Record<string, unknown>)[key];
  return Array.isArray(property) ? property.filter((item): item is string => typeof item === "string") : [];
}

function getNumberProperty(value: unknown, key: string) {
  if (typeof value !== "object" || value === null || !(key in value)) return null;
  const property = (value as Record<string, unknown>)[key];
  return typeof property === "number" ? property : null;
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-rose-600">{message}</p> : null;
}

async function revalidateLineageQueries(queryClient: QueryClient) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["explorer"] }),
    queryClient.invalidateQueries({ queryKey: ["report-lineage"] }),
  ]);
}
