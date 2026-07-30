# Phase 2 Pull Request Template

Every PR in Phase 2 must follow this standard format before review and merge.

---

## PR Metadata

- **PR Number**: PR #
- **Title**: `type(scope): concise description`
- **Target Release**: `v0.13.0`
- **Primary ADR References**: ADR-0XX

---

## 1. Objective & Rationale
Briefly state the goal of this PR and why it exists in the Phase 2 sequence.

---

## 2. Vertical Slice Summary
Identify which components of the full stack are delivered in this PR:
- [ ] **Backend Service**:
- [ ] **REST API Endpoint**:
- [ ] **Frontend Page / Surface**:
- [ ] **TypeScript / Pydantic Data Models**:
- [ ] **Automated Tests**:
- [ ] **Documentation**:

---

## 3. Files Modified & Created
List all modified and newly created files:
- `[NEW] path/to/file.py`
- `[MODIFY] path/to/file.tsx`

---

## 4. Security & Threat Model Review
- **Trust Boundary Impact**:
- **Authorization & Determinism**:
- **Auditability & Logging**:
- **Zero Trust Compliance**:

---

## 5. Automated Validation & Test Evidence
Report the execution results of all required verification commands:
```bash
# Backend pytest
.venv/bin/python -m pytest

# Backend ruff check
.venv/bin/ruff check

# Frontend build & tests
cd frontend && npm run build
cd frontend && npm run test
```

---

## 6. Documentation Checklist
- [ ] Target ADR headers updated to *Implemented* (if applicable)
- [ ] `docs/api/management-api.md` updated with new endpoints (if applicable)
- [ ] `README.md` or architecture guides updated

---

## 7. Definition of Done
- [ ] Code meets all Python 3.13+ and React 19/TypeScript standards
- [ ] 100% test pass rate across backend pytest and frontend Vitest
- [ ] Zero ruff lint violations
- [ ] Frontend builds cleanly with zero TypeScript errors
- [ ] Zero synthetic mocks in production path
- [ ] Architecture Review Board principles satisfied
