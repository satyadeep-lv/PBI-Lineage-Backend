import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  FileKey2,
  KeyRound,
  ListChecks,
  LockKeyhole,
  ScanSearch,
  ServerCog,
  ShieldCheck,
  Snowflake,
  SquareTerminal,
  UserCheck,
  Users,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";

const guideSections = [
  { id: "before-you-begin", label: "Before you begin", number: "01" },
  { id: "power-bi", label: "Power BI and Fabric", number: "02" },
  { id: "scanner", label: "Admin Scanner", number: "03" },
  { id: "snowflake", label: "Snowflake", number: "04" },
  { id: "backend", label: "Backend and hosting", number: "05" },
  { id: "use-application", label: "Use the application", number: "06" },
  { id: "verification", label: "Verify and troubleshoot", number: "07" },
  { id: "references", label: "Official references", number: "08" },
];

const powerBiScopes = [
  "Power BI Service: Workspace.Read.All",
  "Power BI Service: Report.Read.All",
  "Power BI Service: Dataset.Read.All",
  "Microsoft Fabric: Workspace.Read.All",
  "Microsoft Fabric: Item.ReadWrite.All",
];

const backendInstall = `cd C:\\Users\\Administrator\\Desktop\\PBI-Lineage-Backend
py -3.13 -m venv .venv
.venv\\Scripts\\python.exe -m pip install --upgrade pip
.venv\\Scripts\\python.exe -m pip install --requirement requirements-dev.txt
copy .env.example .env
.venv\\Scripts\\python.exe -m pytest
.venv\\Scripts\\python.exe -m fastapi dev app/main.py`;

const localEnvironment = `CORS_ALLOWED_ORIGINS=["http://localhost:5173"]
ALLOWED_HOSTS=["localhost","127.0.0.1"]
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
ENABLE_API_DOCS=true
SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=false`;

const productionEnvironment = `ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=[]
ALLOWED_HOSTS=["<application-host>","127.0.0.1","localhost"]
FORCE_HTTPS=false
# IIS terminates/enforces HTTPS. Enable FORCE_HTTPS only with forwarded scheme.
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
ENABLE_API_DOCS=false
SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=false
LINEAGE_ADMIN_API_KEY=<secret-from-a-secure-store>`;

const frontendCommands = `cd C:\\Users\\Administrator\\Desktop\\PBI-Lineage-Frontend
npm.cmd ci
npm.cmd run dev`;

export function SetupGuide() {
  return (
    <main className="power-ai-aware flex-1 bg-app">
      <section className="border-b border-border bg-surface">
        <div className="mx-auto max-w-screen-2xl px-4 py-10 sm:px-6 sm:py-12 lg:px-8">
          <div className="max-w-4xl">
            <Badge className="rounded-[8px] border border-cyan-200 bg-cyan-50 text-cyan-900">
              <BookOpenCheck className="mr-1 size-3" />
              Start here
            </Badge>
            <h1 className="mt-5 text-3xl font-semibold leading-tight tracking-normal text-zinc-950 sm:text-4xl">
              Set up PBI Lineage Explorer
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-zinc-600 sm:text-lg">
              Complete these prerequisites before opening the operational workspace. The guide covers Microsoft sign-in, Power BI and Fabric tenant access, Admin Scanner metadata, optional Snowflake lineage, and the FastAPI host configuration used by this application.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button nativeButton={false} render={<a href="#before-you-begin" />}>
                Begin with prerequisites
                <ArrowRight data-icon="inline-end" className="size-4" />
              </Button>
              <Button nativeButton={false} variant="outline" render={<Link to="/" />}>
                View overview
              </Button>
            </div>
          </div>

          <div className="mt-9 grid border-y border-zinc-200 sm:grid-cols-3">
            <ReadinessItem icon={Users} title="Microsoft administrator" text="Entra app registration and Fabric tenant settings" />
            <ReadinessItem icon={ServerCog} title="Backend operator" text="FastAPI environment, HTTPS, proxy, and one worker" />
            <ReadinessItem icon={Snowflake} title="Snowflake administrator" text="Optional account, authentication, role, and object access" />
          </div>
        </div>
      </section>

      <div className="mx-auto grid max-w-screen-2xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[240px_minmax(0,1fr)] lg:px-8 lg:py-10">
        <aside className="hidden lg:block">
          <nav aria-label="Setup guide sections" className="sticky top-20 border-l border-border pl-4">
            <p className="mb-3 text-xs font-semibold uppercase text-muted-foreground">On this page</p>
            <ol className="space-y-1">
              {guideSections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="flex items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-surface hover:text-foreground"
                  >
                    <span className="font-mono text-[11px] text-fabric">{section.number}</span>
                    <span>{section.label}</span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>

        <article className="min-w-0 space-y-8">
          <nav aria-label="Setup guide sections on small screens" className="overflow-x-auto border-b border-border pb-3 lg:hidden">
            <div className="flex min-w-max gap-2">
              {guideSections.map((section) => (
                <a key={section.id} href={`#${section.id}`} className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground">
                  {section.number} {section.label}
                </a>
              ))}
            </div>
          </nav>

          <GuideSection
            id="before-you-begin"
            number="01"
            icon={ListChecks}
            title="Before you begin"
            description="Identify the people and access needed before entering any credentials. One person may hold several roles, but the responsibilities remain separate."
          >
            <div className="overflow-x-auto border border-zinc-200 bg-white">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Owner</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">What they prepare</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Values or approval</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 text-zinc-700">
                  <RoleRow owner="Entra administrator" responsibility="Create the application registration and approve delegated access when tenant policy requires it." evidence="Tenant ID and application client ID" />
                  <RoleRow owner="Fabric administrator" responsibility="Allow the selected identity, enable Scanner metadata settings, and control the permitted security group." evidence="Tenant-setting approval" />
                  <RoleRow owner="Workspace administrator" responsibility="Grant the user or service principal access to the workspaces and semantic models being inspected." evidence="Workspace role and model access" />
                  <RoleRow owner="Snowflake administrator" responsibility="Create or approve a read-oriented identity and role for the target databases and lineage function." evidence="Account identifier, user, role, warehouse" />
                  <RoleRow owner="Backend operator" responsibility="Install dependencies, configure environment policy, protect secrets, and expose the API through the application origin." evidence="Host, HTTPS, environment, health status" />
                </tbody>
              </table>
            </div>

            <Checklist
              title="Preflight checklist"
              items={[
                "The backend host can reach Microsoft identity, Power BI, Fabric, and Snowflake over outbound HTTPS.",
                "You know whether people will sign in interactively or the application will run unattended.",
                "The intended Microsoft identity can access at least one Power BI workspace and report.",
                "You know whether Admin Scanner, XMLA, and Snowflake enrichment are required; all three add separate prerequisites.",
                "Secrets will be entered only into the secured application or backend runtime, never into source control or frontend environment files.",
              ]}
            />

            <Callout tone="amber" icon={CircleAlert} title="Use least privilege">
              Start with a test workspace and a dedicated security group. Scanner access can reveal tenant-wide metadata, so it should not be enabled broadly just to solve an ordinary workspace permission problem.
            </Callout>
          </GuideSection>

          <GuideSection
            id="power-bi"
            number="02"
            icon={KeyRound}
            title="Configure Power BI and Fabric"
            description="The backend acquires separate Power BI and Fabric tokens. A successful Power BI token does not automatically prove Fabric item-definition access."
          >
            <Subheading title="Choose the sign-in mode" />
            <div className="overflow-x-auto border border-zinc-200 bg-white">
              <table className="w-full min-w-[840px] border-collapse text-left text-sm">
                <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Mode</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Use it for</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Required input</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Important setup</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 text-zinc-700">
                  <AuthRow mode="Device code" use="A person exploring with their own Power BI access" input="Tenant ID and client ID" setup="Public-client flow plus delegated Power BI and Fabric permissions" />
                  <AuthRow mode="Service principal" use="Unattended access and the Admin Scanner" input="Tenant ID, client ID, and client-secret value" setup="Dedicated security group, tenant settings, workspace access, and secret rotation" />
                  <AuthRow mode="Browser SSO" use="A deployment-managed redirect sign-in experience" input="Tenant ID and client ID" setup="Public-client redirect URI matching the backend callback exactly" />
                </tbody>
              </table>
            </div>
            <p className="text-sm leading-6 text-zinc-600">
              The current Power BI setup screen directly supports device code and service principal. Browser SSO is an optional backend deployment path; configure it only when the callback and frontend redirect origins are controlled by the operator.
            </p>

            <Subheading title="Create the Microsoft Entra application" />
            <NumberedSteps
              items={[
                <><strong>Register the app.</strong> In Microsoft Entra admin center, open App registrations, create a single-tenant application, and record the Directory (tenant) ID and Application (client) ID.</>,
                <><strong>Enable interactive authentication.</strong> For device code, enable public client flows. For browser SSO, also add the backend callback under Mobile and desktop applications; do not register it only as a confidential Web callback.</>,
                <><strong>Add delegated permissions for interactive sign-in.</strong> For device code or browser SSO, add the five Power BI and Fabric permissions listed below, then obtain administrator consent when your tenant policy requires it. Do not treat this list as service-principal permissions.</>,
                <><strong>Grant content access.</strong> Add the signing-in user to each required Power BI/Fabric workspace and grant access to the semantic models, reports, gateways, and capacities they need to inspect.</>,
                <><strong>Test both providers.</strong> In the application, start Microsoft sign-in, complete the Microsoft prompt, and use Check status until both Power BI and Fabric report ready.</>,
              ]}
            />

            <div className="grid gap-4 md:grid-cols-2">
              <InfoPanel icon={UserCheck} title="Delegated permissions requested by the backend">
                <ul className="space-y-2 text-sm text-zinc-700">
                  {powerBiScopes.map((scope) => (
                    <li key={scope} className="flex gap-2">
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                      <code className="break-all text-xs sm:text-sm">{scope}</code>
                    </li>
                  ))}
                </ul>
              </InfoPanel>
              <InfoPanel icon={FileKey2} title="Values to collect">
                <DefinitionList
                  items={[
                    ["Tenant ID", "Directory identifier from Microsoft Entra overview"],
                    ["Client ID", "Application identifier from the app registration"],
                    ["Client secret", "Service principal only; record the value once and protect it"],
                    ["Callback URI", "Browser SSO only; must equal MICROSOFT_SSO_REDIRECT_URI"],
                    ["Workspace access", "User or app identity must be granted the required content role"],
                  ]}
                />
              </InfoPanel>
            </div>

            <Subheading title="Prepare a service principal" />
            <NumberedSteps
              items={[
                <>Create a client secret under Certificates and secrets, record the secret <strong>value</strong>, and define an expiry and rotation owner.</>,
                <>Place the enterprise application/service principal in a dedicated Microsoft Entra security group.</>,
                <>In the Fabric Admin portal, allow that group under the service-principal settings for the Power BI APIs and Fabric APIs required by your chosen operations.</>,
                <>Add the service principal or its allowed group to each workspace with the minimum role required by the Power BI and Fabric endpoints.</>,
                <>Use the Service principal option on the Power BI setup page. A <code>partial</code> result means Power BI succeeded while Fabric still needs permission or tenant configuration.</>,
              ]}
            />

            <Callout tone="sky" icon={ShieldCheck} title="Interactive and unattended access are different">
              Delegated sign-in acts with a person&apos;s access. A service principal acts as the application and must be independently permitted by tenant settings and workspace roles. Do not use a client secret for device code or browser SSO.
            </Callout>
          </GuideSection>

          <GuideSection
            id="scanner"
            number="03"
            icon={ScanSearch}
            title="Enable the Power BI Admin Scanner"
            description="Scanner configuration is separate from ordinary workspace access. Complete this section only when tenant-wide inventory, dashboard metadata, datasource instances, or DAX and mashup extraction are required."
          >
            <NumberedSteps
              items={[
                <>Use a dedicated service principal and security group approved by a Fabric administrator.</>,
                <>In Admin portal, open Tenant settings, then Admin API settings, and allow the group to use read-only Power BI admin APIs.</>,
                <>Enable enhanced admin API responses with detailed metadata for table, column, and measure metadata.</>,
                <>Enable enhanced admin API responses with DAX and mashup expressions when expressions and Power Query source evidence are required. The detailed-metadata setting must be enabled first.</>,
                <>For the Scanner-specific service-principal registration, follow Microsoft&apos;s rule not to add admin-consent-required Power BI permissions. Authorization comes from the allowed tenant security group.</>,
                <>Allow tenant-setting changes time to propagate, sign in with the service principal, then run a small one-workspace scan before selecting a wider scope.</>,
              ]}
            />

            <div className="grid gap-4 md:grid-cols-2">
              <InfoPanel icon={BadgeCheck} title="Expected Scanner evidence">
                <ul className="space-y-2 text-sm leading-6 text-zinc-700">
                  <Bullet>Workspaces, reports, dashboards, semantic models, and dataflows returned by Microsoft.</Bullet>
                  <Bullet>Tables, columns, measures, relationships, roles, and expressions when tenant settings permit them.</Bullet>
                  <Bullet>Datasource instances, configured-by identities, and report-to-model bindings present in the scan result.</Bullet>
                </ul>
              </InfoPanel>
              <InfoPanel icon={CircleAlert} title="What Scanner does not replace">
                <ul className="space-y-2 text-sm leading-6 text-zinc-700">
                  <Bullet>Workspace access needed by ordinary report and Fabric definition endpoints.</Bullet>
                  <Bullet>Fabric item permissions required to retrieve PBIR or TMDL definitions.</Bullet>
                  <Bullet>Capacity, XMLA, gateway-administrator, or Snowflake permissions.</Bullet>
                </ul>
              </InfoPanel>
            </div>

            <details className="border border-zinc-200 bg-white px-4 py-3 open:pb-4">
              <summary className="cursor-pointer text-sm font-semibold text-zinc-950">Optional XMLA metadata setup</summary>
              <div className="mt-4 space-y-3 text-sm leading-6 text-zinc-600">
                <p>Native XMLA extraction is optional and Windows-specific. Install the x64 Microsoft Analysis Services OLE DB provider (MSOLAP) on the backend host and keep a 64-bit Python runtime.</p>
                <p>The workspace must use a compatible Fabric, Premium, Embedded, or PPU capacity with XMLA enabled. Grant the identity workspace access and Build/read access to the semantic model and any upstream model it uses.</p>
                <p>Configure <code>XMLA_PROVIDER=MSOLAP</code> and set <code>XMLA_TENANT_NAME</code> when <code>myorg</code> is not correct for the tenant.</p>
              </div>
            </details>
          </GuideSection>

          <GuideSection
            id="snowflake"
            number="04"
            icon={Snowflake}
            title="Configure optional Snowflake access"
            description="Snowflake is the currently implemented optional database connector for live source enrichment and deep table or column lineage. The Database setup area is designed to support additional providers over time, and Power BI inventory can be used without a database session."
          >
            <Subheading title="Choose an authentication method" />
            <div className="grid gap-4 sm:grid-cols-2">
              <MethodPanel title="Password or MFA" badge="Interactive" text="Useful for a controlled manual session. Choose the MFA authenticator when the Snowflake user policy requires a passcode or approval." />
              <MethodPanel title="RSA key pair" badge="Hosted" text="Well suited to unattended operation. Register the public key on a dedicated Snowflake user and protect the private PEM and passphrase outside source control." />
              <MethodPanel title="OAuth token" badge="Enterprise" text="Use an access token issued through your approved Snowflake OAuth integration. Token lifecycle and renewal remain an operator responsibility." />
              <MethodPanel title="External browser" badge="Local only" text="The browser opens on the backend host, not on the end user's computer. Keep this method disabled for remote containers and unattended servers." />
            </div>

            <Subheading title="Prepare the Snowflake role" />
            <NumberedSteps
              items={[
                <>Create or choose a dedicated Snowflake user and a least-privilege role. Avoid using <code>ACCOUNTADMIN</code> for routine application sessions.</>,
                <>Grant the role access to the warehouse and visibility/access for the target databases, schemas, tables, views, and columns that will be traced.</>,
                <>Confirm the account edition and role can use <code>SNOWFLAKE.CORE.GET_LINEAGE</code>. The function requires Enterprise Edition or higher, and inaccessible objects return an error rather than hidden lineage.</>,
                <>Collect the account identifier and user. Add the warehouse, database, schema, and role when you want a predictable session context.</>,
                <>On the Database setup page, choose the matching method, connect, and use Check status to verify the current account, user, role, warehouse, database, schema, and remaining session time.</>,
              ]}
            />

            <div className="overflow-x-auto border border-zinc-200 bg-white">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Application field</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Meaning</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Required</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 text-zinc-700">
                  <ValueRow field="Account identifier" meaning="Snowflake connector account identifier for your organization and account" requirement="Yes" />
                  <ValueRow field="User" meaning="Snowflake identity associated with the selected authentication method" requirement="Yes" />
                  <ValueRow field="Warehouse" meaning="Compute warehouse available to the lineage session" requirement="Recommended" />
                  <ValueRow field="Database and schema" meaning="Default object context; fully qualified objects can still be traced" requirement="Recommended" />
                  <ValueRow field="Role" meaning="Least-privilege role with target-object and lineage access" requirement="Recommended" />
                  <ValueRow field="Credential" meaning="Password/passcode, private PEM/passphrase, or OAuth token" requirement="Depends on method" />
                </tbody>
              </table>
            </div>

            <Callout tone="amber" icon={LockKeyhole} title="Session and secret behavior">
              Microsoft and Snowflake sessions are separate HttpOnly cookies. Snowflake connections live only in the backend process and expire after 45 minutes by default. Submitted passwords, tokens, and private keys must remain transient and must never be copied into browser storage, logs, Git, or a frontend build.
            </Callout>
          </GuideSection>

          <GuideSection
            id="backend"
            number="05"
            icon={ServerCog}
            title="Configure the FastAPI backend and host"
            description="The frontend and backend are independent repositories. They can share one Windows machine, but they should communicate only through HTTP and retain separate builds, deployment paths, and source control."
          >
            <Subheading title="Install and start locally" />
            <CodeBlock label="Windows terminal" value={backendInstall} />
            <p className="text-sm leading-6 text-zinc-600">
              The full backend package already includes the Snowflake Connector, Snowpark, and cryptography dependencies. Run one API worker because Microsoft sessions, Snowflake connections, cache entries, and scan coordination are currently process-local.
            </p>

            <Subheading title="Review the backend environment" />
            <div className="overflow-x-auto border border-zinc-200 bg-white">
              <table className="w-full min-w-[860px] border-collapse text-left text-sm">
                <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Setting</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">When to configure it</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Rule</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 text-zinc-700">
                  <SettingRow name="CORS_ALLOWED_ORIGINS" use="Frontend and API use different origins" rule="JSON list of exact browser origins; same-origin IIS needs no CORS origin" />
                  <SettingRow name="ALLOWED_HOSTS" use="Every non-local deployment" rule="Use explicit public/internal host names rather than a wildcard" />
                  <SettingRow name="MICROSOFT_SSO_REDIRECT_URI" use="Browser SSO only" rule="Must exactly match the registered public-client callback" />
                  <SettingRow name="LINEAGE_ADMIN_API_KEY" use="Protected Scanner, lineage, Snowflake, and app-auth routes" rule="Only an authenticated server-side gateway or operator client may send it; never compile it into JavaScript" />
                  <SettingRow name="AUTH_COOKIE_SECURE" use="HTTPS production" rule="Set true in production; local HTTP requires false" />
                  <SettingRow name="AUTH_COOKIE_SAMESITE" use="Cookie policy" rule="Keep lax for the normal same-origin/redirect flow unless architecture requires otherwise" />
                  <SettingRow name="FORCE_HTTPS" use="Direct HTTPS or a scheme-aware reverse proxy" rule="Enable only when the original HTTPS scheme is forwarded correctly; otherwise enforce HTTPS at IIS" />
                  <SettingRow name="ENABLE_API_DOCS" use="Developer-only API documentation" rule="Keep true locally and false on a public production host" />
                  <SettingRow name="SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH" use="Backend-host browser SSO" rule="Keep false for remote, containerized, or unattended operation" />
                  <SettingRow name="LINEAGE_DATABASE_PATH" use="Persistent snapshots and scan jobs" rule="Use a durable absolute path when the working directory can change" />
                  <SettingRow name="XMLA_PROVIDER / XMLA_TENANT_NAME" use="Optional native XMLA" rule="Match the installed MSOLAP provider and tenant path" />
                </tbody>
              </table>
            </div>

            <div className="grid min-w-0 gap-4 md:grid-cols-2">
              <div className="min-w-0">
                <p className="mb-2 text-sm font-semibold text-zinc-950">Local development example</p>
                <CodeBlock label=".env" value={localEnvironment} />
              </div>
              <div className="min-w-0">
                <p className="mb-2 text-sm font-semibold text-zinc-950">Production policy example</p>
                <CodeBlock label=".env" value={productionEnvironment} />
              </div>
            </div>

            <Subheading title="Connect the frontend" />
            <CodeBlock label="Second Windows terminal" value={frontendCommands} />
            <div className="grid gap-4 md:grid-cols-2">
              <InfoPanel icon={SquareTerminal} title="Development">
                <p className="text-sm leading-6 text-zinc-700">Keep FastAPI on <code>127.0.0.1:8000</code> and open the frontend with <code>localhost:5173</code>. Vite proxies relative API and OpenAPI requests to FastAPI.</p>
              </InfoPanel>
              <InfoPanel icon={Workflow} title="IIS production">
                <p className="text-sm leading-6 text-zinc-700">Serve <code>build/client</code> as static files, rewrite application routes to <code>index.html</code>, and reverse-proxy <code>/api</code> plus <code>/openapi.json</code> to the loopback backend. Keep the backend port private.</p>
              </InfoPanel>
            </div>
            <p className="text-sm leading-6 text-zinc-600">
              For same-origin IIS hosting, leave <code>VITE_API_ORIGIN</code> blank. Do not place Microsoft secrets, Snowflake credentials, or the backend administration key in a <code>VITE_*</code> variable because Vite values are visible in the browser bundle.
            </p>
          </GuideSection>

          <GuideSection
            id="use-application"
            number="06"
            icon={Workflow}
            title="Use the application in order"
            description="Once administrators and the backend operator complete their work, an analyst can follow this sequence without needing to understand internal object IDs."
          >
            <ol className="divide-y divide-zinc-200 border-y border-zinc-200 bg-white">
              <ApplicationStep number="1" title="Read this guide" text="Confirm the required people, identity mode, tenant settings, and optional integrations are ready." />
              <ApplicationStep number="2" title="Review the overview" text="Understand the source-to-report workflow and the evidence each analysis view provides." />
              <ApplicationStep number="3" title="Connect Power BI" text="Enter the tenant and application details, finish sign-in, then check both Power BI and Fabric status." />
              <ApplicationStep number="4" title="Connect Snowflake when needed" text="Choose an approved authentication method and confirm the resolved role and session context." />
              <ApplicationStep number="5" title="Open Explorer" text="Select a workspace and report by name; inspect assets, report detail, semantic objects, and column mappings." />
              <ApplicationStep number="6" title="Run focused lineage" text="Use Report Lineage, Table Impact, or Measure Impact for directed dependency diagrams and exportable evidence." />
              <ApplicationStep number="7" title="Run Scanner deliberately" text="Choose a small workspace scope first, wait for completion, then inspect the full administrative inventory." />
            </ol>
            <div className="flex flex-wrap gap-3">
              <Button nativeButton={false} variant="outline" render={<Link to="/" />}>
                Open overview
              </Button>
              <Button nativeButton={false} render={<Link to="/workspace/power-bi" />}>
                Start Power BI setup
                <ArrowRight data-icon="inline-end" className="size-4" />
              </Button>
            </div>
          </GuideSection>

          <GuideSection
            id="verification"
            number="07"
            icon={CheckCircle2}
            title="Verify the setup and resolve common failures"
            description="Validate one layer at a time. A green backend check proves the API is reachable; it does not prove Microsoft, Fabric, Scanner, XMLA, or Snowflake authorization."
          >
            <Checklist
              title="Acceptance checklist"
              items={[
                "The header reports Backend online through the same origin used by the browser.",
                "Power BI status is connected and at least one expected workspace is listed by name.",
                "Fabric status is connected and one report definition or semantic model definition loads.",
                "If enabled, a one-workspace Scanner run reaches Succeeded and returns detailed metadata.",
                "If enabled, Snowflake status shows the intended account, user, role, warehouse, database, and schema.",
                "Explorer and focused lineage views load evidence, and a representative table can be copied and downloaded.",
              ]}
            />

            <div className="overflow-x-auto border border-zinc-200 bg-white">
              <table className="w-full min-w-[900px] border-collapse text-left text-sm">
                <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Symptom</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Check first</th>
                    <th className="border-b border-zinc-200 px-4 py-3 font-semibold">Likely owner</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 text-zinc-700">
                  <TroubleRow symptom="Backend offline" check="FastAPI process, health route, Vite/IIS proxy, firewall, and exact browser host" owner="Backend operator" />
                  <TroubleRow symptom="Microsoft sign-in will not start" check="Tenant/client IDs, public-client flow, redirect configuration, and outbound HTTPS" owner="Entra administrator" />
                  <TroubleRow symptom="Power BI ready, Fabric partial" check="Fabric delegated permission or service-principal tenant setting, workspace role, and item identity support" owner="Fabric administrator" />
                  <TroubleRow symptom="Workspace or report missing" check="The signed-in identity's workspace role and object access; do not troubleshoot with IDs first" owner="Workspace administrator" />
                  <TroubleRow symptom="Scanner returns 401/403" check="Dedicated group, read-only Admin API setting, metadata settings, service-principal session, and admin-key policy" owner="Fabric/backend administrator" />
                  <TroubleRow symptom="Definition or XMLA data is partial" check="Fabric item access, compatible capacity, XMLA setting, Build permission, and MSOLAP installation" owner="Workspace/backend administrator" />
                  <TroubleRow symptom="Snowflake cannot connect" check="Account identifier, authentication policy, credential method, role, warehouse, and outbound HTTPS" owner="Snowflake administrator" />
                  <TroubleRow symptom="Snowflake lineage is empty or denied" check="Enterprise Edition, object accessibility, role context, and whether Snowflake has lineage evidence" owner="Snowflake administrator" />
                </tbody>
              </table>
            </div>

            <Callout tone="rose" icon={CircleAlert} title="Do not solve authorization failures by exposing secrets">
              Never put a client secret, Snowflake credential, OAuth token, private key, session cookie, or administration key into a screenshot, exported table, URL, source file, frontend environment variable, or support message. Use sanitized status and error codes for troubleshooting.
            </Callout>
          </GuideSection>

          <GuideSection
            id="references"
            number="08"
            icon={BookOpenCheck}
            title="References"
            description="Use the official product documentation as the authority for current permissions, tenant labels, authentication policy, and feature availability."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <ReferenceGroup
                title="Microsoft Power BI and Fabric"
                links={[
                  ["Power BI REST API overview", "https://learn.microsoft.com/en-us/rest/api/power-bi/"],
                  ["Register a Microsoft Entra application", "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"],
                  ["Fabric REST API identity support", "https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support"],
                  ["Set up metadata scanning", "https://learn.microsoft.com/en-us/fabric/admin/metadata-scanning-setup"],
                  ["Admin API tenant settings", "https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-admin-api-settings"],
                  ["Analysis Services client libraries", "https://learn.microsoft.com/en-us/analysis-services/client-libraries"],
                ]}
              />
              <ReferenceGroup
                title="Snowflake"
                links={[
                  ["Snowflake connection options", "https://docs.snowflake.com/en/guides-overview-connecting"],
                  ["Python Connector connections", "https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect"],
                  ["Snowpark Python setup", "https://docs.snowflake.com/en/developer-guide/snowpark/python/setup"],
                  ["Key-pair authentication", "https://docs.snowflake.com/en/user-guide/key-pair-auth"],
                  ["SNOWFLAKE.CORE.GET_LINEAGE", "https://docs.snowflake.com/en/sql-reference/functions/get_lineage-snowflake-core"],
                ]}
              />
            </div>

            <details className="border border-zinc-200 bg-white px-4 py-3 open:pb-4">
              <summary className="cursor-pointer text-sm font-semibold text-zinc-950">Supplemental community reading supplied for this project</summary>
              <div className="mt-4 space-y-3">
                <ExternalReference label="Fabric Community: setting up the Power BI REST API" href="https://community.fabric.microsoft.com/blog/community_blog/setting-up-power-bi-rest-api-for-the-first-time/4821699" />
                <ExternalReference label="Medium: Power BI API for administrators" href="https://medium.com/@dxsmith12/the-power-bi-api-for-administrators-1339b0d593ca" />
              </div>
              <p className="mt-4 text-xs leading-5 text-zinc-500">Community articles can help with orientation, but confirm every tenant setting and permission against the official Microsoft documentation above.</p>
            </details>
          </GuideSection>
        </article>
      </div>
    </main>
  );
}

function ReadinessItem({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return (
    <div className="flex gap-3 border-b border-zinc-200 px-3 py-5 last:border-b-0 sm:border-b-0 sm:border-r sm:px-5 sm:first:pl-0 sm:last:border-r-0">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><Icon className="size-4" /></span>
      <span>
        <span className="block text-sm font-semibold text-zinc-950">{title}</span>
        <span className="mt-1 block text-xs leading-5 text-zinc-500">{text}</span>
      </span>
    </div>
  );
}

function GuideSection({ id, number, icon: Icon, title, description, children }: { id: string; number: string; icon: LucideIcon; title: string; description: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 border border-zinc-200 bg-white">
      <header className="border-b border-zinc-200 px-4 py-5 sm:px-6">
        <div className="flex items-start gap-4">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-fabric text-primary-foreground"><Icon className="size-5" /></span>
          <div className="min-w-0">
            <p className="font-mono text-xs text-fabric">STEP {number}</p>
            <h2 className="mt-1 text-xl font-semibold tracking-normal text-zinc-950 sm:text-2xl">{title}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-zinc-600">{description}</p>
          </div>
        </div>
      </header>
      <div className="space-y-6 px-4 py-6 sm:px-6">{children}</div>
    </section>
  );
}

function Subheading({ title }: { title: string }) {
  return <h3 className="border-l-2 border-cyan-600 pl-3 text-base font-semibold text-zinc-950">{title}</h3>;
}

function RoleRow({ owner, responsibility, evidence }: { owner: string; responsibility: string; evidence: string }) {
  return <tr><td className="px-4 py-3 font-medium text-zinc-950">{owner}</td><td className="px-4 py-3 leading-6">{responsibility}</td><td className="px-4 py-3 leading-6">{evidence}</td></tr>;
}

function AuthRow({ mode, use, input, setup }: { mode: string; use: string; input: string; setup: string }) {
  return <tr><td className="px-4 py-3 font-medium text-zinc-950">{mode}</td><td className="px-4 py-3 leading-6">{use}</td><td className="px-4 py-3 leading-6">{input}</td><td className="px-4 py-3 leading-6">{setup}</td></tr>;
}

function ValueRow({ field, meaning, requirement }: { field: string; meaning: string; requirement: string }) {
  return <tr><td className="px-4 py-3 font-medium text-zinc-950">{field}</td><td className="px-4 py-3 leading-6">{meaning}</td><td className="px-4 py-3">{requirement}</td></tr>;
}

function SettingRow({ name, use, rule }: { name: string; use: string; rule: string }) {
  return <tr><td className="px-4 py-3"><code className="break-all text-xs font-semibold text-zinc-950">{name}</code></td><td className="px-4 py-3 leading-6">{use}</td><td className="px-4 py-3 leading-6">{rule}</td></tr>;
}

function TroubleRow({ symptom, check, owner }: { symptom: string; check: string; owner: string }) {
  return <tr><td className="px-4 py-3 font-medium text-zinc-950">{symptom}</td><td className="px-4 py-3 leading-6">{check}</td><td className="px-4 py-3 leading-6">{owner}</td></tr>;
}

function NumberedSteps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="space-y-3">
      {items.map((item, index) => (
        <li key={index} className="flex gap-3 text-sm leading-6 text-zinc-700">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-zinc-300 bg-zinc-50 font-mono text-[11px] font-semibold text-zinc-700">{index + 1}</span>
          <span>{item}</span>
        </li>
      ))}
    </ol>
  );
}

function Checklist({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="border border-zinc-200 bg-zinc-50 px-4 py-4 sm:px-5">
      <p className="text-sm font-semibold text-zinc-950">{title}</p>
      <ul className="mt-3 grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-sm leading-6 text-zinc-700">
            <CheckCircle2 className="mt-1 size-4 shrink-0 text-emerald-600" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function InfoPanel({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: ReactNode }) {
  return (
    <div className="border border-zinc-200 bg-white p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-cyan-700" />
        <h4 className="text-sm font-semibold text-zinc-950">{title}</h4>
      </div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function DefinitionList({ items }: { items: [string, string][] }) {
  return (
    <dl className="space-y-3 text-sm">
      {items.map(([term, definition]) => (
        <div key={term}>
          <dt className="font-medium text-zinc-950">{term}</dt>
          <dd className="mt-0.5 leading-5 text-zinc-600">{definition}</dd>
        </div>
      ))}
    </dl>
  );
}

function Bullet({ children }: { children: ReactNode }) {
  return <li className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-cyan-600" /><span>{children}</span></li>;
}

function MethodPanel({ title, badge, text }: { title: string; badge: string; text: string }) {
  return (
    <div className="border-l-2 border-fabric bg-subtle px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-zinc-950">{title}</h4>
        <Badge className="rounded-[6px] border border-zinc-200 bg-white text-zinc-600">{badge}</Badge>
      </div>
      <p className="mt-2 text-sm leading-6 text-zinc-600">{text}</p>
    </div>
  );
}

function CodeBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden border border-zinc-800 bg-zinc-950 text-zinc-100">
      <div className="border-b border-zinc-800 px-4 py-2 font-mono text-[11px] uppercase text-zinc-400">{label}</div>
      <pre className="overflow-x-auto p-4 text-xs leading-6"><code>{value}</code></pre>
    </div>
  );
}

function Callout({ tone, icon: Icon, title, children }: { tone: "amber" | "sky" | "rose"; icon: LucideIcon; title: string; children: ReactNode }) {
  const styles = {
    amber: "border-amber-300 bg-amber-50 text-amber-950",
    sky: "border-sky-300 bg-sky-50 text-sky-950",
    rose: "border-rose-300 bg-rose-50 text-rose-950",
  };
  return (
    <div className={`border-l-4 px-4 py-4 ${styles[tone]}`}>
      <div className="flex gap-3">
        <Icon className="mt-0.5 size-5 shrink-0" />
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-sm leading-6 opacity-80">{children}</p>
        </div>
      </div>
    </div>
  );
}

function ApplicationStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <li className="grid gap-2 px-4 py-4 sm:grid-cols-[40px_180px_minmax(0,1fr)] sm:items-start sm:gap-4">
      <span className="font-mono text-xs font-semibold text-cyan-700">{number.padStart(2, "0")}</span>
      <span className="text-sm font-semibold text-zinc-950">{title}</span>
      <span className="text-sm leading-6 text-zinc-600">{text}</span>
    </li>
  );
}

function ReferenceGroup({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div className="border border-zinc-200 bg-white p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-zinc-950">{title}</h3>
      <ul className="mt-3 divide-y divide-zinc-200">
        {links.map(([label, href]) => (
          <li key={href}>
            <ExternalReference label={label} href={href} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExternalReference({ label, href }: { label: string; href: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 py-3 text-sm text-cyan-800 hover:text-cyan-950 hover:underline">
      <span>{label}</span>
      <ExternalLink data-icon="inline-end" className="size-4 shrink-0 transition-transform duration-300 ease-apple" />
    </a>
  );
}
