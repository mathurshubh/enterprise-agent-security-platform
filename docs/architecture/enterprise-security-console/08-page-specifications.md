# 08 — Page Specifications

## Purpose

This document provides detailed specifications for all **nine canonical pages** comprising the Enterprise Security Console navigation architecture.

---

## Scope

Defines purpose, target users, entity ownership, backend API bindings, UI component layout, and availability status for each console page.

---

## Page Specification Directory

### 1. Command Center (`/`)
- **Operational Mode:** MONITOR
- **Purpose:** Central operational landing surface surfacing items requiring immediate action (Zone 1 Action Required Queue) and overall platform security posture (Zone 2 Awareness).
- **Target Users:** SOC Analyst, Security Engineer, Platform Administrator.
- **Entity Ownership:** Aggregates across all platform entities.
- **API Bindings:** `GET /api/v1/info`, `/agents`, `/sessions`, `/audit/events`. Phase 2+: `/approvals/pending`, `/findings`.
- **Status:** Available in Phase 1 (Zone 2 metrics); upgraded in Phase 2 (Zone 1 work queue).

### 2. Approval Queue (`/approvals`)
- **Operational Mode:** MONITOR
- **Purpose:** Work queue enabling authorized SOC analysts to review, approve, reject, or escalate agent sessions held in `REQUIRE_APPROVAL` or `HOLD_SESSION` states.
- **Target Users:** SOC Analyst (Tier 2+), Security Administrator.
- **Entity Ownership:** `EnforcementDecision`, `EnforcementOutcome` ([ADR-019](../../adr/ADR-019-behavioral-enforcement-engine.md), [ADR-020](../../adr/ADR-020-agent-security-operations.md)).
- **API Bindings:** `GET /api/v1/approvals/pending`, `POST /api/v1/approvals/:id/release`, `POST /api/v1/approvals/:id/reject`.
- **Status:** Gated by Phase 2 backend approval APIs.

### 3. Sessions List (`/sessions`)
- **Operational Mode:** INVESTIGATE
- **Purpose:** Inventory and search interface for all active and historical agent execution sessions.
- **Target Users:** SOC Analyst, Security Engineer.
- **Entity Ownership:** `Session` ([ADR-003](../../adr/ADR-003-runtime-security-orchestrator.md)).
- **API Bindings:** `GET /api/v1/sessions`.
- **Status:** Available in Phase 1 (promoted to primary navigation).

### 4. Session Workspace (`/sessions/:id`)
- **Operational Mode:** INVESTIGATE
- **Purpose:** Multi-panel forensic investigation environment for deep-dive session analysis.
- **Target Users:** SOC Analyst, Security Engineer.
- **Entity Ownership:** `Session`, `BehavioralEvent`, `Finding`, `RiskAssessment`, `EnforcementDecision`.
- **API Bindings:** Phase 1: `GET /sessions`, `/audit/events`. Phase 3: `GET /sessions/:id/events`, `/sessions/:id/timeline`.
- **Status:** Simplified view in Phase 1; full multi-panel workspace in Phase 3.

### 5. Findings & Alerts (`/findings`)
- **Operational Mode:** INVESTIGATE
- **Purpose:** Centralized catalog of threat detection rule firings and behavioral anomalies.
- **Target Users:** SOC Analyst, Security Engineer.
- **Entity Ownership:** `BehavioralFinding` ([ADR-017](../../adr/ADR-017-behavioral-detection-engine.md)).
- **API Bindings:** `GET /api/v1/findings`, `GET /api/v1/findings/:id`.
- **Status:** Gated by Phase 2 backend findings API.

### 6. Audit Trail (`/audit`)
- **Operational Mode:** INVESTIGATE
- **Purpose:** Immutable chronological log of authoritative runtime security decisions.
- **Target Users:** Compliance Officer, Security Analyst, Auditor.
- **Entity Ownership:** `AuditEvent` ([ADR-004](../../adr/ADR-004-deterministic-security-pipeline.md)).
- **API Bindings:** `GET /api/v1/audit/events`.
- **Status:** Available in Phase 1.

### 7. Agent Registry (`/agents`)
- **Operational Mode:** GOVERN
- **Purpose:** Governance interface for registered Enterprise Agent identities, risk tiers, and approved tool permissions.
- **Target Users:** Platform Administrator, Security Engineer.
- **Entity Ownership:** `Agent` ([ADR-003](../../adr/ADR-003-runtime-security-orchestrator.md)).
- **API Bindings:** `GET /api/v1/agents`.
- **Status:** Available in Phase 1.

### 8. Tool Registry (`/tools`)
- **Operational Mode:** GOVERN
- **Purpose:** Inventory of executable tools, parameter definitions, and capability policies.
- **Target Users:** Security Engineer, Platform Administrator.
- **Entity Ownership:** `Tool` ([ADR-005](../../adr/ADR-005-tool-registry.md)).
- **API Bindings:** `GET /api/v1/tools`.
- **Status:** Available in Phase 1.

### 9. Detection Rules (`/detection`)
- **Operational Mode:** GOVERN
- **Purpose:** Active threat detection rules catalog with OWASP LLM Top 10 and MITRE ATLAS/ATT&CK control mappings.
- **Target Users:** Security Engineer, Compliance Officer.
- **Entity Ownership:** `DetectionRule` ([ADR-004](../../adr/ADR-004-deterministic-security-pipeline.md)).
- **API Bindings:** `GET /api/v1/detection/rules`.
- **Status:** Available in Phase 1.

### 10. Scenario Library (`/scenarios`)
- **Operational Mode:** GOVERN
- **Purpose:** Library of security validation benchmarks and prompt injection/exfiltration attack scenarios.
- **Target Users:** Security Engineer, Red Team Specialist.
- **Entity Ownership:** `AttackScenario` ([ADR-010](../../adr/ADR-010-scenario-execution-architecture.md)).
- **API Bindings:** `GET /api/v1/scenarios`, `GET /api/v1/scenarios/:id`.
- **Status:** Available in Phase 1 (promoted to primary navigation).

---

## Design Rationale

Explicit page specifications eliminate guesswork during frontend engineering. Defining entity ownership and API bindings per page prevents overlapping service calls and ensures strict adherence to the Information Architecture ([03-information-architecture.md](03-information-architecture.md)).

---

## Tradeoffs

- **API Boundary Dependency:** Pages requiring backend capabilities not yet implemented (e.g., `/approvals`, `/findings`) are cleanly deferred to Phase 2 rather than implemented with mock data.

---

## Dependencies

- Serves as the implementation mandate for UI Component Architecture ([09-ui-component-architecture.md](09-ui-component-architecture.md)).

---

## Relationship to Other Architecture Documents

- Implements Navigation Architecture ([04-navigation-architecture.md](04-navigation-architecture.md)).

---

## Future Evolution

As Multi-Agent Governance ([ADR-021](../../adr/ADR-021-multi-agent-governance.md)) and SOC Case Management ([ADR-020](../../adr/ADR-020-agent-security-operations.md)) mature, two additional page specifications (`/agents/topology` and `/cases`) will be added to this specification directory.
