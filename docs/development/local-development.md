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

Start the FastAPI Management API and Runtime Security engine locally:

```bash
# Start backend server using python -m uvicorn (defaults to http://127.0.0.1:8000)
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Verify backend health by visiting:
- Healthcheck Endpoint: `http://127.0.0.1:8000/health`
- OpenAPI Documentation: `http://127.0.0.1:8000/docs`

---

## 7. Run Frontend Console

In a separate terminal, start the Vite development server for the Enterprise Security Console:

```bash
cd frontend
npm run dev
```

The console will be accessible at `http://127.0.0.1:3000`. API requests to `/api/*` are automatically proxied to the backend at `http://127.0.0.1:8000`.

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
