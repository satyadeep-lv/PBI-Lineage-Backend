# PBI Lineage Backend - Setup Guide

The supported project toolchain is:

- Official 64-bit CPython 3.13, with 3.13.15 used by CI and containers.
- Python's standard `venv` module for the project environment.
- pip requirements files with a committed constraints file.
- FastAPI and Uvicorn for the API runtime.

For the complete new-machine procedure, provider prerequisites, and production
notes, follow [INSTALLATION.md](INSTALLATION.md). This file is the short setup
reference for an existing development machine.

## Create The Environment

From the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

On Linux or macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

The dependency files have separate responsibilities:

| File | Purpose |
| --- | --- |
| `requirements.txt` | Direct production dependencies |
| `requirements-dev.txt` | Production dependencies plus test and lint tools |
| `constraints.txt` | Fully resolved versions shared by local setup, CI, and containers |
| `pyproject.toml` | Ruff and pytest configuration only |

Do not copy `.venv` between machines. Recreate it from the committed files.

## Configure The Application

Create the local environment file and review every value before exposing the
API outside the local machine:

```powershell
Copy-Item .env.example .env
```

Never commit `.env`, access tokens, client secrets, passwords, or private keys.

## Validate The Installation

```powershell
python --version
python -m pip check
ruff check .
ruff format --check .
python -m pytest
```

Python should report `3.13.x`, pip should report no broken requirements, and all
quality checks should pass.

## Start The API

```powershell
fastapi dev app/main.py
```

Then open:

```text
Swagger:   http://127.0.0.1:8000/docs
Health:    http://127.0.0.1:8000/api/v1/health
Readiness: http://127.0.0.1:8000/api/v1/health/ready
```

Keep one API worker until Microsoft sessions, Snowflake sessions, cache, and
scan coordination are moved from process-local state to shared infrastructure.

## Windows Container Builds

The production Dockerfile installs the verified official CPython installer,
creates `C:\app\.venv`, and installs `requirements.txt`. It uses Windows Server
Core LTSC 2025 because XMLA requires Windows COM, ADODB, and MSOLAP.

Use these targets for focused build validation:

```powershell
docker build --target python-base -t pbi-lineage-python-base:test .
docker build --target builder -t pbi-lineage-builder:test .
```

The complete runtime image additionally requires the official x64 MSOLAP MSI
URL through the `MSOLAP_MSI_URL` build argument. See `INSTALLATION.md` and the
deployment runbooks under `REF_DOC` before building or deploying that image.
