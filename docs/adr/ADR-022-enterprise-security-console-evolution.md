# ADR-022: Enterprise Security Console Evolution

- **Status:** Accepted
- **Date:** 2026-07-25
- **Deciders:** Enterprise Agent Security Platform
- **Supersedes:** ADR-009 Enterprise Security Console (Architectural Evolution)
- **Superseded by:** None

---

# Context

[ADR-008: Enterprise Management API](ADR-008-enterprise-management-api.md) established the read-only management plane exposing platform state outside the Runtime Security Boundary.

[ADR-009: Enterprise Security Console](ADR-009-enterprise-security-console.md) established the baseline React/Vite/Tailwind frontend technology stack and single-page application (SPA) shell. While ADR-009 defined the technology stack, the user interface architecture required evolution to support operational security workflows.

[ADR-014](ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) through [ADR-021](ADR-021-multi-agent-governance.md) established the comprehensive Behavioral Intelligence architecture, including non-blocking telemetry, append-only event persistence, stateful threat detection, cumulative risk scoring, dynamic enforcement overrides, AgentSecOps incident workflows, and multi-agent governance.

The original frontend implementation (v0.9.0–v0.11.0) represented **platform inventory** (listing agents, tools, rules, events, scenarios) rather than **platform operations**. While sufficient for basic platform metadata inspection, a static inventory layout cannot support enterprise security operations, real-time alert triage, human-in-the-loop approval workflows, or forensic session replay.

To bridge the gap between the advanced backend architecture (ADR-014–ADR-021) and the user interface, the platform requires an architectural evolution of the Enterprise Security Console.

The foundational platform security invariants remain absolute:

> **The LLM is an untrusted intent parser.**
> **All security decisions remain 100% deterministic and backend-enforced.**

The console remains strictly outside the Runtime Security Boundary. It does not evaluate policies, calculate risk scores, or execute tools.

---

# Authority

This Architecture Decision Record becomes the **canonical frontend architecture** for the Enterprise Agent Security Platform beginning with version `v0.12.0`.

All future frontend capabilities, page additions, component designs, and state management implementations must extend this architecture rather than introducing parallel interaction models, redundant layout structures, or client-side security evaluation logic.

---

# Decision Drivers

The architectural evolution is governed by seven core decision drivers:

1. **Preserve Zero Trust Boundaries:** Maintain complete isolation between the untrusted browser client and the deterministic runtime security pipeline ([ADR-001](ADR-001-zero-trust-security-model.md)).
2. **Preserve Deterministic Security:** Ensure all authorization, threat detection, risk scoring, and containment decisions remain backend-owned ([ADR-002](ADR-002-llm-untrusted-intent-parser.md), [ADR-004](ADR-004-deterministic-security-pipeline.md)).
3. **Backend Remains Source of Truth:** Prohibit client-side calculation or fabrication of security state ([ADR-008](ADR-008-enterprise-management-api.md)).
4. **Align Frontend with Behavioral Intelligence:** Map the user interface directly to the Canonical Artifact Lifecycle established in [ADR-014](ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md).
5. **Support Enterprise Security Operations:** Enable SOC analysts to triage alerts, review held sessions, and conduct evidence-first investigations ([ADR-020](ADR-020-agent-security-operations.md)).
6. **Maintain Incremental Delivery:** Ensure all frontend changes are strictly additive with zero URL breakage ([AGENTS.md](../../AGENTS.md)).
7. **Ensure Long-Term Stability:** Establish a navigation and information architecture capable of absorbing future capabilities through v1.0.0 without structural rewrites.

---

# Problem Statement

The legacy frontend architecture suffered from five operational deficits because it represented platform inventory rather than platform operations:

1. **Operational Blindness:** Security analysts had no centralized work surface indicating which active sessions or behavioral threats required immediate intervention.
2. **Investigation Fragmentation:** Security artifacts (events, findings, risk scores, enforcement decisions) were displayed in disconnected tables without causal hyperlinking, forcing analysts to manually correlate string IDs.
3. **Approval Deadlock:** The Behavioral Enforcement Engine ([ADR-019](ADR-019-behavioral-enforcement-engine.md)) can hold agent sessions pending human review (`REQUIRE_APPROVAL`), but the UI lacked an interactive approval workflow for reviewing and releasing held sessions.
4. **Temporal Blindness:** Static tabular layouts hid the chronological evolution of multi-step agent behavior, making temporal risk accumulation invisible.
5. **Governance Opacity:** Analysts could not visually trace whether a containment action correctly followed policy threshold rules.

---

# Decision

The platform adopts the **Enterprise Security Console Evolution Architecture** for version `v0.12.0` through `v1.0.0`.

This decision establishes seven core architectural evolution mandates:

1. **Workflow-Centric Navigation Architecture:** Replaces entity-based sidebar lists with three operational modes comprising nine canonical routes:
   - `MONITOR` — Command Center (`/`), Approval Queue (`/approvals`).
   - `INVESTIGATE` — Sessions (`/sessions`), Findings (`/findings`), Audit Trail (`/audit`).
   - `GOVERN` — Agents (`/agents`), Tools (`/tools`), Detection Rules (`/detection`), Scenarios (`/scenarios`).

2. **Work-Oriented Command Center Landing:** Replaces static metric dashboards with a two-zone operational landing surface:
   - **Zone 1: Action Required Queue** (dominant top zone surfacing held sessions, high-severity findings, and review tasks).
   - **Zone 2: Operational Awareness** (supporting lower zone rendering overall posture metrics).

3. **Session Investigation Workspace as Central Experience:** Establishes the multi-panel workspace (`/sessions/:id`) anchored by a **Focal Behavioral Timeline** as the primary forensic environment for analyzing agent behavior.

4. **Canonical Investigation Graph Contract:** Formalizes the causal artifact chain (`Agent → Session → ToolInvocation → PolicyEvaluation → BehavioralEvent → Finding → RiskAssessment → EnforcementDecision → AuditEvent → Case`) as a first-class architectural contract governing entity models, navigation hyperlinks, and evidence traversal.

5. **Two-Axis Information Architecture Model:** Structures all console views along two orthogonal dimensions: **Lifecycle Progression** ($\text{Registry} \to \text{Audit}$) $\times$ **Scope Granularity** ($\text{Platform} \to \text{Event}$).

6. **Audited Operator Write Command Pattern:** Restricts client-side write operations strictly to governance commands (session approvals/rejections, incident case updates, analyst notes). Prohibits optimistic UI state mutations for security-critical writes.

7. **Backend-Gated Four-Phase Roadmap:** Gates frontend phase delivery behind backend API readiness (Phase 1: Existing APIs $\to$ Phase 2: Behavioral Intelligence $\to$ Phase 3: Investigation Workspace $\to$ Phase 4: Real-Time Operations).

---

# Non-Goals

This architectural decision intentionally excludes the following non-goals:

- **Does NOT redesign backend architecture:** Preserves all backend service boundaries, API contracts, and domain models.
- **Does NOT move security decisions into the frontend:** Authorization, policy evaluation, detection, risk scoring, and response selection remain 100% backend-enforced.
- **Does NOT introduce speculative APIs:** All specified frontend data contracts correspond strictly to existing or proposed backend ADR specifications (ADR-014–ADR-021).
- **Does NOT replace the frontend technology stack:** Retains the React 19, TypeScript, Vite, Tailwind CSS v4, and React Router v7 stack established in [ADR-009](ADR-009-enterprise-security-console.md).
- **Does NOT redefine trust boundaries:** The client application remains completely outside the Runtime Security Boundary.

---

# Alignment with Existing ADRs

This evolution directly supports and extends previous Architecture Decision Records:

- **ADR-001 (Zero Trust) & ADR-002 (LLM Untrusted):** Preserves strict trust boundaries; client UI remains untrusted; all security logic remains deterministic and backend-owned.
- **ADR-008 (Management API) & ADR-009 (Security Console):** Preserves the read-only management boundary; retains the React/Vite/Tailwind tech stack defined in ADR-009 while evolving its operational architecture.
- **ADR-014 (Behavioral Intelligence Suite):** Implements the Canonical Artifact Lifecycle as the structural foundation of the Information Architecture.
- **ADR-015 to ADR-019 (Telemetry, Event Store, Detection, Risk, Enforcement):** Surfaces behavioral events, findings, risk evolution trajectories, and active enforcement containment states in the UI.
- **ADR-020 (AgentSecOps):** Implements the human-in-the-loop Approval Queue, evidence chain navigation, and incident investigation workflows.
- **ADR-021 (Multi-Agent Governance):** Establishes the architectural home for multi-agent delegation topology views under `GOVERN`.

---

# Related Documents & Normative References

The documentation package under `docs/architecture/enterprise-security-console/` serves as the **normative implementation reference** for this ADR:

- [01-overview.md](../architecture/enterprise-security-console/01-overview.md) — Console Purpose, Personas, and Operational Questions.
- [02-design-principles.md](../architecture/enterprise-security-console/02-design-principles.md) — The 10 Permanent Governing Design Principles.
- [03-information-architecture.md](../architecture/enterprise-security-console/03-information-architecture.md) — Two-Axis IA Model.
- [04-navigation-architecture.md](../architecture/enterprise-security-console/04-navigation-architecture.md) — Navigation Hierarchy and Route Structure.
- [05-operational-model.md](../architecture/enterprise-security-console/05-operational-model.md) — Command Center & Action Required Queue.
- [06-investigation-graph.md](../architecture/enterprise-security-console/06-investigation-graph.md) — Canonical Investigation Graph Contract.
- [07-session-investigation-workspace.md](../architecture/enterprise-security-console/07-session-investigation-workspace.md) — Session Workspace Layout & Panels.
- [08-page-specifications.md](../architecture/enterprise-security-console/08-page-specifications.md) — Detailed 9-Page Specifications.
- [09-ui-component-architecture.md](../architecture/enterprise-security-console/09-ui-component-architecture.md) — Reusable Components & Untrusted Content Isolation.
- [10-data-flow.md](../architecture/enterprise-security-console/10-data-flow.md) — Data Flow, TanStack Query, and Audited Writes.
- [11-implementation-roadmap.md](../architecture/enterprise-security-console/11-implementation-roadmap.md) — Four-Phase Backend-Gated Delivery Plan.

If implementation guidance in the specification files conflicts with this ADR, **this ADR takes precedence**.

---

# Migration Strategy

1. **Phase 1 (v0.12.0 — Zero Backend Changes):**
   - Restructure `Sidebar.tsx` into `MONITOR`, `INVESTIGATE`, `GOVERN` sections.
   - Expose orphaned routes `/sessions` and `/scenarios` explicitly in the navigation sidebar.
   - Implement basic single-panel `/sessions/:id` detail page.
   - Refactor reusable `<MetricCard>` and `<SearchBar>` components into `src/components/common/`.
   - All existing URL paths preserved without breakage.

2. **Phase 2 (v0.13.0 — Behavioral Intelligence):**
   - Deploy Action Required Work Queue in Command Center when `/approvals/pending` and `/findings` APIs ship.
   - Build `/approvals` and `/findings` pages.
   - Integrate TanStack Query caching layer.

3. **Phase 3 (v0.14.0 — Investigation Workspace):**
   - Build multi-panel Session Investigation Workspace (`/sessions/:id`) anchored by Focal Behavioral Timeline.

4. **Phase 4 (v1.0.0 — Enterprise Operations):**
   - Integrate SSE streaming, SOC incident cases (`/cases`), forensic replay controls, and agent delegation topology graph (`/agents/topology`).

---

# Consequences

## Positive
- Establishes a stable, production-grade frontend foundation through `v1.0.0` without requiring future navigation redesigns.
- Transforms the console from passive inventory representation into a high-throughput, workflow-centric security operations environment.
- Directly resolves operational blindness, investigation fragmentation, approval deadlock, temporal blindness, and governance opacity.
- Establishes strict visual isolation around untrusted prompt and LLM outputs, preventing analyst spoofing.
- Provides a clear four-phase engineering roadmap with zero URL breakage.

## Negative / Risks
- Phase 2+ features depend strictly on backend API readiness.
- Synchronizing selection across 6 panels in the Session Investigation Workspace increases frontend state complexity.

## Neutral
- Requires frontend developers to adhere to the 10 Governing Design Principles and the Canonical Investigation Graph contract for all future PRs.
