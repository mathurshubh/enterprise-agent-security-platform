# 03 — Information Architecture

## Purpose

This document defines the **Two-Axis Information Architecture (IA)** model for the Enterprise Security Console. It establishes how entity types, views, and workflows are structured across two orthogonal dimensions: **Lifecycle Progression** and **Scope Granularity**.

---

## Scope

Governs the structural organization of all pages, navigation routes, layout containers, and cross-view linking models within the frontend application.

---

## The Two-Axis Model

The Information Architecture is structured along two conceptual axes:

1. **Horizontal Axis — Lifecycle Progression:** Mirrors the flow of artifacts through the backend security pipeline ([ADR-014](../../adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md)):
   `Registry Objects → Telemetry/Events → Findings → Risk → Enforcement → Operations → Audit`

2. **Vertical Axis — Scope Granularity:** Defines the depth of information displayed:
   `Platform Level (Global) → Agent Level → Session Level → Event Level`

```text
                                LIFECYCLE PROGRESSION (Horizontal Axis)
                  Registry    Events      Findings     Risk      Enforcement  Operations   Audit
                ┌───────────┬───────────┬───────────┬───────────┬───────────┬───────────┬───────────┐
  Platform      │ Registries│ Telemetry │ All       │ Posture   │ Action    │ Work      │ Audit     │
  Level         │ (Agents/  │ Health    │ Findings  │ Summary   │ Summary   │ Queue     │ Timeline  │
                │  Tools)   │           │           │           │           │           │           │
SCOPE           ├───────────┼───────────┼───────────┼───────────┼───────────┼───────────┼───────────┤
GRANULARITY     │ Agent     │ Agent     │ Agent     │ Agent     │ Agent     │ Agent     │ Agent     │
(Vertical Axis) │ Profile   │ Events    │ Findings  │ Risk      │ Active    │ Cases     │ Audit     │
                │           │           │           │ History   │ Overrides │           │ History   │
                ├───────────┼───────────┼───────────┼───────────┼───────────┼───────────┼───────────┤
                │ Session   │ Session   │ Session   │ Session   │ Session   │ Session   │ Session   │
                │ Metadata  │ Timeline  │ Findings  │ Trajectory│ Decision  │ Approval  │ Audit     │
                │           │           │           │           │           │ State     │ Trail     │
                ├───────────┼───────────┼───────────┼───────────┼───────────┼───────────┼───────────┤
                │ Event     │ Event     │ Finding   │ Score     │ Applied   │ Analyst   │ Event     │
                │ Record    │ Payload   │ Details   │ Breakdown │ Action    │ Note      │ Record    │
                └───────────┴───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘
```

---

## Mapping Pages to the Two-Axis Grid

Every view in the console occupies a precise coordinate in the two-axis model:

| Console View | Path | Scope Granularity | Lifecycle Coordinates | Primary Operational Mode |
|---|---|---|---|---|
| **Command Center** | `/` | Platform | All (Aggregated Action Queue & Awareness) | **MONITOR** |
| **Approval Queue** | `/approvals` | Platform / Session | Enforcement → Operations | **MONITOR** |
| **Sessions** | `/sessions` | Platform / Agent | Events → Session Overview | **INVESTIGATE** |
| **Session Workspace** | `/sessions/:id` | Session | Events → Findings → Risk → Enforcement | **INVESTIGATE** |
| **Findings** | `/findings` | Platform / Agent | Detection → Behavioral Findings | **INVESTIGATE** |
| **Audit Trail** | `/audit` | Platform / Agent | Audit Events | **INVESTIGATE** |
| **Agents** | `/agents` | Agent | Registry → Posture | **GOVERN** |
| **Tools** | `/tools` | Tool | Registry → Capabilities | **GOVERN** |
| **Detection Rules** | `/detection` | Platform | Detection Rule Metadata | **GOVERN** |
| **Scenarios** | `/scenarios` | Platform | Scenario Content & Verification | **GOVERN** |

---

## Navigation & Drill-Down Model

Navigation follows two primary interaction vectors:

1. **Top-Down Drill-Down (Vertical Traversal):**
   An analyst begins at the Platform level (Command Center), selects a high-risk Agent, enters a specific Session, and inspects an individual Event payload.

2. **Causal Evidence Traversal (Horizontal Traversal):**
   An analyst inspecting a Behavioral Finding jumps directly to its causing Behavioral Events, its resulting Risk Assessment, or its active Enforcement Decision.

---

## Design Rationale

Traditional administrative interfaces structure pages solely around backend database tables (e.g., "Agents Page", "Tools Page"). This service-centric IA forces security analysts to manually correlate IDs across disconnected pages.

The Two-Axis IA model structures information around the security lifecycle and analytical scope, reflecting how security operations teams actually investigate threats.

---

## Tradeoffs

- **Matrix Complexity:** Requires developers to maintain explicit route and relationship mappings across entity boundaries.
- **Deep Linking Requirements:** Requires robust URL query-parameter and route state management to support precise multi-axis deep links (e.g., `/sessions/sess-123?event=evt-456&tab=policy`).

---

## Dependencies

- Aligns with the Canonical Artifact Lifecycle in [ADR-014](../../adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md).
- Implemented via Navigation Architecture ([04-navigation-architecture.md](04-navigation-architecture.md)).

---

## Relationship to Other Architecture Documents

- Provides the structural foundation for Page Specifications ([08-page-specifications.md](08-page-specifications.md)) and Investigation Graph ([06-investigation-graph.md](06-investigation-graph.md)).

---

## Future Evolution

When Multi-Agent Governance ([ADR-021](../../adr/ADR-021-multi-agent-governance.md)) is implemented, the vertical scope axis will expand upward to include **Agent Group / Mesh Level** topology scope.
