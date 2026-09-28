import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  Building2,
  CheckCircle2,
  CircleAlert,
  Database,
  ExternalLink,
  FileKey2,
  FolderLock,
  KeyRound,
  ListChecks,
  LockKeyhole,
  ScanSearch,
  ShieldCheck,
  Snowflake,
  UserCheck,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";

const guideSections = [
  { id: "before-you-begin", label: "Before you begin", number: "01" },
  { id: "user-sign-in", label: "App for user sign-in", number: "02" },
  { id: "service-principal", label: "Service principal", number: "03" },
  { id: "workspace-access", label: "Workspace access", number: "04" },
  { id: "scanner", label: "Admin Scanner", number: "05" },
  { id: "snowflake", label: "Snowflake read role", number: "06" },
  { id: "verification", label: "Verify and troubleshoot", number: "07" },
  { id: "references", label: "Official references", number: "08" },
];

// What the backend requests on a device-code sign-in: three Power BI scopes,
// then two Fabric scopes acquired silently from the same account.
const delegatedScopes: [string, string][] = [
  ["Power BI", "Workspace.Read.All"],
  ["Power BI", "Report.Read.All"],
  ["Power BI", "Dataset.Read.All"],
  ["Fabric", "Workspace.Read.All"],
  ["Fabric", "Item.ReadWrite.All"],
];

const snowflakeRoleScript = `-- Run in a Snowflake worksheet. Replace <warehouse> and <database>,
-- and repeat block 2 for every database the application should read.

-- 1. Role and warehouse
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS LINEAGE_READER
  COMMENT = 'Read-only role for PBI Lineage Explorer';
GRANT ROLE LINEAGE_READER TO ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE LINEAGE_READER;

-- 2. Read every object in the database, now and in the future
GRANT USAGE ON DATABASE <database> TO ROLE LINEAGE_READER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL VIEWS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE VIEWS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL MATERIALIZED VIEWS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE MATERIALIZED VIEWS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL DYNAMIC TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL EXTERNAL TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE EXTERNAL TABLES IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON ALL STREAMS IN DATABASE <database> TO ROLE LINEAGE_READER;
GRANT SELECT ON FUTURE STREAMS IN DATABASE <database> TO ROLE LINEAGE_READER;

-- 3. Access history, account usage, and lineage
USE ROLE ACCOUNTADMIN;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE LINEAGE_READER;
GRANT VIEW LINEAGE ON ACCOUNT TO ROLE LINEAGE_READER;`;

const snowflakeDatabaseRoles = `USE ROLE ACCOUNTADMIN;
-- OBJECT_DEPENDENCIES, TABLES, COLUMNS, VIEWS
GRANT DATABASE ROLE SNOWFLAKE.OBJECT_VIEWER TO ROLE LINEAGE_READER;
-- ACCESS_HISTORY, QUERY_HISTORY
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE LINEAGE_READER;`;

const snowflakeKeyPair = `openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub`;

const snowflakeUserScript = `USE ROLE USERADMIN;
CREATE USER IF NOT EXISTS PBI_LINEAGE_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = LINEAGE_READER
  DEFAULT_WAREHOUSE = <warehouse>
  RSA_PUBLIC_KEY = '<contents of rsa_key.pub without the BEGIN and END lines>'
  COMMENT = 'PBI Lineage Explorer service user';

USE ROLE SECURITYADMIN;
GRANT ROLE LINEAGE_READER TO USER PBI_LINEAGE_SVC;`;

const snowflakeCheckScript = `USE ROLE LINEAGE_READER;
USE WAREHOUSE <warehouse>;
SHOW GRANTS TO ROLE LINEAGE_READER;

-- Account usage and access history are readable
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES;
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
WHERE query_start_time > DATEADD(day, -1, CURRENT_TIMESTAMP());

-- Lineage resolves for a table the role can read
SELECT *
FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<database>.<schema>.<table>', 'TABLE', 'UPSTREAM', 2));`;

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
              Create the identities the application signs in with: a Microsoft Entra app for people who use their own access, a service principal for unattended and tenant-wide access, and a read-only Snowflake role that can see every object in your databases and their access history.
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
            <ReadinessItem icon={Users} title="Microsoft Entra administrator" text="App registrations, service principal, secret, and security group" />
            <ReadinessItem icon={ShieldCheck} title="Fabric administrator" text="Tenant settings and workspace roles" />
            <ReadinessItem icon={Snowflake} title="Snowflake administrator" text="Read-only role, service user, and account usage access" />
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
            description="Decide how the application will sign in to Microsoft, then line up the administrators who own each step. One person may hold several of these roles."
          >
            <Subheading title="Choose how the application signs in" />
            <GuideTable
              minWidth="min-w-[760px]"
              headers={["Sign-in", "Use it for", "You will need", "Set up in"]}
              rows={[
                ["Device code", "A person exploring with their own Power BI and Fabric access", "Tenant ID and client ID", "Step 02"],
                ["Service principal", "Unattended access, the same access for a whole team, and the Admin Scanner", "Tenant ID, client ID, and client secret value", "Step 03"],
              ]}
            />
            <p className="text-sm leading-6 text-zinc-600">
              You can set up both. They use separate app registrations, and both need the workspace access in Step 04.
            </p>

            <Subheading title="Who does what" />
            <GuideTable
              headers={["Owner", "What they prepare", "What they hand over"]}
              rows={[
                ["Entra administrator", "The user sign-in app, the service principal and its client secret, admin consent, and the security group.", "Tenant ID, both client IDs, and the secret value"],
                ["Fabric administrator", "Developer and Admin API tenant settings for the service principal's security group.", "Tenant-setting approval"],
                ["Workspace administrator", "A role for each person or the service principal in every workspace to be inspected.", "Workspace role per workspace"],
                ["Snowflake administrator", "The read-only role, the service user, and access to account usage and access history.", "Account identifier, user, role, and warehouse"],
              ]}
            />

            <Checklist
              title="Preflight checklist"
              items={[
                "You know whether people will sign in with their own access, the application will sign in as itself, or both.",
                "A test workspace with at least one report and its semantic model is ready for the first sign-in.",
                "A dedicated Microsoft Entra security group can be created for the service principal.",
                "You know which Snowflake databases the lineage role must read.",
                "A secret store is ready for the client secret and the Snowflake private key. Neither goes into source control, email, or chat.",
              ]}
            />

            <Callout tone="amber" icon={CircleAlert} title="Use least privilege">
              Start with a test workspace and a dedicated security group. Scanner access reveals tenant-wide metadata, so do not enable it broadly just to solve an ordinary workspace permission problem.
            </Callout>
          </GuideSection>

          <GuideSection
            id="user-sign-in"
            number="02"
            icon={KeyRound}
            title="Register an app for user sign-in"
            description="Device code sign-in acts with the signed-in person's own access. The application requests a Power BI token and then a Fabric token, so a working Power BI sign-in does not prove Fabric access."
          >
            <NumberedSteps
              items={[
                <><strong>Register the app.</strong> In the Microsoft Entra admin center, open Applications › App registrations › New registration. Choose <em>Accounts in this organizational directory only</em>, leave the redirect URI empty, and register. Record the Directory (tenant) ID and Application (client) ID from Overview.</>,
                <><strong>Allow public client flows.</strong> Under Authentication, set <em>Allow public client flows</em> to Yes and save. Device code is a public-client flow: without this setting Microsoft rejects the sign-in. This app never gets a client secret.</>,
                <><strong>Add the delegated permissions.</strong> Under API permissions, choose Add a permission › Power BI Service › Delegated permissions, and select <code>Workspace.Read.All</code>, <code>Report.Read.All</code>, <code>Dataset.Read.All</code>, and <code>Item.ReadWrite.All</code>. The Fabric scopes are listed under the same Power BI Service API.</>,
                <><strong>Grant admin consent.</strong> Select <em>Grant admin consent</em> for your tenant. The Fabric token is requested silently after the Power BI sign-in, so a user never gets the chance to approve it. Without consent, Fabric stays not ready.</>,
                <><strong>Give each person workspace access.</strong> Device code can only see what the signed-in person can see, so each user needs the workspace roles in Step 04.</>,
                <><strong>Sign in.</strong> In the application, open Workspace › Power BI setup, choose Device code, enter the tenant and client IDs, and select Start Microsoft sign-in. Finish the Microsoft prompt, then use Check status until Power BI and Fabric both show Connected.</>,
              ]}
            />

            <div className="grid gap-4 md:grid-cols-2">
              <InfoPanel icon={UserCheck} title="Delegated permissions the application requests">
                <ul className="space-y-2 text-sm text-zinc-700">
                  {delegatedScopes.map(([provider, scope]) => (
                    <li key={`${provider}-${scope}`} className="flex gap-2">
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                      <span><span className="text-zinc-500">{provider}:</span> <code className="break-all text-xs sm:text-sm">{scope}</code></span>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs leading-5 text-zinc-500">No tenant-wide permission such as <code>Tenant.Read.All</code> is requested. The Admin Scanner uses the service principal instead.</p>
              </InfoPanel>
              <InfoPanel icon={FileKey2} title="Values to collect">
                <DefinitionList
                  items={[
                    ["Tenant ID", "Directory (tenant) ID from the app's Overview page"],
                    ["Client ID", "Application (client) ID from the same page"],
                    ["Client secret", "None. Device code never uses a secret"],
                    ["Admin consent", "Granted for all four permissions"],
                  ]}
                />
              </InfoPanel>
            </div>
          </GuideSection>

          <GuideSection
            id="service-principal"
            number="03"
            icon={Building2}
            title="Create a service principal"
            description="A service principal signs in as the application itself. It needs its own app registration, a client secret, membership in an allowed security group, and a role in every workspace it reads."
          >
            <NumberedSteps
              items={[
                <><strong>Register a separate app.</strong> Create a second single-tenant app registration for the service principal and record its tenant and client IDs. Keeping it apart from the user sign-in app keeps it free of delegated permissions.</>,
                <><strong>Do not add API permissions.</strong> A service principal is authorized by Fabric tenant settings and workspace roles, not by API permissions. The read-only admin APIs used by the Scanner reject an app that carries admin-consent-required Power BI permissions.</>,
                <><strong>Create a client secret.</strong> Under Certificates &amp; secrets, add a client secret and copy its <strong>Value</strong>, not the Secret ID. It is shown only once. Record the expiry date and who rotates it. The application supports client secrets, not certificates.</>,
                <><strong>Create a security group.</strong> In Microsoft Entra ID › Groups, create a group with the group type Security, and add the service principal as a member by searching for the app name.</>,
                <><strong>Allow the group to call the APIs.</strong> In the Fabric Admin portal, open Tenant settings › Developer settings and enable <em>Service principals can call Fabric public APIs</em> (called <em>Service principals can use Fabric APIs</em> in older tenants). Choose <em>Specific security groups</em>, add the group, and apply. This setting covers both the Power BI and Fabric calls.</>,
                <><strong>Add it to workspaces.</strong> In each workspace, open Manage access and add the service principal or its group with the role from Step 04. Tenant settings alone do not show it any content.</>,
                <><strong>Connect.</strong> In Workspace › Power BI setup, choose Service principal, enter the tenant ID, client ID, and secret value, and select Connect service principal. <em>Partial</em> means Power BI connected but Fabric did not; re-check the tenant setting and the workspace role. Tenant-setting changes can take up to 15 minutes to apply.</>,
              ]}
            />

            <div className="grid gap-4 md:grid-cols-2">
              <InfoPanel icon={FileKey2} title="Values to collect">
                <DefinitionList
                  items={[
                    ["Tenant ID", "Directory (tenant) ID"],
                    ["Client ID", "Application (client) ID of the service principal's app"],
                    ["Client secret", "The secret Value, kept in a secret store until it is entered"],
                    ["Security group", "The group allowed in the Developer and Admin API tenant settings"],
                  ]}
                />
              </InfoPanel>
              <InfoPanel icon={ShieldCheck} title="Interactive and unattended access are different">
                <p className="text-sm leading-6 text-zinc-700">
                  Delegated sign-in acts with a person&apos;s access. A service principal acts as the application and must be allowed separately, by tenant settings and workspace roles. Never use the client secret with device code.
                </p>
              </InfoPanel>
            </div>
          </GuideSection>

          <GuideSection
            id="workspace-access"
            number="04"
            icon={FolderLock}
            title="Grant workspace and item access"
            description="Tenant settings let an identity call the APIs; workspace roles decide what it can see. Grant the same access to each person who uses device code, or to the service principal or its security group."
          >
            <GuideTable
              minWidth="min-w-[860px]"
              headers={["Application feature", "What it reads", "Minimum access"]}
              rows={[
                ["Overview, Workspace content", "Workspaces, reports, and semantic models", "Viewer on each workspace"],
                ["Report details: Pages", "Report pages", "Viewer"],
                ["Report details: Data sources, Semantic objects, Database mapping, Visual fields", "Report (PBIR) and semantic model (TMDL) definitions from Fabric", "Contributor. Fabric returns a definition only to an identity with read and write permission on the item"],
                ["Report lineage, Table impact, Measure impact", "The same definitions for every report bound to the model", "Contributor on the report and model workspaces"],
                ["A report bound to a model in another workspace", "The model's definition in its own workspace", "The same role in the model's workspace"],
                ["Gateway sources (optional checkbox)", "Gateway data sources", "Gateway admin on each gateway"],
                ["XMLA metadata (optional)", "Model metadata over the XMLA endpoint", "Build permission on the model, on a Premium, Fabric, or PPU capacity with the XMLA endpoint set to Read"],
              ]}
            />

            <Callout tone="amber" icon={CircleAlert} title="Why Contributor">
              Fabric only returns report and semantic model definitions to an identity that can edit the item, so Contributor is the lowest workspace role that loads the definition-based sections. The application itself only reads. With Viewer, the inventory and pages still load, and the definition-based sections show an access warning instead of data.
            </Callout>
          </GuideSection>

          <GuideSection
            id="scanner"
            number="05"
            icon={ScanSearch}
            title="Enable the Power BI Admin Scanner"
            description="The Scanner reads tenant-wide metadata through the Power BI admin APIs. It works only with the service principal and is optional; skip this step if workspace-level access is enough."
          >
            <NumberedSteps
              items={[
                <>Use the service principal from Step 03 and its security group. Device code cannot run the Scanner because it never requests tenant-wide permission.</>,
                <>In the Fabric Admin portal, open Tenant settings › Admin API settings and enable <em>Service principals can access read-only admin APIs</em> for the group under <em>Specific security groups</em>.</>,
                <>Enable <em>Enhance admin APIs responses with detailed metadata</em> for table, column, and measure metadata.</>,
                <>Enable <em>Enhance admin APIs responses with DAX and mashup expressions</em> when you need measure expressions and Power Query sources. It needs the detailed-metadata setting first.</>,
                <>Confirm the app carries no admin-consent-required Power BI permissions: Microsoft Entra ID › Enterprise applications › your app › Permissions should list no Power BI permissions of type Application.</>,
                <>Allow up to 15 minutes for the settings to apply, connect as the service principal, and run a one-workspace scan before a wider one. Each scan uses Microsoft admin API quota.</>,
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
                  <Bullet>The workspace roles that ordinary report and Fabric definition calls need.</Bullet>
                  <Bullet>Contributor access for PBIR and TMDL definitions.</Bullet>
                  <Bullet>XMLA, gateway-admin, or Snowflake permissions.</Bullet>
                </ul>
              </InfoPanel>
            </div>
          </GuideSection>

          <GuideSection
            id="snowflake"
            number="06"
            icon={Snowflake}
            title="Create the Snowflake read role"
            description="Snowflake is the database connector for source enrichment and deep table and column lineage. The role below can read every object in the chosen databases and the SNOWFLAKE.ACCOUNT_USAGE views, including ACCESS_HISTORY, that lineage is built from. It cannot change anything."
          >
            <Subheading title="What the role is granted" />
            <GuideTable
              minWidth="min-w-[760px]"
              headers={["Grant", "What it gives the application"]}
              rows={[
                [<code>USAGE</code>, "A warehouse to run lineage and metadata queries."],
                [<code>USAGE, SELECT</code>, "Every schema, table, view, materialized view, dynamic table, external table, and stream in each database, including ones created later. Lineage stops at any object the role cannot read."],
                [<code>IMPORTED PRIVILEGES</code>, <>All <code>SNOWFLAKE.ACCOUNT_USAGE</code> views: <code>ACCESS_HISTORY</code> (which queries read and wrote which columns), <code>QUERY_HISTORY</code>, and <code>OBJECT_DEPENDENCIES</code> (which views depend on which tables).</>],
                [<code>VIEW LINEAGE</code>, <>Calls to <code>SNOWFLAKE.CORE.GET_LINEAGE</code>. The PUBLIC role holds it by default; granting it directly keeps lineage working if it is revoked from PUBLIC.</>],
              ]}
            />

            <Subheading title="Create the role" />
            <CodeBlock label="Snowflake worksheet · SECURITYADMIN and ACCOUNTADMIN" value={snowflakeRoleScript} />

            <details className="border border-zinc-200 bg-white px-4 py-3 open:pb-4">
              <summary className="cursor-pointer text-sm font-semibold text-zinc-950">Narrower alternative to IMPORTED PRIVILEGES</summary>
              <div className="mt-4 space-y-3 text-sm leading-6 text-zinc-600">
                <p><code>IMPORTED PRIVILEGES</code> opens every account usage view. To limit the role to the views lineage uses, grant these two SNOWFLAKE database roles instead of the <code>IMPORTED PRIVILEGES</code> line.</p>
                <CodeBlock label="Snowflake worksheet · ACCOUNTADMIN" value={snowflakeDatabaseRoles} />
              </div>
            </details>

            <Subheading title="Create the application user" />
            <p className="text-sm leading-6 text-zinc-600">
              Create a dedicated service user that signs in with a key pair. The setup screen takes the private key without a passphrase, so generate an unencrypted PKCS#8 key and keep it in your secret store.
            </p>
            <CodeBlock label="Terminal with OpenSSL" value={snowflakeKeyPair} />
            <CodeBlock label="Snowflake worksheet · USERADMIN and SECURITYADMIN" value={snowflakeUserScript} />
            <p className="text-sm leading-6 text-zinc-600">
              A <code>TYPE = SERVICE</code> user cannot sign in with a password. To use password sign-in instead, grant <code>LINEAGE_READER</code> to a person&apos;s user.
            </p>

            <Subheading title="Check the role" />
            <CodeBlock label="Snowflake worksheet · LINEAGE_READER" value={snowflakeCheckScript} />

            <InfoPanel icon={CircleAlert} title="Good to know">
              <ul className="space-y-2 text-sm leading-6 text-zinc-700">
                <Bullet>Account usage views lag behind: <code>ACCESS_HISTORY</code> and <code>OBJECT_DEPENDENCIES</code> by up to 3 hours, <code>QUERY_HISTORY</code> by up to 45 minutes. New objects appear after that.</Bullet>
                <Bullet><code>GET_LINEAGE</code> needs Enterprise Edition or higher and traces at most 5 levels per call; the application goes deeper by repeating the call.</Bullet>
                <Bullet>A schema&apos;s own future grants take precedence over the database-level future grants above. If a schema already has future grants, repeat the grants for that schema.</Bullet>
                <Bullet>Do not use <code>ACCOUNTADMIN</code> or <code>SYSADMIN</code> as the application&apos;s role; both can change data.</Bullet>
              </ul>
            </InfoPanel>

            <Subheading title="Choose how the application signs in to Snowflake" />
            <div className="grid gap-4 sm:grid-cols-2">
              <MethodPanel title="Key pair" badge="Recommended" text="For the service user above. Paste the unencrypted private key PEM on the Database setup page." />
              <MethodPanel title="OAuth token" badge="Enterprise" text="An access token from your approved Snowflake OAuth integration, issued for LINEAGE_READER. Renewing the token stays with you." />
              <MethodPanel title="Password" badge="Person user" text="For a person's user that holds LINEAGE_READER. Snowflake is phasing out single-factor passwords, so prefer a key pair." />
              <MethodPanel title="External browser" badge="Local only" text="Opens a browser on the backend host, not on your computer. It stays off unless the backend operator turns it on." />
            </div>

            <GuideTable
              headers={["Application field", "What to enter", "Required"]}
              rows={[
                ["Account identifier", <>Your <code>orgname-account_name</code> identifier, not a URL</>, "Yes"],
                ["User", <><code>PBI_LINEAGE_SVC</code>, or the person&apos;s user that holds the role</>, "Yes"],
                ["Role", <><code>LINEAGE_READER</code></>, "Recommended"],
                ["Warehouse", "The warehouse granted to the role", "Recommended"],
                ["Database and schema", "Default context; fully qualified names still trace", "Optional"],
                ["Credential", "Private key PEM, OAuth token, or password, depending on the method", "Depends on method"],
              ]}
            />

            <Callout tone="amber" icon={LockKeyhole} title="Keep credentials out of the browser">
              Microsoft and Snowflake sessions are separate. Credentials are sent once to the backend and never stored in browser storage. Keep the private key, OAuth token, and passwords in a secret store, never in Git, screenshots, or chat.
            </Callout>
          </GuideSection>

          <GuideSection
            id="verification"
            number="07"
            icon={CheckCircle2}
            title="Verify access and resolve common failures"
            description="Check one identity at a time. A connected status proves the sign-in worked; the checks below prove the access behind it."
          >
            <Checklist
              title="Acceptance checklist"
              items={[
                "Device code: Power BI and Fabric both show Connected, and an expected workspace is listed by name.",
                "Service principal: the same result with the Service principal option, and no Partial status.",
                "A report's Semantic objects and Visual fields load, which proves Fabric definition access.",
                "If enabled, a one-workspace Scanner run reaches Succeeded and returns detailed metadata.",
                "Database setup shows LINEAGE_READER as the role and the intended warehouse.",
                "A Snowflake table trace returns upstream objects.",
              ]}
            />

            <GuideTable
              minWidth="min-w-[900px]"
              headers={["Symptom", "Check first", "Likely owner"]}
              rows={[
                ["Device code sign-in fails at once", "Allow public client flows is Yes on the app, and the tenant and client IDs match", "Entra administrator"],
                ["Power BI ready, Fabric not ready", "Admin consent for the delegated permissions (device code), or the Fabric public APIs tenant setting for the group (service principal)", "Entra or Fabric administrator"],
                ["Service principal is rejected", "Secret Value rather than Secret ID, secret expiry, group membership, tenant-setting scope, and up to 15 minutes for changes", "Entra or Fabric administrator"],
                ["Workspace or report missing", "The identity has a role in that workspace; a service principal must be added explicitly", "Workspace administrator"],
                ["Definition sections show an access warning", "Contributor on the report and model workspaces, and no protected sensitivity label on the item", "Workspace administrator"],
                ["Scanner returns 401 or 403", "Read-only admin API setting for the group, the metadata settings, and no admin-consent-required permissions on the app", "Fabric administrator"],
                ["Snowflake cannot connect", "Account identifier format, user type (service users need a key pair or OAuth), registered public key, and network policy", "Snowflake administrator"],
                ["Account usage or access history not authorized", "IMPORTED PRIVILEGES on SNOWFLAKE, or the OBJECT_VIEWER and GOVERNANCE_VIEWER database roles", "Snowflake administrator"],
                ["Snowflake lineage empty or denied", "Enterprise Edition, SELECT on the traced object, VIEW LINEAGE, and account usage latency for new objects", "Snowflake administrator"],
              ]}
            />

            <Callout tone="rose" icon={CircleAlert} title="Do not solve access failures by exposing secrets">
              Never put a client secret, Snowflake credential, OAuth token, private key, or session cookie into a screenshot, exported table, URL, source file, or support message. Use the sanitized status and error codes for troubleshooting.
            </Callout>

            <div className="flex flex-wrap gap-3">
              <Button nativeButton={false} render={<Link to="/workspace/power-bi" />}>
                Start Power BI setup
                <ArrowRight data-icon="inline-end" className="size-4" />
              </Button>
              <Button nativeButton={false} variant="outline" render={<Link to="/workspace/database" />}>
                <Database className="size-4" />
                Connect Snowflake
              </Button>
            </div>
          </GuideSection>

          <GuideSection
            id="references"
            number="08"
            icon={BookOpenCheck}
            title="References"
            description="Use the official product documentation as the authority for current permissions, tenant setting names, authentication policy, and feature availability."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <ReferenceGroup
                title="Microsoft Entra, Power BI, and Fabric"
                links={[
                  ["Register a Microsoft Entra application", "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"],
                  ["Power BI REST API overview", "https://learn.microsoft.com/en-us/rest/api/power-bi/"],
                  ["Fabric REST API identity support", "https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support"],
                  ["Developer tenant settings for service principals", "https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer"],
                  ["Enable service principals for admin APIs", "https://learn.microsoft.com/en-us/fabric/admin/enable-service-principal-admin-apis"],
                  ["Set up metadata scanning", "https://learn.microsoft.com/en-us/fabric/admin/metadata-scanning-setup"],
                  ["Admin API tenant settings", "https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-admin-api-settings"],
                  ["Fabric Get Item Definition permissions", "https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item-definition"],
                ]}
              />
              <ReferenceGroup
                title="Snowflake"
                links={[
                  ["Account Usage views and database roles", "https://docs.snowflake.com/en/sql-reference/account-usage"],
                  ["ACCESS_HISTORY view", "https://docs.snowflake.com/en/sql-reference/account-usage/access_history"],
                  ["Data lineage access control", "https://docs.snowflake.com/en/user-guide/ui-snowsight-lineage"],
                  ["GRANT privileges", "https://docs.snowflake.com/en/sql-reference/sql/grant-privilege"],
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

// The first column names the row; wide tables scroll inside their own border.
function GuideTable({ headers, rows, minWidth = "min-w-[720px]" }: { headers: string[]; rows: ReactNode[][]; minWidth?: string }) {
  return (
    <div className="overflow-x-auto border border-zinc-200 bg-white">
      <table className={`w-full ${minWidth} border-collapse text-left text-sm`}>
        <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
          <tr>
            {headers.map((header) => (
              <th key={header} className="border-b border-zinc-200 px-4 py-3 font-semibold">{header}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 text-zinc-700">
          {rows.map((cells, rowIndex) => (
            <tr key={rowIndex}>
              {cells.map((cell, cellIndex) => (
                <td key={cellIndex} className={cellIndex === 0 ? "px-4 py-3 font-medium text-zinc-950" : "px-4 py-3 leading-6"}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
