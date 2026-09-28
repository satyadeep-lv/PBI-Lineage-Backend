import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Database,
  Loader2,
  LogOut,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "~/components/ui/select";
import { Textarea } from "~/components/ui/textarea";
import { type ApiResult, SETUP_ENDPOINTS } from "~/lib/api-catalog";
import type { ExecuteEndpoint } from "~/lib/use-api-executor";

const authenticationMethods = ["password", "key_pair", "external_browser", "oauth"] as const;

const databaseSchema = z
  .object({
    authenticationMethod: z.enum(authenticationMethods),
    accountIdentifier: z.string().trim().min(1, "Account identifier is required."),
    user: z.string().trim().min(1, "User is required."),
    credential: z.string(),
    warehouse: z.string(),
    database: z.string(),
    schemaName: z.string(),
    role: z.string(),
  })
  .superRefine((values, context) => {
    if (values.authenticationMethod !== "external_browser" && !values.credential.trim()) {
      context.addIssue({ code: "custom", path: ["credential"], message: "A credential is required for this authentication method." });
    }
  });

type DatabaseFormValues = z.infer<typeof databaseSchema>;

export function DatabaseSetup({
  execute,
  result,
  error,
  isRunning,
  catalogReady,
  onNext,
}: {
  execute: ExecuteEndpoint;
  result: ApiResult | null;
  error: string | null;
  isRunning: boolean;
  catalogReady: boolean;
  onNext: () => void;
}) {
  const form = useForm<DatabaseFormValues>({
    resolver: zodResolver(databaseSchema),
    defaultValues: { authenticationMethod: "password", accountIdentifier: "", user: "", credential: "", warehouse: "", database: "", schemaName: "", role: "" },
  });
  const authenticationMethod = form.watch("authenticationMethod");
  const isDatabaseResult = result?.endpoint.includes("/auth/snowflake/") ?? false;
  const details = isDatabaseResult ? asRecord(result?.body) : null;
  const connected = result?.ok && details?.status === "authenticated";

  async function connect(values: DatabaseFormValues) {
    const body: Record<string, unknown> = {
      authentication_method: values.authenticationMethod,
      account_identifier: values.accountIdentifier.trim(),
      user: values.user.trim(),
    };
    addOptional(body, "warehouse", values.warehouse);
    addOptional(body, "database", values.database);
    addOptional(body, "schema_name", values.schemaName);
    addOptional(body, "role", values.role);
    if (values.authenticationMethod === "password") {
      body.password = values.credential;
      body.authenticator = "snowflake";
    } else if (values.authenticationMethod === "key_pair") {
      body.private_key_pem = values.credential;
    } else if (values.authenticationMethod === "oauth") {
      body.token = values.credential;
    }
    await execute(SETUP_ENDPOINTS.databaseConnect, { body });
  }

  const credentialLabel = authenticationMethod === "key_pair" ? "Private key PEM" : authenticationMethod === "oauth" ? "OAuth token" : "Password";

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-4 sm:px-6">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric-secondary text-white"><Database className="size-5" /></span>
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2"><span className="text-xs font-semibold uppercase text-fabric-secondary">Step 2 of 2</span>{connected && <ConnectedBadge />}</div>
            <h1 className="text-lg font-semibold">Connect the Snowflake database</h1>
            <p className="mt-1 text-sm text-muted-foreground">Use a Snowflake account with access to the source data needed for lineage enrichment.</p>
          </div>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <div className="mb-6 flex items-start gap-3 border border-sky-200 bg-sky-50 p-3 text-sm leading-6 text-sky-900"><ShieldCheck className="mt-1 size-4 shrink-0" /><span>Enter connection details, select the access method, then connect. Credentials are sent to the FastAPI backend and are not stored in browser storage.</span></div>
        <form onSubmit={form.handleSubmit(connect)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="authentication-method">Authentication method</Label>
              <Select value={authenticationMethod} onValueChange={(value) => {
                if (value && authenticationMethods.includes(value as DatabaseFormValues["authenticationMethod"])) {
                  form.setValue("authenticationMethod", value as DatabaseFormValues["authenticationMethod"]);
                  form.clearErrors("credential");
                }
              }}>
                <SelectTrigger id="authentication-method" className="h-10 w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="password">Password</SelectItem><SelectItem value="key_pair">Key pair</SelectItem><SelectItem value="external_browser">External browser</SelectItem><SelectItem value="oauth">OAuth token</SelectItem></SelectContent>
              </Select>
            </div>
            <FormField label="Account identifier" error={form.formState.errors.accountIdentifier?.message}><Input id="account-identifier" placeholder="organization-account" aria-invalid={Boolean(form.formState.errors.accountIdentifier)} {...form.register("accountIdentifier")} /></FormField>
            <FormField label="User" error={form.formState.errors.user?.message}><Input id="database-user" placeholder="service.user" aria-invalid={Boolean(form.formState.errors.user)} {...form.register("user")} /></FormField>
            {authenticationMethod !== "external_browser" && <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="database-credential">{credentialLabel}</Label>{authenticationMethod === "key_pair" ? <Textarea id="database-credential" className="min-h-32 resize-y font-mono text-xs" placeholder="-----BEGIN PRIVATE KEY-----" aria-invalid={Boolean(form.formState.errors.credential)} {...form.register("credential")} /> : <Input id="database-credential" type="password" placeholder={credentialLabel} aria-invalid={Boolean(form.formState.errors.credential)} {...form.register("credential")} />}<FieldError message={form.formState.errors.credential?.message} /></div>}
            <FormField label="Warehouse"><Input id="warehouse" placeholder="COMPUTE_WH" {...form.register("warehouse")} /></FormField>
            <FormField label="Database"><Input id="database" placeholder="ANALYTICS" {...form.register("database")} /></FormField>
            <FormField label="Schema"><Input id="schema-name" placeholder="PUBLIC" {...form.register("schemaName")} /></FormField>
            <FormField label="Role"><Input id="database-role" placeholder="LINEAGE_READER" {...form.register("role")} /></FormField>
          </div>
          <Button type="submit" className="mt-5" disabled={isRunning || !catalogReady}>{isRunning ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />} Connect database</Button>
        </form>
        <DatabaseStatus details={details} connected={Boolean(connected)} error={isDatabaseResult ? error : null} isRunning={isRunning} catalogReady={catalogReady} onCheck={() => void execute(SETUP_ENDPOINTS.databaseStatus)} onDisconnect={() => void execute(SETUP_ENDPOINTS.databaseLogout)} />
        <div className="mt-6 flex justify-end border-t border-zinc-200 pt-5"><Button type="button" variant="outline" onClick={onNext}>Open Explorer <ArrowRight data-icon="inline-end" className="size-4" /></Button></div>
      </div>
    </section>
  );
}

function DatabaseStatus({ details, connected, error, isRunning, catalogReady, onCheck, onDisconnect }: {
  details: Record<string, unknown> | null;
  connected: boolean;
  error: string | null;
  isRunning: boolean;
  catalogReady: boolean;
  onCheck: () => void;
  onDisconnect: () => void;
}) {
  const fields = [
    ["Account", stringValue(details, "current_account") ?? stringValue(details, "account_identifier")],
    ["Signed in as", stringValue(details, "current_user") ?? stringValue(details, "user")],
    ["Role", stringValue(details, "current_role")],
    ["Warehouse", stringValue(details, "current_warehouse")],
    ["Database", stringValue(details, "current_database")],
    ["Schema", stringValue(details, "current_schema")],
  ].filter(([, value]) => Boolean(value));
  return (
    <div className="mt-6 border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div><div className="flex items-center gap-2">{connected ? <CheckCircle2 className="size-4 text-emerald-700" /> : <Database className="size-4 text-zinc-500" />}<h2 className="text-sm font-semibold">Connection status</h2></div><p className="mt-1 text-sm leading-6 text-zinc-600">{connected ? "Snowflake is connected and ready for optional source enrichment." : "No Snowflake session has been confirmed yet. Database setup is optional, but it improves source evidence when it is available."}</p></div>
        <div className="flex shrink-0 flex-wrap gap-2"><Button type="button" variant="outline" size="sm" disabled={isRunning || !catalogReady} onClick={onCheck}>{isRunning ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCcw className="size-3.5" />} Check status</Button><Button type="button" variant="outline" size="sm" disabled={isRunning || !catalogReady} onClick={onDisconnect}><LogOut className="size-3.5" /> Disconnect</Button></div>
      </div>
      {error && <div className="mt-4 flex gap-2 border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900"><CircleAlert className="mt-0.5 size-4 shrink-0" />The connection check could not complete. Confirm the backend and Snowflake access, then try again.</div>}
      {fields.length > 0 && <dl className="mt-4 grid gap-px border border-zinc-200 bg-zinc-200 sm:grid-cols-3">{fields.map(([label, value]) => <div key={label} className="bg-white p-3"><dt className="text-xs text-zinc-500">{label}</dt><dd className="mt-1 break-all text-sm font-medium text-zinc-900">{value}</dd></div>)}</dl>}
    </div>
  );
}

function ConnectedBadge() {
  return <Badge className="rounded-[8px] border border-emerald-200 bg-emerald-50 text-emerald-800"><CheckCircle2 className="mr-1 size-3" /> Connected</Badge>;
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function stringValue(value: Record<string, unknown> | null, key: string) {
  const property = value?.[key];
  return typeof property === "string" && property ? property : null;
}

function addOptional(target: Record<string, unknown>, key: string, value: string) {
  const trimmed = value.trim();
  if (trimmed) target[key] = trimmed;
}

function FormField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}<FieldError message={error} /></div>;
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-rose-600">{message}</p> : null;
}
