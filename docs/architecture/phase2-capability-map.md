# Phase 2 Capability Map
## Enterprise Agent Security Platform (v0.13.0)

This document maps every capability introduced in Phase 2 across its full architectural stack: from governing ADR to backend domain service, REST API endpoint, frontend surface, Pydantic/TypeScript data models, test suite, and documentation.

---

## Capability Mappings

### 1. Tool Registry Consolidation & Scenario Benchmark Assertions
- **ADR**: [ADR-005: Tool Registry](../adr/ADR-005-tool-registry.md), [ADR-010: Scenario Execution Architecture](../adr/ADR-010-scenario-execution-architecture.md), [ADR-013: Scenario Runner Service Boundaries](../adr/ADR-013-scenario-runner-service-boundaries.md)
- **Backend Service**: `ToolService`, `ToolRegistry`, `ScenarioRunnerService`
- **Management API**: `GET /api/v1/tools`, `GET /api/v1/scenarios`
- **Frontend Surface**: Tool Registry (`/tools`), Scenario Library (`/scenarios`)
- **Data Model**: `ToolDefinition` (Pydantic), `Tool` (TypeScript `src/types/tool.ts`), `Scenario` (`expected_decision`)
- **Tests**: `tests/registry/test_tool_registry.py`, `tests/services/test_scenario_runner_service.py`
- **Target PR**: **PR #69**

---

### 2. Enterprise Frontend Infrastructure & Server State Management
- **ADR**: [ADR-022: Enterprise Security Console Evolution](../adr/ADR-022-enterprise-security-console-evolution.md)
- **Backend Service**: N/A (Frontend Architecture Slice)
- **Management API**: Management API REST Client (`apiClient.ts`)
- **Frontend Surface**: Application Shell (`AppLayout.tsx`, `App.tsx`)
- **Data Model**: TanStack Query Cache Keys, Feature Flags Schema (`src/config/featureFlags.ts`), Permission Context Stub (`PermissionGuard.tsx`)
- **Tests**: Vitest tests (`src/components/common/__tests__/`)
- **Target PR**: **PR #70**

---

### 3. Behavioral Telemetry & Event Store (Vertical Slice 1)
- **ADR**: [ADR-015: Behavioral Telemetry Architecture](../adr/ADR-015-behavioral-telemetry-architecture.md), [ADR-016: Behavioral Event Store and Data Model](../adr/ADR-016-behavioral-event-store-and-data-model.md)
- **Backend Service**: `TelemetryEmitterService`, `BehavioralEventStore`
- **Management API**: `GET /api/v1/telemetry/events`
- **Frontend Surface**: Audit Trail (`/audit`)
- **Data Model**: `BehavioralEvent` (Pydantic & TypeScript `src/types/auditEvent.ts`)
- **Tests**: `tests/services/test_telemetry_service.py`, `tests/services/test_event_store_service.py`
- **Target PR**: **PR #71**

---

### 4. Session-Scoped Detection & Behavioral Findings (Vertical Slice 2)
- **ADR**: [ADR-017: Behavioral Detection Engine](../adr/ADR-017-behavioral-detection-engine.md)
- **Backend Service**: `DetectionEngineService`, `FindingRepository`
- **Management API**: `GET /api/v1/findings`, `GET /api/v1/findings/{id}`
- **Frontend Surface**: Findings & Threat Console (`/findings`)
- **Data Model**: `Finding` (Pydantic & TypeScript `src/types/finding.ts`), `DetectionRule`
- **Tests**: `tests/detection/test_detection_engine.py`, `tests/services/test_detection_service.py`
- **Target PR**: **PR #72**

---

### 5. Dynamic Behavioral Risk Assessment (Vertical Slice 3)
- **ADR**: [ADR-018: Behavioral Risk Engine](../adr/ADR-018-behavioral-risk-engine.md)
- **Backend Service**: `RiskEngineService`, `RiskRepository`
- **Management API**: `GET /api/v1/risk/state/{session_id}`, `GET /api/v1/risk/agents/{agent_id}`
- **Frontend Surface**: Agents Page (`/agents`), Sessions Page (`/sessions`), Command Center Metric Cards (`/`)
- **Data Model**: `RiskState` (Pydantic & TypeScript `src/types/riskState.ts`)
- **Tests**: `tests/services/test_risk_service.py`
- **Target PR**: **PR #73**

---

### 6. Behavioral Enforcement & Pending Approval Queue (Vertical Slice 4)
- **ADR**: [ADR-019: Behavioral Enforcement Engine](../adr/ADR-019-behavioral-enforcement-engine.md), [ADR-020: Agent Security Operations](../adr/ADR-020-agent-security-operations.md)
- **Backend Service**: `EnforcementEngineService`, `PendingApprovalRepository`
- **Management API**: `GET /api/v1/approvals/pending`, `POST /api/v1/approvals/{id}/release`, `POST /api/v1/approvals/{id}/reject`
- **Frontend Surface**: Approval Queue (`/approvals`), Command Center Zone 1 (`/`)
- **Data Model**: `PendingApproval` (Pydantic & TypeScript `src/types/approval.ts`)
- **Tests**: `tests/services/test_enforcement_service.py`, `tests/api/test_management_api.py`
- **Target PR**: **PR #74**

---

### 7. Single-Panel Session Timeline & Forensic Replay (Vertical Slice 5)
- **ADR**: [ADR-020: Agent Security Operations](../adr/ADR-020-agent-security-operations.md)
- **Backend Service**: `SessionService`, `BehavioralEventStore`
- **Management API**: `GET /api/v1/sessions/{id}/events`
- **Frontend Surface**: Session Detail Page (`/sessions/:id`), Session Timeline Component
- **Data Model**: `SessionDetail` (TypeScript `src/types/sessionDetail.ts`)
- **Tests**: `tests/services/test_session_service.py`, Vitest `SessionTimeline.test.tsx`
- **Target PR**: **PR #75**

---

### 8. System Integration & Phase 2 Release Verification
- **ADR**: [ADR-014: Behavioral Intelligence and Autonomous Agent Governance](../adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) through [ADR-022](../adr/ADR-022-enterprise-security-console-evolution.md)
- **Backend Service**: All Services (Full Platform Integration)
- **Management API**: All Management API Endpoints
- **Frontend Surface**: Entire Enterprise Security Console (`v0.13.0`)
- **Data Model**: Complete Platform Domain Graph
- **Tests**: `tests/integration/test_phase2_e2e.py`, full `pytest` suite, `ruff check`, `npm run build`, Vitest suite
- **Target PR**: **PR #76**
