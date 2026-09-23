# PBI Lineage Backend

Standalone FastAPI backend for Power BI, Microsoft Fabric, and optional
Snowflake metadata discovery, report definition retrieval, PBIR normalization,
physical-source discovery, lineage graph construction, and impact analysis.

This backend is being split out from the original Streamlit-based PBI Lineage
Explorer so the application can evolve into a cleaner service-oriented
architecture.

## What This Service Does

Current capabilities:

- Supports Microsoft device-code authentication, browser Authorization Code +
  PKCE SSO, and Microsoft Entra service-principal client-secret authentication
  for unattended application sessions.
- Stores short-lived in-memory auth sessions.
- Lists Power BI workspaces.
- Gets one Power BI workspace.
- Lists Power BI reports in a workspace.
- Gets one Power BI report.
- Gets one report from the authenticated user's My workspace.
- Lists report pages.
- Gets one report page.
- Lists Power BI semantic models/datasets in a workspace.
- Lists Power BI gateways for which the authenticated user is an administrator.
- Gets connection metadata for one datasource on an accessible Power BI gateway.
- Lists datasources on an accessible Power BI gateway.
- Runs the Power BI Admin metadata-scanning workflow for modified workspace
  discovery, scan submission, status polling, and complete scan-result
  retrieval.
- Retrieves Fabric report definitions.
- Decodes and normalizes PBIR report definitions.
- Extracts visual titles, visual positions, visual types, page metadata, and
  semantic model references from PBIR.
- Extracts visual field references for columns, measures, hierarchies, sorts,
  filters, and projections.
- Retrieves Fabric semantic model definitions in TMDL/TMSL format.
- Parses TMDL semantic model definitions into tables, columns, measures,
  relationships, hierarchies, calculated tables, and Power Query partitions.
- Carries semantic model source-path evidence into lineage matches.
- Extracts XMLA semantic model metadata through an ADODB COM/MSOLAP adapter
  when the host has the Analysis Services OLE DB provider configured.
- Combines parsed Fabric TMDL and XMLA metadata into a source-preserving
  semantic metadata response with object reconciliation evidence.
- Adds lineage diagnostics with match confidence, candidate suggestions, and
  summary counts by status and object type.
- Exposes provider authentication/scope diagnostics.
- Validates Fabric report definition formats separately from semantic model
  definition formats.
- Surfaces provider error details for Fabric request and operation failures.
- Runs in a deployed Windows container environment with COM, ADODB, and MSOLAP
  available at runtime.
- Is publicly hosted over HTTPS through Cloudflare DNS, an AWS Application Load
  Balancer, and a private Windows ECS task.
- Parses measure, calculated-column, and calculated-table DAX references and
  reports unresolved references and dependency cycles.
- Extracts supported Power Query/M connectors, native SQL objects, navigation
  targets, files, URLs, storage accounts, and query-to-source mappings.
- Parses an allowlisted, non-secret subset of gateway `connectionDetails` and
  matches gateway datasources to detected query sources.
- Exposes five frontend-ready explorer datasets plus one combined snapshot for
  source database lineage, semantic objects, DAX-to-source lineage, report
  layout, and visual-to-semantic lookup. Shared provider evidence is fetched
  once per request with bounded concurrency.
- Builds canonical upstream-to-downstream lineage graphs spanning physical
  sources, queries, semantic objects, DAX dependencies, and report visuals.
- Provides reverse impact, graph search, and upstream/downstream navigation.
- Discovers workspace-level report/semantic-model inventory and bindings.
- Authenticates live Snowflake connector sessions with password/MFA, in-memory
  RSA private keys, external-browser SSO for interactive local hosts, or OAuth.
- Traces Snowflake table or column lineage beyond the provider's five-level
  `SNOWFLAKE.CORE.GET_LINEAGE` call limit by expanding boundary objects in
  bounded parallel waves. The supplied procedure logic runs in the backend;
  no stored procedure is installed in a customer account.
- Retains the earlier optional Snowflake SQL API path for normalizing
  `ACCOUNT_USAGE.OBJECT_DEPENDENCIES` evidence supplied with a bearer token.
- Persists versioned graph snapshots in SQLite, detects incremental changes,
  caches graph reads, runs asynchronous scan jobs, and validates lineage quality.
- Builds synchronous or asynchronous live lineage scans from workspace/model
  IDs and an optional report ID using the current Fabric and Power BI session.
  Provider tokens stay in process memory and are never written to scan-job
  payloads or graph storage.
- Provides configurable API-key enforcement, secure headers/cookies, trusted
  hosts, request-size limits, readiness checks, and Prometheus-format metrics.
- Exposes an authenticated, evidence-grounded Power AI (`/ai/status`,
  `/ai/chat`, `/ai/chat/stream`) that explains — and never invents — facts a
  deterministic Measure/Report/Impact agent gathers from the existing
  lineage services; the model is skipped entirely whenever evidence is
  insufficient, ambiguous, or conflicting. Provider-independent
  (OpenAI/Anthropic/Gemini/Azure OpenAI/a local fake provider, switchable by
  configuration alone) and disabled by default (see "Power AI" below).

Remaining acceptance and scale work:

- Improve semantic model parser coverage for more TMDL shapes.
- Run live XMLA acceptance validation against a Power BI/Fabric capacity.
- Validate the browser SSO callback against its public-client redirect URI in
  the target Microsoft Entra tenant.
- Run live Snowflake authentication and deep-lineage acceptance with a role
  permitted to call `SNOWFLAKE.CORE.GET_LINEAGE`.
- Add production-grade auth/session storage.
- Move lineage persistence and scan coordination to shared infrastructure before
  running multiple API workers/tasks.
- Expand DAX and Power Query grammar coverage with tenant-derived fixtures.
- Automate ECS task-definition registration and service rollout after an
  immutable Amazon ECR image is published.
- Add production high availability, alarms, and autoscaling.
- Power AI: persist conversation history (currently request-scoped only, so
  cross-turn pronoun resolution like "that measure" is not implemented), add
  an LLM fallback router for genuinely ambiguous intent, add Snowflake-backed
  evidence tools, wire live TMDL-vs-XMLA conflict checking into the default
  request path (currently opt-in only, since XMLA needs a Windows/MSOLAP
  host), and add a standing evaluation-fixture suite. The
  Measure/Report/Impact agents, tool registry, grounded composer, grounding
  validator, and deterministic fallback renderer are implemented and tested.

Power AI is being introduced in controlled phases; only its
provider-independent foundation is included in this phase (see "Power AI"
below). It never derives lineage facts itself — it explains facts the
existing deterministic lineage engine already computed.

## Technology Stack

- Python 3.13
- FastAPI
- Pydantic / Pydantic Settings
- httpx
- MSAL
- LiteLLM (provider-neutral LLM adapter for Power AI)
- Snowflake Connector for Python
- Snowpark Python
- cryptography for in-memory RSA key loading
- Python `venv` and pip
- pytest / pytest-asyncio
- ruff
- Windows Docker Engine / Windows Server Core LTSC 2025
- Amazon ECR, ECS EC2 (Windows Server 2025), Application Load Balancer, and
  CloudWatch Logs
- GitHub Actions with OIDC and a dedicated Windows self-hosted build runner
- Cloudflare DNS and AWS Certificate Manager

## Quick Start

For a complete clean-machine installation, including Microsoft/Fabric,
Power BI Scanner, Windows XMLA/MSOLAP, Snowflake, container, network, security,
and troubleshooting steps, follow [`INSTALLATION.md`](INSTALLATION.md).

Create and activate the virtual environment, then install dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

Run the development server:

```powershell
fastapi dev app/main.py
```

Default local docs:

```text
http://127.0.0.1:8000/docs
```

Run tests:

```powershell
python -m pytest
```

Run linting:

```powershell
ruff check .
ruff format --check .
```

### Windows Container Deployment

The supported image is Windows-only because XMLA uses `pywin32`, Windows COM,
`ADODB.Connection`, and the Microsoft Analysis Services OLE DB Provider
(`MSOLAP`). Do not replace it with a Linux base image unless those dependencies
are revalidated.

Set `MSOLAP_MSI_URL` to the public x64 Microsoft installer URL, then build the
production image:

```powershell
$MSOLAP_MSI_URL = "<Microsoft MSOLAP x64 MSI URL>"
docker build `
  --build-arg "MSOLAP_MSI_URL=$MSOLAP_MSI_URL" `
  -t pbi-lineage-backend:prod .
```

Run the verified local container:

```powershell
docker run --rm `
  --name pbi-lineage-api `
  -p 8000:8000 `
  pbi-lineage-backend:prod
```

The image starts Uvicorn on `0.0.0.0:8000` with one worker. One worker is
intentional until the in-memory Microsoft authentication state and live
Snowflake connector-session ownership are redesigned for shared/multi-worker
operation. Local production-image build and container runtime validation
completed successfully on Windows Server 2025, and the image is now deployed
on AWS Windows ECS capacity.

### Hosted AWS Deployment

The public backend is available at `https://api.<domain>`. The root domain is
intentionally separate so it can host a future frontend.

```text
Cloudflare DNS
  -> AWS Application Load Balancer HTTPS :443
  -> private ECS Windows task HTTP :8000
  -> FastAPI
```

- AWS Region: `ap-south-1`.
- The ECR repository stores immutable images tagged with the full Git SHA.
- The ECS service uses Windows Server 2025 EC2 capacity, `awsvpc` networking,
  and private task IPs. Port `8000` is reachable only from the load balancer
  security group.
- The load balancer redirects HTTP `:80` to HTTPS `:443`; its target group uses
  `GET /api/v1/health` as the health check.
- GitHub Actions authenticates to AWS with OIDC and builds Windows images on a
  dedicated self-hosted Windows runner. ECR build/push is operational; automatic
  ECS rollout after the push is the remaining CI/CD automation step.

Check the hosted service:

```text
https://api.<domain>/api/v1/health
https://api.<domain>/docs
```

Deployment architecture, operational procedures, and recovery guidance are in
[`REF_DOC/PBI-Lineage-Backend-Deployment-Context.md`](REF_DOC/PBI-Lineage-Backend-Deployment-Context.md)
and [`REF_DOC/PBI-Lineage-Backend-AWS-Deployment-Runbook.md`](REF_DOC/PBI-Lineage-Backend-AWS-Deployment-Runbook.md).

## Environment

`.env.example`:

```text
APP_NAME=PBI Lineage Backend
APP_VERSION=0.1.0
ENVIRONMENT=development
API_V1_PREFIX=/api/v1
LOG_LEVEL=INFO
XMLA_TENANT_NAME=myorg
XMLA_PROVIDER=MSOLAP
# MICROSOFT_SSO_REDIRECT_URI=
LINEAGE_DATABASE_PATH=data/lineage.db
LINEAGE_CACHE_TTL_SECONDS=30
LINEAGE_CACHE_MAX_ENTRIES=128
LINEAGE_SCAN_MAX_CONCURRENCY=2
SNOWFLAKE_SESSION_MAX_AGE_SECONDS=2700
SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=false
CORS_ALLOWED_ORIGINS=[]
ALLOWED_HOSTS=["*"]
FORCE_HTTPS=false
ENABLE_API_DOCS=true
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
MAX_REQUEST_BODY_BYTES=10485760
EXPOSE_METRICS=true
AI_ENABLED=false
AI_PROVIDER=fake
AI_MODEL=fake-model
AI_TEMPERATURE=0.1
AI_MAX_TOKENS=4000
AI_REQUEST_TIMEOUT_SECONDS=30
AI_STREAMING_ENABLED=true
```

`MICROSOFT_SSO_REDIRECT_URI` is only required to enable
`GET /auth/microsoft/sso/login`; it must exactly match a public-client/native
redirect URI registered under **Mobile and desktop applications** on the Entra
app registration. Public client flows must be enabled because this
implementation uses `PublicClientApplication`, PKCE, and no client secret. A
redirect registered only under **Web** represents a confidential client and is
not compatible with this implementation without changing it to use a secret
or certificate. See Microsoft's [authorization-code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
and [redirect URI platform configuration](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri).

For production, set `AUTH_COOKIE_SECURE=true`, configure explicit
`ALLOWED_HOSTS`, provide `LINEAGE_ADMIN_API_KEY`, and normally disable API docs.
`CORS_ALLOWED_ORIGINS` and `ALLOWED_HOSTS` use JSON-list syntax in environment
variables. SQLite and the in-process scan scheduler match the current
single-worker deployment; move both to shared infrastructure before scaling to
multiple workers or tasks.

Snowflake connector sessions are also process-local and default to a 45-minute
maximum age. Keep `SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=false` on hosted
runtimes: the connector opens the browser on the backend host, not in the API
caller's browser. Use OAuth or key-pair authentication for unattended hosting.

XMLA live extraction requires a Windows host with `pywin32` and the Microsoft
Analysis Services OLE DB Provider (`MSOLAP`) installed. The backend opens an
`ADODB.Connection` through COM and passes the Power BI access token in the OLE
DB connection string. The production Dockerfile supplies and verifies these
Windows dependencies in a Windows Server Core LTSC 2025 container. Live XMLA
still needs a Power BI/Fabric capacity with XMLA enabled and a permitted user.

Power AI (`AI_*`) is disabled by default (`AI_ENABLED=false`) and defaults to
the network-free `fake` provider even when enabled, so existing deployments
are unaffected unless explicitly configured. Set `AI_PROVIDER` to `openai`,
`anthropic`, `gemini`, or `azure_openai` and provide only that provider's
credential (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or
`AZURE_OPENAI_API_KEY`); `AI_API_BASE`/`AI_API_VERSION` are for Azure
OpenAI/Ollama-style custom endpoints. Provider switching never requires
rewriting agents, tools, endpoints, or evidence schemas — only these
settings change. The first request to a real (non-`fake`) provider on a
fresh host may require one-time outbound HTTPS access to
`openaipublic.blob.core.windows.net` for LiteLLM's bundled tokenizer data;
this is unrelated to chat completions themselves (token usage is read from
each provider's own API response) and is normally satisfied once during
image build, not at request time. See "Power AI" below for the current
scope.

### GitHub production feature switches

The Azure backend deployment reads two non-secret switches from the GitHub
`production` environment. They are no longer hardcoded in the VM deployment
script and both fail closed (`false`) when the variable is missing.

| GitHub environment variable | Values | Recommended production value | Effect |
| --- | --- | --- | --- |
| `ENABLE_API_DOCS` | `true` or `false` | `false` unless operators need the live catalog | Controls FastAPI Swagger/ReDoc and `/openapi.json`. The frontend API Reference needs `/openapi.json` for the complete live operation list. |
| `AI_ENABLED` | `true` or `false` | `false` until Power AI is approved | Controls `/api/v1/ai/chat` and `/api/v1/ai/chat/stream`. `/api/v1/ai/status` remains the frontend's source of truth. |

Configure them in GitHub:

1. Open the **PBI-Lineage-Backend** repository.
2. Go to **Settings -> Environments -> production**.
3. Under **Environment variables**, create `ENABLE_API_DOCS` and
   `AI_ENABLED` using lowercase `true` or `false`.
4. Run **Actions -> Backend CD -> Run workflow** from `main`, or merge a
   commit that completes Backend CI while `DEPLOYMENT_ENABLED=true`.
5. Verify Power AI with `GET /api/v1/ai/status`. Changing a GitHub variable
   does not alter the already-running container until Backend CD redeploys it.

The automated Azure deployment currently keeps `AI_PROVIDER=fake`, which is
deterministic and requires no external API key. `AI_ENABLED=true` therefore
enables the safe end-to-end Power AI path, not a paid external model. Before
switching to a real provider, extend the deployment to load the selected
provider credential from Azure Key Vault. Never put provider keys in GitHub
variables, frontend `VITE_*` values, workflow logs, or source control.

For local development, set the same backend values in `.env` and restart
FastAPI. No frontend AI environment variable is required.

## API Overview

All endpoints are mounted under `/api/v1`.

### Health

```text
GET /api/v1/health
GET /api/v1/health/live
GET /api/v1/health/ready
GET /api/v1/health/metrics
```

### Authentication

```text
POST /api/v1/auth/microsoft/device/start
GET  /api/v1/auth/microsoft/device/status
GET  /api/v1/auth/microsoft/device/{session_id}/status
POST /api/v1/auth/microsoft/device/logout
GET  /api/v1/auth/microsoft/sso/login
GET  /api/v1/auth/microsoft/sso/callback
POST /api/v1/auth/microsoft/service-principal/session
GET  /api/v1/auth/microsoft/service-principal/session/status
DELETE /api/v1/auth/microsoft/service-principal/session
POST /api/v1/auth/snowflake/session
GET  /api/v1/auth/snowflake/session/status
DELETE /api/v1/auth/snowflake/session
```

Device auth status is intended to show:

- Overall auth status.
- Power BI connection result.
- Fabric connection result.
- Requested scopes.
- Granted scopes.
- Missing scopes.
- Provider error code.

`GET /microsoft/sso/login` is a browser-redirect alternative to device code:
it starts a Microsoft Entra ID Authorization Code + PKCE flow (public client,
no client secret) for the same delegated Power BI/Fabric scopes as device
code, and creates an identical cookie-backed session on success (readable by
`GET /microsoft/device/status` and closable by `POST /microsoft/device/logout`
with `authentication_method="sso"` instead of `"device_code"`).
Query parameters:

- `tenant_id`, `client_id` (required): same meaning as the device-code route.
- `post_login_redirect_uri` (optional): where to send the browser after a
  successful login. Its origin must exactly match one entry in
  `CORS_ALLOWED_ORIGINS`, or the request is rejected with
  `AUTH_REDIRECT_NOT_ALLOWED` before any redirect to Microsoft happens. When
  omitted, `GET /microsoft/sso/callback` returns the same JSON status body as
  `GET /microsoft/device/status` instead of redirecting.

`GET /microsoft/sso/login` requires `MICROSOFT_SSO_REDIRECT_URI` to be set and
requires a matching public-client/native redirect URI under **Mobile and
desktop applications**, with public client flows enabled. This flow only
acquires delegated Power BI/Fabric resource tokens; it does not use an OpenID
Connect `id_token` and does not establish any product-level user identity or
role. Pending state and PKCE verifiers are process-local, single-use, and valid
for ten minutes, so the callback must return to the same API instance until
shared session storage is implemented.

The service-principal session route accepts `tenant_id`, `client_id`, and
`client_secret`, then requests independent application tokens for these MSAL
client-credential scopes:

```text
https://analysis.windows.net/powerbi/api/.default
https://api.fabric.microsoft.com/.default
```

The client secret is a write-only request value. It is not returned, logged,
or stored in the process-local session. The response reports token acquisition
and any JWT application roles; it does not claim that a downstream tenant API
has authorized the app. A Power BI token is required for session creation. If
Fabric token acquisition fails, the response is `partial` and the Power BI
token remains usable. These routes use `X-Lineage-Admin-Key` when
`LINEAGE_ADMIN_API_KEY` is configured.

Microsoft's official client-credential flow uses one resource's `/.default`
scope per token request. See [Microsoft identity platform daemon application
guidance](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-daemon-acquire-token).

The Snowflake routes create, inspect, and close a separate HttpOnly session
cookie named `pbi_lineage_snowflake_session`. They do not reuse the Microsoft
Power BI/Fabric session.

### Power BI Metadata

```text
GET /api/v1/workspaces
GET /api/v1/workspaces/{workspace_id}
GET /api/v1/workspaces/{workspace_id}/reports
GET /api/v1/workspaces/{workspace_id}/reports/{report_id}
GET /api/v1/workspaces/{workspace_id}/reports/{report_id}/pages
GET /api/v1/workspaces/{workspace_id}/reports/{report_id}/pages/{page_name}
GET /api/v1/workspaces/{workspace_id}/semantic-models
GET /api/v1/reports/{report_id}
```

`GET /api/v1/reports/{report_id}` uses the Power BI **My workspace** endpoint.
It is distinct from the existing workspace-scoped report route.

`GET /api/v1/workspaces` reports each workspace's `type` and omits the ones
Power BI provisions for itself (`AdminInsights`, shown in the portal as "Admin
monitoring"): their semantic models are not readable through the Fabric
definition APIs, so every lineage call against them fails upstream. Filtering
is by `type`, not by the localizable display name. The single-workspace
`GET /workspaces/{workspace_id}` route is not filtered — asking for one
directly returns it.

Reports carry `dataset_workspace_id` (Power BI's `datasetWorkspaceId`) for
reports bound to a semantic model in another workspace. Power BI only
populates it in some tenants, so treat it as a hint: the explorer resolves a
model's workspace as explicit `semantic_model_workspace_id` → the report's
`dataset_workspace_id` → the report's own workspace. Note that a report
reaching into a second workspace is more often a *composite model* (a
DirectQuery-to-semantic-model table), which shows up in the source datasets
rather than here — see Explorer Data.

### Power BI Gateways

```text
GET /api/v1/gateways
GET /api/v1/gateways/{gateway_id}/datasources
GET /api/v1/gateways/{gateway_id}/datasources/{datasource_id}
```

Gateway endpoints require a Power BI token with `Dataset.Read.All` or
`Dataset.ReadWrite.All`, and the authenticated user must be a gateway admin.
Virtual network gateways are not supported by these Power BI APIs. Datasource
responses preserve connection metadata and credential type, but never expose
credential values.

Datasource responses also include `sso_enabled`, derived from the
provider's `credentialType`/`credentialDetails.useEndUserOAuth2Credentials`.
It reports Microsoft Entra ID SSO passthrough for OAuth2-credentialed
connectors only (for example Snowflake, Azure SQL, Azure Databricks): `true`
or `false` when Microsoft returns the end-user OAuth2 flag, and `null` when
that flag is absent or the datasource uses another credential type. Kerberos
and SAML AD-SSO (used by on-premises sources such as SQL Server, Oracle, and
SAP) are not exposed by this API and are never reported; `null` means "not
applicable or unknown," not "SSO is off."
The same field is carried onto matched entries in
`PhysicalSourceDiscoveryResponse.sources` (`/lineage/physical-sources/analyze`)
when a detected Power Query source resolves to a gateway datasource. The
Explorer endpoints do not yet expose this field; their source-database-lineage
row is a separate, explicitly-mapped schema.

### Power BI Scanner

The Scanner routes have their own `Scanner` section in Swagger:

```text
GET  /api/v1/scanner/workspaces/modified
POST /api/v1/scanner/workspaces/scan
GET  /api/v1/scanner/scans/{scan_id}/status
GET  /api/v1/scanner/scans/{scan_id}/result
```

Recommended app-only workflow:

1. Authenticate with `POST /auth/microsoft/service-principal/session`.
2. Get tenant workspace IDs from `/scanner/workspaces/modified`. Optional
   `modified_since` must be UTC and between 30 minutes and 30 days old.
3. Submit 1-100 workspace UUIDs to `/scanner/workspaces/scan`.
4. Poll `/scanner/scans/{scan_id}/status` until `status` is `Succeeded`.
5. Read `/scanner/scans/{scan_id}/result` within 24 hours.

Scan request example:

```json
{
  "workspaces": ["<workspace-uuid>"],
  "lineage": true,
  "datasource_details": true,
  "dataset_schema": true,
  "dataset_expressions": true,
  "get_artifact_users": false
}
```

The result response contains `scan_id`, sorted top-level `sections`, an
inventory `summary`, and `payload`. `payload` is the complete Microsoft
response and is intentionally not narrowed by backend schemas. Depending on
the requested flags, tenant settings, item type, and available metadata, it can
contain:

- Workspaces, state/capacity/storage properties, tags, and users.
- Reports, dashboards and tiles, semantic models/datasets, dataflows, and
  datamarts.
- Report/model ownership, timestamps, endorsement, sensitivity labels, users,
  and tags.
- Semantic tables, columns, measures and DAX, relationships, roles and row
  filters, shared expressions, table source/M expressions, and upstream
  dataflow references.
- Datasource usages plus top-level `datasourceInstances` connection details and
  `misconfiguredDatasourceInstances`.

`get_artifact_users` defaults to false because it can return user identifiers.
The summary counts workspaces, artifacts, semantic objects, expressions, and
datasource instances while the raw payload remains authoritative.

For service-principal scanning, enable the app's security group in the Fabric
admin setting for read-only admin APIs. Microsoft requires that this app have
no admin-consent-required Power BI permissions configured. Enable the separate
detailed-metadata and DAX/mashup-expression tenant settings when schema and
expressions are needed. Delegated administrator tokens instead require
`Tenant.Read.All` or `Tenant.ReadWrite.All`; the current device-code flow does
not request either tenant-wide scope. See [metadata scanning
setup](https://learn.microsoft.com/en-us/fabric/admin/metadata-scanning-setup),
[metadata scanning overview](https://learn.microsoft.com/en-us/fabric/governance/metadata-scanning-overview),
and the official [scan submission API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-post-workspace-info).

Microsoft limits modified-workspace discovery to 30 calls/hour, scan
submissions to 500 calls/hour with at most 16 simultaneous requests, and scan
result reads to 500 calls/hour. The backend maps provider `401`, `403`, `429`,
and upstream failures through the existing structured error contract; it does
not bypass or locally emulate these tenant controls.

### Explorer Data

```text
POST /api/v1/explorer/snapshot
POST /api/v1/explorer/source-database-lineage
POST /api/v1/explorer/report-source-tables
POST /api/v1/explorer/semantic-model-objects
POST /api/v1/explorer/measure-source-lineage
POST /api/v1/explorer/report-layout
POST /api/v1/explorer/visual-source-lookup
```

These routes are the typed replacement for the five legacy Streamlit tables,
plus `/report-source-tables`, a newer addition. Use `/snapshot` for the
initial explorer load; it retrieves each distinct workspace, report, report
definition, and semantic model definition once, runs independent provider
calls concurrently with a bounded limit, and derives all six datasets from the
shared evidence. Use a focused endpoint for lazy-loaded tabs when only one
table is needed. DAX and Power Query analysis run outside the event loop, and
two reports sharing one semantic model share one definition request.

Request example:

```json
{
  "reports": [
    {
      "workspace_id": "<workspace-uuid>",
      "report_id": "<report-uuid>",
      "semantic_model_id": "<optional-model-uuid>",
      "semantic_model_workspace_id": "<optional-model-workspace-uuid>",
      "app_name": "<optional-display-context>"
    }
  ],
  "include_gateway_sources": false,
  "include_cross_model_matching": false,
  "report_definition_format": "PBIR",
  "semantic_model_definition_format": "TMDL"
}
```

`semantic_model_id` is inferred from the Power BI report or normalized PBIR
connection when omitted. Keep `semantic_model_workspace_id` separate for
cross-workspace bindings. Gateway discovery is opt-in because it adds calls and
requires gateway-admin access. `app_name` is optional caller-supplied display
context; the service does not guess app membership from workspace report data.
The source and measure datasets return Snowflake-ready
`source_fully_qualified_name` values without the separate server/account host.
After Snowflake session authentication, pass a selected table or table/column
to `POST /api/v1/lineage/snowflake/trace` for the legacy table-lineage or
column-lineage action; explorer retrieval does not trigger Snowflake queries
automatically.

Two classes of Power-BI-generated noise are filtered out. `GET /workspaces`
omits workspaces Power BI provisions itself (`type: "AdminInsights"` — the
"Admin monitoring" workspace), whose semantic models are not readable through
the Fabric definition APIs and fail upstream on every lineage call. Every
explorer dataset also drops Auto Date/Time tables (`LocalDateTable_<guid>`
and `DateTableTemplate_<guid>`), which Power BI Desktop adds per date column
and which can easily outnumber the real tables. The filter is applied once to
the parsed model, so the physical-source and DAX analysis derived from it stay
consistent; the raw `/semantic-models/{id}/definition/parsed` route still
reports the model exactly as Fabric returns it.

A table bound with DirectQuery to another semantic model has no inline Power
Query — TMDL records it as an `entity` partition (`entityName` +
`expressionSource`) pointing at a model-level shared `expression`. Those are
resolved: the shared expression's `AnalysisServices.Database(<xmla endpoint>,
<model>)` call becomes a source with `provider: "analysis_services"`, the
workspace endpoint as its server, the upstream model as its database, and the
partition's `entityName` as the object — so a cross-workspace composite table
reports where it actually reads from instead of "unknown".

`/source-database-lineage` and `/report-source-tables` always emit one row per
semantic table, even when no physical source could be resolved (a calculated
table is still skipped, matching Power BI's own semantics). An unresolved
table gets `source_object_type: "unknown"` and
`source_fully_qualified_name: "Unknown Source (e.g., Local Excel File, Web
Data, Dataflow, or Calculated Table)"` rather than being silently dropped —
this mirrors the legacy Streamlit tool's behavior, where a table backed by an
Excel import, a Web.Contents call the parser doesn't recognize, or a dataflow
still shows up in the inventory instead of vanishing from it.

`include_cross_model_matching` (default `false`) enables upstream (composite
/ DirectQuery-for-dataset) resolution for `/visual-source-lookup`: when a
visual field matches a local table that is itself sourced from another Power
BI dataset, the row is redirected to the true upstream table/column instead
of the local passthrough one. This is opt-in because it costs a Power BI
Admin API tenant-lineage scan (`admin/workspaces/getInfo?lineage=true`,
submit + poll + fetch) per request, which needs admin-scanner permissions and
adds real latency; leaving it off keeps today's same-model-only matching.
When enabled, each `VisualSourceLookupRow` also carries `primary_dataset_id`
(the report's own bound dataset), and, for matched rows,
`matched_dataset_id`/`matched_semantic_model`/`matched_model_role`
(`"primary"` or `"upstream"`) — `matched_model_role` is always `"primary"`
with matching disabled. The redirect itself is a column-level join: a local
column's `sourceLineageTag` (TMDL) / `SourceLineageTag` (live XMLA) is looked
up against every other model's column `lineageTag`, first hit wins, and
`match_reason` gets an `"; upstream object matched by SourceLineageTag"`
suffix (or the bare sentence when there was no prior reason, which is the
common case — a matched field's `match_reason` is otherwise empty). This
follows the same DMV-level signal the legacy tool reads over live XMLA, but
sourced from TMDL so it works without a Windows/MSOLAP host; discovery is
scoped to the primary dataset's own workspace(s) plus whatever upstream
workspace(s) the scan reports — it does not chase upstream-of-upstream
chains beyond that first hop.

`/report-source-tables` returns the distinct physical database tables/views a
report ultimately reads from — one row per (workspace, report, physical
table), not one row per semantic table/partition/query mapping. Use it when
only a flat table inventory is needed (e.g. a "which tables does this report
touch" listing); use `/source-database-lineage` when the semantic
table/partition/query breakdown is needed too. Each row is: `workspace_name`,
`report_name`, `report_id`, `semantic_model_id` ("Dataset ID"),
`source_account` (the connector's account/server host — the Snowflake
account identifier for `Snowflake.Databases`, or the storage account name for
Azure Blob sources), `source_database`, `source_schema`, `table_name`, and
`source_object_type` (`table`, `view`, or one of the non-table-shaped values
`query`/`file`/`url`/`endpoint`/`unknown` also used by
`/source-database-lineage`). The `table`/`view` distinction is only resolved
when Power Query's `Kind="Table"`/`Kind="View"` navigation marker is present
in the M expression; sources resolved from a native SQL `FROM`/`JOIN` or a
`Schema=`/`Item=` navigation record default to `table` since the object kind
cannot be determined from static text. Not every source is a database object:
for a file-, folder- or URL-backed table there is no account/database/schema
to report, so `table_name` falls back to the file path or URL and
`source_object_type` is `file`/`url` — the row still identifies what the table
reads from instead of being four nulls.

Legacy screen mapping:

| Legacy table | Endpoint | Main response rows |
|---|---|---|
| Source DB Lineage | `/explorer/source-database-lineage` | Report/model IDs, semantic table and partition, provider endpoint/object, fully qualified source name, gateway IDs |
| — (new) | `/explorer/report-source-tables` | Workspace/report/dataset IDs, source account, database, schema, table name, and table/view object type — deduplicated to one row per physical table |
| Semantic Model Objects | `/explorer/semantic-model-objects` | Tables, columns, calculated columns/tables, measures, hierarchies, DAX, types, visibility, and source paths |
| Measure Source Lineage | `/explorer/measure-source-lineage` | Measure/calculated-object DAX, terminal semantic sources, dependency depth, physical source, and fully qualified name |
| Report Layout | `/explorer/report-layout` | Pages, visuals, roles, fields, query references, definition counts, and visual coordinates |
| Visual Source Lookup | `/explorer/visual-source-lookup` | Visual fields joined to semantic objects with status, confidence, reason, source path, coordinates, and (opt-in) cross-model dataset/role |

### Unified Lineage

```text
POST /api/v1/lineage/dax/analyze
POST /api/v1/lineage/physical-sources/analyze
POST /api/v1/lineage/snowflake/normalize
POST /api/v1/lineage/snowflake/discover
POST /api/v1/lineage/snowflake/trace
POST /api/v1/lineage/graphs
POST /api/v1/lineage/live-graphs
GET  /api/v1/lineage/graphs/{graph_id}
GET  /api/v1/lineage/graphs/{graph_id}/versions
GET  /api/v1/lineage/graphs/{graph_id}/impact/{node_id}
GET  /api/v1/lineage/graphs/{graph_id}/search
GET  /api/v1/lineage/graphs/{graph_id}/navigate/{node_id}
GET  /api/v1/lineage/graphs/{graph_id}/changes
GET  /api/v1/lineage/graphs/{graph_id}/validate
GET  /api/v1/lineage/estate/discover
POST /api/v1/lineage/scan-jobs
POST /api/v1/lineage/scan-jobs/live
GET  /api/v1/lineage/scan-jobs/{job_id}
```

Graph edges use upstream-to-downstream direction. Containment and semantic-model
relationship edges are marked as non-lineage so downstream impact traversals do
not confuse ownership structure with data flow. Re-saving unchanged graph
content does not create a new version; changed content receives the next SQLite
snapshot version and can be compared through the `changes` endpoint.

When `LINEAGE_ADMIN_API_KEY` is configured, every `/lineage` and `/scanner`
endpoint plus Snowflake and Microsoft service-principal session routes require
the `X-Lineage-Admin-Key` header. Power BI estate discovery additionally uses
the existing authenticated Microsoft session. Gateway `connectionDetails`
parsing is restricted to an allowlist of endpoint metadata and never includes
credential values.

`live-graphs` retrieves parsed Fabric TMDL, optionally retrieves and matches a
report definition, and optionally enriches Power Query sources with accessible
gateway datasource metadata. `scan-jobs/live` runs the same pipeline in the
bounded background-job manager. Neither endpoint persists provider tokens.
The older `/snowflake/discover` route accepts its short-lived credential only
through the `Authorization: Bearer` header and reads
`ACCOUNT_USAGE.OBJECT_DEPENDENCIES` through the Snowflake SQL API. The new
`/snowflake/trace` route uses the authenticated connector session cookie and
calls `SNOWFLAKE.CORE.GET_LINEAGE` for table/column lineage.

### Snowflake Authentication And Deep Lineage

Snowflake authentication and every lineage route are protected by
`X-Lineage-Admin-Key` when `LINEAGE_ADMIN_API_KEY` is configured. Send
credentials only over HTTPS. Request bodies, passwords, tokens, private keys,
and passphrases are not copied into session metadata, logs, persistence, or the
API response. Authentication material exists only in request memory and any
private in-memory state retained by the live Snowflake connector connection.

Common optional connection fields for every method are `warehouse`, `database`,
`schema_name`, and `role`. `account_identifier` is the connector account value,
such as `organization-account`; do not send a full Snowflake URL.

Password authentication:

```json
{
  "authentication_method": "password",
  "account_identifier": "organization-account",
  "user": "LINEAGE_USER",
  "password": "<password>",
  "authenticator": "snowflake",
  "warehouse": "LINEAGE_WH",
  "role": "LINEAGE_READER"
}
```

For username/password MFA, set `authenticator` to
`username_password_mfa`. Supply `passcode` separately or set
`passcode_in_password=true` when the passcode is appended to the password.

RSA key-pair authentication accepts PKCS#8 or PKCS#1 PEM text. Escaped `\n`
newlines are normalized, encrypted keys use `private_key_passphrase`, and the
key is converted to unencrypted PKCS#8 DER only in process memory for the
Snowflake connector:

```json
{
  "authentication_method": "key_pair",
  "account_identifier": "organization-account",
  "user": "LINEAGE_USER",
  "private_key_pem": "-----BEGIN ENCRYPTED PRIVATE KEY-----\n...\n-----END ENCRYPTED PRIVATE KEY-----",
  "private_key_passphrase": "<passphrase>",
  "warehouse": "LINEAGE_WH",
  "role": "LINEAGE_READER"
}
```

External-browser SSO is intended only for an interactive local backend and must
be explicitly enabled with `SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=true`:

```json
{
  "authentication_method": "external_browser",
  "account_identifier": "organization-account",
  "user": "LINEAGE_USER",
  "warehouse": "LINEAGE_WH",
  "role": "LINEAGE_READER"
}
```

OAuth is the external/unattended option for a hosted API:

```json
{
  "authentication_method": "oauth",
  "account_identifier": "organization-account",
  "user": "LINEAGE_USER",
  "token": "<snowflake-oauth-access-token>",
  "warehouse": "LINEAGE_WH",
  "role": "LINEAGE_READER"
}
```

On successful connection, the backend runs a current-account/user/role/context
query, stores only the live connection plus sanitized identity metadata, and
sets the HttpOnly cookie. Re-authentication closes the previous cookie's
connection. Logout, expiry, or graceful application shutdown also closes the
connection; logout defers connection closure until an active trace finishes.

Trace one table:

```json
{
  "object_name": "ANALYTICS.PUBLIC.SALES",
  "direction": "UPSTREAM",
  "max_depth": 50,
  "max_concurrency": 8
}
```

Trace one column by adding `column_name`; `object_domain` is inferred as
`COLUMN` and must not conflict if explicitly supplied:

```json
{
  "object_name": "ANALYTICS.PUBLIC.SALES",
  "column_name": "NET_AMOUNT",
  "direction": "UPSTREAM",
  "max_depth": 50,
  "max_concurrency": 8,
  "max_nodes": 5000,
  "max_edges": 10000,
  "max_queries": 2000,
  "include_process": true
}
```

The service calls `GET_LINEAGE` with at most five levels. Every object returned
at the five-level boundary becomes a new frontier root; independent roots in a
frontier are queried concurrently up to `max_concurrency`. Stable IDs, visited
roots, and edge deduplication prevent repeated work and cycles. `max_depth`,
`max_nodes`, `max_edges`, and `max_queries` bound each request. A failed root
query fails the request; a failed deeper branch returns the partial snapshot
with `truncated=true` and a `SNOWFLAKE_LINEAGE_BRANCH_FAILED` warning. Returned
`PROCESS` evidence is retained when `include_process=true`.

This ports the supplied procedure's recursive five-level traversal into the
service and supports both table and column roots. It does not create or call
`TRACE_COLUMN_LINEAGE` in Snowflake. The procedure's heuristic `GET_DDL` and
query-history fallback for `COLUMN_TRANSFORMATION`/`MODIFICATION_SQL` is not
executed: that path requires broader history privileges, can disclose SQL text,
and is less authoritative than `GET_LINEAGE`. If Snowflake returns no lineage,
the API returns the root with no inferred edges instead of guessing.

`GET_LINEAGE` is a Snowflake Enterprise Edition feature and each authenticated
role still needs access to the relevant objects; inaccessible objects produce a
Snowflake error.
The backend uses the Python connector directly because Snowpark sessions use
the same connector authentication mechanisms and this integration executes SQL
only; `snowflake-snowpark-python` is not required.

References:

- [Snowpark session creation](https://docs.snowflake.com/en/developer-guide/snowpark/python/creating-session)
- [Snowpark Python setup](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup)
- [Snowflake Connector authentication](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect)
- [`SNOWFLAKE.CORE.GET_LINEAGE`](https://docs.snowflake.com/en/sql-reference/functions/get_lineage-snowflake-core)

### Fabric Definitions

```text
POST /api/v1/workspaces/{workspace_id}/reports/{report_id}/definition
POST /api/v1/workspaces/{workspace_id}/reports/{report_id}/definition/normalized
POST /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/definition
POST /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/definition/parsed
GET /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/metadata
POST /api/v1/workspaces/{workspace_id}/reports/{report_id}/semantic-lineage
```

Report definition endpoints accept `format=PBIR` or `format=PBIR-Legacy`.
The default is `PBIR`.

Semantic model definition endpoints accept `format=TMDL` or `format=TMSL`.
The default is `TMDL`.

The semantic-lineage endpoint returns visual field matches, source-path
evidence, match confidence, candidate suggestions for unmatched fields, and a
diagnostics summary.

Semantic-lineage query parameters:

- `semantic_model_id` is required.
- `semantic_model_workspace_id` is optional and defaults to the report
  workspace.
- `reportFormat` accepts `PBIR` or `PBIR-Legacy` and defaults to `PBIR`.
- `semanticModelFormat` accepts `TMDL` or `TMSL` and defaults to `TMDL`.

Do not pass `reportFormat=TMDL`; `TMDL` is only valid for semantic model
definitions.

### XMLA Metadata

```text
GET  /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/xmla/metadata
POST /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/column-lineage
```

Optional query parameters (both routes):

- `workspaceName`
- `databaseName`

`GET .../xmla/metadata` uses the Power BI token dependency and the XMLA
ADODB/MSOLAP adapter to query `$SYSTEM.TMSCHEMA_*` rowsets for tables,
columns, measures, partitions, hierarchies, levels, and relationships, plus
`$SYSTEM.DISCOVER_CALC_DEPENDENCY` for the engine's own computed
measure/calculated-column/calculated-table dependency graph
(`calc_dependencies`). Workspace names are URI encoded in the
`powerbi://api.powerbi.com/v1.0/{tenant}/{workspace}` endpoint. If
`workspaceName` or `databaseName` is not supplied, the service resolves the
workspace name and semantic model name from Power BI REST before opening the
XMLA connection because XMLA URLs use names, not REST object IDs.

If `pywin32`, Windows COM, or the Microsoft Analysis Services OLE DB Provider
is not available on the host, the client returns
`PROVIDER_INTEGRATION_NOT_CONFIGURED` with a setup message.

`POST .../column-lineage` returns every measure/calculated column/calculated
table mapped to the physical database columns it ultimately reads from. It is
XMLA-primary, not TMDL-based: the dependency graph comes from
`DISCOVER_CALC_DEPENDENCY` (Microsoft's own engine-computed graph, not a
regex guess over DAX text — so there is no `DAX_REFERENCE_UNRESOLVED`-style
failure mode), and the physical source comes from
`TMSCHEMA_PARTITIONS.QueryDefinition` (the partition's real M/SQL text, as
reported live by the engine). `app/services/xmla_column_lineage_adapter.py`
converts that XMLA metadata into the same `ParsedSemanticModelResponse`/DAX
dependency shapes the rest of the lineage code already understands, so
`PhysicalSourceDiscoveryService` (which extracts `database.schema.table`-
qualified `FROM`/`JOIN` targets and Power Query navigation, including the
`Kind="Database"/"Schema"/"Table"/"View"` chain) and the native-SQL
`SELECT`-list parser (`app/services/sql_column_parser.py`) run unchanged
against engine-reported text instead of parsed TMDL text.

The `SELECT`-list parser resolves both explicit (`expr AS alias`) and
implicit (`expr alias`, no `AS`) aliases, and — critically for a computed
projection — returns **every** physical column a single semantic column's
expression reads from, not just one: `FIRST_NAME || ' ' || LAST_NAME AS
FULL_NAME` resolves to both `FIRST_NAME` and `LAST_NAME`, each surfaced as its
own entry in that row's `physical_columns`. Each entry's `resolution_method`
is `native_query_select` when the physical column name(s) came from the
partition's native SQL projection, or `same_name_assumed` when no native
query was found (or it didn't reference that column) and the semantic
model's `SourceColumn` name is assumed to match the physical column name
unchanged. The SQL parser is intentionally not a full SQL engine: a computed
expression with no identifiable column reference (e.g. a hardcoded string
literal) falls back to assuming a physical column named after its alias, and
it does not track subqueries nested in the column list or later
`Table.RenameColumns` M steps. Warnings surfaced from physical source
discovery (`POWER_QUERY_SOURCE_NOT_DETECTED`, `GATEWAY_CONNECTION_DETAILS_INVALID`)
are included unchanged; `calc_dependencies` rows the engine reports for
non-calculation object types (relationships, RLS, etc.) are ignored rather
than surfaced as noise. Gateway-datasource enrichment is not included in
this endpoint. This route needs a Windows host with the same XMLA/MSOLAP
setup as `GET .../xmla/metadata` — it is not available on non-Windows
deployments or when XMLA is disabled on the capacity.

### Merged Semantic Model Metadata

```text
GET /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/metadata
```

This endpoint requires both Fabric authentication for the TMDL definition and
Power BI authentication for XMLA. It accepts `workspaceName` and `databaseName`
for XMLA name resolution; `format` is intentionally restricted to `TMDL`.

The response preserves both source payloads instead of overwriting one with the
other. Its `reconciliation.matches` list matches tables, columns, measures,
hierarchies, hierarchy levels, partitions, and relationships by normalized
identity and reports `matched`, `definition_only`, or `xmla_only`. TMDL source
paths remain the definition evidence; XMLA provides runtime metadata.

### Power AI

```text
GET  /api/v1/ai/status
POST /api/v1/ai/chat
POST /api/v1/ai/chat/stream
```

**Core rule: no verified evidence, no factual answer.** Power AI never
derives lineage, DAX, sources, dependencies, or impact itself — every fact
in a response is traced to one deterministic backend call (semantic model
parsing, the lineage graph, impact analysis, report definitions). If the
backend cannot prove an answer, the response says so
(`status: "insufficient_evidence"`) and the language model is **never
invoked** to guess. All three routes require the same authenticated Power BI
session as every other route (`get_powerbi_access_token`, plus an optional
Fabric session for anything needing report/semantic-model definitions) and
`X-Lineage-Admin-Key` when `LINEAGE_ADMIN_API_KEY` is configured.

`GET /ai/status` is unchanged: `{enabled, provider, model,
streaming_enabled, configured}`, never the credential itself.

`POST /ai/chat` accepts `message`, `conversation_id`, `audience`
(`general`/`business`/`developer`), and `context` (`workspace_id`,
`report_id`, `semantic_model_id`, `object_type`, `object_id`,
`object_name`). Client-supplied IDs are never trusted directly —
`AIContextResolver` re-validates workspace/report/semantic-model access
through the real Power BI/Fabric services before anything is used as
evidence, and a well-formed but inaccessible (e.g. cross-tenant) GUID is
rejected identically to a nonexistent one. The response is:

```json
{
  "conversation_id": "...",
  "status": "answered",
  "answer": "...",
  "claims": [{"text": "...", "evidence_ids": ["E1", "E2"]}],
  "evidence": [{"evidence_id": "E1", "object_type": "measure", "fact_type": "definition", "source_type": "tmdl", "value": "...", "verification_status": "verified", "...": "..."}],
  "agent": "measure_agent",
  "suggested_questions": ["..."],
  "usage": {"provider": "...", "model": "...", "tokens": 0}
}
```

`status` is one of `answered`, `insufficient_evidence`, `ambiguous`,
`conflicting_evidence`, or `out_of_scope`. Only `answered` ever has a
non-null `usage` — every other status means the model was never called.
`claims` is only populated when the model successfully produced a
citation-backed answer; `evidence` is always populated when evidence
exists, independent of whether the model was used, so the frontend can show
its own evidence view even on a fallback answer.

Pipeline: `AIContextResolver` (validate + fetch) → `Supervisor`
(deterministic keyword/object-type routing into
`measure_agent`/`report_agent`/`impact_agent` — an LLM router is not needed
yet since every intent this phase implements routes deterministically) →
agent (calls a small set of registered, read-only tools —
`app/ai/tools/registry.py` — that wrap `SemanticModelDefinitionService`,
`LineageGraphService`, `ImpactAnalysisService`,
`LineageNavigationService`/`LineageSearchService`,
`ReportDefinitionService`/`ReportSemanticLineageService`,
`PhysicalSourceDiscoveryService`; no lineage algorithm is reimplemented) →
`EvidenceBundle`. If `can_answer` is false, the response is rendered
directly from the bundle and the model is skipped entirely. Otherwise the
`GroundedComposer` asks the model for a structured `{summary, claims}` JSON
object citing evidence IDs (via `ModelGateway.generate()` — no
provider-specific structured-output feature, so this works identically for
every provider), and `GroundedResponseValidator` mechanically rejects the
whole response if any claim has no citation or cites an evidence ID that
does not exist in the bundle — it never strips a bad citation and keeps the
sentence. On rejection (or any composer/provider failure),
`DeterministicAnswerRenderer` renders the answer directly from the evidence
instead, so a factual answer still reaches the caller even when model
composition breaks. If a semantic model's TMDL definition and live XMLA
metadata disagree on a measure's DAX, the response is
`conflicting_evidence` with both values — never a silent pick.

`POST /ai/chat/stream` (SSE, `text/event-stream`) runs the exact same
pipeline to a fully validated response **before** sending anything —
grounding always happens before streaming, never token-by-token
speculative output. Events, in order: `metadata` (conversation id, status,
agent) → `evidence` → one or more `delta` (the already-validated answer
text, chunked) → `complete` (claims/usage/suggested_questions — the answer
text itself is not repeated) → `error` on any failure instead of `complete`.

Provider switching (OpenAI/Anthropic/Gemini/Azure OpenAI/a local `fake`
provider) is an `AI_PROVIDER`/`AI_MODEL`/credential configuration change
only; no endpoint, schema, agent, or tool differs by provider. Every
provider except `fake` is reached through one adapter
(`LiteLLMModelGateway`); no vendor SDK is imported outside that one file,
and LiteLLM itself is imported lazily (only when a real provider is
actually used) so the application's startup, `/ai/status`, and the default
`fake` provider never depend on it being importable.

Known limitations in this phase: conversation history is not yet persisted,
so cross-turn pronoun resolution ("what depends on *that* measure") is not
implemented — each request is resolved independently; intent routing is
deterministic only (no LLM fallback router, since nothing implemented yet
needs one); Snowflake-backed evidence tools are not included; a standing
evaluation-fixture suite is not included (covered instead by the unit/API
tests under `tests/unit/test_ai_*.py`).

## Folder Structure

```text
app/
  ai/
    models/
    context/
    tools/
    orchestration/
    agents/
    composition/
    providers/
    services/
  api/
  clients/
  core/
  domain/
  repositories/
  schemas/
  services/
  utils/
tests/
  api/
  unit/
INSTALLATION.md
constraints.txt
requirements.txt
requirements-dev.txt
```

## File And Folder Purpose

### Dependency files

- `requirements.txt` lists direct production dependencies.
- `requirements-dev.txt` adds test and lint tooling.
- `constraints.txt` pins the complete resolved Python 3.13 dependency set used
  by local environments, CI, and the production image.
- `pyproject.toml` contains pytest and Ruff configuration only.

### `app/main.py`

Application factory and FastAPI entrypoint. It configures:

- App metadata.
- Explicit CORS and trusted-host middleware.
- Optional HTTPS redirects.
- Security headers and request-body limits.
- HTTP metrics and structured request logging.
- Request logging middleware.
- Request ID middleware.
- Exception handlers.
- API router mounting.
- Graceful closure of live Snowflake connector sessions on shutdown.

### `app/api`

FastAPI routing layer.

- `app/api/router.py`
  - Combines all v1 routers under health, Microsoft/Snowflake auth, workspaces,
    reports, gateways, scanner, explorer, and lineage.
- `app/api/v1/health.py`
  - Health, liveness, and readiness endpoints.
- `app/api/v1/auth.py`
  - Microsoft device auth plus protected client-secret service-principal
    session/status/logout endpoints.
  - Browser-redirect Microsoft SSO login (Authorization Code + PKCE) and
    callback endpoints, sharing the same session cookie and status/logout
    routes as device auth.
  - Delegated scope diagnostics and application-token status for Power BI and
    Fabric.
- `app/api/v1/scanner.py`
  - Protected modified-workspace, scan submission, status, and full-result
    endpoints in a separate Swagger section.
- `app/api/v1/snowflake_auth.py`
  - Password/MFA, RSA key-pair, external-browser, and OAuth Snowflake session
    authentication plus cookie status/logout.
- `app/api/v1/workspaces.py`
  - Workspace, report, page, semantic model, report definition, normalized
    report definition, semantic model definition, semantic metadata,
    semantic lineage, and XMLA metadata endpoints.
- `app/api/v1/reports.py`
  - My workspace Power BI report-detail endpoint.
- `app/api/v1/gateways.py`
  - Gateway discovery plus gateway datasource list/detail endpoints.
- `app/api/v1/explorer.py`
  - Combined and focused frontend-ready explorer data endpoints.
- `app/api/v1/lineage.py`
  - Unified DAX, physical-source, Snowflake normalization, supplied-evidence
    and live graph, deep Snowflake table/column tracing, impact, search,
    navigation, versioning, validation, estate, and scan-job endpoints.
- `app/api/v1/ai.py`
  - Power AI status and chat endpoints. Router-level lineage-admin-key gate
    plus per-route authenticated Power BI session, matching every other
    subsystem's auth conventions.
- `app/api/dependencies/credentials.py`
  - FastAPI dependencies for extracting Power BI/Fabric credentials and the
    Snowflake connector-session ID from their separate HttpOnly cookies.
- `app/api/dependencies/lineage.py`
  - Singleton lineage repository, cache/store, and scan-manager dependencies.
- `app/api/dependencies/security.py`
  - Optional constant-time lineage administration API-key enforcement.

### `app/ai`

Power AI. Never a second source of truth for lineage: only `app/core` and
`app/services`/`app/schemas` (read-only, via the tool layer) are dependencies
— no lineage/DAX/impact algorithm is reimplemented here. No vendor SDK is
imported outside `providers/litellm_gateway.py`.

- `app/ai/models/enums.py`
  - `AudienceType`, `MessageRole`, `AIAnswerStatus`
    (`answered`/`insufficient_evidence`/`ambiguous`/`conflicting_evidence`/`out_of_scope`),
    `VerificationStatus`, `AIIntent`.
- `app/ai/models/messages.py`, `requests.py`
  - Provider-neutral `ModelMessage`/`ModelRequest` plus the public
    `AIChatRequest`/`AIChatContext` API contract.
- `app/ai/models/responses.py`
  - Provider-neutral `ModelResponse`/`ModelChunk`/`TokenUsage`, plus the
    public `AIStatusResponse`/`AIUsage`/`AIChatResponse`
    (`status`/`claims`/`evidence`/`agent`/`suggested_questions`/`usage`).
- `app/ai/models/context.py`
  - `ResolvedObject`/`ResolvedAIContext` — the access-checked, evidence-
    carrying context every tool/agent reads from instead of raw client input.
- `app/ai/models/evidence.py`
  - `EvidenceItem` (one fact traced to one deterministic call),
    `EvidenceConflict`, `EvidenceBundle`, `GroundedClaim`.
- `app/ai/context/resolver.py`
  - `AIContextResolver`: validates workspace/report/semantic-model access
    against the caller's real Power BI/Fabric session (never trusts a
    client-supplied ID directly; a forbidden and a nonexistent ID fail
    identically) and resolves a named object via `LineageSearchService`
    against a graph built from already-fetched evidence. Also exports
    `build_lineage_graph`, the single call site every tool shares.
- `app/ai/tools/`
  - `base.py` (`Tool` dataclass — explicit name/description/required-context/
    handler, no dynamic dispatch), `registry.py` (`TOOL_REGISTRY`),
    `measure_tools.py`, `report_tools.py`, `lineage_tools.py`,
    `impact_tools.py` — thin adapters over
    `SemanticModelDefinitionService`/`LineageGraphService`/
    `ImpactAnalysisService`/`LineageNavigationService`/
    `ReportSemanticLineageService`/`PhysicalSourceDiscoveryService`,
    returning `EvidenceItem`s only.
- `app/ai/orchestration/intent.py`, `supervisor.py`
  - Deterministic keyword/object-type intent classification and the
    `Supervisor` that picks one agent from it — no model call.
- `app/ai/agents/measure_agent.py`, `report_agent.py`, `impact_agent.py`
  - Each calls a small, fixed set of tools and assembles one
    `EvidenceBundle`, including the measure agent's TMDL-vs-XMLA conflict
    check (opt-in — only runs when XMLA metadata is explicitly supplied).
- `app/ai/composition/`
  - `persona.py` (presentation-only per-audience hints), `grounded_composer.py`
    (prompt-based structured JSON via `ModelGateway.generate()`, Pydantic-
    validated — no provider-specific structured output), `grounding_validator.py`
    (`GroundedResponseValidator` — every claim must cite an evidence id that
    exists in the bundle, or the whole response is rejected),
    `deterministic_renderer.py` (`DeterministicAnswerRenderer` — renders
    straight from the evidence bundle, used for every non-`answered` status
    and as the fallback when composition/validation fails),
    `suggested_questions.py` (deterministic, no model call).
- `app/ai/providers/base.py`
  - The `ModelGateway` `Protocol` (`generate`/`stream`) — unchanged since
    the provider-independent foundation phase.
- `app/ai/providers/fake_gateway.py`
  - Deterministic, network-free `ModelGateway` selected by `AI_PROVIDER=fake`
    (the default); keeps an unconfigured deployment fully functional and
    testable.
- `app/ai/providers/litellm_gateway.py`
  - `ModelGateway` backed by LiteLLM's unified `acompletion()`/streaming API;
    maps `litellm.exceptions.*` to normalized `AI*` application exceptions.
    Imports `litellm` lazily inside its methods rather than at module load,
    so application startup and every other AI provider never depend on it.
- `app/ai/providers/factory.py`
  - Builds the configured gateway from `Settings` and reports (without ever
    returning it) whether a credential is present for the selected provider.
- `app/ai/services/ai_service.py`
  - Orchestrates the whole pipeline: resolver → supervisor/agent → no-
    evidence gate (skips the model entirely when evidence is insufficient)
    → grounded composer → validator → deterministic fallback. Emits
    structured logs and grounding metrics at each stage.
- `app/ai/services/streaming.py`
  - SSE event generator for `/ai/chat/stream`; runs the same pipeline to a
    fully validated response before emitting anything.

### `app/clients`

Provider clients. These files should know provider URL/protocol details but
should not contain business normalization logic.

- `provider_http_client.py`
  - Shared HTTP behavior, provider error mapping, and upstream error-detail
    extraction.
- `powerbi_client.py`
  - Power BI REST API client for workspace resources, My workspace report
    detail, gateways, gateway datasources, and Admin metadata scanning.
- `fabric_client.py`
  - Microsoft Fabric API client.
  - Handles report and semantic model definition endpoints and long-running
    operation result APIs.
  - Uses `PBIR` by default for report definitions and `TMDL` by default for
    semantic model definitions.
- `xmla_client.py`
  - XMLA endpoint and connection-string construction.
  - ADODB COM connection wrapper using the Microsoft Analysis Services OLE DB
    Provider (`MSOLAP`).
  - TMSCHEMA rowset queries and raw metadata mapping for tables, columns,
    measures, partitions, hierarchies, levels, and relationships.
  - Raises a configured integration error when Windows COM, `pywin32`, or
    `MSOLAP` is unavailable.
- `snowflake_client.py`
  - Optional Snowflake SQL API client for
    `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES`, including asynchronous
    statement polling and OAuth/key-pair token-type headers.
- `snowflake_session_client.py`
  - Creates and validates connector sessions for password/MFA, in-memory RSA
    key-pair, local external-browser, and OAuth authentication.
- `snowflake_lineage_query_client.py`
  - Executes parameter-bound `SNOWFLAKE.CORE.GET_LINEAGE` queries and maps
    table/column edges plus `PROCESS` evidence.

### `app/core`

Cross-cutting application infrastructure.

- `config.py`
  - Environment-backed settings.
  - Includes XMLA settings plus Snowflake session lifetime and guarded
    external-browser enablement.
- `auth_session.py`
  - Auth cookie name and max-age constants.
- `microsoft_auth.py`
  - Microsoft authority/resource/scope constants and scope diagnostic helpers.
- `exceptions.py`
  - Application exception classes.
- `error_handlers.py`
  - FastAPI exception handlers and consistent error response shape.
- `logging.py`
  - JSON logging and sensitive value redaction.
- `request_id.py`
  - Request ID middleware and `X-Request-ID` response propagation.
- `request_context.py`
  - Context variable for request IDs.
- `request_logging.py`
  - Structured request completion logs.
- `security.py`
  - Security response headers and request-body size enforcement.
- `metrics.py`
  - Low-cardinality HTTP counters, duration summaries, in-progress gauge, and
    Prometheus rendering.

### `app/repositories`

- `lineage_repository.py`
  - SQLite schema and access layer for immutable graph versions and persisted
    scan-job status. Graph content hashes exclude capture time so unchanged
    snapshots are deduplicated.

### `app/schemas`

Pydantic API contracts.

- `workspace.py`
  - Workspace list/detail responses.
- `report.py`
  - Report list/detail responses.
- `gateway.py`
  - Gateway list/detail and gateway datasource response contracts.
- `report_page.py`
  - Report page list/detail responses.
- `semantic_model.py`
  - Semantic model list responses.
- `report_definition.py`
  - Raw Fabric report definition response.
- `semantic_model_definition.py`
  - Raw Fabric semantic model definition response.
- `parsed_semantic_model.py`
  - Parsed TMDL semantic model response with tables, columns, measures,
    relationships, hierarchies, partitions, warnings, and source-path evidence.
- `dax_dependency.py`, `physical_source.py`
  - DAX dependency and Power Query/gateway physical-source contracts.
- `explorer.py`
  - Multi-report explorer request, five typed flat-row datasets, warnings,
    selected-report context, and combined snapshot contracts.
- `scanner.py`
  - Scanner request/status contracts, modified workspace IDs, result summary,
    and complete provider payload response.
- `snowflake_auth.py`, `snowflake_lineage.py`
  - Discriminated Snowflake authentication requests, sanitized session status,
    SQL API normalization, and bounded deep-lineage snapshot contracts.
- `lineage_graph.py`, `impact_analysis.py`, `estate.py`
  - Canonical graph, reverse impact, and estate discovery contracts.
- `lineage_persistence.py`, `lineage_change.py`, `lineage_search.py`
  - Snapshot/version, incremental diff, search, and navigation contracts.
- `lineage_validation.py`, `scan_job.py`, `operations.py`
  - Data-quality validation, asynchronous jobs, and readiness contracts.
- `normalized_report_definition.py`
  - API shape for normalized PBIR reports, pages, visuals, positions, semantic
    model references, and visual field references.
- `report_semantic_lineage.py`
  - API shape for report visual field to semantic model object lineage,
    diagnostics, match confidence, and candidate suggestions.
- `xmla_metadata.py`
  - API shape for XMLA semantic model metadata, including tables, columns,
    measures, partitions, hierarchies, relationships, counts, and warnings.
- `semantic_model_metadata.py`
  - Combined Fabric TMDL/XMLA metadata response and reconciliation evidence.
- `auth.py`
  - Microsoft device and client-secret requests/responses, delegated scope
    diagnostics, and application-token status.
- `error.py`
  - Structured API error response models.
- `exceptions.py`
  - Older duplicate exception schema/module. Active app code uses
    `app.core.exceptions`.

### `app/services`

Business logic layer. Routes call services; services call clients.

- `workspace_service.py`
  - Maps Power BI workspace payloads.
- `report_service.py`
  - Maps workspace-scoped and My workspace Power BI reports, plus pages.
- `gateway_service.py`
  - Maps gateway and gateway datasource list/detail metadata, validates provider
    identity, and preserves non-secret connection information.
  - Derives `sso_enabled` (Microsoft Entra ID SSO passthrough) for
    OAuth2-credentialed datasources; leaves it `null` when the provider flag is
    absent or the credential type is not OAuth2.
- `semantic_model_service.py`
  - Maps Power BI datasets/semantic models.
- `report_definition_service.py`
  - Retrieves Fabric report definitions and handles long-running operations.
  - Defaults report definition extraction to `PBIR`.
  - Preserves Fabric operation failure details when available.
- `semantic_model_definition_service.py`
  - Retrieves Fabric semantic model definitions and handles long-running
    operations.
  - Defaults semantic model definition extraction to `TMDL`.
  - Preserves Fabric operation failure details when available.
- `semantic_model_definition_parser.py`
  - Parses TMDL semantic model definition parts into API-ready semantic objects.
- `report_semantic_lineage_service.py`
  - Matches normalized report visual field references to parsed semantic model
    objects and produces diagnostics.
- `xmla_metadata_service.py`
  - Maps XMLA adapter output into the XMLA metadata response contract and
    validates adapter payload shape.
- `semantic_model_metadata_service.py`
  - Retrieves parsed TMDL and XMLA metadata concurrently, validates source
    identity, and reconciles source-preserving object evidence.
- `report_definition_decoder.py`
  - Decodes structural JSON definition parts from base64 payloads.
- `report_definition_normalizer.py`
  - Normalizes PBIR report definitions into pages, visuals, positions, titles,
    semantic model references, and warnings.
- `visual_field_reference_extractor.py`
  - Extracts visual-to-field references from PBIR visual semantic queries.
- `dax_dependency_service.py`
  - Resolves DAX references for measures and calculated columns/tables and uses
    strongly connected components for dependency-cycle detection.
- `physical_source_service.py`
  - Extracts supported Power Query/M connector calls, navigation targets,
    native SQL objects, and query-level mappings; safely reconciles gateway
    connection endpoints.
  - Carries each gateway datasource's `sso_enabled` flag onto its own
    gateway-derived source and onto any matched detected source.
- `explorer_service.py`
  - Deduplicates request-scoped provider retrieval by workspace/report/model,
    applies bounded concurrency, and assembles the five UI-ready datasets.
- `scanner_service.py`
  - Maps scanner workflow responses, validates provider identities/shapes,
    normalizes modified timestamps, summarizes inventory, and preserves the
    complete result payload.
- `lineage_graph_service.py`
  - Constructs canonical stable-ID nodes and upstream-to-downstream edges across
    source, query, semantic, DAX, Snowflake, and report evidence.
- `impact_analysis_service.py`, `lineage_search_service.py`
  - Downstream impact traversal plus graph search and neighborhood navigation.
- `estate_discovery_service.py`
  - Discovers workspaces, reports, semantic models, report/model bindings, and
    a canonical estate graph while retaining partial-workspace warnings.
- `snowflake_lineage_service.py`
  - Normalizes Snowflake object-dependency rows and deduplicates objects/edges.
- `snowflake_deep_lineage_service.py`
  - Expands five-level Snowflake table/column frontiers in bounded concurrent
    waves with cycle detection, stable IDs, limits, and partial-branch warnings.
- `lineage_store_service.py`, `ttl_cache.py`
  - Cached access to versioned SQLite graph snapshots.
- `lineage_change_service.py`, `lineage_validation_service.py`
  - Version-to-version graph diffs and structural/data-quality checks.
- `scan_job_service.py`
  - Bounded asynchronous supplied-evidence and live graph-build jobs with
    persisted status and interrupted-job recovery; provider tokens are retained
    only by the running task.
- `live_lineage_scan_service.py`
  - Retrieves parsed TMDL plus optional report/gateway evidence and assembles a
    validated canonical graph from live provider resources.
- `operations_service.py`
  - Database and production security configuration readiness checks.
- `services/auth/device_auth_store.py`
  - In-memory device auth session/token store.
- `services/auth/microsoft_device_auth_service.py`
  - MSAL device-code auth, token validation, Fabric silent auth attempt, and
    scope diagnostic population. Its Fabric silent-acquisition step is a
    `@staticmethod` reused directly by the SSO login service below.
- `services/auth/microsoft_sso_auth_service.py`
  - MSAL public-client Authorization Code + PKCE auth: builds the Microsoft
    authorize URL and code challenge, then exchanges the returned code for
    Power BI/Fabric tokens and creates a session identical in shape to a
    device-code session (`authentication_method="sso"`).
- `services/auth/sso_login_store.py`
  - Short-lived, single-use, in-memory store for a pending SSO login's PKCE
    verifier and redirect target, keyed by the OAuth `state` value.
- `services/auth/microsoft_service_principal_auth_service.py`
  - Uses MSAL confidential-client `/.default` token requests for Power BI and
    Fabric, stores only short-lived tokens, and reports partial Fabric auth.
- `services/auth/powerbi_auth_service.py`
  - Power BI token validation wrapper.
- `services/auth/fabric_auth_service.py`
  - Fabric token validation wrapper.
- `services/auth/snowflake_auth_service.py`
  - Optional legacy Snowflake SQL API orchestration.
- `services/auth/snowflake_session_auth_service.py`
  - Connector authentication orchestration and sanitized status/logout models.
- `services/auth/snowflake_session_store.py`
  - Thread-safe process-local live connection store with expiry, active-use
    checkout, deferred close, replacement cleanup, and shutdown cleanup.

### `tests`

Automated tests.

- `tests/conftest.py`
  - FastAPI test client fixture.
- `tests/api/test_auth.py`
  - Device auth plus browser SSO login/callback, state, redirect, cookie, and
    provider-status behavior.
- `tests/unit/test_microsoft_sso_auth_service.py`
  - PKCE authorization, one-time state, token exchange, Power BI validation,
    Fabric acquisition, and session creation.
- `tests/api/test_microsoft_service_principal_auth.py`
  - Client-secret route, HttpOnly cookie, status, and secret-redaction behavior.
- `tests/api/test_scanner_resources.py`
  - Scanner route registration, authentication dependency, requests, and
    response shapes.
- `tests/api/test_report_resources.py`
  - Workspace and My workspace report-route behavior with dependency overrides.
- `tests/api/test_gateway_resources.py`
  - Gateway route behavior with Power BI authentication overrides.
- `tests/api/test_lineage_resources.py`
  - Unified graph build/store/version/search/validation and analysis endpoints.
- `tests/api/test_snowflake_auth.py`
  - Snowflake auth cookie, status/logout, replacement, and trace-route behavior.
- `tests/unit/test_microsoft_auth.py`
  - Scope diagnostic helper tests.
- `tests/unit/test_report_service.py`
  - Workspace and My workspace report-service mapping/validation.
- `tests/unit/test_powerbi_client.py`
  - My workspace report, gateway, and gateway datasource URL construction.
- `tests/unit/test_scanner_client.py`, `tests/unit/test_scanner_service.py`
  - Official Admin API URLs/options, scan mapping, full payload preservation,
    and summary counts.
- `tests/unit/test_microsoft_service_principal_auth_service.py`
  - App-only Power BI/Fabric acquisition, partial auth, failure handling, and
    non-persistence of the submitted client secret.
- `tests/unit/test_gateway_service.py`
  - Gateway/datasource mapping, provider identity validation, and tri-state
    OAuth2 SSO passthrough detection.
- `tests/unit/test_semantic_model_service.py`
  - Semantic model service mapping/validation.
- `tests/unit/test_report_definition_service.py`
  - Fabric report definition immediate and long-running behavior.
- `tests/unit/test_semantic_model_definition_service.py`
  - Fabric semantic model definition behavior.
- `tests/unit/test_fabric_client.py`
  - Fabric report and semantic model definition URL/query construction.
- `tests/unit/test_provider_http_client.py`
  - Provider HTTP error mapping and upstream diagnostic detail extraction.
- `tests/unit/test_semantic_model_definition_parser.py`
  - Parsed TMDL semantic model behavior.
- `tests/unit/test_report_semantic_lineage_service.py`
  - Report visual field to semantic model object matching and diagnostics.
- `tests/unit/test_xmla_client.py`
  - XMLA endpoint encoding, connection-string construction, ADODB rowset
    mapping, adapter setup failures, and access-token redaction.
- `tests/unit/test_xmla_metadata_service.py`
  - XMLA metadata contract mapping and validation.
- `tests/unit/test_semantic_model_metadata_service.py`
  - Combined semantic metadata reconciliation and source identity validation.
- `tests/unit/test_report_definition_decoder.py`
  - Base64/JSON definition decoding.
- `tests/unit/test_report_definition_normalizer.py`
  - PBIR normalization behavior.
- `tests/unit/test_visual_field_reference_extractor.py`
  - Visual semantic field extraction.
- `tests/unit/test_logging.py`
  - Sensitive value redaction.
- `tests/unit/test_dax_dependency_service.py`
  - DAX dependencies, unresolved references, string/comment exclusion, cycles.
- `tests/unit/test_physical_source_service.py`
  - Power Query/M, native SQL, gateway sanitization, and source mappings.
- `tests/unit/test_lineage_graph_service.py`
  - Canonical graph and end-to-end downstream impact paths.
- `tests/unit/test_estate_discovery_service.py`
  - Estate inventory, report/model bindings, and estate graph behavior.
- `tests/unit/test_snowflake_lineage_service.py`
  - Snowflake dependency normalization and SQL API request contracts.
- `tests/unit/test_snowflake_session_auth.py`
  - Password/MFA, RSA, external-browser, OAuth, connector identity, redaction,
    expiry, active checkout, and connection cleanup.
- `tests/unit/test_snowflake_deep_lineage_service.py`
  - Five-level continuation, seven-branch concurrency, table/column modes,
    quoted identifiers, query binding, cycles, limits, and branch failures.
- `tests/unit/test_lineage_platform_services.py`
  - SQLite versions, diffs, TTL cache, search/navigation, validation, and jobs.
- `tests/unit/test_live_lineage_scan_service.py`
  - Live TMDL/gateway orchestration, partial gateway access, and graph output.
- `tests/unit/test_explorer_service.py`, `tests/api/test_explorer_resources.py`
  - Explorer call deduplication, bounded concurrency, all five row mappings,
    focused route selection, authentication dependencies, and validation.
- `tests/unit/test_security_operations.py`
  - Security headers, API-key enforcement, body limits, readiness, and metrics.
- `tests/unit/test_ai_fake_gateway.py`
  - `FakeModelGateway` deterministic generate/stream behavior.
- `tests/unit/test_ai_model_gateway.py`
  - `LiteLLMModelGateway` request mapping, response/streaming normalization,
    and provider-error-to-application-exception mapping. Skips cleanly
    (without failing collection for the rest of the suite) if `litellm`
    cannot be imported in the current environment.
- `tests/unit/test_ai_service.py`
  - `AI_ENABLED` gating, status reporting without secret exposure, the
    no-evidence gate (asserts the gateway is never called), persona
    presentation-only rendering, and simulated multi-provider independence.
- `tests/unit/test_ai_context_resolver.py`
  - Valid workspace/report/semantic-model resolution; inaccessible workspace,
    out-of-workspace report, and unverifiable semantic model rejected;
    forbidden vs. nonexistent workspace access fail identically; ambiguous
    and unknown object names.
- `tests/unit/test_ai_tools.py`
  - Each registered tool against real parsed-semantic-model/report fixtures
    — correct evidence, no invented facts when context is missing.
- `tests/unit/test_ai_supervisor_routing.py`
  - Deterministic intent classification and agent routing, including the
    out-of-scope fallback.
- `tests/unit/test_ai_measure_agent.py`, `test_ai_impact_agent.py`,
  `test_ai_report_agent.py`
  - Full evidence-bundle assembly per agent, including the TMDL-vs-XMLA
    conflicting-evidence case for measures.
- `tests/unit/test_ai_grounding.py`
  - Grounded composer + validator: accepts well-formed cited claims;
    rejects a hallucinated claim with no evidence ids; rejects a claim
    citing a nonexistent evidence id; the deterministic fallback still
    returns the exact DAX from evidence when composition is rejected.
- `tests/unit/test_ai_fake_gateway.py`
  - `FakeModelGateway` deterministic generate/stream behavior.
- `tests/unit/test_ai_model_gateway.py`
  - `LiteLLMModelGateway` request mapping, response/streaming normalization,
    and provider-error-to-application-exception mapping. Skips cleanly
    (without failing collection for the rest of the suite) if `litellm`
    cannot be imported in the current environment.
- `tests/api/test_ai_resources.py`
  - `/ai/status`, `/ai/chat`, and `/ai/chat/stream` authentication,
    `AI_DISABLED` handling, an end-to-end grounded measure answer with
    mocked provider calls, and the SSE event sequence with no duplicated
    final answer.

## Phase History

This timeline follows the repository milestone history provided by the
maintainer. Commit IDs and author details are intentionally omitted.

| Date | Milestone | Status | Summary |
| --- | --- | --- | --- |
| Aug 18, 2026 | Backend initialization | Completed | Initialized the FastAPI backend. |
| Aug 18, 2026 | Backend setup guide | Completed | Added the backend setup guide. |
| Aug 18, 2026 | Phase 1 | Completed | Completed the initial backend foundation. |
| Aug 18, 2026 | Phase 2.3 | Completed | Continued backend foundation work. |
| Aug 21, 2026 | Phase 2.6 | Completed | Continued backend foundation work. |
| Aug 21, 2026 | Phase 2.7 | Completed | Continued backend foundation work. |
| Aug 24, 2026 | Phase 3.1 | Completed | Added workspace discovery and authentication. |
| Aug 24, 2026 | Phase 3.2 | Completed | Added report and semantic model listing. |
| Aug 24, 2026 | Phase 3.2 test/refinement | Completed | Added tests and refinements for report and semantic model listing. |
| Aug 26, 2026 | Phase 3.3 | Completed | Added Fabric report definition retrieval. |
| Aug 26, 2026 | Phase 3.4 | Completed | Added report definition decoding and normalization. |
| Aug 26, 2026 | Phase 3.5 | Completed | Added visual semantic query and field reference extraction. |
| Aug 28, 2026 | Phase 3.6 | Completed locally | Stabilized auth diagnostics and Fabric scope handling. |
| Aug 28, 2026 | Phase 3.7 | Completed locally | Finalized semantic model definition retrieval coverage. |
| Aug 28, 2026 | Phase 3.8 | Completed locally | Added parsed semantic model definition output. |
| Aug 28, 2026 | Phase 3.9 | Completed locally | Added report visual field to semantic model object matching. |
| Aug 28, 2026 | Phase 3.10 | Completed locally | Improved TMDL parser fidelity and source-path evidence. |
| Aug 28, 2026 | Phase 3.11 | Completed locally | Added lineage diagnostics, candidate suggestions, and summary counts. |
| Aug 28, 2026 | Phase 3.12 | Completed locally | Added XMLA metadata contracts and service/client boundary. |
| Aug 28, 2026 | Phase 3.12.1 | Completed locally | Corrected Fabric report definition formats to default to PBIR and reject semantic-model-only formats. |
| Aug 28, 2026 | Phase 3.12.2 | Completed locally | Added upstream provider diagnostic detail for Fabric request and operation failures. |
| Aug 28, 2026 | Phase 3.13 | Completed locally | Implemented the XMLA ADODB/MSOLAP adapter path and TMSCHEMA metadata extraction mapping. |
| Aug 28, 2026 | Phase 3.14 | Completed locally | Added source-preserving Fabric TMDL/XMLA semantic metadata reconciliation. |
| Aug 31, 2026 | Phase 6.0 | Completed locally | Added My workspace report detail, gateway discovery, and gateway datasource metadata contracts. |
| Aug 31, 2026 | Phase 5.1-5.5 | Completed locally | Added DAX reference resolution and dependency-cycle detection for measures and calculated columns/tables. |
| Aug 31, 2026 | Phase 6.1-6.4 | Completed locally | Added Power Query/M extraction, source detection, physical-object mapping, and tested gateway/query mappings. |
| Aug 31, 2026 | Phase 7 | Completed locally | Added canonical stable-ID nodes, edges, and end-to-end graph construction. |
| Aug 31, 2026 | Phase 8 | Completed locally | Added downstream reverse-impact paths with depth limits. |
| Aug 31, 2026 | Phase 9 | Completed locally | Added workspace/estate inventory, report/model bindings, and an estate graph. |
| Aug 31, 2026 | Phase 10 | Completed locally | Added optional Snowflake SQL API/object-dependency normalization, connector authentication sessions, and concurrent deep table/column lineage. |
| Aug 31, 2026 | Phase 11-17 | Completed locally | Added unified APIs, search/navigation, TTL caching, scan jobs, SQLite versions, incremental diffs, and validation. |
| Aug 31, 2026 | Phase 18-20 | Completed locally | Added configurable security controls, operational readiness, and Prometheus metrics. |
| Sep 1, 2026 | Explorer read-model integration | Completed locally | Added five focused frontend datasets, a shared snapshot API, request-scoped call deduplication, and bounded parallel retrieval. |
| Sep 2, 2026 | Microsoft app auth and metadata scanner | Completed locally | Added protected Entra client-secret sessions plus the official four-step Power BI Admin scanner workflow with full-payload retention and summary counts. |
| Sep 14, 2026 | Browser SSO and gateway SSO metadata | Completed locally | Added delegated Authorization Code + PKCE login, shared auth-session diagnostics, and tri-state gateway OAuth2 SSO passthrough metadata. |
| Deferred | Phase 21 | Not started by design | PowerAI remains excluded until backend and frontend workflows are complete. |

The Phase 3.6-3.14 execution labels are retained for history. Against the
original roadmap, they finish Phase 3 report-level lineage and implement Phase
4 semantic model metadata. The original roadmap numbering above is now the
authoritative phase view; Phase 6.0 remains only a historical execution label.

### Latest Completed Phase

Phase 20 is the latest completed roadmap phase. The explorer read models,
Microsoft app-auth/scanner integration, browser SSO, and gateway SSO metadata
are post-phase extensions and do not renumber the roadmap. They strengthen
original Phase 2 authentication, Phase 6 physical-source mapping, and Phase 9
estate discovery while retaining the rule that source evidence is preserved
rather than silently overwritten.

### Next Phase

No PowerAI work starts next. The immediate work is live tenant acceptance,
including browser SSO, Snowflake auth/`GET_LINEAGE`, frontend integration,
broader DAX/M fixture coverage, and replacing in-memory auth plus
single-instance SQLite/job coordination before horizontal scaling.

The Phase 3.14 implementation has a tenant-dependent acceptance check that is
not part of local automated testing:

- Validate XMLA extraction against a Premium, PPU, or Fabric capacity with XMLA
  enabled.
- Confirm workspace naming, tenant naming, and semantic model `Initial Catalog`
  behavior with real workspaces.
- Confirm the merged metadata endpoint returns expected source counts and
  reconciliation statuses for a real semantic model.

## Current Review Notes

Phases 3.6 through 20, the explorer integration, Microsoft authentication,
gateway SSO metadata, and the Scanner API are locally verified with Ruff and
pytest: 241 tests pass. Browser SSO is contract-tested locally but still
requires a live Entra redirect-flow acceptance check. The only known suite
warning is the third-party FastAPI/TestClient deprecation for Starlette's
`httpx` integration.

## Development Notes

- Keep API route handlers thin.
- Put provider HTTP details in `app/clients`.
- Put mapping, polling, decoding, and normalization in `app/services`.
- Keep response contracts in `app/schemas`.
- Use `AppException` subclasses for expected failures.
- Do not log access tokens, decoded payload values, authorization headers, or
  sensitive query strings.
- For Fabric definition changes, test both `200` immediate and `202`
  long-running operation paths.
- For PBIR normalization changes, use small encoded JSON fixture parts.
- Treat locally decoded JWT scopes as diagnostics only.
