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

`requirements.txt` is the only Python dependency file developers and CI install, and the file `pip-audit` scans. It is **generated**: never edit it by hand.

### Managing Python Dependencies

| File | Maintained by | Contents |
|---|---|---|
| `requirements.in` | Humans | Direct dependencies only, grouped into runtime and development/test |
| `requirements.txt` | `scripts/compile-requirements.sh` | The complete pinned dependency graph |
| `requirements-tools.txt` | Humans | The pinned pip-tools toolchain used to generate `requirements.txt`. Not an application dependency |

The script installs the toolchain into a separate `.venv-tools/` virtualenv.

**Lock policy**

`requirements.txt` is a committed lock, not a fresh resolution. pip-compile reuses the pins already in `requirements.txt` and only resolves what the change requires:

| Operation | Command | Effect on existing pins |
|---|---|---|
| Normal compile | `scripts/compile-requirements.sh` | Preserved. Only intentional `requirements.in` changes are resolved |
| Intentional upgrade | `scripts/compile-requirements.sh --upgrade-package <package>` | Only that package, and the transitive changes it requires, are re-resolved |
| CI verification | `scripts/compile-requirements.sh --check` | Never changed. Verifies the committed `requirements.txt` is reproducible and never upgrades dependencies |

Dependency lock generation is standardized on **Python 3.13**, the version CI uses. Do not regenerate `requirements.txt` with another Python version: the script refuses to run with one.

**Adding a dependency**

1. Add the direct dependency to the appropriate section of `requirements.in`.
2. Regenerate the lockfile:

   ```bash
   scripts/compile-requirements.sh
   ```

3. Review the `requirements.txt` diff, including any new transitive dependencies.
4. Install and validate:

   ```bash
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -m pytest
   ```

5. Commit `requirements.in` and `requirements.txt` together.

**Updating a dependency**

Upgrades are intentional operations. Upgrade one package at a time and review the transitive changes it brings:

```bash
scripts/compile-requirements.sh --upgrade-package <package>
```

Then validate and commit as above. Dependabot follows the same model: it updates `requirements.txt` from `requirements.in` using the compile options in `pyproject.toml`.

**Verifying the lockfile**

CI runs this check. It recompiles copies in a temporary directory, with the committed `requirements.txt` supplying the existing pins, and fails if the result differs from the committed file. It never modifies the working tree:

```bash
scripts/compile-requirements.sh --check
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

## 6. Start the Development Environment

One command starts the backend and the console together and handles local development
authentication:

```bash
scripts/dev-start.sh
```

It generates an **ephemeral** JWT signing secret, mints one development token from that
exact secret, starts the backend with the secret and the console with the token, and
verifies the pair before handing over. You never generate, copy or export credentials
yourself. Both values are passed through the process environment rather than command-line
arguments, so they are not exposed in the process argument list, and neither is written to
disk.

```text
scripts/dev-start.sh
  ├── ephemeral JWT_SECRET_KEY ─────────▶ FastAPI      (verifies with this secret)
  └── ANALYST token from that secret ───▶ Vite proxy   (sends it to FastAPI)
```

- **Console:** `http://localhost:3000`
- **Backend:** `http://127.0.0.1:8000` (health at `/health`, API docs at `/docs`)
- **Stop:** press `Ctrl+C`. Both processes stop, and the secret and token cease to exist,
  so the token cannot be replayed against a backend started later.

Before starting, the script checks the virtual environment, the Python version, backend
and frontend dependencies and the ports, and explains what to fix when a check fails. It
then confirms that an authenticated request to `/api/v1/agents` returns `200` and that an
unauthenticated one still returns `401`. Neither the secret nor the token is ever printed.

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Ports to bind. The console is pointed at the backend the script started |
| `EASP_DEV_TOKEN_ROLE` | `ANALYST` | Set to `ADMIN` only when testing admin or runtime-execution endpoints. No other role is accepted |
| `EASP_DEV_TOKEN_LIFETIME_MINUTES` | `1440` | Token lifetime, bounded by the ephemeral secret |
| `EASP_DEV_RELOAD` | unset | `1` runs the backend with `--reload` |

`scripts/dev-start.sh --dry-run` runs the checks and credential setup without starting
anything.

> [!IMPORTANT]
> Never commit a development secret or token, and never put either in a `.env` file. The
> script keeps both in process environment variables only. The application does not load
> `.env` files.

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

### Starting the processes separately — advanced troubleshooting only

> [!WARNING]
> `scripts/dev-start.sh` is the supported workflow. Starting the processes by hand
> requires transferring the same signing secret between two processes yourself, which is
> exactly the coordination this script exists to remove. Use it only when troubleshooting
> the environment itself.

**The token must be minted from the same secret the backend runs with.** A mismatch is
the usual cause of a `401` reading `Invalid token: Signature verification failed`, while a
missing token reads `Missing authorization credentials`.

In one terminal, export a signing key and start the backend:

```bash
export JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal, export **the same** `JWT_SECRET_KEY`, then mint a token from it
without printing it:

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

Start the Vite development server from that second terminal, so it inherits the variable:

```bash
cd frontend
npm run dev
```

The console will be accessible at `http://127.0.0.1:3000`. API requests to `/api/*` are proxied to the backend at `http://127.0.0.1:8000` with the token attached.

- Use an `ANALYST` token for the console, not `ADMIN`, so it runs with the least-privileged management role.
- A hand-minted token expires after 60 minutes by default. When the console reports `401`, mint a new one and restart `npm run dev`.
- `EASP_DEV_API_TARGET` points the proxy at a backend on another port; it must stay on this machine, because the proxy attaches credentials to everything it forwards.
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
