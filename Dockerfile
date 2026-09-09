# escape=`

# ============================================================
# Stage 1 - CPython base
# ============================================================

FROM mcr.microsoft.com/windows/servercore:ltsc2025 AS python-base

SHELL ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

ARG PYTHON_VERSION=3.13.15
ARG PYTHON_INSTALLER_SHA256=edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403
ENV PYTHON_HOME="C:\Python313"

# ------------------------------------------------------------
# Install official CPython with pip
# ------------------------------------------------------------

RUN $installerUrl = `
        'https://www.python.org/ftp/python/{0}/python-{0}-amd64.exe' `
        -f $env:PYTHON_VERSION; `
    Invoke-WebRequest `
        -UseBasicParsing `
        -Uri $installerUrl `
        -OutFile C:\python-installer.exe; `
    $actualHash = (Get-FileHash C:\python-installer.exe -Algorithm SHA256).Hash; `
    if ($actualHash -ne $env:PYTHON_INSTALLER_SHA256) { `
        throw ('Python installer SHA-256 mismatch: {0}' -f $actualHash) `
    }; `
    $process = Start-Process `
        -FilePath C:\python-installer.exe `
        -ArgumentList `
            '/quiet', `
            'InstallAllUsers=1', `
            'TargetDir=C:\Python313', `
            'Include_launcher=0', `
            'Include_pip=1', `
            'Include_test=0', `
            'PrependPath=0', `
            'Shortcuts=0' `
        -Wait `
        -PassThru; `
    if (($process.ExitCode -ne 0) -and ($process.ExitCode -ne 3010)) { `
        throw ( `
            'Python installation failed with exit code {0}' `
            -f $process.ExitCode `
        ) `
    }; `
    Remove-Item C:\python-installer.exe -Force

RUN & (Join-Path $env:PYTHON_HOME 'python.exe') --version; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; `
    & (Join-Path $env:PYTHON_HOME 'python.exe') -m pip --version; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }


# ============================================================
# Stage 2 - Backend dependencies
# ============================================================

FROM python-base AS builder

WORKDIR C:\app

RUN & (Join-Path $env:PYTHON_HOME 'python.exe') -m venv C:\app\.venv; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ------------------------------------------------------------
# Install project dependencies
# ------------------------------------------------------------

COPY requirements.txt constraints.txt ./

RUN & 'C:\app\.venv\Scripts\python.exe' `
        -m pip install `
        --disable-pip-version-check `
        --no-cache-dir `
        --requirement requirements.txt; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ------------------------------------------------------------
# Verify Python dependencies
# ------------------------------------------------------------

RUN & 'C:\app\.venv\Scripts\python.exe' `
        -c 'import fastapi, uvicorn, httpx'; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; `
    Write-Host 'Python dependencies verified'


# ============================================================
# Stage 3 - Runtime
# ============================================================

FROM python-base AS runtime

SHELL ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

WORKDIR C:\app

ENV PYTHONDONTWRITEBYTECODE="1"
ENV PYTHONUNBUFFERED="1"
ENV PYTHONUTF8="1"

# ------------------------------------------------------------
# Install MSOLAP
# ------------------------------------------------------------

ARG MSOLAP_MSI_URL

RUN if ([string]::IsNullOrWhiteSpace($env:MSOLAP_MSI_URL)) { `
        throw 'MSOLAP_MSI_URL build argument is required.' `
    }; `
    Write-Host 'Downloading MSOLAP...'; `
    Invoke-WebRequest `
        -UseBasicParsing `
        -Uri $env:MSOLAP_MSI_URL `
        -OutFile C:\msolap.msi; `
    Write-Host 'Installing MSOLAP...'; `
    $process = Start-Process `
        -FilePath 'msiexec.exe' `
        -ArgumentList '/i', 'C:\msolap.msi', '/qn', '/norestart' `
        -Wait `
        -PassThru; `
    Write-Host "MSOLAP installer exit code: $($process.ExitCode)"; `
    if (($process.ExitCode -ne 0) -and ($process.ExitCode -ne 3010)) { `
        throw "MSOLAP installation failed with exit code $($process.ExitCode)" `
    }; `
    Remove-Item C:\msolap.msi -Force

# ------------------------------------------------------------
# Copy virtual environment from builder
# ------------------------------------------------------------

COPY --from=builder C:\app\.venv C:\app\.venv

# ------------------------------------------------------------
# Copy backend
# ------------------------------------------------------------

COPY app .\app

# ------------------------------------------------------------
# Verify Python
# ------------------------------------------------------------

RUN & 'C:\app\.venv\Scripts\python.exe' --version; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ------------------------------------------------------------
# Verify backend dependencies
# ------------------------------------------------------------

RUN & 'C:\app\.venv\Scripts\python.exe' `
        -c 'import fastapi, uvicorn, httpx, win32com.client, pythoncom'; `
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; `
    Write-Host 'Runtime dependencies OK'

# ------------------------------------------------------------
# Verify ADODB COM
# ------------------------------------------------------------

RUN $connection = New-Object -ComObject ADODB.Connection; `
    if ($null -eq $connection) { `
        throw 'Unable to create ADODB.Connection COM object' `
    }; `
    Write-Host 'ADODB COM OK'

# ------------------------------------------------------------
# Verify MSOLAP registration
# ------------------------------------------------------------

RUN $providers = @( `
        Get-ChildItem `
            'HKLM:\SOFTWARE\Classes' `
            -ErrorAction SilentlyContinue `
        | Where-Object { $_.PSChildName -like 'MSOLAP*' } `
    ); `
    if ($providers.Count -eq 0) { `
        throw 'MSOLAP provider was not registered correctly.' `
    }; `
    Write-Host 'MSOLAP registration verified'; `
    $providers | Select-Object -ExpandProperty PSChildName

EXPOSE 8000

CMD ["C:\\app\\.venv\\Scripts\\python.exe", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
