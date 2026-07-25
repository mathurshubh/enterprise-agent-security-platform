# 11 — Implementation Roadmap

## Purpose

This document specifies the **Four-Phase Implementation Roadmap** for delivering the Enterprise Security Console architecture from version `v0.12.0` through `v1.0.0`.

---

## Scope

Defines phase boundaries, backend prerequisites, implementation deliverables, and validation criteria across all four execution phases.

---

## Phase Matrix Overview

```text
Phase 1: Foundation (v0.12.0)      Phase 2: Behavioral Intel (v0.13.0)
• Existing Backend APIs Only       • Gated by BI & Approval APIs
• Sidebar Navigation Restructure   • Action Required Queue (Zone 1)
• Promote /sessions & /scenarios   • Approval Queue Page (/approvals)
• Basic Session Detail Page        • Findings Page (/findings)
• Shared Component Refactoring     • TanStack Query Cache Layer
                                                 │
                                                 ▼
Phase 4: Operations (v1.0.0)       Phase 3: Investigation (v0.14.0)
• Gated by Streaming & Cases APIs  • Gated by Session Detail APIs
• Session Forensic Replay          • Multi-Panel Session Workspace
• Real-time SSE Alert Streaming    • Focal Behavioral Timeline
• Incident Case Management         • Coordinated Panels A-F
• Multi-Agent Governance Topology  • Evidence Chain Traversal
```

---

## Phase Breakdown & Deliverables

### Phase 1 — Foundation & Navigation Restructure (`v0.12.0`)
**Backend Prerequisites:** None (uses existing Management API: `/agents`, `/tools`, `/detection/rules`, `/audit/events`, `/sessions`, `/scenarios`, `/info`).

#### Key Deliverables:
1. **Sidebar Navigation Restructure:** Implement 3-mode section headers (`MONITOR`, `INVESTIGATE`, `GOVERN`) and 9 canonical sidebar items in `src/components/layout/Sidebar.tsx`.
2. **Promote Orphaned Routes:** Expose `/sessions` and `/scenarios` explicitly in the navigation sidebar.
3. **Basic Session Detail View (`/sessions/:id`):** Implement basic single-panel session detail page filtering existing audit events by `agent_id` and timestamp.
4. **Command Center Refactoring:** Maintain existing dashboard metrics as Zone 2 (Operational Awareness); add degraded-mode banner for Zone 1.
5. **Shared Component Extraction:** Refactor duplicate JSX into `<MetricCard>` (`src/components/common/`) and `<SearchBar>`.
6. **Type System Graph References:** Add upstream/downstream causal relationship interfaces to `src/types/`.

---

### Phase 2 — Behavioral Intelligence Integration (`v0.13.0`)
**Backend Prerequisites:** Behavioral Intelligence endpoints (`GET /api/v1/findings`, `GET /api/v1/approvals/pending`, `POST /api/v1/approvals/:id/release`, `GET /api/v1/risk/state/:id`).

#### Key Deliverables:
1. **Action Required Work Queue (Zone 1):** Deploy primary work queue on Command Center landing surface for held sessions and high-severity findings.
2. **Approval Queue Page (`/approvals`):** Build interactive queue page allowing authorized analysts to review and issue audited approval releases.
3. **Findings & Alerts Page (`/findings`):** Build behavioral threat findings catalog with severity filtering and detail drawers.
4. **Evidence Chain Traversal:** Enable hyperlinked navigation across Findings, Risk States, and Audit Events.
5. **TanStack Query Caching:** Integrate TanStack Query cache layer into custom service hooks.

---

### Phase 3 — Session Investigation Workspace (`v0.14.0`)
**Backend Prerequisites:** Session timeline APIs (`GET /api/v1/sessions/:id/events`, `GET /api/v1/sessions/:id/timeline`, `GET /api/v1/sessions/:id/risk`).

#### Key Deliverables:
1. **Multi-Panel Workspace Architecture (`/sessions/:id`):** Build coordinated multi-panel layout anchored by Focal Behavioral Timeline.
2. **Focal Behavioral Timeline:** Interactive horizontal timeline renderer with color-coded event markers.
3. **Coordinated Contextual Panels:** Implement Event Detail (Panel A), Evidence Chain (Panel B), Tool Activity (Panel C), and Risk Evolution (Panel D).
4. **Selection State Synchronization:** Implement `SessionWorkspaceContext` to synchronize selection across all open workspace panels.

---

### Phase 4 — Enterprise Operations & Real-Time Intelligence (`v1.0.0`)
**Backend Prerequisites:** Real-time streaming (`GET /api/v1/telemetry/stream`), Incident Cases API (`/cases`), Multi-Agent Governance API (`/governance/topology`).

#### Key Deliverables:
1. **Session Forensic Replay:** Add playback controls (Play, Pause, Step, Speed) to the Session Workspace for step-by-step forensic replay ([ADR-020](../../adr/ADR-020-agent-security-operations.md)).
2. **Real-Time SSE Streaming:** Connect TanStack Query cache invalidation to Server-Sent Events stream for instant alert delivery.
3. **Incident Case Management (`/cases`):** Implement SOC incident case management and analyst annotation tools ([ADR-020](../../adr/ADR-020-agent-security-operations.md)).
4. **Multi-Agent Governance Topology (`/agents/topology`):** Build interactive multi-agent delegation tree visualization ([ADR-021](../../adr/ADR-021-multi-agent-governance.md)).

---

## Design Rationale

Gating frontend phase execution behind corresponding backend API readiness guarantees strict compliance with Principle 1 (Backend Is Truth). Delivering Phase 1 immediately provides clean navigation and reusable components without requiring backend alterations.

---

## Tradeoffs

- **Dependent Timelines:** Phase 2 and Phase 3 frontend timelines are directly bound to backend Behavioral Intelligence endpoint deployment schedules.

---

## Dependencies

- Governed by [ADR-022: Enterprise Security Console Evolution](../../adr/ADR-022-enterprise-security-console-evolution.md).

---

## Relationship to Other Architecture Documents

- Integrates all previous architecture documents ([01](01-overview.md)–[10](10-data-flow.md)) into a structured engineering execution plan.

---

## Future Evolution

Following version `v1.0.0`, future console updates will adhere to the Phase 4 architectural model, extending specific operational views without altering the core navigation, IA, or component patterns.
