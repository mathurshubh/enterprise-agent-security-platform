# Phase 2 Architecture Baseline & Governance Specification (v0.13.0)

---

## 1. Purpose

This document formally establishes the **Phase 2 Architecture Baseline & Governance Specification** for version `v0.13.0` of the Enterprise Agent Security Platform.

> [!NOTE]
> Historical planning document retained for architectural history.

Following extensive architectural design reviews, threat modeling, data contract definitions, and capability roadmap planning, the Phase 2 Architecture Baseline is approved and becomes the governing architectural reference for all subsequent implementation work. This baseline specification serves as the authoritative standard against which all future implementation pull requests, code changes, and architectural proposals will be evaluated.

Implementation officially begins in **PR #69**. Repository-wide architecture planning concludes with PR #68; future code reviews will focus exclusively on individual vertical slice implementation conformance.

---

## 2. Current Status & Canonical PR Roadmap

The project repository reflects the following canonical development history:

### Planning Phase
- **PR #66**: Phase 2 Implementation Planning *(Merged)*
- **PR #67**: Development Workflow & Local Development Documentation *(Merged)*
- **PR #68**: Architecture Baseline & Governance *(Merged — Governance Approved)*

### Foundation Phase
- **PR #69**: Runtime Foundation & Tool Registry Consolidation *(Implementation Officially Begins Here)*
- **PR #70**: Enterprise Frontend Foundation (TanStack Query, Error Boundaries, Lazy Loading, Flags)

### Capability Delivery
- **PR #71**: Behavioral Telemetry Pipeline & Event Store *(Vertical Slice 1)*
- **PR #72**: Session-Scoped Detection Engine & Behavioral Findings *(Vertical Slice 2)*
- **PR #73**: Dynamic Behavioral Risk Assessment *(Vertical Slice 3)*
- **PR #74**: Behavioral Enforcement Engine & Pending Approvals *(Vertical Slice 4)*
- **PR #75**: Session Timeline & Forensic Replay *(Vertical Slice 5)*

### Release Validation
- **PR #76**: Phase 2 Integration Verification & `v0.13.0` Release

---

## 3. Approved Capability Pipeline

The platform capability pipeline operates strictly in the following sequence:

```text
┌─────────────────┐
│ Runtime Engine  │ (Executes tool invocations)
└────────┬────────┘
         │ (Emits raw, immutable telemetry facts)
         ▼
┌─────────────────┐
│ Behavioral      │ (Append-only event store: BehavioralEventStore)
│ Event Store     │
└────────┬────────┘
         │ (Windowed evaluation of event streams)
         ▼
┌─────────────────┐
│ Detection       │ (Evaluates rules; emits Findings to FindingRepository)
│ Engine          │
└────────┬────────┘
         │ (Calculates multi-factor risk scores)
         ▼
┌─────────────────┐
│ Behavioral      │ (Computes dynamic RiskState; emits to RiskRepository)
│ Risk Engine     │
└────────┬────────┘
         │ (Evaluates risk thresholds & policy actions)
         ▼
┌─────────────────┐
│ Enforcement     │ (Enforces ALLOW / DENY / HOLD_SESSION; emits PendingApprovals)
│ Engine          │
└────────┬────────┘
         │ (Human-in-the-loop analyst intervention)
         ▼
┌─────────────────┐
│ Approval        │ (Audited Release / Reject actions update session state)
│ Workflow        │
└────────┬────────┘
         │ (Step-by-step forensic inspection)
         ▼
┌─────────────────┐
│ Investigation   │ (Timeline replay & evidence chain traversal: /sessions/:id)
│ & Operations    │
└─────────────────┘
```

---

## 4. Architectural Invariants

The following rules are non-negotiable and must never be violated in any implementation PR:

1. **Behavioral Event Store is Append-Only**: The `BehavioralEventStore` records raw, immutable runtime facts (`ToolInvocationStarted`, `PolicyEvaluated`, `ToolExecutionCompleted`). It **never** stores derived entities (`Findings`, `RiskAssessments`, `EnforcementDecisions`, `PendingApprovals`).
2. **Findings are Derived State**: `Finding` objects are produced exclusively by the `DetectionEngineService` evaluating event streams. They are never generated directly by runtime tools or LLM prompts.
3. **Risk Score Calculation is Deterministic**: `RiskState` scores (`0–100`) and risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) are calculated deterministically by `RiskEngineService` using multi-factor threat severity algorithms.
4. **Enforcement Consumes Risk State**: The `EnforcementEngineService` evaluates policy actions (`ALLOW`, `DENY`, `HOLD_SESSION`, `REQUIRE_APPROVAL`) based on deterministic risk thresholds and policy rules.
5. **LLM is an Untrusted Intent Parser**: The LLM parses natural language into candidate `ToolInvocation` objects. Zero security logic, policy evaluation, or risk assessment occurs inside LLM prompts or client-side code ([ADR-002](../adr/ADR-002-llm-untrusted-intent-parser.md)).
6. **No Security Decisions in Frontend**: The Enterprise Security Console renders backend state and invokes REST endpoints. Frontend components never perform authorization or policy decisioning.

---

## 5. Trust Boundaries

```text
  [ Untrusted User / LLM Prompt ]
                 │
                 ▼
════════════════════════════════════════════════════════════ (Trust Boundary 1: API Gateway)
  [ FastAPI Management / Runtime API ]
                 │
                 ▼
════════════════════════════════════════════════════════════ (Trust Boundary 2: Deterministic Engine)
  [ Policy Engine / Detection Engine / Risk Engine / Enforcement Engine ]
                 │
                 ▼
════════════════════════════════════════════════════════════ (Trust Boundary 3: Tool Sandbox)
  [ Environment / Operating System Capability Execution ]
```

---

## 6. Security Principles

- **Zero Trust**: Capabilities denied by default unless permitted by explicit policy. Unsafe parameter patterns trigger immediate session holding (`HOLD_SESSION`).
- **Least Privilege**: Agents are granted minimum required capabilities for specific operational contexts.
- **Deterministic Authorization**: All authorization decisions remain 100% deterministic and outside the LLM ([ADR-004](../adr/ADR-004-deterministic-security-pipeline.md)).
- **Defense in Depth**: Multi-layer security pipeline combining static tool policy, dynamic windowed detection, multi-factor risk scoring, and human-in-the-loop holding queues.
- **Full Auditability**: Every execution attempt, parameter payload, rule firing, risk score change, and analyst intervention is logged to append-only telemetry stores.

---

## 7. Repository Structure

```text
enterprise-agent-security-platform/
├── app/                        # FastAPI Backend & Security Services
│   ├── api/                    # API Routers (management.py, runtime.py)
│   ├── auth/                   # Authentication & Authorization
│   ├── detection/              # Threat Detection Rules
│   ├── models/                 # Pydantic Domain Models
│   ├── policy/                 # Deterministic Policy Engine
│   ├── registry/               # Tool & Scenario Registries
│   ├── services/               # Core Security & Domain Services
│   └── tools/                  # Standard Tool Implementations
├── frontend/                   # React 19 / Vite Enterprise Console
│   ├── src/
│   │   ├── api/                # Axios Management API Client
│   │   ├── components/         # UI Primitives & Common Widgets
│   │   ├── config/             # Navigation & Feature Flags Config
│   │   ├── hooks/              # Custom Data Fetching Hooks
│   │   ├── layouts/            # AppLayout Component
│   │   ├── pages/              # 9 Canonical Console Page Surfaces
│   │   └── types/              # TypeScript Type Definitions
├── docs/                       # Architecture, ADRs, & Specs
│   ├── adr/                    # Architecture Decision Records (ADR-001..022)
│   ├── architecture/           # Architecture Specifications & Freeze
│   ├── development/            # Engineering Workflows & Checklists
│   └── releases/               # Version Release Notes
└── tests/                      # Pytest Automated Test Suite
```

---

## 8. Implementation Rules

1. **Vertical Slice Requirement**: Every frontend capability must be backed by real, operational backend services and REST APIs. Mocks and synthetic state are forbidden.
2. **Backend Before Frontend**: Domain services and Management API endpoints must exist and be tested before frontend components consume them.
3. **Lockstep Documentation**: Code and documentation must be updated in the same PR.
4. **Mandatory Quality Gates**:
   - Backend: `.venv/bin/python -m pytest` (100% pass) and `.venv/bin/ruff check` (0 violations)
   - Frontend: `npm run build` (0 TypeScript errors)
5. **ADR for Architectural Changes**: Material architectural alterations require a formal ADR and must explicitly supersede this baseline specification.

---

## 9. Non-Goals (Explicitly Out of Scope for v0.13.0)

- **LLM-Based Triage Agents**: Security decisions will not be delegated to LLMs.
- **Production PostgreSQL Infrastructure Deployment**: Relational database migration belongs to Phase 4. Thread-safe in-memory stores (`RLock`) govern Phase 2.
- **OpenTelemetry / Prometheus Collector Pipelines**: Standardized OTel collector exports belong to Phase 4.
- **Real-Time SSE Alert Streaming**: Polling via TanStack Query governs Phase 2; SSE streaming belongs to Phase 4.

---

## 10. Future Extensibility Points

- **Phase 3 (v0.14.0)**: Multi-panel forensic investigation workspace (`/sessions/:id`), SOC case management (`/cases`), and multi-agent delegation topology (`/agents/topology`).
- **Phase 4 (v1.0.0)**: Relational DB persistence (`PostgreSQL`), distributed event messaging (`Redis`), OpenTelemetry trace exporters, and Prometheus metrics scraping.

---

## 11. Governance Lifecycle

- **Planning Concludes with PR #68**: Repository-wide architectural planning officially concludes with PR #68.
- **Implementation Begins with PR #69**: Active implementation officially begins in PR #69 (`Runtime Foundation & Tool Registry Consolidation`).
- **Repository-Wide Architecture Reviews Complete**: Repository-wide architecture reviews are complete. Future pull request reviews will focus exclusively on implementation conformance.
- **Conformance Requirement**: The Phase 2 Architecture Baseline is approved and becomes the governing architectural reference for all subsequent implementation work.
- **ADR Requirement for Material Changes**: Material architectural changes require a new ADR that explicitly supersedes this baseline.
