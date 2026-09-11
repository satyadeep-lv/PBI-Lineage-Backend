# PBI Lineage Backend

Standalone FastAPI backend for Power BI, Microsoft Fabric, and optional
Snowflake metadata discovery, report definition retrieval, PBIR normalization,
physical-source discovery, lineage graph construction, and impact analysis.

This backend is being split out from the original Streamlit-based PBI Lineage
Explorer so the application can evolve into a cleaner service-oriented
architecture.

## What This Service Does

Current capabilities:

- Supports Microsoft device-code authentication for interactive testing and
  Microsoft Entra service-principal client-secret authentication for
  unattended application sessions.
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

Remaining acceptance and scale work:

- Improve semantic model parser coverage for more TMDL shapes.
- Run live XMLA acceptance validation against a Power BI/Fabric capacity.
- Run live Snowflake authentication and deep-lineage acceptance with a role
  permitted to call `SNOWFLAKE.CORE.GET_LINEAGE`.
- Add production-grade auth/session storage.
- Move lineage persistence and scan coordination to shared infrastructure before
  running multiple API workers/tasks.
- Expand DAX and Power Query grammar coverage with tenant-derived fixtures.
- Automate ECS task-definition registration and service rollout after an
  immutable Amazon ECR image is published.
- Add production high availability, alarms, and autoscaling.

PowerAI is intentionally deferred until the backend and frontend lineage
workflows are complete. No PowerAI endpoint or service is included in this phase.

## Technology Stack

- Python 3.13
- FastAPI
- Pydantic / Pydantic Settings
- httpx
- MSAL
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
```

`MICROSOFT_SSO_REDIRECT_URI` is only required to enable
`GET /auth/microsoft/sso/login`; it must exactly match a "Web" platform
redirect URI registered on the Entra app registration (with public client
flows still allowed, since the flow uses PKCE and no client secret).

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
— `authentication_method` is simply `"sso"` instead of `"device_code"`).
Query parameters:

- `tenant_id`, `client_id` (required) — same meaning as the device-code route.
- `post_login_redirect_uri` (optional) — where to send the browser after a
  successful login. Its origin must exactly match one entry in
  `CORS_ALLOWED_ORIGINS`, or the request is rejected with
  `AUTH_REDIRECT_NOT_ALLOWED` before any redirect to Microsoft happens. When
  omitted, `GET /microsoft/sso/callback` returns the same JSON status body as
  `GET /microsoft/device/status` instead of redirecting.

`GET /microsoft/sso/login` requires `MICROSOFT_SSO_REDIRECT_URI` to be set and
requires the Entra app registration to have a matching "Web" platform redirect
URI with public client flows still enabled (PKCE replaces the client secret
for this flow). This flow only acquires delegated Power BI/Fabric resource
tokens; it does not use an OpenID Connect id_token and does not establish any
product-level user identity or role.

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
or `false` when the datasource uses OAuth2 credentials, `null` for every
other credential type. Kerberos and SAML AD-SSO (used by on-premises sources
such as SQL Server, Oracle, and SAP) are not exposed by this API and are
never reported; `null` means "not applicable or unknown," not "SSO is off."
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
POST /api/v1/explorer/semantic-model-objects
POST /api/v1/explorer/measure-source-lineage
POST /api/v1/explorer/report-layout
POST /api/v1/explorer/visual-source-lookup
```

These routes are the typed replacement for the five legacy Streamlit tables.
Use `/snapshot` for the initial explorer load; it retrieves each distinct
workspace, report, report definition, and semantic model definition once, runs
independent provider calls concurrently with a bounded limit, and derives all
five datasets from the shared evidence. Use a focused endpoint for lazy-loaded
tabs when only one table is needed. DAX and Power Query analysis run outside the
event loop, and two reports sharing one semantic model share one definition
request.

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

Legacy screen mapping:

| Legacy table | Endpoint | Main response rows |
|---|---|---|
| Source DB Lineage | `/explorer/source-database-lineage` | Report/model IDs, semantic table and partition, provider endpoint/object, fully qualified source name, gateway IDs |
| Semantic Model Objects | `/explorer/semantic-model-objects` | Tables, columns, calculated columns/tables, measures, hierarchies, DAX, types, visibility, and source paths |
| Measure Source Lineage | `/explorer/measure-source-lineage` | Measure/calculated-object DAX, terminal semantic sources, dependency depth, physical source, and fully qualified name |
| Report Layout | `/explorer/report-layout` | Pages, visuals, roles, fields, query references, definition counts, and visual coordinates |
| Visual Source Lookup | `/explorer/visual-source-lookup` | Visual fields joined to semantic objects with status, confidence, reason, source path, and coordinates |

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
GET /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/xmla/metadata
```

Optional query parameters:

- `workspaceName`
- `databaseName`

This endpoint uses the Power BI token dependency and the XMLA ADODB/MSOLAP
adapter to query `$SYSTEM.TMSCHEMA_*` rowsets for tables, columns, measures,
partitions, hierarchies, levels, and relationships. Workspace names are URI
encoded in the `powerbi://api.powerbi.com/v1.0/{tenant}/{workspace}` endpoint.
If `workspaceName` or `databaseName` is not supplied, the service resolves the
workspace name and semantic model name from Power BI REST before opening the
XMLA connection because XMLA URLs use names, not REST object IDs.

If `pywin32`, Windows COM, or the Microsoft Analysis Services OLE DB Provider
is not available on the host, the client returns
`PROVIDER_INTEGRATION_NOT_CONFIGURED` with a setup message.

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

## Folder Structure

```text
app/
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
- `app/api/dependencies/credentials.py`
  - FastAPI dependencies for extracting Power BI/Fabric credentials and the
    Snowflake connector-session ID from their separate HttpOnly cookies.
- `app/api/dependencies/lineage.py`
  - Singleton lineage repository, cache/store, and scan-manager dependencies.
- `app/api/dependencies/security.py`
  - Optional constant-time lineage administration API-key enforcement.

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
    OAuth2-credentialed datasources; leaves it `null` for every other
    credential type rather than guessing.
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
  - Device auth route/status/logout behavior.
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
  - Gateway and datasource mapping, including provider identity validation.
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
| Deferred | Phase 21 | Not started by design | PowerAI remains excluded until backend and frontend workflows are complete. |

The Phase 3.6-3.14 execution labels are retained for history. Against the
original roadmap, they finish Phase 3 report-level lineage and implement Phase
4 semantic model metadata. The original roadmap numbering above is now the
authoritative phase view; Phase 6.0 remains only a historical execution label.

### Latest Completed Phase

Phase 20 is the latest completed roadmap phase. The explorer read models and
Microsoft app-auth/scanner integration are post-phase extensions and do not
renumber the roadmap. They strengthen original Phase 2 authentication and
Phase 9 estate discovery while retaining the rule that source evidence is
preserved rather than silently overwritten.

### Next Phase

No PowerAI work starts next. The immediate work is live tenant acceptance,
including Snowflake auth/`GET_LINEAGE`, frontend integration, broader DAX/M
fixture coverage, and replacing in-memory auth plus single-instance SQLite/job
coordination before horizontal scaling.

The Phase 3.14 implementation has a tenant-dependent acceptance check that is
not part of local automated testing:

- Validate XMLA extraction against a Premium, PPU, or Fabric capacity with XMLA
  enabled.
- Confirm workspace naming, tenant naming, and semantic model `Initial Catalog`
  behavior with real workspaces.
- Confirm the merged metadata endpoint returns expected source counts and
  reconciliation statuses for a real semantic model.

## Current Review Notes

Phases 3.6 through 20, the explorer integration, Microsoft app authentication,
and the Scanner API are locally verified with Ruff and pytest: 223 tests pass.
The only known test-suite warning is a third-party FastAPI/TestClient warning
about Starlette's `httpx` integration.

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
