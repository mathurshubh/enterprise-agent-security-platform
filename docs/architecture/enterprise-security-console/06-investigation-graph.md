# 06 — Investigation Graph

## Purpose

This document formalizes the **Canonical Investigation Graph** as a first-class architectural contract governing entity relationships, evidence-chain traversal, and navigation dependencies throughout the Enterprise Security Console.

---

## Scope

Governs TypeScript domain models (`frontend/src/types/`), evidence-chain navigation links, detail view relationships, and API contract joins across all console features.

---

## The Canonical Investigation Graph Contract

The Investigation Graph establishes the strict causal sequence of security artifacts generated during agent execution:

```text
Agent (ADR-003)
  └─ Session (ADR-003)
       └─ Tool Invocation (ADR-002)
            ├─ Policy Evaluation (ADR-006)
            └─ Behavioral Event (ADR-016)
                 └─ Behavioral Finding (ADR-017)
                      └─ Risk Assessment (ADR-018)
                           └─ Enforcement Decision (ADR-019)
                                ├─ Enforcement Outcome (ADR-020)
                                └─ Audit Event (ADR-004)
                                     └─ Case / Investigation (ADR-020)
```

---

## Architectural Rules of the Investigation Graph

### 1. Strictly Typed Causal Relationships
Every entity interface in `src/types/` MUST declare explicit references to its immediate upstream parent(s) and downstream child(ren). No entity exists as an isolated record.

```typescript
// Example Architectural Relationship Definitions
export interface BehavioralFinding {
  id: string;
  ruleName: string;
  severity: RiskTier;
  // Upstream Causal Links
  sessionId: string;
  contributingEventIds: string[];
  // Downstream Impact Links
  riskAssessmentId?: string;
}

export interface RiskAssessment {
  id: string;
  score: number;
  // Upstream Causal Links
  sessionId: string;
  contributingFindingIds: string[];
  // Downstream Impact Links
  enforcementDecisionId?: string;
}
```

### 2. Mandatory Hyperlink Traversal
Every UI component rendering a security artifact (e.g., table row, detail drawer, timeline marker, card) MUST render clickable hyperlink controls for all declared upstream and downstream entity IDs.

### 3. Bidirectional Navigation
An analyst MUST be able to navigate seamlessly in both directions along the graph:
- **Downstream Traversal (Cause → Effect):** `Tool Invocation → Behavioral Finding → Risk Assessment → Enforcement Decision → Audit Event`.
- **Upstream Traversal (Effect → Cause):** `Enforcement Decision → Triggering Risk Assessment → Contributing Findings → Behavioral Events → Original Tool Invocation`.

---

## Page Mapping Against the Investigation Graph

Every page in the console owns a specific node or sub-graph segment:

| Console View | Owned Node / Sub-Graph Segment | Upstream Traversal Target | Downstream Traversal Target |
|---|---|---|---|
| **Agents Page** | `Agent` Node | Platform Registry | `Sessions`, `Audit Events` |
| **Sessions Page** | `Session` Node | `Agent` | `Session Workspace` |
| **Session Workspace** | `Session → Event → Finding → Risk → Enforcement` | `Agent` | `Audit Events`, `Cases` |
| **Findings Page** | `Behavioral Finding` Node | `Behavioral Events`, `Session` | `Risk Assessment` |
| **Audit Trail** | `Audit Event` Node | `Enforcement Decision`, `Session` | Export SIEM / Compliance |
| **Approval Queue** | `Enforcement Decision` Node | `Risk Assessment`, `Session` | `Enforcement Outcome` |

---

## Design Rationale

Without a formal graph contract, UI components degrade into isolated views displaying unlinked string IDs (e.g., plain text `session_id: "sess-123"`). This forces analysts during active investigations to copy-paste strings across search bars, severely degrading triage velocity.

Formalizing the Canonical Investigation Graph as a first-class architectural contract guarantees that every ID rendered in the console is an interactive navigation node.

---

## Tradeoffs

- **Strict Type Requirements:** Backend API response DTOs must supply correlation identifiers (e.g., `finding_id` on risk assessments) to satisfy frontend type contracts.

---

## Dependencies

- Directly derives from the Canonical Artifact Lifecycle in [ADR-014](../../adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md).
- Powers the Evidence Chain panel in Session Investigation Workspace ([07-session-investigation-workspace.md](07-session-investigation-workspace.md)).

---

## Relationship to Other Architecture Documents

- Governs UI Component Architecture ([09-ui-component-architecture.md](09-ui-component-architecture.md)) and Data Flow ([10-data-flow.md](10-data-flow.md)).

---

## Future Evolution

When Multi-Agent Governance ([ADR-021](../../adr/ADR-021-multi-agent-governance.md)) is introduced, the Investigation Graph will introduce cross-agent delegation edges (`Delegation` node connecting Initiating Agent $A_I$ to Target Agent $A_T$).
