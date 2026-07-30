# Phase 2 Master Implementation Plan
## Enterprise Agent Security Platform (v0.13.0)

## Executive Overview

This document serves as the canonical master implementation guide for **Phase 2 (v0.13.0)** of the Enterprise Agent Security Platform.

Phase 2 transforms the platform from an application shell into an operational **Behavioral Intelligence & Security Operations Platform**. To guarantee architectural integrity, Phase 2 strictly enforces the **Vertical Slice Principle**: every frontend capability must be backed by real, deterministic backend services and management APIs. Synthetic mocks, UI-centric state, and placeholder workflows are explicitly prohibited.

---

## 1. Implementation Principles & Architectural Constraints

1. **Backend is the Source of Truth**: All security evaluations, telemetry records, detection rule firings, risk scores, and enforcement actions originate from deterministic Python backend services.
2. **LLM as Untrusted Intent Parser**: The LLM converts natural language into structured `ToolInvocation` objects. No security logic, policy evaluation, or risk assessment occurs inside LLM prompts or client-side code.
3. **Deterministic Authorization**: All authorization decisions remain 100% deterministic and outside the LLM.
4. **Zero Trust & Least Privilege**: Access to tools and capabilities is denied by default unless permitted by explicit policy. Unsafe parameter patterns trigger immediate session holding (`HOLD_SESSION`).
5. **Append-Only Behavioral Telemetry**: The `BehavioralEventStore` is append-only and records immutable runtime facts (`ToolInvocationStarted`, `PolicyEvaluated`, `ToolExecutionCompleted`). It **never** stores derived entities (`Findings`, `RiskAssessments`, `EnforcementDecisions`, `Approvals`).
6. **No Frontend Security Logic**: Frontend components render backend state and invoke REST endpoints. No authorization or security decisioning occurs in React components.
7. **Small Reviewable PRs**: Implementation proceeds incrementally across 8 reviewable PRs (PR #66 to PR #73).
8. **Documentation Evolves with Implementation**: Code and documentation are updated in lockstep within each PR.

---

## 2. Capability Pipeline

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

## 3. Dependency Matrix (Backend Services → Frontend Enablement)

This matrix establishes the strict dependency rules governing frontend enablement. A frontend capability cannot be built until its enabling backend service and REST API are fully implemented and verified.

| Backend Capability | Management API Endpoint | Enabled Frontend Surface | Target PR |
|---|---|---|---|
| **Consolidated Tool Registry** | `GET /api/v1/tools` | Tool Registry (`/tools`) | **PR #66** |
| **Scenario Execution Engine** | `GET /api/v1/scenarios` | Scenario Library (`/scenarios`) | **PR #66** |
| **Frontend Server State Infra** | Client REST Client (`apiClient.ts`) | TanStack Query Caching & Shell | **PR #67** |
| **Behavioral Event Store** | `GET /api/v1/telemetry/events` | Audit Trail (`/audit`) | **PR #68** |
| **Behavioral Detection Engine** | `GET /api/v1/findings`, `GET /api/v1/findings/{id}` | Findings Console (`/findings`) | **PR #69** |
| **Dynamic Behavioral Risk Engine**| `GET /api/v1/risk/state/{session_id}` | Dynamic Risk Badges on Console Pages | **PR #70** |
| **Behavioral Enforcement Engine** | `GET /api/v1/approvals/pending`, `POST release/reject` | Approval Queue (`/approvals`) & Zone 1 | **PR #71** |
| **Session Events Stream** | `GET /api/v1/sessions/{id}/events` | Session Detail & Timeline Replay (`/sessions/:id`) | **PR #72** |
| **Integrated Platform Core** | All REST Management API Endpoints | Enterprise Security Console `v0.13.0` | **PR #73** |

---

## 4. ADR Implementation Tracker (v0.13.0)

| ADR | Title | Current Status | Target PR | Dependencies | Blocking Issues | Documentation Status |
|---|---|---|---|---|---|---|
| **ADR-014** | Behavioral Intelligence & Autonomous Agent Governance | Proposed | PR #73 | PRs #66–#72 | None | Up to date |
| **ADR-015** | Behavioral Telemetry Architecture | Proposed | PR #68 | PR #66 | None | Up to date |
| **ADR-016** | Behavioral Event Store and Data Model | Proposed | PR #68 | PR #68 | None | Up to date |
| **ADR-017** | Behavioral Detection Engine | Proposed | PR #69 | PR #68 | None | Up to date |
| **ADR-018** | Behavioral Risk Engine | Proposed | PR #70 | PR #69 | None | Up to date |
| **ADR-019** | Behavioral Enforcement Engine | Proposed | PR #71 | PR #70 | None | Up to date |
| **ADR-020** | Agent Security Operations | Proposed | PR #71, PR #72 | PR #70 | None | Up to date |
| **ADR-021** | Multi-Agent Governance | Proposed | Phase 3 | PR #73 | None | Up to date |
| **ADR-022** | Enterprise Security Console Evolution | Implemented (Phase 1) | PR #73 | PRs #66–#72 | None | Up to date |

---

## 5. Detailed PR-by-PR Implementation Checklists

---

### PR #66: Core Runtime Cleanup & Registry Synchronization

#### Implementation Order
1. Refactor `ToolRegistry` (`app/registry/tool_registry.py`) to delegate metadata lookup to `ToolService`.
2. Define unified `ToolDefinition` model (`app/models/tool.py`).
3. Refactor `ScenarioRunnerService` (`app/services/scenario_runner_service.py`) to execute tool invocations via public `AgentRuntimeService` interfaces only.
4. Update `Scenario` model (`app/models/scenario.py`) to add `expected_decision: PolicyDecision` and implement assertion validation.
5. Align TypeScript interfaces (`frontend/src/types/tool.ts`) with backend Pydantic models.

#### Expected Artifacts & Contracts
- **Classes**: `ToolService`, `ToolRegistry`, `ScenarioRunnerService`
- **Endpoints**: `GET /api/v1/tools`, `GET /api/v1/scenarios`
- **Tests**: `tests/registry/test_tool_registry.py`, `tests/services/test_scenario_runner_service.py`
- **Documentation**: `docs/architecture/05-tool-registry.md`, `docs/architecture/scenario-execution.md`

#### Definition of Done
- [ ] 100% backend pytest suite passes
- [ ] Zero duplication between `ToolRegistry` and `ToolService`
- [ ] Scenario runner executes tools exclusively via public runtime interfaces
- [ ] Benchmark scenarios validate `expected_decision` assertions
- [ ] Frontend `src/types/tool.ts` matches Pydantic `ToolDefinition` schema 1:1

---

### PR #67: Enterprise Frontend Infrastructure & Server State Management

#### Implementation Order
1. Install `@tanstack/react-query` in `frontend/`.
2. Create TanStack Query Provider wrapper (`src/main.tsx`).
3. Refactor existing hooks (`useAgents`, `useTools`, `useSessions`, `useAuditEvents`, `useScenarios`) to use TanStack Query `useQuery`.
4. Create `ErrorBoundary.tsx` component (`src/components/common/`) and wrap page outlet.
5. Add route-level code-splitting (`React.lazy` + `Suspense`) in `App.tsx`.
6. Implement client-side feature flags module (`src/config/featureFlags.ts`).
7. Implement permission guard stub (`src/components/common/PermissionGuard.tsx`).

#### Expected Artifacts & Contracts
- **Classes / Components**: `ErrorBoundary`, `PermissionGuard`, TanStack Query Hooks
- **Config**: `src/config/featureFlags.ts`, `src/config/navigation.ts`
- **Tests**: Vitest tests (`src/components/common/__tests__/`)
- **Documentation**: `docs/architecture/enterprise-security-console/09-ui-component-architecture.md`

#### Definition of Done
- [ ] TanStack Query manages all data fetching across custom hooks
- [ ] Application shell operates with zero page reloads
- [ ] React Error Boundary isolates component errors gracefully
- [ ] Routes load lazily via `React.lazy`
- [ ] `npm run build` succeeds cleanly with zero TypeScript errors

---

### PR #68: Behavioral Telemetry Pipeline & Event Store (Vertical Slice 1)

#### Implementation Order
1. Implement `BehavioralEvent` model (`app/models/behavioral_event.py`).
2. Implement append-only `BehavioralEventStore` (`app/services/event_store_service.py`) protected by `threading.RLock`.
3. Implement `TelemetryEmitterService` (`app/services/telemetry_service.py`).
4. Instrument `RuntimeService` (`app/services/runtime_service.py`) to emit telemetry events on tool call start, evaluation, and completion.
5. Add Management API endpoint `GET /api/v1/telemetry/events` (`app/api/v1/management.py`).
6. Update `auditService.ts` and `useAuditEvents.ts` to consume `GET /api/v1/telemetry/events`.
7. Update Audit Trail page (`/audit`) to render real behavioral events.

#### Expected Artifacts & Contracts
- **Classes**: `TelemetryEmitterService`, `BehavioralEventStore`
- **Endpoints**: `GET /api/v1/telemetry/events`
- **Tests**: `tests/services/test_telemetry_service.py`, `tests/services/test_event_store_service.py`
- **Documentation**: Update [ADR-015](../adr/ADR-015-behavioral-telemetry-architecture.md) and [ADR-016](../adr/ADR-016-behavioral-event-store-and-data-model.md) headers to *Implemented*.

#### Definition of Done
- [ ] Executing a runtime tool generates a valid `BehavioralEvent` record
- [ ] `BehavioralEventStore` provides thread-safe append and query operations
- [ ] Management API exposes `GET /api/v1/telemetry/events`
- [ ] Audit Trail (`/audit`) console page renders live event telemetry
- [ ] ADR-015 and ADR-016 documentation updated to *Implemented*

---

### PR #69: Session-Scoped Detection Engine & Behavioral Findings (Vertical Slice 2)

#### Implementation Order
1. Implement `Finding` model (`app/models/finding.py`) and `FindingRepository`.
2. Implement `DetectionEngineService` (`app/services/detection_engine_service.py`) evaluating event windows.
3. Implement stateful rules: `PromptInjectionDetectionRule`, `DataExfiltrationRule`, `SensitiveFileAccessRule`.
4. Add Management API endpoints `GET /api/v1/findings` and `GET /api/v1/findings/{id}`.
5. Create `findingService.ts` and `useFindings.ts` frontend TanStack Query hooks.
6. Build Findings Console UI (`/findings`) with severity badges, category filters, and detail drawer.
7. Replace `GatedPlaceholderPage` on `/findings` with live Findings UI.

#### Expected Artifacts & Contracts
- **Classes**: `DetectionEngineService`, `FindingRepository`, Detection Rules
- **Endpoints**: `GET /api/v1/findings`, `GET /api/v1/findings/{id}`
- **Tests**: `tests/detection/test_detection_engine.py`, `tests/services/test_detection_service.py`
- **Documentation**: Update [ADR-017](../adr/ADR-017-behavioral-detection-engine.md) header to *Implemented*; update `docs/api/management-api.md`.

#### Definition of Done
- [ ] Windowed detection rules correctly identify prompt injection and data exfiltration patterns
- [ ] Detection engine emits `Finding` objects to `FindingRepository`
- [ ] Management API endpoints expose findings catalog
- [ ] Findings Console (`/findings`) renders live findings with severity filtering and detail drawers
- [ ] ADR-017 updated to *Implemented*

---

### PR #70: Dynamic Behavioral Risk Assessment (Vertical Slice 3)

#### Implementation Order
1. Implement `RiskState` model (`app/models/risk_state.py`) and `RiskRepository`.
2. Implement `RiskEngineService` (`app/services/risk_engine_service.py`) calculating dynamic risk scores (`0–100`) and assigning levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
3. Connect `RiskEngineService` to consume `Finding` events and update session/agent risk scores.
4. Add Management API endpoints `GET /api/v1/risk/state/{session_id}` and `GET /api/v1/risk/agents/{agent_id}`.
5. Create `riskService.ts` and `useRiskState.ts` hooks.
6. Update Agents (`/agents`), Sessions (`/sessions`), and Dashboard (`/`) pages to surface live dynamic risk badges.

#### Expected Artifacts & Contracts
- **Classes**: `RiskEngineService`, `RiskRepository`
- **Endpoints**: `GET /api/v1/risk/state/{session_id}`, `GET /api/v1/risk/agents/{agent_id}`
- **Tests**: `tests/services/test_risk_service.py`
- **Documentation**: Update [ADR-018](../adr/ADR-018-behavioral-risk-engine.md) header to *Implemented*.

#### Definition of Done
- [ ] Dynamic risk engine calculates risk scores from threat findings and tool criticality
- [ ] Risk levels update dynamically across agent sessions
- [ ] Management API exposes risk state endpoints
- [ ] Console pages surface live dynamic risk badges
- [ ] ADR-018 updated to *Implemented*

---

### PR #71: Behavioral Enforcement Engine & Pending Approval Queue (Vertical Slice 4)

#### Implementation Order
1. Implement `EnforcementEngineService` (`app/services/enforcement_service.py`) evaluating policy actions (`ALLOW`, `DENY`, `HOLD_SESSION`, `REQUIRE_APPROVAL`).
2. Implement `PendingApproval` model (`app/models/approval.py`) and `PendingApprovalRepository` (`RLock` protected).
3. Connect `EnforcementEngineService` to place high-risk sessions in `HOLD_SESSION` status and create pending approval tickets.
4. Add Management API endpoints:
   - `GET /api/v1/approvals/pending`
   - `POST /api/v1/approvals/{id}/release`
   - `POST /api/v1/approvals/{id}/reject`
5. Create `approvalService.ts` and `useApprovals.ts` hooks.
6. Build interactive Approval Queue UI (`/approvals`) allowing analysts to review held sessions and issue audited Release/Reject actions.
7. Replace `GatedPlaceholderPage` on `/approvals` with live Approval Queue UI.
8. Activate Zone 1 (Action Required Work Queue) on Command Center landing surface (`/`).

#### Expected Artifacts & Contracts
- **Classes**: `EnforcementEngineService`, `PendingApprovalRepository`
- **Endpoints**: `GET /api/v1/approvals/pending`, `POST release`, `POST reject`
- **Tests**: `tests/services/test_enforcement_service.py`, `tests/api/test_management_api.py`
- **Documentation**: Update [ADR-019](../adr/ADR-019-behavioral-enforcement-engine.md) and [ADR-020](../adr/ADR-020-agent-security-operations.md) headers to *Implemented*.

#### Definition of Done
- [ ] High-risk tool calls are held deterministically in pending approvals
- [ ] Analyst Release action resumes execution; Reject action terminates session
- [ ] Approval Queue (`/approvals`) renders live pending approvals
- [ ] Command Center Zone 1 surfaces active pending approvals
- [ ] ADR-019 and ADR-020 updated to *Implemented*

---

### PR #72: Single-Panel Session Timeline & Forensic Replay (Vertical Slice 5)

#### Implementation Order
1. Add Management API endpoint `GET /api/v1/sessions/{id}/events`.
2. Create `useSessionEvents(sessionId)` TanStack Query hook.
3. Build `SessionDetailPage.tsx` (`/sessions/:id`) rendering session metadata, risk assessment state, and chronological event sequence.
4. Build `SessionTimeline.tsx` component visualizing tool calls, parameters, decision badges, and finding markers per step.
5. Connect Session table rows (`/sessions`) to navigate to `/sessions/:id`.

#### Expected Artifacts & Contracts
- **Classes / Components**: `SessionDetailPage`, `SessionTimeline`
- **Endpoints**: `GET /api/v1/sessions/{id}/events`
- **Tests**: `tests/services/test_session_service.py`, Vitest `SessionTimeline.test.tsx`
- **Documentation**: Update `docs/architecture/enterprise-security-console/08-page-specifications.md`.

#### Definition of Done
- [ ] `GET /api/v1/sessions/{id}/events` returns chronological telemetry events
- [ ] `/sessions/:id` renders focal event timeline with parameter inspection
- [ ] Step selection highlights associated policy decisions and findings markers
- [ ] Back navigation to `/sessions` operates cleanly

---

### PR #73: Phase 2 E2E System Integration Verification & Release v0.13.0

#### Implementation Order
1. Build end-to-end integration test (`tests/integration/test_phase2_e2e.py`) verifying full lifecycle: Agent execution → Telemetry → Detection → Finding → Risk update → Session hold → Approval queue → Release action → Resume.
2. Build Vitest frontend integration suite.
3. Synchronize `README.md`, `AGENTS.md`, and all architecture docs.
4. Verify ADR status headers (ADR-014 through ADR-022) reflect implementation status.
5. Create Phase 2 Release Notes (`docs/releases/v0.13.0.md`).

#### Expected Artifacts & Contracts
- **Tests**: `tests/integration/test_phase2_e2e.py`, full backend pytest suite, `ruff check`, `npm run build`, Vitest suite
- **Documentation**: `README.md`, `AGENTS.md`, `docs/releases/v0.13.0.md`

#### Definition of Done
- [ ] End-to-end integration test passes 100%
- [ ] Full `pytest` suite passes (250+ tests)
- [ ] `ruff check` reports zero violations
- [ ] `npm run build` succeeds cleanly
- [ ] Version `v0.13.0` release notes committed to repository

---

## 6. Release Plan: Platform Version v0.13.0

### Scope
Delivers the complete Behavioral Intelligence engine (Telemetry Pipeline, Event Store, Stateful Detection Engine, Dynamic Risk Engine, Behavioral Enforcement Engine, Pending Approval Queue) and the operational Enterprise Security Console (`/audit`, `/findings`, `/approvals`, `/sessions/:id`, Command Center Zone 1).

### Release Criteria
- **Backend Quality**: 100% pass rate across all unit, service, API, and integration tests; zero `ruff` violations.
- **Frontend Quality**: Zero TypeScript compilation errors; zero build warnings; Vitest component suite passes cleanly.
- **Security Invariants**: 100% deterministic decisioning; zero security logic in LLM prompts or frontend components; append-only telemetry store.
- **Documentation Quality**: All ADR headers updated; OpenAPI specifications synchronized; release notes committed.

### Merge Requirements
All 8 PRs (PR #66 to PR #73) merged sequentially into `main` after passing all automated CI checks and code review.

---

## 7. Final Implementation Readiness Validation

The Review Board has conducted a final sanity check of this implementation plan:

- **Sequencing**: Validated. PR #66 consolidates registry models; PR #67 hardens frontend infrastructure; PRs #68–#72 deliver 5 clean vertical slices in pipeline order; PR #73 verifies system integration.
- **Implementation Tasks**: Complete. All domain services, repository classes, REST endpoints, and React components are explicitly assigned to target PRs.
- **Documentation**: Complete. All ADRs, API docs, and architecture guides are mapped.
- **Testing**: Complete. Every PR specifies backend `pytest` and frontend Vitest test coverage expectations.

**Conclusion**: The implementation plan contains **zero gaps** and is **READY FOR IMMEDIATE EXECUTION**.
