# ADR-019: Behavioral Enforcement Engine

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-019 Review)
- Implementation: Deferred (No production code modified; technology-agnostic enforcement architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established Behavioral Intelligence as an observational subsystem operating alongside the Runtime Security Pipeline to govern multi-step autonomous agent behavior over extended execution lifespans.

[ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) defined non-blocking telemetry event emission.

[ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md) established the append-only security evidence repository.

[ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md) defined deterministic threat pattern analysis producing immutable **Behavioral Findings**.

[ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md) defined cumulative risk scoring producing **Behavioral Risk Assessments** and active **Current Behavioral Risk State**.

To translate derived risk state into deterministic governance actions and policy overrides, the platform requires a dedicated decision engine—the **Behavioral Enforcement Engine**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

Behavioral Enforcement is strictly a deterministic, compiled platform capability. The LLM has no access, write authority, or influence over enforcement decisions, policy mapping, threshold evaluation, or containment actions.

---

# Problem Statement

Behavioral Risk (ADR-018) calculates cumulative risk scores and maintains active session posture. However, risk scoring alone does not change execution controls. Without a dedicated Behavioral Enforcement Engine:

- **Lack of Automated Containment:** High cumulative risk levels would remain purely analytical, failing to trigger automated session suspension, human approval holds, or capability restrictions.
- **Violation of Enforcement Boundaries:** Allowing risk evaluators or detection rules to directly block tool execution would pollute security boundaries and create un-auditable enforcement coupling.
- **Probabilistic Governance Risks:** Attempting to determine mitigation actions using LLMs or unexplainable AI models would introduce non-deterministic security responses, unauthorized agent terminations, and vulnerability to prompt injection.
- **Absence of Derived Enforcement State:** Security operations teams would lack a structured, immutable record of why specific containment actions were applied to an agent session.

Therefore, the platform requires a deterministic, policy-driven Behavioral Enforcement Engine.

---

# Architectural Direction

The platform introduces the **Behavioral Enforcement Engine** as a policy evaluation and decision subsystem operating within the Deterministic Platform Zone:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                 Behavioral Risk Engine (ADR-018)                        │
│                (Current Behavioral Risk State)                          │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Current Risk State Stream)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                Behavioral Enforcement Engine                            │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ State Ingestion      │──>│ Enforcement Context Assembly           │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Policy Mapping & Threshold Evaluator   │  │
│                             └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Enforcement Decision Generator         │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Enforcement Decisions & State)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Runtime Security Pipeline                              │
│       (Primary Execution & Single-Request Enforcement Boundary)         │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │ (ALLOW Only)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Secure Tool Execution Zone                           │
└─────────────────────────────────────────────────────────────────────────┘
```

The Behavioral Enforcement Engine answers one question:

> **"Given the current Behavioral Risk State and deterministic enterprise policy, what security action should the platform take?"**

---

# Critical Architectural Boundary

A foundational architectural boundary governs Behavioral Enforcement:

> **Behavioral Enforcement decides; the Runtime Security Pipeline executes.**

- **Behavioral Enforcement Engine (ADR-019) owns:** Response determination, policy mapping, threshold evaluation, escalation logic, containment decisions, and generating immutable Behavioral Enforcement Decisions.
- **Runtime Security Pipeline (Core Runtime) owns:** Request authorization, single-request policy evaluation, tool execution control, request blocking, and physically intercepting/halting live tool calls.

The Behavioral Enforcement Engine **cannot directly terminate tool code or mutate runtime memory**. It communicates deterministic enforcement decisions back to the Runtime Security Pipeline as active policy overrides. The Runtime Security Pipeline remains the sole component capable of affecting live execution.

---

# Analytical Progression Across Behavioral Intelligence

The end-to-end analytical pipeline across Behavioral Intelligence establishes a strict, single-responsibility progression:

$$\text{Behavioral History (ADR-016)} \longrightarrow \text{Detection Context (ADR-017)} \longrightarrow \text{Behavioral Findings (ADR-017)} \longrightarrow \text{Risk Context (ADR-018)} \longrightarrow \text{Behavioral Risk Assessment (ADR-018)} \longrightarrow \text{Current Behavioral Risk State (ADR-018)} \longrightarrow \text{Enforcement Context (ADR-019)} \longrightarrow \text{Behavioral Enforcement Decision (ADR-019)} \longrightarrow \text{Current Enforcement State (ADR-019)} \longrightarrow \text{Runtime Security Pipeline} \longrightarrow \text{Tool Execution}$$

Every stage owns exactly one responsibility. No responsibility overlap is permitted.

---

# Architectural Principles

1. **Deterministic Enforcement:** Enforcement decisions are strictly policy-driven and deterministic. Given an identical `Current Behavioral Risk State` and identical enterprise policy configuration, the Enforcement Engine must always produce identical enforcement decisions.
2. **Policy-Driven Governance:** Behavioral Enforcement executes enterprise security policies defined by platform administrators. It never invents policy rules, infers dynamic exceptions, or relies on probabilistic logic.
3. **Monotonic Enforcement Invariant:** Behavioral Enforcement may only **strengthen** execution restrictions (e.g., escalating from `OBSERVE` to `REQUIRE_APPROVAL` or `SUSPEND_AGENT`). It can never relax authorization, override a request-level policy denial, or bypass Zero Trust authorization checks.
4. **Complete Explainability:** Every enforcement decision must explicitly record the triggering risk assessment, applicable policy rule, evaluated thresholds, selected enforcement action, and justification.
5. **Replay Consistency:** Running the Enforcement Engine during forensic replay (ADR-016) produces the exact same sequence of enforcement decisions as live stream execution.
6. **Separation of Decision and Execution:** Behavioral Enforcement determines containment actions but relies on the Runtime Security Pipeline to intercept and enforce live requests.

---

# Design Constraints

The Behavioral Enforcement Engine observes strict scope limits:

- **Must Not Discover Threat Patterns:** Sequence analysis and threat detection are owned exclusively by ADR-017.
- **Must Not Calculate Risk Scores:** Risk score aggregation and temporal decay are owned exclusively by ADR-018.
- **Must Not Execute Tool Code:** Tool execution and sandbox containment are owned by the Secure Execution Zone.
- **Must Not Perform Request Authorization:** Single-request RBAC and permission checks are owned by `AuthorizationService`.
- **Must Not Perform LLM Reasoning:** Policy evaluation and mitigation mapping must remain strictly non-LLM based.
- **Technology-Agnostic Design:** Defines enforcement actions, decision schemas, lifecycle phases, and trust boundaries without mandating specific policy engines, message brokers, or vendor technologies.

---

# Decision

The platform adopts the **Behavioral Enforcement Engine** as the canonical governance decision architecture for Behavioral Intelligence.

This decision establishes seven core architectural capabilities:

1. **Deterministic Enforcement Pipeline Architecture:** Context assembly, policy mapping, and threshold evaluation.
2. **Transient Enforcement Context Abstraction:** Derived analytical view isolating policy evaluation.
3. **Behavioral Enforcement Decision Schema:** Standardized, immutable representation of governance decisions.
4. **Current Enforcement State Model:** Derived active posture consumed by the Runtime Security Pipeline.
5. **Enforcement Lifecycle:** Conceptual progression from generation to release and archival.
6. **Canonical Enforcement Action Taxonomy:** Seven standardized containment tiers.
7. **Deterministic Escalation Model:** Tiered risk-to-response escalation mappings.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns single-request authorization, policy checks, tool execution control, and physical enforcement. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async telemetry emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, session timelines, and replay queries. |
| **Behavioral Detection Engine (ADR-017)** | Owns stateful rule evaluation, sequence analysis, and Behavioral Findings generation. |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative risk scoring, score weighting, decay, and Behavioral Risk Assessments. |
| **Behavioral Enforcement Engine (ADR-019)** | Owns policy mapping, threshold evaluation, escalation, and **Behavioral Enforcement Decisions**. |
| **AgentSecOps Console (ADR-020)** | Owns enforcement monitoring, manual override workflows, and SOC dashboards. |
| **Behavioral Governance (Future ADRs)** | Owns enterprise policy definitions operating on enforcement state. |

---

# Detailed Architectural Specifications

## 1. Enforcement Pipeline Architecture

The enforcement pipeline evaluates risk posture through six sequential phases:

```text
Behavioral Risk State (ADR-018) ──> Enforcement Context ──> Policy Mapping ──> Threshold Evaluation ──> Enforcement Decision ──> Pipeline Override
```

1. **Risk State Ingestion:** Consumes active `Current Behavioral Risk State` published by ADR-018.
2. **Enforcement Context Assembly:** Constructs an ephemeral, read-only analytical view containing applicable policy rules, active thresholds, tenant boundaries, and escalation state.
3. **Policy Mapping:** Maps the current risk metrics to enterprise policy definitions configured for the target agent role.
4. **Threshold Evaluation:** Evaluates whether cumulative risk scores or severity counts breach configured containment thresholds.
5. **Enforcement Decision Generation:** Instantiates an immutable **Behavioral Enforcement Decision**.
6. **Pipeline Override Publishing:** Updates the active `Current Enforcement State` consumed by the Runtime Security Pipeline.

## 2. Enforcement Context

To establish a clean architectural abstraction separating risk posture from policy execution, the Enforcement Engine constructs a transient **Enforcement Context**:

- **Ephemeral & Read-Only:** Derived analytical view created solely for the duration of policy evaluation.
- **Derived from Risk State:** Constructed exclusively from `Current Behavioral Risk State` (ADR-018) and enterprise policy definitions.
- **Non-Persisted:** Never written back into the Behavioral Event Store (ADR-016) or Behavioral Findings (ADR-017).
- **No Historical Authority:** Not historical evidence; serves purely as a transient evaluation workspace.
- **No Direct State Mutation:** Cannot modify risk assessments, historical events, or telemetry.

Conceptually, the Enforcement Context encapsulates parameters such as active enterprise policies, risk threshold matrices, target session/agent identifiers, tenant isolation context (`tenant_id`), and historical escalation state.

## 3. Behavioral Enforcement Decision Schema & Concept

A **Behavioral Enforcement Decision** is a canonical, derived architectural artifact representing an evaluated governance action:

- **Metadata Envelope:**
  - `enforcement_id`: Unique UUID identifier for the enforcement decision.
  - `schema_version`: Version string of the active enforcement policy schema (e.g., `1.0`).
  - `timestamp`: UTC timestamp when the decision was generated.

- **Context Envelope:**
  - `agent_id`: Affected Enterprise Agent identifier.
  - `session_id`: Primary execution session identifier.
  - `tenant_id`: Multi-tenant organization identifier.

- **Decision Payload:**
  - `triggering_assessment_id`: Reference to the `assessment_id` (ADR-018) that triggered the decision.
  - `triggering_policy_id`: Identifier of the enterprise policy rule that fired.
  - `enforcement_action`: Selected containment category (e.g., `REQUIRE_APPROVAL`, `SUSPEND_AGENT`).
  - `severity_tier`: Escalation tier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `rationale`: Human-readable, deterministic explanation of the enforcement decision.
  - `execution_constraints`: Parameters governing the action (e.g., hold timeout duration, restricted tool list).

> **Enforcement Decision Immutability**  
> Once generated, a Behavioral Enforcement Decision is immutable. Decisions are derived historical evidence and must never be modified in place. Updated enforcement determinations (e.g., releasing a hold or escalating suspension) are represented by generating new enforcement decision records. This preserves deterministic replay, forensic integrity, and complete auditability.

## 4. Current Enforcement State vs. Enforcement Decision

The platform maintains a clear structural distinction between historical decisions and active state:

$$\text{Behavioral Risk State (ADR-018)} \longrightarrow \text{Behavioral Enforcement Decision (Immutable - ADR-019)} \longrightarrow \text{Current Enforcement State (Active Posture - ADR-019)}$$

- **Behavioral Enforcement Decision:** An immutable, timestamped historical record of a policy decision made at moment $T_k$. Preserved permanently in audit evidence.
- **Current Enforcement State:** A transient, derived posture object representing the active containment restrictions enforced on an ongoing session or agent. The Runtime Security Pipeline queries this state during single-request authorization checks.

## 5. Enforcement Lifecycle

Behavioral Enforcement Decisions and States progress through a conceptual lifecycle:

```text
Generated ──> Delivered ──> Applied ──> Released / Expired ──> Archived
```

1. **Generated:** Immutably instantiated following policy threshold evaluation.
2. **Delivered:** Published to the Runtime Security Pipeline as an active policy override.
3. **Applied:** Intercepted by the Runtime Security Pipeline to restrict live tool invocations.
4. **Released / Expired:** De-escalated via explicit administrator intervention or automated policy timeout.
5. **Archived:** Preserved alongside session audit records for compliance reporting.

## 6. Canonical Enforcement Actions Taxonomy

The Enforcement Engine evaluates seven standardized categories of containment actions:

1. **Observe:** Log heightened risk state without restricting tool execution.
2. **Notify:** Emit real-time security alert notifications to SOC channels (ADR-020).
3. **Require Human Approval:** Intercept tool calls matching specific capabilities and hold execution pending administrative sign-off.
4. **Hold Session:** Temporarily pause all agent execution requests across the session.
5. **Restrict Capability:** Dynamically revoke access to specific high-risk tool categories (e.g., blocking `network` tools while allowing `filesystem` reads).
6. **Suspend Agent:** Immediately suspend the Enterprise Agent identity, rejecting all subsequent tool requests across all sessions.
7. **Terminate Session:** Forcefully terminate the active execution session context and revoke session tokens.

## 7. Deterministic Escalation Model

Enforcement actions follow a progressive, deterministic escalation path mapped to cumulative risk levels:

```text
LOW (Observe / Notify) ──> MEDIUM (Require Approval) ──> HIGH (Restrict Capability / Hold) ──> CRITICAL (Suspend Agent / Terminate Session)
```

- **LOW Risk Tier:** `Observe` baseline activity and emit diagnostic telemetry.
- **MEDIUM Risk Tier:** Trigger `Notify` alerts and enforce `Require Human Approval` on sensitive capabilities.
- **HIGH Risk Tier:** Enforce `Restrict Capability` (revoking write/network access) and `Hold Session`.
- **CRITICAL Risk Tier:** Immediately trigger `Suspend Agent` and `Terminate Session`.

---

# Trust Boundaries & Access Model

The Enforcement Engine operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                 Behavioral Risk Engine (ADR-018)                        │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Read-Only Risk State - Tenant Isolated)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                Behavioral Enforcement Engine                            │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │         Deterministic Policy Mapping & Decision Engine            │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Enforcement Decisions & State)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Runtime Security Pipeline                             │
│         (Sole Component Executing Live Request Overrides)               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary & Execution Guarantees

- **Read Access:** Reads active `Current Behavioral Risk State` from ADR-018. Cannot modify risk assessments, findings, or telemetry.
- **Write Access:** Emits immutable **Behavioral Enforcement Decisions** and publishes active **Current Enforcement State** objects.
- **Multi-Tenant Isolation:** Policy mapping and threshold evaluation enforce strict multi-tenant boundary checks (`tenant_id`). Enforcement states cannot cross tenant boundaries.
- **Execution Isolation:** The Enforcement Engine does not execute tool code or intercept live socket/HTTP connections. It passes decision state to the Runtime Security Pipeline, which remains the sole execution authority.

---

# Availability & Fail-Safe Philosophy

The Enforcement Engine adheres to a fail-safe operational philosophy:

> **Enforcement Fail-Safe Philosophy**  
> Behavioral enforcement provides dynamic, risk-aware policy overrides. If the Enforcement Engine experiences an unexpected component failure, policy mapping timeout, or decision dispatch error, the Runtime Security Pipeline continues operating safely using baseline, deterministic request-level authorization and policy rules. Behavioral governance capabilities may become temporarily degraded, but baseline request security and Zero Trust authorization remain 100% active.

---

# Benefits

- **Automated Behavioral Containment:** Translates multi-turn risk scores into immediate, automated security responses (approvals, throttling, suspension).
- **Preserves Pipeline Architecture:** Maintains clear separation between decision making (ADR-019) and physical request interception (Runtime Security Pipeline).
- **Deterministic & Explainable:** Every containment action maps directly to explicit policy IDs, risk thresholds, and justification trails.
- **Replay Consistency:** Guarantees identical governance decisions during live stream execution or retrospective forensic replay.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Policy Complexity:** Managing fine-grained risk threshold matrices for diverse enterprise agent roles requires clear administrative policy definitions.
- **State Synchronization:** Distributing active `Current Enforcement State` to multi-node Runtime Security Pipelines requires efficient state publishing.

## Alternatives Considered

### Option A: Direct Tool Interception inside Enforcement Engine
Allow the Enforcement Engine to directly kill process threads or close HTTP sockets during tool execution.
- **Rejected:** Violates Single Responsibility Principle and corrupts pipeline architecture. The Runtime Security Pipeline must remain the single enforcement boundary.

### Option B: Use LLMs to Determine Enforcement Actions
Deploy an LLM ("governance officer agent") to decide whether an agent should be suspended based on session context.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). LLMs introduce non-deterministic suspensions, un-auditable governance actions, high latency, and vulnerability to adversarial prompt manipulation.

### Option C: Combine Risk Calculation and Enforcement
Merge risk scoring (ADR-018) and enforcement decision making (ADR-019) into a single module.
- **Rejected:** Conflates analytical risk measurement with policy-driven governance decisions, preventing security teams from tuning enforcement policies independently of risk scoring models.

---

# Scope

### In Scope (ADR-019)
- Deterministic Enforcement Engine architecture and evaluation pipeline.
- Transient Enforcement Context abstraction.
- Behavioral Enforcement Decision schema definition and immutability invariant.
- Distinction between historical Enforcement Decisions and active Current Enforcement State.
- Seven canonical enforcement action categories and deterministic escalation model.
- Read-only trust boundaries and multi-tenant isolation.
- Fail-safe operational philosophy.

### Out of Scope (Deferred to Future ADRs)
- **Telemetry Generation & Emission:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Event Persistence & Storage:** Owned by [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md).
- **Stateful Detection Rules:** Owned by [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md).
- **Risk Scoring Algorithms:** Owned by [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md).
- **SOC Governance Dashboards:** Owned by [ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md).

---

# Consequences

## Positive
- Completes the automated Behavioral Intelligence governance loop from detection to containment.
- Maintains strict deterministic explainability for all containment actions.
- Preserves the performance and architectural isolation of the Runtime Security Pipeline.

## Negative
- Requires maintaining active enforcement state objects across active agent sessions.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to automated behavioral containment and policy overrides.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; enforcement logic is strictly non-LLM, deterministic platform code.
- **Principle 3 – Deterministic Security Enforcement:** Realized; risk posture triggers deterministic, policy-driven actions.
- **Principle 4 – Explicit Trust Boundaries:** Enforced via decision-only publishing and pipeline execution isolation.
- **Principle 8 – Complete Auditability:** Enhanced by linking every enforcement decision to triggering risk assessments.

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
