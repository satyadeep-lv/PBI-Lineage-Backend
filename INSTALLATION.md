# PBI Lineage Backend - New PC Installation Guide

This guide sets up a fresh development or validation machine from a clean
clone. It covers the core API first, then the optional Microsoft/Fabric,
Power BI Scanner, XMLA, Snowflake, and Windows-container capabilities.

Do not copy `.venv`, `.env`, cached tokens, or local session state from another
computer. Clone the repository, create a new virtual environment, install from
the committed requirements files, and provide credentials through the intended
runtime inputs.

## 1. Choose The Required Capability

| Capability | Supported host | Additional requirement |
| --- | --- | --- |
| Core API, parsers, tests, and non-XMLA endpoints | Windows, Linux, or macOS with Python 3.13 support | Git, CPython, pip, and outbound package access |
| Native live XMLA extraction | 64-bit Windows | `pywin32`, ADODB COM, and x64 MSOLAP |
| Snowflake connector and deep lineage | Windows, Linux, or macOS | Snowflake account, role, warehouse, and outbound HTTPS |
| Production-image validation | Compatible Windows container host | Docker in Windows-container mode and the x64 MSOLAP installer URL |

The repository CI runs the general Python test suite on Linux. Live XMLA is a
Windows-only integration and needs a separate Windows acceptance test.

## 2. Install Base Tools

### Windows

Open PowerShell and install Git and the supported Python line:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Python.Python.3.13 -e --source winget
```

If `winget` is unavailable, install
[Git for Windows](https://git-scm.com/download/win) and the official 64-bit
[Python 3.13.15 release](https://www.python.org/downloads/release/python-31315/)
manually. Keep pip enabled and select the option to add Python to `PATH`.

Close and reopen PowerShell, then verify:

```powershell
git --version
py -3.13 --version
py -3.13 -m pip --version
```

If `py -3.13` is unavailable but `python --version` reports `3.13.x`, use
`python` in place of `py -3.13` in the commands below.

### Linux Or macOS

Install Git, CPython 3.13, pip, and the operating system's Python venv package
with the package manager. For example, Debian/Ubuntu installations commonly
require `python3.13-venv`. Start a new shell and verify `git --version`,
`python3.13 --version`, and `python3.13 -m pip --version`.

## 3. Clone The Repository

Choose a normal development directory, not a protected system folder:

```powershell
cd C:\Projects
git clone https://github.com/satyadeep0987/PBI-Lineage-Backend.git
cd PBI-Lineage-Backend
git switch main
git pull --ff-only
```

Use `main` to reproduce the stable repository state. For development, create a
short-lived branch from the latest `origin/main`; do not edit `main` directly:

```powershell
git fetch origin
git switch -c feature/<work-item> origin/main
```

Replace `<work-item>` before running the command. Private-repository access, if
enabled later, must be configured through GitHub authentication or Git
Credential Manager.

## 4. Create The Virtual Environment And Install Dependencies

Python 3.13 is the supported baseline. From the repository root on Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

If PowerShell blocks `Activate.ps1`, either allow locally created scripts for
the current user or invoke `.venv\Scripts\python.exe` directly. On Linux or
macOS, use:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

`requirements.txt` contains runtime packages. `requirements-dev.txt` includes
the runtime file plus pytest and Ruff. `constraints.txt` pins the complete
resolved dependency set used by local development, CI, and containers. Keep
`.venv` local and disposable; never commit or copy it between computers.

Verify the environment:

```powershell
python --version
python -c "import sys; assert sys.prefix != sys.base_prefix; print(sys.executable)"
python -c "import fastapi, httpx, msal, snowflake.connector; print('Python dependencies OK')"
python -m pip check
git status --short
```

Expected results:

- Python reports version `3.13.x`.
- The executable path is inside the repository's `.venv` directory.
- Imports finish with `Python dependencies OK` and `pip check` reports no
  broken requirements.
- `git status --short` is empty on an unchanged clone.

Python's standard [`venv`](https://docs.python.org/3/library/venv.html) module
creates the isolated environment. pip installs the committed package lists by
using its documented [requirements-file
support](https://pip.pypa.io/en/stable/reference/requirements-file-format/).

## 5. Create Local Configuration

Create a local `.env` from the committed template:

```powershell
Copy-Item .env.example .env
```

The defaults are suitable for an API bound only to local loopback. Review every
setting before exposing the process to a LAN, browser frontend, or public
network.

| Setting | Local default or example | Purpose |
| --- | --- | --- |
| `APP_NAME`, `APP_VERSION`, `ENVIRONMENT` | Development defaults | Service identity and runtime policy |
| `API_V1_PREFIX` | `/api/v1` | API route prefix |
| `LOG_LEVEL` | `INFO` | Structured application log level |
| `XMLA_TENANT_NAME` | `myorg` | XMLA tenant path; set tenant domain/ID for cross-tenant cases |
| `XMLA_PROVIDER` | `MSOLAP` | Installed Analysis Services OLE DB provider name |
| `LINEAGE_DATABASE_PATH` | `data/lineage.db` | SQLite graph and scan-job store |
| `LINEAGE_CACHE_TTL_SECONDS` | `30` | In-process graph cache lifetime |
| `LINEAGE_CACHE_MAX_ENTRIES` | `128` | Maximum in-process graph cache entries |
| `LINEAGE_SCAN_MAX_CONCURRENCY` | `2` | Internal graph scan-job concurrency |
| `SNOWFLAKE_SESSION_MAX_AGE_SECONDS` | `2700` | Process-local Snowflake session lifetime |
| `SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH` | `false` | Allows local backend-host browser SSO only when explicitly enabled |
| `CORS_ALLOWED_ORIGINS` | `[]` | Exact browser frontend origins as a JSON list |
| `ALLOWED_HOSTS` | `["*"]` locally | Trusted host names; use explicit values outside local development |
| `FORCE_HTTPS` | `false` locally | Application-level HTTPS redirect policy |
| `ENABLE_API_DOCS` | `true` locally | Swagger and ReDoc availability |
| `AUTH_COOKIE_SECURE` | `false` for local HTTP | Require HTTPS before setting this to true |
| `AUTH_COOKIE_SAMESITE` | `lax` | Microsoft and Snowflake session-cookie policy |
| `MAX_REQUEST_BODY_BYTES` | `10485760` | Maximum accepted request body |
| `EXPOSE_METRICS` | `true` | Prometheus-format health metrics endpoint |
| `LINEAGE_ADMIN_API_KEY` | No default | Protects lineage, Scanner, Snowflake auth, and Microsoft app-auth routes |

For a local frontend on port 5173, use JSON-list syntax:

```text
CORS_ALLOWED_ORIGINS=["http://localhost:5173"]
ALLOWED_HOSTS=["localhost","127.0.0.1","testserver"]
```

`testserver` is required only by FastAPI's local TestClient. It is not a public
DNS name and should be omitted from production hosts.

Generate a strong administration key after dependencies are installed:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For the first test run, leave `LINEAGE_ADMIN_API_KEY` commented out exactly as
shown in `.env.example`. After Section 6 passes, place the generated value in
the local `.env` as `LINEAGE_ADMIN_API_KEY=<generated-value>` and restart the
API. Send the same value only in the `X-Lineage-Admin-Key` request header. The
current API tests do not inject an ambient key into every protected request, so
setting it before the test run would intentionally turn those requests into
`401` responses.

Never commit `.env`, secrets, tokens, RSA keys, Snowflake passwords, or
downloaded credential files.

The SQLite parent directory and schema are created automatically. Use an
absolute `LINEAGE_DATABASE_PATH` if the process may start from different
working directories. Restart the API after changing `.env`; settings are
cached for the process lifetime.

## 6. Verify Code Quality Before Starting

Run the same local checks used by CI:

```powershell
ruff check .
ruff format --check .
python -m pytest
```

All commands must pass before testing provider credentials. Provider calls are
mocked in the automated suite, so passing tests confirms the installation but
does not prove tenant, capacity, gateway, or Snowflake permissions.

After the tests pass, apply the generated `LINEAGE_ADMIN_API_KEY` and any
stricter runtime host/CORS values, restart the process, and use that key for
protected Swagger calls.

## 7. Start And Smoke-Test The API

Start the development server from the repository root:

```powershell
fastapi dev app/main.py
```

The default endpoints are:

```text
Swagger:   http://127.0.0.1:8000/docs
OpenAPI:   http://127.0.0.1:8000/openapi.json
Health:    http://127.0.0.1:8000/api/v1/health
Liveness:  http://127.0.0.1:8000/api/v1/health/live
Readiness: http://127.0.0.1:8000/api/v1/health/ready
Metrics:   http://127.0.0.1:8000/api/v1/health/metrics
```

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

Health should return `status: ok`; readiness should return `status: ready`.
Stop the development server with `Ctrl+C`.

Keep one API worker. Microsoft sessions, live Snowflake connections, TTL cache,
and scan coordination are process-local; multiple workers or machines require
shared session, cache, persistence, and job infrastructure first.

## 8. Configure Microsoft And Fabric Access

The backend supports interactive device-code authentication and unattended
service-principal client-secret authentication. Both require outbound HTTPS to
Microsoft identity and provider endpoints.

### Option A - Device-Code Authentication

In Microsoft Entra admin center:

1. Register a single-tenant application.
2. Record the Directory/Tenant ID and Application/Client ID.
3. Under Authentication, enable public client flows for device-code login.
4. Add delegated Power BI permissions `Workspace.Read.All`, `Report.Read.All`,
   and `Dataset.Read.All`.
5. Add delegated Fabric permissions `Workspace.Read.All` and
   `Item.ReadWrite.All`.
6. Grant administrator consent where required by tenant policy.
7. Give the authenticating user access to the required workspaces, reports,
   semantic models, gateways, Fabric items, and capacities.

Use Swagger to call:

```text
POST /api/v1/auth/microsoft/device/start
GET  /api/v1/auth/microsoft/device/status
```

Open the returned verification URL, enter the user code, complete sign-in, and
poll status. The browser retains the HttpOnly session cookie. Power BI and
Fabric use different token audiences, so inspect both provider results. A
successful Power BI login does not guarantee Fabric authentication.

The current device flow does not request delegated `Tenant.Read.All`; use the
service-principal path below for the Power BI Scanner workflow.

### Option B - Service Principal With Client Secret

In Microsoft Entra admin center:

1. Register a single-tenant application and record tenant ID and client ID.
2. Create a client secret under Certificates & secrets and securely record the
   secret value at creation time.
3. Add the service principal to a dedicated Entra security group.
4. In Fabric Admin portal, enable `Service principals can use Fabric APIs` for
   that security group.
5. For ordinary workspace APIs, add the service principal or its group to each
   required workspace with the minimum role needed by the target APIs.

Call this route over HTTPS outside localhost:

```text
POST /api/v1/auth/microsoft/service-principal/session
```

Request body:

```json
{
  "tenant_id": "<tenant-uuid>",
  "client_id": "<application-uuid>",
  "client_secret": "<secret-value>"
}
```

Add `X-Lineage-Admin-Key` when configured. The service requests independent
Power BI and Fabric `/.default` tokens. It never stores the client secret. A
`partial` response means the Power BI token was acquired but the Fabric token
was not.

Microsoft app registration guidance: [register an application with Microsoft
Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app).

Fabric service-principal guidance: [identity support for Fabric REST
APIs](https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support).

## 9. Configure Power BI Scanner Access

Scanner service-principal authorization is separate from ordinary workspace
API authorization. A Fabric administrator must:

1. Enable the read-only Power BI/Fabric Admin API service-principal tenant
   setting for the dedicated security group.
2. Confirm the service principal is a direct or effective member of that group.
3. Enable detailed metadata responses to return semantic model tables,
   columns, and measures.
4. Enable DAX and mashup expression responses when DAX and Power Query/M are
   required.
5. Follow the Scanner-specific Microsoft rule: do not configure
   admin-consent-required Power BI permissions on the service-principal app.

After service-principal login, use this sequence:

```text
GET  /api/v1/scanner/workspaces/modified
POST /api/v1/scanner/workspaces/scan
GET  /api/v1/scanner/scans/{scan_id}/status
GET  /api/v1/scanner/scans/{scan_id}/result
```

Submit between 1 and 100 workspace UUIDs, poll until `Succeeded`, then retrieve
the result within Microsoft's result-retention period. The backend returns a
summary and preserves the complete Microsoft payload.

Official setup: [set up metadata scanning in an
organization](https://learn.microsoft.com/en-us/fabric/admin/metadata-scanning-setup).

## 10. Enable Native XMLA On Windows

Skip this section if XMLA endpoints are not needed. The rest of the backend can
run without MSOLAP.

1. Use 64-bit Windows and a 64-bit Python 3.13 virtual environment.
2. Install the current x64 Microsoft Analysis Services OLE DB Provider
   (`MSOLAP`) as an administrator from Microsoft's client-library page.
3. Keep `XMLA_PROVIDER=MSOLAP`, unless the installed provider requires a
   version-specific registered name.
4. Configure `XMLA_TENANT_NAME` when `myorg` is not valid for the tenant.
5. Ensure the workspace is on Fabric, Premium, Embedded, or PPU capacity with
   XMLA enabled for the required operation.
6. Grant the identity access to the workspace and Build/read access to the
   semantic model and any required upstream semantic models.

Official MSOLAP download page: [Analysis Services client
libraries](https://learn.microsoft.com/en-us/analysis-services/client-libraries).

Verify Python COM and ADODB:

```powershell
python -c "import pythoncom, win32com.client; c = win32com.client.Dispatch('ADODB.Connection'); print('ADODB COM OK')"
Get-ChildItem 'HKLM:\SOFTWARE\Classes' | Where-Object { $_.PSChildName -like 'MSOLAP*' } | Select-Object -ExpandProperty PSChildName
```

Then authenticate to Microsoft and test:

```text
GET /api/v1/workspaces/{workspace_id}/semantic-models/{semantic_model_id}/xmla/metadata
```

An HTTP `501` with `PROVIDER_INTEGRATION_NOT_CONFIGURED` normally means the
Windows COM/MSOLAP runtime is absent or not registered. Authentication,
capacity, workspace naming, catalog naming, or semantic-model permission issues
normally appear only after the provider can load.

## 11. Configure Snowflake Access

Installing `requirements.txt` includes the Snowflake Connector for Python,
Snowpark Python, and cryptography. Do not create the reference stored procedure
in a customer account; the backend implements repeated
`SNOWFLAKE.CORE.GET_LINEAGE` traversal itself.

Provide a Snowflake account and a least-privilege role with:

- Access to the required warehouse and object databases/schemas.
- Visibility of the tables or columns being traced.
- Permission to call `SNOWFLAKE.CORE.GET_LINEAGE` for the target objects.
- An account/edition that supports the required lineage function.

Supported session methods are password/MFA, RSA key pair, local external
browser, and OAuth:

```text
POST   /api/v1/auth/snowflake/session
GET    /api/v1/auth/snowflake/session/status
DELETE /api/v1/auth/snowflake/session
POST   /api/v1/lineage/snowflake/trace
```

Keep `SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH=false` on remote or unattended
hosts. External-browser authentication opens on the backend machine. Prefer
OAuth or RSA key pair for hosted operation. Authentication values are request
inputs and must not be placed in source control.

Official reference: [installing the Snowflake Python
Connector](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-install).

## 12. Optional Windows Container Setup

The committed production Dockerfile uses Windows Server Core LTSC 2025 because
it installs and validates ADODB COM and MSOLAP. It cannot be built as a Linux
container.

1. Install Docker Desktop or another compatible Windows container engine.
2. Verify that the Windows edition, virtualization, and container mode support
   the LTSC 2025 base image.
3. Switch Docker to Windows containers.
4. Obtain the current x64 MSOLAP MSI URL from Microsoft's client-library page.

Build from the repository root:

```powershell
$MSOLAP_MSI_URL = "<official-x64-msolap-msi-url>"
docker build `
  --build-arg "MSOLAP_MSI_URL=$MSOLAP_MSI_URL" `
  -t pbi-lineage-backend:local .
```

Run a local validation container:

```powershell
docker run --rm `
  --name pbi-lineage-api `
  --env-file .env `
  -p 8000:8000 `
  pbi-lineage-backend:local
```

Do not publish port 8000 directly on a production host. The deployed design
places it behind an HTTPS load balancer and runs exactly one worker. Review
Docker's current [Windows installation
requirements](https://docs.docker.com/desktop/setup/install/windows-install/).

## 13. Network And Firewall Requirements

Allow outbound TCP 443 as required for the selected capabilities:

| Purpose | Destination |
| --- | --- |
| Clone and source updates | `github.com` and GitHub content endpoints |
| Python and package installation | `python.org`, `pypi.org`, and `files.pythonhosted.org` |
| Microsoft sign-in | `login.microsoftonline.com` |
| Power BI REST and XMLA | `api.powerbi.com` |
| Fabric REST | `api.fabric.microsoft.com` |
| Snowflake | The account's approved `*.snowflakecomputing.com` endpoints |

Corporate TLS inspection or an outbound proxy can require organization-issued
root certificates and standard proxy environment variables. Do not disable TLS
verification to work around certificate failures. Accurate system time is also
required for OAuth, TLS, cookies, and token expiration.

For local use, allow inbound TCP 8000 only from the intended machine/network.
Binding to `127.0.0.1` requires no remote inbound access.

## 14. Final Installation Checklist

- Repository is cloned from the expected remote and checked out to the intended
  branch.
- `python --version` reports Python 3.13 from the local `.venv`.
- `python -m pip install --requirement requirements-dev.txt` and
  `python -m pip check` complete successfully.
- `.env` exists locally, is ignored by Git, and contains no shared plaintext
  production credentials.
- Ruff lint, Ruff format check, and pytest pass.
- Health and readiness return successful results.
- CORS, trusted hosts, secure-cookie policy, and administration API key match
  the actual exposure level.
- Microsoft app/user, tenant settings, workspace permissions, and both token
  audiences are verified if Power BI/Fabric is required.
- Scanner-specific admin settings are verified before Scanner API testing.
- x64 MSOLAP, ADODB COM, capacity XMLA, and Build permission are verified if
  native XMLA is required.
- Snowflake role, warehouse, authentication method, and lineage access are
  verified if Snowflake enrichment is required.
- Only one API worker is configured until process-local state is moved to shared
  infrastructure.

## 15. Common Setup Failures

| Symptom | Check |
| --- | --- |
| `py -3.13` or `python3.13` is not recognized | Install official 64-bit Python 3.13, enable pip/PATH, and reopen the terminal |
| `Activate.ps1` is blocked | Set an approved current-user execution policy or invoke `.venv\Scripts\python.exe` directly |
| Imports fail after installation | Confirm the virtual environment is active, reinstall `requirements-dev.txt`, and run `python -m pip check` |
| Readiness returns `503` | Check SQLite path permissions and production security settings |
| Microsoft login times out | Verify DNS/outbound 443 to `login.microsoftonline.com` and proxy/TLS policy |
| Power BI token succeeds but API returns `401` or `403` | Check token audience, tenant service-principal setting, security-group membership, workspace role, and API-specific permission requirements |
| Fabric status is unavailable or partial | Verify the Fabric token audience, Fabric service-principal tenant setting, consent, workspace access, and API identity support |
| Scanner omits tables, columns, DAX, or M | Enable the detailed metadata and DAX/mashup tenant settings, then run a new scan |
| XMLA returns integration-not-configured | Verify 64-bit Windows, `pywin32`, ADODB COM, and registered x64 MSOLAP |
| XMLA provider loads but the request fails | Check capacity XMLA mode, workspace/model names, tenant path, Build/read permission, and token identity |
| Snowflake external browser opens on the wrong computer | It opens on the backend host; use OAuth/RSA for remote hosting |
| Browser calls lose authentication cookies | Use exact CORS origins, enable frontend credentials, and align HTTPS, Secure, and SameSite cookie settings |

For AWS/Azure deployment, CI/CD, startup/shutdown, and recovery procedures, use
the deployment documents under `REF_DOC` after completing this local baseline.
