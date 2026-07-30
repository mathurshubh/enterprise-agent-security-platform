# Engineering Development Workflow

This document defines the standard engineering lifecycle, branch strategy, commit conventions, pre-PR quality gates, and branch maintenance workflows for all contributors to the **Enterprise Agent Security Platform**.

---

## 1. Daily Development Lifecycle

```text
Start Day / Feature
         │
         ▼
Sync Main Branch (`git checkout main && git pull`)
         │
         ▼
Create Feature Branch (`git checkout -b feature/...`)
         │
         ▼
Incremental Development & Tests (`pytest`, `npm run build`)
         │
         ▼
Run Quality Gates (`ruff check`, `pytest`, `npm run build`)
         │
         ▼
Commit & Push (`git commit`, `git push origin ...`)
         │
         ▼
Create Pull Request (PR Template & Review)
         │
         ▼
Merge PR & Post-Merge Cleanup (`git branch -d`)
```

---

## 2. Sync Repository

Always start feature development from an up-to-date `main` branch:

```bash
# Switch to main branch
git checkout main

# Fetch and rebase latest main changes
git pull --rebase origin main
```

---

## 3. Create Feature Branch

Branch names must follow a clean, type-prefixed naming convention reflecting the work scope:

```bash
# Feature branch format: <type>/<short-description>
git checkout -b feature/v0.13-telemetry-emitter
```

### Allowed Branch Prefixes
- `feature/` or `feat/` — New capability or vertical slice implementation
- `refactor/` — Internal refactoring without behavioral or API contract changes
- `fix/` or `bugfix/` — Bug fix or vulnerability remediation
- `docs/` — Documentation updates, ADR additions, or specification changes
- `test/` — Adding or improving test coverage

---

## 4. Incremental Development Best Practices

- **Small, Incremental Changes**: Implement work in focused logical chunks. Avoid oversized, sprawling PRs.
- **Vertical Slice Alignment**: Whenever building frontend surfaces, ensure enabling backend services and REST APIs exist. Avoid synthetic mocks.
- **Code & Docs in Lockstep**: Update architecture documentation, API schemas, and README guides alongside code changes.
- **Preserve Invariants**: Never violate platform security principles (Backend as Source of Truth, LLM as Untrusted Intent Parser, Deterministic Decisioning).

---

## 5. Commit Message Guidelines

Commit messages follow standard Conventional Commits formatting:

```text
<type>(<scope>): <short description>
```

### Commit Types
- `feat(telemetry)`: Implement behavioral telemetry emitter
- `refactor(core)`: Consolidate tool registry models
- `fix(runtime)`: Resolve parameter sanitization edge case
- `docs(adr)`: Update ADR-016 status to Implemented
- `test(detection)`: Add windowed detection rule unit tests

### Example Good Commit Message
```text
feat(telemetry): implement append-only behavioral event store

- Create BehavioralEvent Pydantic domain model
- Implement thread-safe BehavioralEventStore using RLock
- Add GET /api/v1/telemetry/events management API endpoint
- Update /audit console view to render live event records
```

---

## 6. Pre-PR Quality Gates

Before opening a Pull Request, execute the full local quality gate suite:

```bash
# 1. Check Git status and review uncommitted diffs
git status
git diff

# 2. Run backend code quality linter (Ruff)
.venv/bin/ruff check

# 3. Run backend pytest suite (100% pass required)
.venv/bin/python -m pytest

# 4. Verify frontend build & type check
cd frontend && npm run build && cd ..

# 5. Verify documentation matches implementation
```

*Never open a PR with failing tests or lint errors.*

---

## 7. Creating the Pull Request

1. **Push Branch to Remote**:
   ```bash
   git push -u origin feature/v0.13-telemetry-emitter
   ```

2. **Open Pull Request**: Navigate to GitHub and open a PR targeting `main`.
3. **Fill PR Template**: Use the standard PR template (`docs/development/pr-template-phase2.md`). Document:
   - Objective & Vertical Slice scope
   - Files changed
   - Security & threat model impact
   - Verification command results
4. **Request Review**: Assign appropriate reviewers and address feedback.

---

## 8. Post-Merge Cleanup

After your PR is merged into `main`, clean up your local and remote branches to keep your working repository pristine:

```bash
# 1. Switch back to main
git checkout main

# 2. Pull the merged main branch
git pull origin main

# 3. Delete local feature branch
git branch -d feature/v0.13-telemetry-emitter

# 4. Prune remote tracking references
git fetch --prune
```

---

## 9. Starting the Next Feature

With `main` cleanly updated and old feature branches deleted, repeat the workflow for your next PR:

```bash
git checkout main
git pull origin main
git checkout -b feature/v0.13-detection-engine
```
