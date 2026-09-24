# 11 — Implementation Roadmap

## Purpose

This document specifies the **Implementation Roadmap** for the Enterprise Security Console and the visible **Product Demonstration Track**.

It establishes an incremental progression from the platform's backend durable state foundation through dedicated operational, investigative, and control-plane UI surfaces, culminating in the mature Enterprise Browser Management Console.

---

## Core Architectural & Product Principles

### 1. Client Trust Boundary
> **"The frontend is an observability and control-plane client, never a security authority."**

```text
Browser UI
    ↓
Control-Plane API
    ↓
Domain Services
    ↓
Deterministic Security Controls (PolicyEngine, DetectionEngine, RiskAggregator)
    ↓
Decision / Durable State
```

The browser UI is strictly untrusted:
- The frontend **never** evaluates policy or makes authorization decisions.
- The frontend **never** performs threat detection or calculates risk scores.
- The frontend **never** executes state transitions directly or grants execution authority.
- All security decisions remain 100% server-side, deterministic, and backed by domain services.

### 2. Progressive Product Demonstrability
The platform is designed to be progressively demonstrable through the UI. Reviewers, analysts, and operators can inspect real security posture, follow executions across the evidence chain, and interact with audited control-plane workflows.
- **Zero Synthetic Mocks**: Every UI surface consumes real backend domain state.
- **Backend Is Truth**: UI capabilities are introduced strictly as the enabling backend services and REST APIs become durable.

---

### Status Legend
- **Implemented**: Fully operational in the checked-out codebase with test coverage.
- **In Progress**: Active engineering cycle under implementation.
- **Planned**: Target milestone on the roadmap.

---

## Existing UI Baseline (Implemented)

The platform already possesses an operational console foundation and specialized scenario validation surfaces:

1. **Console Management Shell (Implemented)**:
   - Navigation and resource views for `/agents`, `/tools`, `/sessions`, `/rules`, and `/findings`.
2. **Stage E-A — Scenario Execution Evidence Model (Implemented)**:
   - Typed domain projection (`ScenarioExecutionEvidence`) capturing the complete deterministic evidence chain:
     $$\text{Request} \longrightarrow \text{Authorization (6 checks)} \longrightarrow \text{Detection} \longrightarrow \text{Risk} \longrightarrow \text{Response} \longrightarrow \text{Audit ID} \longrightarrow \text{Final Decision}$$
3. **Stage E-B — Live Scenario Timeline UI (Implemented)**:
   - Interactive, color-coded visual execution timeline (`ScenarioTimeline.tsx`) rendering the authoritative evidence chain, check evaluations, risk tiers, response actions, and audit linkage for benchmark scenarios.

---

## Incremental UI & Product Demonstration Track

```text
Existing Baseline
├── Stage E-A: Scenario Execution Evidence (Implemented)
└── Stage E-B: Live Scenario Timeline UI (Implemented)
      │
      ▼
v0.16 — Durable Security State & Control Plane Foundation (In Progress)
Backend-first state migration enabling trustworthy UI observability
      │
      ▼
v0.17 — Security Operations Dashboard (Planned)
Operational security posture, agent status, and active session visibility
      │
      ▼
v0.18 — Investigation / Evidence Explorer (Planned)
Forensic execution timeline generalizing Stage E across live runtime events
      │
      ▼
v0.19 — Governance Console (Planned)
Administrative management client for agents, tools, sessions, and audit evidence
      │
      ▼
v0.20 — Approval / Control Plane UI (Planned)
Operator workflow client for ExecutionGrant review and authorization releases
      │
      ▼
v1.3 — Enterprise Browser Management Console (Planned)
Mature enterprise consolidation and operations console
```

---

### Milestone Breakdown

### v0.16 — Durable Security State & Control Plane Foundation (In Progress)
**Focus**: Backend-first durable state architecture (ADR-030, ADR-031).

#### Backend State Migration:
- **Repository Protocols & DI Boundaries (PR #180)**: *Implemented*.
- **`AgentRepository` Integration (PR #181)**: *Implemented*.
- **`EnforcementStateRepository` Integration (PR #181)**: *Implemented*.
- **`AuditEvidenceRepository` Integration (PR #182)**: *Implemented*.
- **`SessionRepository` Migration**: *In Progress* (Highest-risk migration: combines active sessions, terminal tombstones, and the rolling detection horizon).
- **`ToolRepository` Migration**: *Planned*.

#### UI Enablement:
Durable state established in v0.16 provides the single source of truth required for trustworthy operational UI observability:
- Durable agent configuration and dynamic enforcement posture.
- Append-only, immutable audit evidence.
- Durable session ownership and permanent terminal tombstones.
- Sliding detection horizon events.
*(Note: v0.16 establishes this backend foundation; UI surfaces consuming this state are scheduled for v0.17+).*

---

### v0.17 — Security Operations Dashboard (Planned)
**Focus**: Operational security visibility for SOC analysts.

#### Planned Capabilities:
- **Platform Posture Overview**: Aggregated agent health, suspension alerts, and active risk distribution.
- **Agent Inventory & Dynamic Posture**: Status cards reflecting authoritative `EnforcementStateRepository` posture.
- **Session Activity Monitor**: Active session inventory and activity metrics backed by `SessionRepository`.
- **Findings & Alerts Summary**: High-severity threat detections and excessive denial trends.
- **Recent Decision Activity**: Log of recent execution decisions (`ALLOW`, `ALERT`, `DENY`, `REQUIRE_APPROVAL`).

---

### v0.18 — Investigation / Evidence Explorer (Planned)
**Focus**: Detailed forensic analysis of individual executions and security events.

#### Planned Capabilities:
- **Runtime Evidence Chain Explorer**: Generalizes the existing Stage E-A/E-B scenario timeline to live runtime executions:
  $$\text{REQUEST} \longrightarrow \text{INTENT} \longrightarrow \text{AUTHORIZATION} \longrightarrow \text{DETECTION} \longrightarrow \text{RISK} \longrightarrow \text{RESPONSE} \longrightarrow \text{AUDIT} \longrightarrow \text{FINAL DECISION}$$
- **Granular Authorization Inspection**: Step-by-step breakdown of the 6 deterministic authorization checks (agent existence, tool existence, RBAC approved tools, agent status, risk tier alignment, resource policy).
- **Threat Detection Evidence**: Detailed context for triggered rules (`PROMPT_INJECTION`, `SENSITIVE_FILE_ACCESS`, `DATA_EXFILTRATION`, `EXCESSIVE_DENIALS`).
- **Refusal & Unreached Stages**: Clear visual indication when a fail-closed check halts the pipeline prior to downstream evaluation.
- **Audit Cross-Referencing**: Direct verification against immutable `AuditEvidenceRepository` records.

---

### v0.19 — Governance Console (Planned)
**Focus**: Administrative governance, policy posture, and compliance auditing.

#### Planned Capabilities:
- **Agent Governance**: Registration, tier classification, tool approvals, and administrative lifecycle management (`ACTIVE`, `DISABLED`).
- **Tool Inventory & Governance**: Declarative capabilities, parameter schemas, risk levels, and sensitivity classifications.
- **Audit Evidence Explorer**: Filtered querying and export of append-only audit events by session, agent, and timestamp.
- **Enforcement History**: Complete audit trail of dynamic suspension and administrative reinstatement transitions.
- **Policy Registry**: Declarative policy inspection as policy domains become durable.

---

### v0.20 — Approval / Control Plane UI (Planned)
**Focus**: Human-in-the-loop control-plane interface for gated execution approvals (ADR-031).

#### Planned Capabilities:
- **Pending Approvals Queue**: Work queue of operations paused by `REQUIRE_APPROVAL` responses.
- **Grant Context Viewer**: In-depth inspection of the proposed `ToolInvocation`, originating agent context, and accumulated risk findings.
- **Analyst Decision Interface**: Audited release (`APPROVE`) or rejection (`REJECT`) controls.
- **Strict Control-Plane Architecture**: The UI dispatches requests to `/api/v1/approvals/:id/release`. The domain service and `ApprovalGrantRepository` validate authorization and atomically update grant status. The browser never directly authorizes tool execution.

---

### v1.3 — Enterprise Browser Management Console (Planned)
**Focus**: Mature, unified enterprise operations console.

#### Scope:
- Consolidates and scales the operational, investigative, and governance capabilities developed in v0.17 through v0.20.
- Enterprise role-based access control (RBAC) across console surfaces (`ANALYST`, `ADMIN`, `AUDITOR`).
- High-throughput forensic event replay and multi-agent governance topology visualization.
- Production-grade streaming and alerting infrastructure.

---

## Alignment with Architecture Documentation

- Governed by [ADR-022: Enterprise Security Console Evolution](../../adr/ADR-022-enterprise-security-console-evolution.md).
- Complements the durable backend architecture defined in [ADR-030](../../adr/ADR-030-durable-state-repository-architecture.md) and [ADR-031](../../adr/ADR-031-execution-grant-approval-control-plane.md).
- Preserves the release trajectory established in [`docs/design/v0.9-enterprise-tool-governance.md`](../../design/v0.9-enterprise-tool-governance.md).
