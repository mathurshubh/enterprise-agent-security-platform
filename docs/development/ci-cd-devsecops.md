# DevSecOps & CI/CD Quality Gates

## 1. Overview

The Enterprise Agent Security Platform enforces an automated **DevSecOps Quality Pipeline** executed via GitHub Actions on every pull request targeting `main` and on direct pushes to `main`.

The pipeline enforces deterministic security and software engineering quality gates prior to code merge, preserving platform invariants: Zero Trust architecture, LLM as an untrusted intent parser, and deterministic server-side security enforcement.

---

## 2. CI/CD Pipeline Architecture

The CI workflow (`.github/workflows/ci.yml`) executes parallel, isolated jobs:

```text
Pull Request / Push to main (permissions: contents: read)
      │
      ├──> Job: Backend Quality (Python 3.13, requirements reproducibility, Ruff linter, Pytest suite)
      │
      ├──> Job: Frontend Quality (Node 20, ESLint, Vite production build)
      │
      ├──> Job: Documentation Quality (Markdownlint)
      │
      ├──> Job: Repository Hygiene (Git diff --check)
      │
      └──> Job: Secret & Vulnerability Scanning (Gitleaks, npm audit)
```

---

## 3. Mandatory Quality Gates

Every pull request must pass all mandatory quality gates before merge eligibility:

| Quality Gate | Tool / Script | Execution Scope | Blocking Criteria |
|:---|:---|:---|:---|
| **Backend Tests** | `pytest` | Full backend test suite | 100% test pass rate |
| **Backend Linting** | `ruff check` | Python models, services, APIs, tests | 0 lint errors |
| **Frontend Linting** | `eslint` | React/TypeScript UI codebase | 0 ESLint errors |
| **Frontend Build** | `tsc -b && vite build` | Production UI bundle | 0 TypeScript/Vite build errors |
| **Documentation** | `markdownlint-cli` | Project Markdown documentation | 0 Markdownlint violations |
| **Repository Hygiene** | `git diff --check` | Git patch and formatting | 0 whitespace or patch errors |
| **Secret Scanning** | `gitleaks` | Git commit history & PR diffs | 0 exposed secrets or credentials |
| **Dependency Reproducibility** | `scripts/compile-requirements.sh --check` (Python 3.13) | `requirements.in` + committed pins → `requirements.txt` | 0 differences from the committed `requirements.txt`; never upgrades dependencies |
| **Dependency Audit** | `npm audit` / `pip-audit` | `frontend/package-lock.json` / `requirements.txt` | npm: 0 high/critical findings; pip-audit: 0 known vulnerabilities |

---

## 4. Local Reproduction Commands

Developers must run quality validation commands locally prior to opening or updating a pull request:

### Backend Quality Gates
```bash
# Verify requirements.txt is reproducible from requirements.in
scripts/compile-requirements.sh --check

# Run Python linter
.venv/bin/ruff check

# Run complete backend test suite
.venv/bin/python -m pytest
```

### Frontend Quality Gates
```bash
cd frontend

# Run ESLint
npm run lint

# Run Vite build
npm run build
```

### Documentation & Hygiene Quality Gates
```bash
# Run Markdown lint
npm run lint:md

# Run Git whitespace check
git diff --check
```

---

## 5. Workflow Security Model

The CI/CD pipeline conforms to strict security and supply-chain guarantees:

- **Least Privilege Permissions:** Top-level and job-level permissions are explicitly declared as `permissions: contents: read`.
- **Pull Request Trust Boundary:** Untrusted PR validation runs strictly under the unprivileged `pull_request` trigger (never `pull_request_target`), isolating workflow execution from repository secrets.
- **Zero Secret Requirement:** The quality pipeline operates entirely without requiring production credentials or third-party API keys.
- **Dependency Locking:** Developers, CI and `pip-audit` all use the same locked dependency definitions: `requirements.txt` for Python, generated from `requirements.in` with a pinned pip-tools toolchain, and `package-lock.json` for Node.js. CI fails if `requirements.txt` is not reproducible from `requirements.in`.
- **Automated Dependency Updates:** GitHub Dependabot (`.github/dependabot.yml`) scans Python (`pip`) and Frontend (`npm`) ecosystems weekly for security advisories.
