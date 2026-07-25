# 04 — Navigation Architecture

## Purpose

This document specifies the primary navigation structure, route hierarchy, sidebar organization, and path migration strategy for the Enterprise Security Console.

---

## Scope

Governs the application navigation sidebar (`src/components/layout/Sidebar.tsx`), route definitions (`src/App.tsx`), and visual section headers across all releases (`v0.12.0` through `v1.0.0`).

---

## Primary Navigation Structure

The primary sidebar navigation is organized into **three operational modes** comprising **nine canonical routes**:

```text
MONITOR
  ├── Command Center         (/)
  └── Approval Queue         (/approvals)

INVESTIGATE
  ├── Sessions               (/sessions)
  ├── Findings               (/findings)
  └── Audit Trail            (/audit)

GOVERN
  ├── Agents                 (/agents)
  ├── Tools                  (/tools)
  ├── Detection Rules        (/detection)
  └── Scenarios              (/scenarios)
```

---

## Route Specification

| Section | Label | Path | Component | Status / Availability |
|---|---|---|---|---|
| **MONITOR** | Command Center | `/` | `<DashboardPage />` | Available (v0.12.0+) |
| **MONITOR** | Approval Queue | `/approvals` | `<ApprovalQueuePage />` | Gated by Phase 2 backend |
| **INVESTIGATE** | Sessions | `/sessions` | `<SessionsPage />` | Available (Promoted in v0.12.0) |
| **INVESTIGATE** | Session Workspace | `/sessions/:id` | `<SessionWorkspacePage />` | Phase 1 (basic) / Phase 3 (full) |
| **INVESTIGATE** | Findings | `/findings` | `<FindingsPage />` | Gated by Phase 2 backend |
| **INVESTIGATE** | Audit Trail | `/audit` | `<AuditTimelinePage />` | Available (v0.12.0+) |
| **GOVERN** | Agents | `/agents` | `<AgentsPage />` | Available (v0.12.0+) |
| **GOVERN** | Tools | `/tools` | `<ToolsPage />` | Available (v0.12.0+) |
| **GOVERN** | Detection Rules | `/detection` | `<DetectionRulesPage />` | Available (v0.12.0+) |
| **GOVERN** | Scenarios | `/scenarios` | `<ScenariosPage />` | Available (Promoted in v0.12.0) |

---

## Phased Navigation Migration Strategy

Migration from the legacy flat sidebar (v0.11.0) to the workflow-centric navigation occurs in four backwards-compatible phases:

```text
Legacy Flat List (v0.11.0)        Phase 1 Navigation (v0.12.0)       Phase 2+ Target (v0.13.0+)
┌────────────────────────┐        ┌────────────────────────┐        ┌────────────────────────┐
│ Dashboard              │        │ MONITOR                │        │ MONITOR                │
│ Agents                 │        │   Command Center       │        │   Command Center       │
│ Tools                  │        │   Sessions (Promoted)  │        │   Approval Queue (NEW) │
│ Detection Rules        │        │                        │        │                        │
│ Audit Timeline         │        │ INVESTIGATE            │        │ INVESTIGATE            │
│                        │        │   Audit Trail          │        │   Sessions             │
│ (Orphaned: /sessions,  │        │                        │        │   Findings (NEW)       │
│  /scenarios)           │        │ GOVERN                 │        │   Audit Trail          │
│                        │        │   Agents               │        │                        │
└────────────────────────┘        │   Tools                │        │ GOVERN                 │
                                  │   Detection Rules      │        │   Agents               │
                                  │   Scenarios (Promoted) │        │   Tools                │
                                  └────────────────────────┘        │   Detection Rules      │
                                                                    │   Scenarios            │
                                                                    └────────────────────────┘
```

### Key Migration Rules:
1. **Zero Path Breakage:** Existing URL paths (`/agents`, `/tools`, `/detection`, `/audit`, `/sessions`, `/scenarios`) never change.
2. **Promote Orphaned Routes Immediately (Phase 1):** `/sessions` and `/scenarios` exist in code but were missing from the sidebar in v0.11.0. Phase 1 adds them explicitly to the sidebar.
3. **Additive Category Expansion:** New routes (`/approvals`, `/findings`) are rendered only when corresponding backend APIs become available.

---

## Design Rationale

Navigational grouping must mirror operational user intent rather than backend database tables:
- **MONITOR:** Operators check what needs immediate action.
- **INVESTIGATE:** Analysts examine evidence to understand incident causality.
- **GOVERN:** Engineers configure rules, registries, and security benchmarks.

Restricting top-level navigation to 3 sections and 9 routes prevents navigation bloat and cognitive overload.

---

## Tradeoffs

- **Categorized Sidebar Height:** Section headers (`MONITOR`, `INVESTIGATE`, `GOVERN`) add vertical spacing to the sidebar, requiring clean typography to prevent visual clutter on lower-resolution screens.

---

## Dependencies

- Updates `src/components/layout/Sidebar.tsx` and `src/App.tsx`.

---

## Relationship to Other Architecture Documents

- Implements Information Architecture ([03-information-architecture.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/enterprise-security-console/03-information-architecture.md)).
- Operational behavior specified in Operational Model ([05-operational-model.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/enterprise-security-console/05-operational-model.md)).

---

## Future Evolution

In Phase 4 (Enterprise Operations), nested sub-routes such as `/agents/topology` (Multi-Agent Governance) or `/cases` (Incident Cases) will be introduced under existing section headers without altering the primary navigation layout.
