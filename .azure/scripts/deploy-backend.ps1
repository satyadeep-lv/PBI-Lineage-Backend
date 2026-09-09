param(
    [Parameter(Mandatory = $false)]
    [string]$Image = "",

    [Parameter(Mandatory = $false)]
    [string]$AcrName = "",

    [Parameter(Mandatory = $false)]
    [string]$KeyVaultName = "",

    [Parameter(Mandatory = $false)]
    [string]$ContainerName = "pbi-lineage-api",

    [Parameter(Mandatory = $false)]
    [int]$HostPort = 8000,

    [Parameter(Mandatory = $false)]
    [int]$ContainerPort = 8000
)

$ErrorActionPreference = "Stop"

# ============================================================
# Validate parameters explicitly.
#
# Do NOT use Mandatory=$true for Azure Run Command parameters.
# A missing mandatory parameter can cause PowerShell to wait
# for interactive input instead of failing immediately.
# ============================================================

$RequiredParameters = @{
    Image        = $Image
    AcrName      = $AcrName
    KeyVaultName = $KeyVaultName
    ContainerName = $ContainerName
}

foreach ($Entry in $RequiredParameters.GetEnumerator()) {

    if ([string]::IsNullOrWhiteSpace($Entry.Value)) {
        throw (
            "Required deployment parameter '$($Entry.Key)' " +
            "was not provided."
        )
    }
}

if (
    $HostPort -lt 1 -or
    $HostPort -gt 65535
) {
    throw "HostPort is invalid: $HostPort"
}

if (
    $ContainerPort -lt 1 -or
    $ContainerPort -gt 65535
) {
    throw "ContainerPort is invalid: $ContainerPort"
}

Write-Host "========================================="
Write-Host "PBI Lineage Backend Deployment"
Write-Host "========================================="
Write-Host "Image:       $Image"
Write-Host "Container:   $ContainerName"
Write-Host "ACR:         $AcrName"
Write-Host "Key Vault:   $KeyVaultName"
Write-Host "Host port:   $HostPort"
Write-Host "Target port: $ContainerPort"

# ============================================================
# Refresh PATH
#
# Azure VM Run Command executes under the VM Agent process.
# The agent can retain an older PATH than an interactive RDP
# session.
# ============================================================

$MachinePath = [Environment]::GetEnvironmentVariable(
    "Path",
    "Machine"
)

$UserPath = [Environment]::GetEnvironmentVariable(
    "Path",
    "User"
)

$env:Path = "$MachinePath;$UserPath;$env:Path"

# ============================================================
# Resolve Docker executable
# ============================================================

$DockerCommand = Get-Command `
    "docker.exe" `
    -ErrorAction SilentlyContinue

if ($DockerCommand) {

    $DockerExe = $DockerCommand.Source
}
else {

    $DockerCandidates = @(
        "C:\Program Files\Docker\docker.exe",
        "C:\Program Files\docker\docker.exe"
    )

    $DockerExe = $DockerCandidates |
        Where-Object {
            Test-Path $_
        } |
        Select-Object -First 1
}

if (-not $DockerExe) {
    throw "docker.exe could not be located on the Azure VM."
}

Write-Host "Docker:"
Write-Host $DockerExe

# ============================================================
# Resolve Azure CLI
# ============================================================

$AzCommand = Get-Command `
    "az.cmd" `
    -ErrorAction SilentlyContinue

if (-not $AzCommand) {

    $AzCommand = Get-Command `
        "az.exe" `
        -ErrorAction SilentlyContinue
}

if ($AzCommand) {

    $AzExe = $AzCommand.Source
}
else {

    $AzCandidates = @(
        "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        "C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    )

    $AzExe = $AzCandidates |
        Where-Object {
            Test-Path $_
        } |
        Select-Object -First 1
}

if (-not $AzExe) {
    throw "Azure CLI could not be located on the Azure VM."
}

Write-Host "Azure CLI:"
Write-Host $AzExe

# ============================================================
# Application directories
# ============================================================

$AppRoot = "C:\pbi-lineage"
$DataRoot = Join-Path $AppRoot "data"
$LogRoot = Join-Path $AppRoot "logs"

foreach ($Directory in @(
    $AppRoot,
    $DataRoot,
    $LogRoot
)) {

    New-Item `
        -ItemType Directory `
        -Path $Directory `
        -Force |
        Out-Null
}

# ============================================================
# Production runtime configuration
# ============================================================

$env:ENVIRONMENT = "production"
$env:LOG_LEVEL = "INFO"

$env:LINEAGE_DATABASE_PATH = "data/lineage.db"

$env:SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH = "false"

# These fields are list[str] in Pydantic.
# They MUST remain valid JSON strings.
$env:CORS_ALLOWED_ORIGINS = '[]'

$env:ALLOWED_HOSTS = (
    '["lvpowerbilineage.com",' +
    '"www.lvpowerbilineage.com",' +
    '"localhost",' +
    '"127.0.0.1"]'
)

# HTTPS terminates at Cloudflare/IIS.
$env:FORCE_HTTPS = "false"

$env:ENABLE_API_DOCS = "false"

$env:AUTH_COOKIE_SECURE = "true"
$env:AUTH_COOKIE_SAMESITE = "lax"

# ============================================================
# Ensure Docker daemon is running
# ============================================================

$DockerService = Get-Service `
    -Name "docker" `
    -ErrorAction SilentlyContinue

if (-not $DockerService) {
    throw "Docker Windows service was not found."
}

if ($DockerService.Status -ne "Running") {

    Write-Host "Starting Docker service..."

    Start-Service `
        -Name "docker"
}

$DockerReady = $false

for ($Attempt = 1; $Attempt -le 12; $Attempt++) {

    Write-Host (
        "Docker readiness attempt " +
        "$Attempt/12"
    )

    & $DockerExe info *> $null

    if ($LASTEXITCODE -eq 0) {

        $DockerReady = $true
        break
    }

    Start-Sleep -Seconds 5
}

if (-not $DockerReady) {
    throw "Docker daemon did not become ready."
}

& $DockerExe version

if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon validation failed."
}

$DockerOsType = & $DockerExe info `
    --format "{{.OSType}}"

if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine Docker OS type."
}

if ($DockerOsType.Trim() -ne "windows") {
    throw (
        "Windows Docker daemon required. " +
        "Detected '$DockerOsType'."
    )
}

Write-Host "Windows Docker daemon ready."

# ============================================================
# Authenticate VM Managed Identity
# ============================================================

Write-Host "Authenticating VM managed identity..."

& $AzExe login `
    --identity `
    --output none

$AzLoginExitCode = $LASTEXITCODE

if ($AzLoginExitCode -ne 0) {
    throw "VM managed identity login failed."
}

Write-Host "Managed identity authentication succeeded."

# ============================================================
# Retrieve production secret from Key Vault
# ============================================================

Write-Host "Loading backend production secrets..."

$LineageAdminApiKey = & $AzExe keyvault secret show `
    --vault-name $KeyVaultName `
    --name "lineage-admin-api-key" `
    --query value `
    --output tsv

$KeyVaultExitCode = $LASTEXITCODE

if ($KeyVaultExitCode -ne 0) {
    throw (
        "Unable to retrieve LINEAGE_ADMIN_API_KEY " +
        "from Key Vault '$KeyVaultName'."
    )
}

$LineageAdminApiKey = (
    $LineageAdminApiKey |
        Out-String
).Trim()

if ([string]::IsNullOrWhiteSpace($LineageAdminApiKey)) {
    throw (
        "LINEAGE_ADMIN_API_KEY retrieved from " +
        "Key Vault is empty."
    )
}

$env:LINEAGE_ADMIN_API_KEY = $LineageAdminApiKey

Write-Host "Backend production secrets loaded successfully."

# Never print LINEAGE_ADMIN_API_KEY.

# ============================================================
# Authenticate to ACR
# ============================================================

Write-Host "Authenticating to Azure Container Registry..."

& $AzExe acr login `
    --name $AcrName

$AcrLoginExitCode = $LASTEXITCODE

if ($AcrLoginExitCode -ne 0) {
    throw "ACR login failed."
}

Write-Host "ACR authentication succeeded."

# ============================================================
# Pull target image
# ============================================================

Write-Host "Pulling backend image..."
Write-Host $Image

& $DockerExe pull $Image

$PullExitCode = $LASTEXITCODE

if ($PullExitCode -ne 0) {
    throw "Failed to pull backend image."
}

# ============================================================
# Container helpers
# ============================================================

function Start-BackendContainer {

    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetImage
    )

    Write-Host "Starting container from:"
    Write-Host $TargetImage

    & $DockerExe run `
        --detach `
        --name $ContainerName `
        --restart unless-stopped `
        --publish "${HostPort}:${ContainerPort}" `
        --volume "${DataRoot}:C:\app\data" `
        --env ENVIRONMENT `
        --env LOG_LEVEL `
        --env LINEAGE_DATABASE_PATH `
        --env SNOWFLAKE_ALLOW_EXTERNAL_BROWSER_AUTH `
        --env CORS_ALLOWED_ORIGINS `
        --env ALLOWED_HOSTS `
        --env FORCE_HTTPS `
        --env ENABLE_API_DOCS `
        --env AUTH_COOKIE_SECURE `
        --env AUTH_COOKIE_SAMESITE `
        --env LINEAGE_ADMIN_API_KEY `
        $TargetImage

    $RunExitCode = $LASTEXITCODE

    if ($RunExitCode -ne 0) {
        throw (
            "Failed to start backend container " +
            "from image '$TargetImage'."
        )
    }
}

function Test-BackendHealth {

    $LiveUrl = (
        "http://127.0.0.1:" +
        "$HostPort/api/v1/health/live"
    )

    $ReadyUrl = (
        "http://127.0.0.1:" +
        "$HostPort/api/v1/health/ready"
    )

    for ($Attempt = 1; $Attempt -le 18; $Attempt++) {

        Write-Host (
            "Backend health attempt " +
            "$Attempt/18"
        )

        $LivePassed = $false
        $ReadyPassed = $false

        try {

            $LiveResponse = Invoke-WebRequest `
                -Uri $LiveUrl `
                -UseBasicParsing `
                -TimeoutSec 10

            if ($LiveResponse.StatusCode -eq 200) {
                $LivePassed = $true
            }
        }
        catch {

            Write-Host "Liveness check not ready yet."
        }

        try {

            $ReadyResponse = Invoke-WebRequest `
                -Uri $ReadyUrl `
                -UseBasicParsing `
                -TimeoutSec 10

            if ($ReadyResponse.StatusCode -eq 200) {
                $ReadyPassed = $true
            }
        }
        catch {

            Write-Host "Readiness check not ready yet."
        }

        Write-Host (
            "Health state: " +
            "live=$LivePassed, " +
            "ready=$ReadyPassed"
        )

        if (
            $LivePassed -and
            $ReadyPassed
        ) {

            return $true
        }

        Start-Sleep -Seconds 5
    }

    return $false
}

function Write-BackendDiagnostics {

    Write-Host ""
    Write-Host "Backend container diagnostics"
    Write-Host "-----------------------------------------"

    & $DockerExe ps `
        -a `
        --filter "name=^/$ContainerName$"

    Write-Host ""
    Write-Host "Last backend logs:"
    Write-Host "-----------------------------------------"

    & $DockerExe logs `
        --tail 200 `
        $ContainerName `
        2>$null
}

# ============================================================
# Preserve currently deployed image
# ============================================================

$PreviousImage = $null

$ExistingContainer = & $DockerExe ps `
    -a `
    --filter "name=^/$ContainerName$" `
    --format "{{.ID}}"

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect existing backend containers."
}

$ExistingContainer = (
    $ExistingContainer |
        Out-String
).Trim()

if (-not [string]::IsNullOrWhiteSpace($ExistingContainer)) {

    $PreviousImage = & $DockerExe inspect `
        --format "{{.Config.Image}}" `
        $ContainerName

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to determine previous backend image."
    }

    $PreviousImage = (
        $PreviousImage |
            Out-String
    ).Trim()

    Write-Host "Previous image:"
    Write-Host $PreviousImage

    Write-Host "Removing existing backend container..."

    & $DockerExe rm `
        --force `
        $ContainerName

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove existing backend container."
    }
}

# ============================================================
# Deploy new image
# ============================================================

try {

    Write-Host ""
    Write-Host "Deploying new backend image..."

    Start-BackendContainer `
        -TargetImage $Image

    Write-Host "Waiting for backend health..."

    if (-not (Test-BackendHealth)) {

        Write-BackendDiagnostics

        throw "Backend health validation failed."
    }

    Write-Host ""
    Write-Host "Backend health checks passed."
}
catch {

    $DeploymentError = $_

    Write-Host ""
    Write-Host "New backend deployment failed."

    Write-BackendDiagnostics

    Write-Host ""
    Write-Host "Removing failed backend container..."

    & $DockerExe rm `
        --force `
        $ContainerName `
        2>$null

    if ($PreviousImage) {

        Write-Host ""
        Write-Host "Rolling back to:"
        Write-Host $PreviousImage

        try {

            Start-BackendContainer `
                -TargetImage $PreviousImage

            Write-Host "Validating rollback..."

            if (-not (Test-BackendHealth)) {

                Write-BackendDiagnostics

                throw (
                    "Rollback container failed " +
                    "health validation."
                )
            }

            Write-Host ""
            Write-Host "Rollback completed successfully."
            Write-Host "DEPLOYMENT_RESULT=ROLLED_BACK"
        }
        catch {

            Write-Host ""
            Write-Host "Rollback failed."

            Write-BackendDiagnostics

            throw (
                "New deployment failed and rollback " +
                "also failed health validation."
            )
        }
    }
    else {

        Write-Host (
            "No previous backend image was available " +
            "for rollback."
        )
    }

    throw $DeploymentError
}

# ============================================================
# Final verification
# ============================================================

$RunningImage = & $DockerExe inspect `
    --format "{{.Config.Image}}" `
    $ContainerName

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect deployed backend container."
}

$RunningImage = (
    $RunningImage |
        Out-String
).Trim()

if ($RunningImage -ne $Image) {
    throw (
        "Deployment image verification failed. " +
        "Expected '$Image', running '$RunningImage'."
    )
}

Write-Host ""
Write-Host "========================================="
Write-Host "Backend deployment completed successfully"
Write-Host "========================================="
Write-Host "Image:"
Write-Host $RunningImage

Write-Host "DEPLOYMENT_RESULT=SUCCESS"

# Remove the secret from the Run Command process environment.
Remove-Item `
    Env:LINEAGE_ADMIN_API_KEY `
    -ErrorAction SilentlyContinue