# Local Development Setup Guide

This document provides a step-by-step guide for configuring, building, running, and testing the **Enterprise Agent Security Platform** in a local development environment.

---

## 1. Environment Requirements

Ensure your local workstation meets the following core tool requirements:

| Tool | Version / Requirement | Purpose |
|---|---|---|
| **Python** | `3.13.0+` | Core backend runtime and domain services |
| **Node.js** | `v20.0.0+` (v22 recommended) | Frontend build toolchain and React environment |
| **npm** | `v10.0.0+` | Package manager for frontend dependencies |
| **Git** | `v2.40.0+` | Version control system |
| **Ollama** *(Optional)* | `v0.1.30+` | Local LLM inference provider (`ollama serve`) |

---

## 2. Clone Repository

Clone the project repository to your local workspace:

```bash
git clone https://github.com/mathurshubh/enterprise-agent-security-platform.git
cd enterprise-agent-security-platform
```

---

## 3. Create Python Virtual Environment

Create and activate a isolated Python virtual environment in the project root:

```bash
# Create virtual environment named .venv
python3 -m venv .venv

# Activate the virtual environment
# macOS / Linux:
source .venv/bin/activate

# Windows (PowerShell):
# .venv\Scripts\Activate.ps1
```

---

## 4. Install Backend Dependencies

With `.venv` activated, install the required Python packages:

```bash
# Upgrade pip and build tools
.venv/bin/python -m pip install --upgrade pip setuptools wheel

# Install dependencies from requirements.txt
.venv/bin/python -m pip install -r requirements.txt
```

---

## 5. Install Frontend Dependencies

Navigate to the `frontend/` directory and install npm packages:

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Return to repository root
cd ..
```

---

## 6. Run Backend Service

The platform fails closed when the JWT signing key is not provisioned: there is no
development fallback, and the application will not start without `JWT_SECRET_KEY`.
Export an explicit secret of at least 32 bytes first.

> [!NOTE]
> `.env` files are **not** loaded by the application. The variable must be exported
> in the shell that starts the server.

```bash
# Generate and export a signing key for this shell session
export JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

# Start backend server using python -m uvicorn (defaults to http://127.0.0.1:8000)
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Verify backend health by visiting:
- Healthcheck Endpoint: `http://127.0.0.1:8000/health`
- OpenAPI Documentation: `http://127.0.0.1:8000/docs`

---

## 7. Run Frontend Console

The backend requires a JWT on every `/api` route, and the browser console holds no credentials. For local development, the Vite development proxy attaches an `Authorization` header to proxied API requests from the `EASP_DEV_API_TOKEN` environment variable.

> [!IMPORTANT]
> This is a local development convenience only. It does not provide production authentication: production console authentication requires an identity provider and is not implemented. The mechanism is active only for `npm run dev`, never for `vite build` or `vite preview`.

```text
Browser
  │  unauthenticated HTTP request
  ▼
Vite dev server (Node process) ── holds EASP_DEV_API_TOKEN
  │  adds Authorization only for trusted local-origin requests
  ▼
FastAPI ── JWT authentication, unchanged
```

- `EASP_DEV_API_TOKEN` is intentionally **not** a `VITE_*` variable. Vite compiles `VITE_*` variables into browser code, so never place the token in one.
- The token is held only by the Vite Node process. The browser never receives or stores it, and it is not included in the production bundle.
- Because the proxy attaches the token automatically, it would otherwise behave like a cookie that any web page open in your browser could use. To prevent that cross-site request forgery, the proxy attaches it only when `Sec-Fetch-Site` is `same-origin`, `none` or absent, and `Origin`, when present, matches the development server's own origin. Other requests are forwarded without the token, and the backend returns `401`.
- Non-browser tools on your machine that send neither header, such as `curl`, also receive the token.
- With a token set, the development server refuses to start if it is explicitly exposed beyond loopback (for example `npm run dev -- --host`) or configured with `server.allowedHosts: true`, because anyone reaching the proxy would act as the token's principal.

In a separate terminal, export the same `JWT_SECRET_KEY` the backend is running with (section 6), then generate a short-lived `ANALYST` token from the repository root without printing it:

```bash
export EASP_DEV_API_TOKEN="$(.venv/bin/python -c '
from app.auth.jwt_service import JWTService
from app.config.settings import get_jwt_secret_key
from app.models.jwt_claims import Role

print(JWTService(secret_key=get_jwt_secret_key()).create_token(
    subject="local-console-analyst",
    agent_id="local-console",
    role=Role.ANALYST,
))
')"
```

Start the Vite development server from the same terminal, so it inherits the variable:

```bash
cd frontend
npm run dev
```

The console will be accessible at `http://127.0.0.1:3000`. API requests to `/api/*` are proxied to the backend at `http://127.0.0.1:8000` with the token attached.

- Use an `ANALYST` token for the console, not `ADMIN`, so it runs with the least-privileged management role.
- Tokens expire after 60 minutes. When the console reports `401`, generate a new token and restart `npm run dev`.
- Without `EASP_DEV_API_TOKEN`, the proxy forwards requests unchanged and the backend returns `401`.
- The token is a credential. Do not commit it or paste it into shared logs.

---

## 8. Run Automated Tests

Always execute backend tests using `.venv/bin/python -m pytest` from the root directory.

```bash
# Run complete test suite
.venv/bin/python -m pytest

# Run targeted test file
.venv/bin/python -m pytest tests/services/test_policy_engine.py

# Run targeted test function
.venv/bin/python -m pytest tests/api/test_management_api.py -k "test_get_agents"

# Run tests in verbose mode with stdout enabled
.venv/bin/python -m pytest -v -s
```

*Note: Do not assume `pytest` is globally installed. Always use `.venv/bin/python -m pytest`.*

---

## 9. Code Quality & Linting

Run Ruff to inspect Python code quality and formatting:

```bash
# Inspect code quality across backend codebase
.venv/bin/ruff check

# Automatically fix safe lint violations
.venv/bin/ruff check --fix
```

---

## 10. Documentation Quality & Linting

The repository uses `markdownlint` to enforce consistent documentation standards.

Install the repository tooling from the project root:

```bash
# Install root-level developer tooling dependencies
npm install
```

To lint documentation files locally:

```bash
# Run the Markdown linter across the repository
npm run lint:md
```

To automatically fix simple mechanical Markdown issues:

```bash
# Run markdownlint with the fix option
npm run lint:md:fix
```

---

## 11. Frontend Production Build

Validate TypeScript types and compile the Vite production bundle:

```bash
cd frontend

# Execute TypeScript type check and production build
npm run build
```

---

## 12. Recommended Local Environment Verification Sequence

Before starting any feature work, run the complete verification sequence to ensure your local environment is 100% operational:

```bash
# 1. Verify working directory is clean
git status

# 2. Run backend test suite
.venv/bin/python -m pytest

# 3. Run backend code quality linter
.venv/bin/ruff check

# 4. Run documentation linter
npm run lint:md

# 5. Verify frontend build
cd frontend && npm run build && cd ..
```

If all 5 steps succeed, your local development environment is ready.
