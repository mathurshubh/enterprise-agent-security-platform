# ADR-020: Agent Security Operations (AgentSecOps)

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-020 Review)
- Implementation: Deferred (No production code modified; technology-agnostic operational control plane architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established the strategic vision for governing multi-step autonomous AI agent behavior over extended execution lifespans.

[ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) defined non-blocking telemetry event emission.

[ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md) established the append-only security evidence repository.

[ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md) defined deterministic sequence analysis producing **Behavioral Findings**.

[ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md) defined cumulative risk scoring producing **Behavioral Risk Assessments** and **Current Behavioral Risk State**.

[ADR-019: Behavioral Enforcement Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md) defined policy mapping producing **Behavioral Enforcement Decisions** and **Current Enforcement State**.

To enable enterprise security operations center (SOC) teams, security analysts, and compliance officers to observe, investigate, govern, approve, audit, and operate autonomous AI agents at enterprise scale, the platform requires an operational governance architecture—**Agent Security Operations (AgentSecOps)**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

AgentSecOps is strictly a deterministic, compiled operational control plane. The LLM has no access, authority, or involvement in operational case management, analyst annotations, human approvals, or incident workflows.

---

# Problem Statement

The Behavioral Intelligence pipeline (ADR-015 through ADR-019) produces rich security telemetry, threat findings, risk assessments, and enforcement decisions. However, raw security evidence alone does not constitute an operational security organization.

Without a dedicated AgentSecOps architecture:

- **Lack of SOC Operational Visibility:** Security analysts would lack centralized visibility into active agent sessions, high-risk agent populations, and behavioral threat timelines.
- **Absence of Human-in-the-Loop Workflows:** Automated hold enforcement decisions (ADR-019) would have no structured mechanism for human review, release, or approval.
- **Conflation of Operational State and Audit Evidence:** Allowing analyst notes, incident statuses, or investigation tags to mutate underlying telemetry or findings would corrupt historical evidence immutability.
- **Un-Audited Operator Interventions:** Manual overrides or session releases executed outside an auditable operational control plane would create severe enterprise compliance vulnerabilities.

Therefore, the platform requires a dedicated AgentSecOps operational governance layer.

---

# Architectural Direction

The platform introduces **Agent Security Operations (AgentSecOps)** as the operational governance control plane operating within the Deterministic Platform Zone:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Behavioral Intelligence Pipeline                     │
│  Events (ADR-016) ──> Findings (ADR-017) ──> Risk State (ADR-018)     │
│                   ──> Enforcement Decisions (ADR-019)                   │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Immutable Security Artifacts Stream)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Runtime Security Pipeline                            │
│                                   │                                     │
│                                   ▼ (Enforcement Outcomes Emitted)      │
│                  Enforcement Outcomes                                   │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Outcome Stream)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AgentSecOps Control Plane                           │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Ingestion & Context  │──>│ Investigation & Replay Harness         │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Incident Case Management & Annotations │  │
│                             └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Manual Approval & Governance Broker    │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Audited Analyst Governance Actions)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Enterprise Security SOC Analysts                      │
└─────────────────────────────────────────────────────────────────────────┘
```

AgentSecOps answers one question:

> **"How do enterprise security teams observe, investigate, govern, approve, audit, and operate AI agents at enterprise scale?"**

---

# Core Philosophy & Architectural Hierarchy

Behavioral Intelligence answers *"What happened?"*; AgentSecOps answers *"What should enterprise operators do with this information?"*.

The complete single-responsibility progression across the platform is established as:

$$\text{Behavioral History (ADR-016)} \longrightarrow \text{Detection Context (ADR-017)} \longrightarrow \text{Behavioral Findings (ADR-017)} \longrightarrow \text{Risk Context (ADR-018)} \longrightarrow \text{Behavioral Risk Assessment (ADR-018)} \longrightarrow \text{Current Behavioral Risk State (ADR-018)} \longrightarrow \text{Enforcement Context (ADR-019)} \longrightarrow \text{Behavioral Enforcement Decision (ADR-019)} \longrightarrow \text{Current Enforcement State (ADR-019)} \longrightarrow \text{Runtime Security Pipeline} \longrightarrow \text{Enforcement Outcome} \longrightarrow \text{AgentSecOps} \longrightarrow \text{Enterprise Security Teams}$$

AgentSecOps consumes security artifacts generated by lower layers; it never performs threat detection, risk calculation, or direct request authorization.

---

# Architectural Principles

1. **Complete Operational Visibility:** Every behavioral event, threat finding, risk assessment, enforcement decision, and outcome must be fully observable and traceable by authorized security operators.
2. **Strict Evidence Immutability:** AgentSecOps operations (case assignments, analyst annotations, incident tagging) create operational governance artifacts. They **never** mutate, overwrite, or delete underlying Behavioral Events (ADR-016), Findings (ADR-017), Risk Assessments (ADR-018), or Enforcement Decisions (ADR-019).
3. **Auditable Operator Governance:** Every manual analyst intervention—including session releases, approval grants, and risk acknowledgments—is explicitly logged as an auditable operational action.
4. **Deterministic Forensic Replay:** Investigation workbenches rely on ADR-016 to reproduce exact, bit-identical session execution timelines for forensic auditing.
5. **Human Governance Primacy:** Human operators may approve, acknowledge, release, escalate, or annotate security state. Human operators cannot alter historical evidence.
6. **Separation of Operations and Enforcement:** AgentSecOps provides operational governance interfaces; physical interception of live request calls remains strictly within the Runtime Security Pipeline.

---

# Design Constraints

AgentSecOps observes strict scope limits:

- **Must Not Produce Telemetry:** Raw telemetry capture is owned exclusively by ADR-015.
- **Must Not Store Raw Events:** Persistence of canonical telemetry events is owned by ADR-016.
- **Must Not Scan Detection Rules:** Threat sequence evaluation is owned by ADR-017.
- **Must Not Compute Risk Scores:** Risk score aggregation and decay are owned by ADR-018.
- **Must Not Generate Enforcement Decisions:** Policy-driven decision generation is owned by ADR-019.
- **Must Not Perform Request Authorization:** Single-request RBAC and permission enforcement are owned by the Runtime Security Pipeline.
- **Must Not Perform LLM Reasoning:** Incident workflows and analyst operations must remain strictly non-LLM based.
- **Technology-Agnostic Design:** Defines operational concepts, investigation workflows, artifact schemas, and trust boundaries without mandating specific SIEM software, dashboard frameworks, or database technologies.

---

# Decision

The platform adopts **Agent Security Operations (AgentSecOps)** as the canonical operational governance control plane for enterprise AI agents.

This decision establishes seven core operational capabilities:

1. **Enforcement Outcome Tracking Architecture:** Execution reporting for enforcement decisions.
2. **Transient Investigation Context Abstraction:** Ephemeral, derived workspace for analyst investigations.
3. **Operational Artifact Schema:** Canonical definitions for Cases, Incidents, Investigations, Annotations, and Reports.
4. **Manual Governance Workflow Model:** Structured analyst actions (Acknowledge, Assign, Release, Escalate).
5. **Human Approval Model:** Audited approval workflow mapping manual sign-offs to pipeline execution.
6. **Incident Case Lifecycle:** Structured state machine for SOC case management.
7. **Operational Metrics & Observability Taxonomy:** Standardized metrics hierarchy for enterprise AI governance.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns single-request authorization, policy execution, tool execution, and emitting **Enforcement Outcomes**. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async telemetry emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, session timelines, and replay queries. |
| **Behavioral Detection Engine (ADR-017)** | Owns stateful rule evaluation, sequence analysis, and Behavioral Findings generation. |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative risk scoring, score weighting, decay, and Behavioral Risk Assessments. |
| **Behavioral Enforcement Engine (ADR-019)** | Owns policy overrides and Behavioral Enforcement Decisions. |
| **AgentSecOps Control Plane (ADR-020)** | Owns operational visibility, SOC workflows, investigation replay, case management, human approvals, and operational reports. |
| **Behavioral Governance (Future ADRs)** | Owns enterprise policy definitions operating on operational metrics. |

---

# Detailed Architectural Specifications

## 1. Enforcement Outcome Architecture

When the Runtime Security Pipeline receives a `Current Enforcement State` from ADR-019 and applies it to a live request, it emits a canonical **Enforcement Outcome**:

- `APPLIED`: The enforcement decision was successfully enforced (e.g., tool call blocked or agent suspended).
- `DEFERRED`: The enforcement action was deferred pending asynchronous human approval (`REQUIRE_APPROVAL`).
- `FAILED`: The enforcement action encountered a runtime pipeline execution failure.
- `REJECTED`: The enforcement decision was rejected by active request-level security invariants.
- `EXPIRED`: An active hold decision expired before human intervention occurred.
- `CANCELLED`: The enforcement action was manually cancelled by an authorized SOC operator.

Enforcement Outcomes provide feedback to AgentSecOps, closing the loop between decision (ADR-019) and execution.

## 2. Investigation Context

To support deep-dive forensic analysis without mutating stored evidence, AgentSecOps constructs a transient **Investigation Context**:

- **Ephemeral & Read-Only:** Derived, transient workspace assembled for analyst investigation sessions.
- **Derived from Immutable Artifacts:** Assembled from Behavioral Events (ADR-016), Findings (ADR-017), Risk Assessments (ADR-018), Enforcement Decisions (ADR-019), and Outcomes.
- **Non-Persisted:** Is not written back into the Behavioral Event Store.
- **No State Mutation:** Cannot modify underlying telemetry or historical security evidence.

Conceptually, the Investigation Context encapsulates session timelines, correlated findings, risk score evolution graphs, enforcement decision histories, analyst annotations, human approval logs, and multi-tenant context (`tenant_id`).

## 3. Operational Artifact Taxonomy

AgentSecOps defines eight canonical operational governance artifacts:

1. **Investigation:** A forensic replay session mapping chronological events, findings, and risk trajectories for an agent.
2. **Incident:** An escalated security event representing a verified policy breach or threat sequence.
3. **Case:** A structured SOC ticket tracking assignment, investigation progress, and remediation.
4. **Analyst Annotation:** An immutable, timestamped note attached to a Case by a human operator.
5. **Manual Approval:** An audited governance artifact representing a human sign-off to release a held session.
6. **Operational Report:** Summary of agent population activity, finding frequency, and enforcement actions over a time window.
7. **Compliance Report:** Auditable evidence report formatted for regulatory compliance verification.
8. **Security Timeline:** Combined visual sequence of events, findings, risk escalations, and operator actions.

## 4. Manual Governance Workflows

Authorized SOC analysts perform manual governance through eight structured operational actions:

- `ACKNOWLEDGE`: Mark a Behavioral Finding or alert as reviewed by an analyst.
- `ASSIGN`: Assign an active Incident Case to a specific security operator or team.
- `INVESTIGATE`: Launch an Investigation Context and forensic replay harness for a session.
- `ANNOTATE`: Attach a immutable analyst annotation to an active Case.
- `APPROVE`: Issue a Manual Approval to release a session held by a `REQUIRE_APPROVAL` decision.
- `RELEASE`: Manually de-escalate an active `Hold Session` or `Restrict Capability` state.
- `ESCALATE`: Escalate an Incident Case to higher-tier incident response teams.
- `CLOSE`: Formally close a Case following remediation verification.

> **Operational Governance Invariant**  
> Manual governance actions create new operational artifacts (Annotations, Approvals, Case State updates). They **never** edit or delete underlying Behavioral Events (ADR-016), Findings (ADR-017), or Risk Assessments (ADR-018).

## 5. Human Approval Model

When Behavioral Enforcement (ADR-019) issues a `REQUIRE_APPROVAL` decision, live tool execution is held by the Runtime Security Pipeline. The human approval workflow proceeds as follows:

```text
Behavioral Enforcement Decision (REQUIRE_APPROVAL - ADR-019)
        ↓
Pipeline Holds Execution (DEFERRED Outcome)
        ↓
AgentSecOps Displays Approval Request (ADR-020)
        ↓
Analyst Issues Manual Approval Artifact (ADR-020)
        ↓
Runtime Security Pipeline Resumes Execution
```

A **Manual Approval** is an operational governance artifact created by a human. It is **not** an enforcement decision or authorization check; it serves as an audited release token consumed by the Runtime Security Pipeline to proceed with execution.

## 6. Case Lifecycle

SOC Incident Cases transition through a five-stage state machine:

```text
Created ──> Assigned ──> Investigating ──> Resolved ──> Closed
```

1. **Created:** Case automatically generated following a `HIGH` or `CRITICAL` risk threshold breach or manual analyst creation.
2. **Assigned:** Case assigned to a primary SOC analyst or owner group.
3. **Investigating:** Analyst actively reviewing Investigation Context and forensic replay timelines.
4. **Resolved:** Containment verified and remediation actions executed.
5. **Closed:** Case closed and archived alongside session audit records.

## 7. Operational Metrics Taxonomy

AgentSecOps establishes an enterprise metrics hierarchy across eight operational categories:

1. **Agent Activity Metrics:** Active sessions, total tool calls, agent population velocity.
2. **Behavioral Findings Metrics:** Finding frequency by category, rule hit rates, detection confidence distribution.
3. **Risk Distribution Metrics:** Session risk score trends, high-risk agent counts, risk escalation velocity.
4. **Enforcement Statistics:** Enforcement decision breakdown (`OBSERVE`, `HOLD`, `SUSPEND`), action success rates.
5. **Investigation Workload:** Active case counts, mean time to acknowledge (MTTA), mean time to resolve (MTTR).
6. **Approval Latency:** Average hold duration for human approval workflows.
7. **Policy Effectiveness:** Policy hit rates, near-miss frequency, override distribution.
8. **Tenant Posture:** Multi-tenant risk and compliance posture metrics (`tenant_id`).

---

# Trust Boundaries & Access Model

AgentSecOps operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│               Behavioral Intelligence Subsystem                         │
│  Events (ADR-016) │ Findings (ADR-017) │ Risk (ADR-018) │ Dec (ADR-019)  │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Read-Only Security Artifacts - Tenant Isolated)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AgentSecOps Control Plane                           │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │   Operational Visibility, Replay Harness & Case Management        │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Manual Approvals & Release Tokens)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Runtime Security Pipeline                             │
│         (Enforces Manual Approvals & Emits Outcomes)                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary Guarantees

- **Read Access:** Reads immutable events, findings, risk assessments, decisions, and outcomes. Cannot modify historical security evidence.
- **Write Access:** Writes operational artifacts (Cases, Annotations, Reports, Manual Approvals).
- **Multi-Tenant Isolation:** All operational views, dashboards, cases, and investigation contexts enforce strict multi-tenant boundaries (`tenant_id`). Analysts cannot view cross-tenant operational data.
- **No Direct Request Authorization:** AgentSecOps does not bypass RBAC or grant baseline tool permissions; manual approvals only release held session overrides within the Runtime Security Pipeline.

---

# Availability & Fail-Operational Philosophy

AgentSecOps adheres to a fail-operational philosophy:

> **AgentSecOps Availability Philosophy**  
> AgentSecOps provides operational visibility, SOC workflows, and manual approvals. If the AgentSecOps control plane experiences an unexpected component failure or UI outage, the Runtime Security Pipeline, Behavioral Detection, Behavioral Risk Engine, and Behavioral Enforcement Engine continue operating with 100% functionality. Baseline Zero Trust security enforcement and automated containment rules remain active. Only operational visibility and manual human approvals become temporarily degraded.

---

# Benefits

- **Enterprise SOC Empowerment:** Equips security teams with specialized visibility, investigation replay tools, and case management for autonomous AI agents.
- **Audited Human-in-the-Loop Governance:** Provides structured, compliant approval workflows for high-risk tool execution holds.
- **Preserves Evidence Integrity:** Complete separation between operational artifacts (notes, cases) and immutable security evidence (events, findings).
- **End-to-End Governance Closure:** Closes the loop from telemetry generation to operational SOC remediation.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Operational Artifact Volume:** Maintaining cases, annotations, and compliance reports requires storage management alongside telemetry data.
- **Approval Latency:** Requiring human sign-off on held sessions introduces latency dependent on SOC analyst availability (mitigated by automated hold expiration timeouts).

## Alternatives Considered

### Option A: Embed Operational Workflows inside SIEM/External Tools
Rely entirely on external third-party SIEM dashboards without defining an in-platform operational control plane architecture.
- **Rejected:** External SIEMs cannot execute platform-native human approval workflows (`REQUIRE_APPROVAL`), forensic replay harnesses (ADR-016), or agent-specific session holds.

### Option B: Allow Analysts to Edit Historical Findings
Permit SOC analysts to alter or delete false-positive findings directly in the findings store.
- **Rejected:** Violates Zero Trust auditability and forensic integrity. False positives are managed by adding analyst annotations and closing cases, never by mutating evidence records.

### Option C: Use LLMs to Automate SOC Case Management
Deploy an LLM ("SOC analyst agent") to auto-close cases and issue manual approvals without human intervention.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). Human approvals and case resolutions must remain strictly human-driven or deterministic code.

---

# Scope

### In Scope (ADR-020)
- AgentSecOps control plane architecture and operational pipeline.
- Enforcement Outcome tracking model.
- Transient Investigation Context abstraction.
- Eight canonical operational governance artifacts and manual governance actions.
- Human approval workflow model and five-stage Case lifecycle.
- Operational metrics hierarchy across eight categories.
- Read-only trust boundaries and multi-tenant isolation.
- Fail-operational availability philosophy.

### Out of Scope (Deferred to Future ADRs)
- **Telemetry Emission:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Event Persistence:** Owned by [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md).
- **Detection Rules:** Owned by [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md).
- **Risk Scoring:** Owned by [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md).
- **Enforcement Decisions:** Owned by [ADR-019: Behavioral Enforcement Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md).
- **Multi-Agent Governance:** Owned by [ADR-021: Multi-Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-021-multi-agent-governance.md).

---

# Consequences

## Positive
- Completes the operational control plane for enterprise AI security teams.
- Establishes auditable human-in-the-loop approval workflows for high-risk actions.
- Preserves 100% evidence immutability while giving analysts rich operational tools.

## Negative
- Requires maintaining operational case data alongside telemetry storage.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to human operator governance and audited approval workflows.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; operational workflows are strictly non-LLM, human/deterministic code.
- **Principle 3 – Deterministic Security Enforcement:** Preserved; human approvals serve as explicit release tokens consumed by deterministic pipeline controls.
- **Principle 4 – Explicit Trust Boundaries:** Enforced via read-only evidence access and isolated operational artifact creation.
- **Principle 8 – Complete Auditability:** Fully realized through complete traceability from SOC case actions back to raw event IDs.

---

# Related Documents

- [ADR-001: Zero Trust Security Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-001-zero-trust-security-model.md)
- [ADR-002: LLM as Untrusted Intent Parser](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-002-llm-untrusted-intent-parser.md)
- [ADR-004: Deterministic Security Pipeline](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-004-deterministic-security-pipeline.md)
- [ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md)
- [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md)
- [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md)
- [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md)
- [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md)
- [ADR-019: Behavioral Enforcement Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md)
