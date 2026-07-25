# 07 — Session Investigation Workspace

## Purpose

This document specifies the **Session Investigation Workspace** (`/sessions/:id`), the primary forensic environment of the Enterprise Security Console.

---

## Scope

Governs the deep-dive investigation interface for inspecting individual Enterprise Agent sessions, multi-panel coordination, temporal event playback, and evidence chain analysis.

---

## Workspace Layout & Coordinated Panels

The workspace replaces static session tables with a coordinated, multi-panel forensic environment anchored by a **Focal Behavioral Timeline**:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Session sess-9824 | Agent: Financial-Bot-02 | Risk: HIGH (82/100)       │
│ Status: HELD (Require Approval) | Duration: 14m 22s | Tenant: corp-finance   │
├─────────────────────────────────────────────────────────────────────────────────┤
│ FOCAL PANEL: BEHAVIORAL TIMELINE (Always Visible Anchor)                        │
│ 14:02:00      14:05:00      14:08:00      14:11:00      14:14:00            │
│ --[Invoke]------[Invoke]------[Finding!]------[Risk Spiked]------[HELD!]-----> │
│                  ▲ (Selected: 14:08:12 - SensitiveFileAccessRule)                │
├───────────────────────────────┬─────────────────────────────────────────────────┤
│ PANEL A: EVENT DETAIL         │ PANEL B: EVIDENCE CHAIN                         │
│ Event ID: evt-3301            │ Upstream Cause:                                 │
│ Tool: file_read               │  └─ BehavioralEvent (14:08:10)                  │
│ Resource: /secrets/keys.pem   │      └─ ToolInvocation (file_read)              │
│ Parameters: { mode: "raw" }   │ Downstream Impact:                              │
│ Decision: REQUIRE_APPROVAL    │  └─ Risk Assessment (Score: 82)                 │
│                               │      └─ Enforcement: HELD SESSION               │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ PANEL C: TOOL ACTIVITY        │ PANEL D: RISK EVOLUTION TRAJECTORY              │
│ 14:02:01 dir_list [/home] OK  │ 100 ┤                                           │
│ 14:05:22 file_read [notes] OK │  80 ┤                    ┌───── (Score: 82)   │
│ 14:08:12 file_read [keys] HELD│  40 ┤        ┌───────────┘                      │
│                               │   0 └────────┴───────────────────────────       │
└───────────────────────────────┴─────────────────────────────────────────────────┘
```

---

## Panel Specifications

### 1. Focal Panel: Behavioral Timeline (Anchor Panel — Always Visible)
- **Visual Representation:** Horizontal interactive timeline plotting events chronologically.
- **Event Mark Types:** Color-coded markers for Tool Invocation, Authorization Check, Behavioral Finding, Risk Score Change, and Enforcement Action.
- **Selection Coordination:** Clicking any timeline marker sets the **Active Selection Target** across all open workspace panels.

### 2. Panel A: Event Detail
- Renders full JSON payload, parameters, execution outcome, and timestamp for the selected timeline event.
- Integrates **Untrusted Content Isolation** styling for raw prompts or model outputs.

### 3. Panel B: Evidence Chain
- Visualizes the upstream causes and downstream impacts of the selected event along the Canonical Investigation Graph.
- Every node in the chain is hyperlinked for one-click focus switching.

### 4. Panel C: Tool Activity Sequence
- Dedicated sequential log of all tool execution requests, parameter targets, latency, and status (`ALLOW`, `DENY`, `HELD`).

### 5. Panel D: Risk Evolution Trajectory
- Interactive line graph plotting cumulative session risk score (0–100) over elapsed session time, annotating score jump points with triggering finding names.

### 6. Panel E: Policy & Authorization Trace
- Step-by-step evaluation trace showing which resource-aware policy rules ([ADR-006](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-006-resource-aware-authorization.md)) matched or denied the invocation.

### 7. Panel F: Enforcement Log
- Audit log of all containment actions applied to the session by the Behavioral Enforcement Engine ([ADR-019](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md)).

---

## Panel Coordination Architecture

All workspace panels subscribe to a shared React Context (`SessionWorkspaceContext`):

```typescript
export interface SessionWorkspaceState {
  sessionId: string;
  selectedEventId: string | null;
  selectedTimestamp: string | null;
  activePanels: PanelType[];
  isReplaying: boolean;
  playbackSpeed: number;
}
```

When an analyst clicks an event marker on the Behavioral Timeline, `selectedEventId` updates in context. Panel A updates its payload, Panel B re-renders the causal chain for that event, Panel C highlights the tool call, Panel D moves its vertical scrubber line to the timestamp, and Panel E shows the policy evaluation trace for that exact step.

---

## Design Rationale

Single-table details force analysts to constantly open modal popups, inspect payloads, close modals, and cross-reference timestamps.

The Session Investigation Workspace provides a **coordinated multi-panel environment** where selecting an event in one view instantly synchronizes all contextual panels. This increases SOC forensic triage speed by eliminating manual tab-switching.

---

## Tradeoffs

- **Screen Real Estate:** Multi-panel layouts require minimum display resolutions (1080p+ recommended). On smaller screens, panels stack or collapse into tabbed panels.
- **State Complexity:** Synchronizing selection across 6 panels requires clean context state management to prevent unnecessary component re-renders.

---

## Dependencies

- Gated by Phase 3 backend APIs (`GET /sessions/:id/events`, `GET /sessions/:id/timeline`).
- In Phase 1 & 2, `/sessions/:id` renders a simplified single-panel view using existing audit logs.

---

## Relationship to Other Architecture Documents

- Implements Principle 5 (Temporal First) and Principle 6 (Session-Centric Investigation) from [02-design-principles.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/enterprise-security-console/02-design-principles.md).
- Visualizes Investigation Graph links ([06-investigation-graph.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/enterprise-security-console/06-investigation-graph.md)).

---

## Future Evolution

In Phase 4 (Enterprise Operations), the workspace will integrate **Analyst Annotation** panels and **Playback Controls** (Play, Pause, Step-Forward, Step-Backward) for full forensic session replay ([ADR-020](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md)).
