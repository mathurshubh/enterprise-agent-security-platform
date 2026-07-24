# ADR-018: Behavioral Risk Engine

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-018 Review)
- Implementation: Deferred (No production code modified; technology-agnostic evaluation architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established Behavioral Intelligence as an observational subsystem operating alongside the Runtime Security Pipeline to govern multi-step autonomous agent behavior over extended execution lifespans.

[ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) defined non-blocking telemetry event generation and dispatching.

[ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md) established the authoritative append-only security evidence repository.

[ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md) defined the deterministic evaluation pipeline that analyzes historical telemetry to generate immutable **Behavioral Findings**.

To aggregate findings across multi-turn sessions, evaluate cumulative threat severity, calculate temporal decay, and determine overall security posture, the platform requires a dedicated risk evaluation capability—the **Behavioral Risk Engine**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

The Risk Engine is strictly a deterministic, compiled platform capability. The LLM has no access, write authority, or influence over risk scoring, score weighting, confidence aggregation, or risk state calculation.

---

# Problem Statement

Behavioral Detection (ADR-017) produces individual Behavioral Findings when specific threat rules fire. However, isolated findings do not provide a complete measure of session risk. A single low-severity finding may be benign, whereas a cluster of low- and medium-severity findings accumulating over a long-horizon session may indicate a severe agentic attack chain.

Without a dedicated Behavioral Risk Engine:

- **Lack of Cumulative Risk Scoring:** Security controls would treat findings in isolation, failing to detect accumulating session risk over extended operational windows.
- **Conflation of Detection, Risk, and Enforcement:** Attempting to combine threat detection (ADR-017) with risk aggregation and enforcement (ADR-019) would violate component separation of concerns and create monolithic security bottlenecks.
- **Probabilistic Risk Reasoning:** Relying on LLMs or unexplainable AI models to score risk would introduce non-deterministic risk scores, un-auditable posture evaluations, and vulnerability to prompt injection.
- **Absence of Derived Risk State:** Security operations teams would lack a structured, real-time risk posture representation for active agents and sessions.

Therefore, the platform requires a deterministic, read-only Behavioral Risk Engine.

---

# Architectural Direction

The platform introduces the **Behavioral Risk Engine** as an observational risk evaluation subsystem operating within the Deterministic Platform Zone:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│               Behavioral Detection Engine (ADR-017)                      │
│                  (Derived Security Findings)                            │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Immutable Behavioral Findings Stream)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Behavioral Risk Engine                              │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Finding Ingestion    │──>│ Risk Context Assembly                  │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Finding Aggregation, Weighting & Decay │  │
│                             └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Risk Assessment & State Generator      │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Behavioral Risk Assessments & State)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│     Downstream Subsystem Consumers (Risk Consumption Layer)             │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ BehavioralEnforcement│──>│ AgentSecOps Risk Dashboard             │  │
│  │      (ADR-019)       │   │               (ADR-020)                │  │
│  └──────────────────────┘   └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

The Behavioral Risk Engine answers one question:

> **"Given everything Detection has observed, how significant is the overall cumulative behavioral risk?"**

It does **not** discover threat patterns from raw telemetry (owned by ADR-017), authorize live requests (owned by the Runtime Security Pipeline), or execute enforcement actions (owned by ADR-019). The Risk Engine consumes Behavioral Findings and produces **Behavioral Risk Assessments** and **Current Behavioral Risk State**.

---

# Architectural Principles

1. **Deterministic Assessment:** Risk scoring is strictly algorithmic and deterministic. Given identical input Behavioral Findings, the Risk Engine must always produce identical risk scores and assessments.
2. **Derived Analytical State:** Risk is a derived analytical view. Behavioral Findings (ADR-017) remain authoritative security evidence. Risk assessments organize and summarize finding significance without replacing underlying evidence.
3. **Read-Only Evidence Consumption:** The Risk Engine reads immutable findings from ADR-017. It never modifies, mutates, or deletes telemetry events (ADR-015/016) or behavioral findings (ADR-017).
4. **Complete Explainability:** Every risk assessment must explicitly identify contributing findings, applied weighting factors, aggregated confidence scores, and mathematical rationale.
5. **Replay Consistency:** Running the Risk Engine during forensic replay (ADR-016) produces identical risk scores and posture timelines as live stream processing.
6. **Separation of Concerns:** Risk evaluation measures significance; it does not discover threats (ADR-017), enforce policy overrides (ADR-019), or grant runtime authorization.

---

# Design Constraints

The Behavioral Risk Engine observes strict scope limits:

- **Must Not Inspect Raw Telemetry:** Telemetry extraction and event storage are owned exclusively by ADR-015 and ADR-016.
- **Must Not Evaluate Sequence Detection Rules:** Pattern matching and rule scans are owned exclusively by ADR-017 (Behavioral Detection Engine).
- **Must Not Execute Enforcement Actions:** Throttling, session holding, agent isolation, and suspension are owned by ADR-019 (Behavioral Enforcement).
- **Must Not Perform LLM Reasoning:** Risk scoring, weight matrix calculation, and posture evaluation must remain strictly non-LLM based.
- **Technology-Agnostic Design:** Defines scoring models, assessment schemas, lifecycle phases, and trust boundaries without mandating specific mathematical libraries, scoring databases, or vendor technologies.

---

# Decision

The platform adopts the **Behavioral Risk Engine** as the canonical risk evaluation architecture for Behavioral Intelligence.

This decision establishes seven core architectural capabilities:

1. **Deterministic Risk Pipeline Architecture:** Risk Context assembly, finding aggregation, weighting, and scoring semantics.
2. **Behavioral Risk Assessment Schema:** Standardized, immutable data representation for derived risk evaluations.
3. **Current Behavioral Risk State Model:** Real-time posture tracking for active agents and sessions.
4. **Risk Lifecycle:** Conceptual state progression from assessment generation to archival.
5. **Multi-Dimensional Risk Taxonomy:** Categorization of risk across session, agent, resource, and identity scopes.
6. **Confidence Aggregation Model:** Mathematical composition of finding confidence into assessment confidence.
7. **Fail-Degraded Availability Model:** Isolated risk failure mechanics protecting runtime pipeline execution.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns single-request authorization, policy checks, and tool execution decisions. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async telemetry emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, session timelines, and replay queries. |
| **Behavioral Detection Engine (ADR-017)** | Owns stateful rule evaluation, sequence analysis, and Behavioral Findings generation. |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative risk scoring, score weighting, decay, and **Behavioral Risk Assessments**. |
| **Behavioral Enforcement (ADR-019)** | Owns policy overrides and enforcement actions (executes through Pipeline). |
| **AgentSecOps Console (ADR-020)** | Owns risk trend visualization, posture dashboards, and investigation workbenches. |
| **Behavioral Governance (Future ADRs)** | Owns governance policies operating on risk state and historical assessments. |

---

# Detailed Architectural Specifications

## 1. Risk Pipeline Architecture

The analytical pipeline evaluates findings through six sequential phases:

```text
Behavioral Findings (ADR-017) ──> Risk Context ──> Finding Aggregation ──> Weighting & Decay ──> Risk Assessment ──> Risk State Update
```

The end-to-end analytical flow across Behavioral Intelligence is structured as:

$$\text{Behavioral History (ADR-016)} \longrightarrow \text{Detection Context (ADR-017)} \longrightarrow \text{Behavioral Findings (ADR-017)} \longrightarrow \text{Risk Context (ADR-018)} \longrightarrow \text{Behavioral Risk Assessment (ADR-018)} \longrightarrow \text{Current Behavioral Risk State (ADR-018)}$$

1. **Finding Ingestion:** Consumes immutable Behavioral Findings emitted by ADR-017 for an active `session_id` or `agent_id`.
2. **Risk Context Assembly:** Constructs an ephemeral, read-only analytical view representing evaluation windows, applicable findings, weighting rules, and confidence metrics.
3. **Finding Aggregation:** Groups findings by risk dimensions (Session, Agent, Identity, Resource) within specified temporal windows.
4. **Weighting & Temporal Decay:** Applies deterministic severity weighting and temporal decay functions to decrease the impact of older findings over time.
5. **Risk Assessment Generation:** Computes cumulative risk scores and instantiates an immutable **Behavioral Risk Assessment**.
6. **Risk State Update:** Updates the transient **Current Behavioral Risk State** representing the active risk posture for the session or agent.

## 2. Risk Context

To establish a clean architectural abstraction between immutable Behavioral Findings and deterministic risk computation, the Risk Engine constructs a transient **Risk Context** during evaluation:

- **Ephemeral & Read-Only:** The Risk Context is a derived, transient analytical view created solely for the duration of risk evaluation.
- **Derived from Behavioral Findings:** It is constructed exclusively from immutable Behavioral Findings generated by ADR-017.
- **Non-Persisted:** It is never written back into the Behavioral Event Store (ADR-016), Behavioral Findings (ADR-017), or Behavioral Risk Assessments (ADR-018).
- **No Historical Authority:** Risk Context is not historical evidence and must never be treated as an auditable security artifact.
- **No State Mutation:** It cannot modify findings, historical telemetry events, or the active Current Behavioral Risk State.

Conceptually, the Risk Context encapsulates evaluation parameters such as the active assessment scope, applicable finding set, temporal evaluation window, weighting configuration, confidence aggregation inputs, assessment target (session, agent, identity, resource), and multi-tenant isolation metadata (`tenant_id`).

## 3. Behavioral Risk Assessment Schema & Concept

A **Behavioral Risk Assessment** is a canonical, derived architectural artifact representing an evaluated risk score at a specific point in time:

- **Metadata Envelope:**
  - `assessment_id`: Unique UUID identifier for the risk assessment.
  - `schema_version`: Version string of the active risk model schema (e.g., `1.0`).
  - `timestamp`: UTC timestamp when the assessment was generated.

- **Context Envelope:**
  - `agent_id`: Affected Enterprise Agent identifier.
  - `session_id`: Primary execution session identifier.
  - `tenant_id`: Multi-tenant organization identifier.

- **Risk & Confidence Metrics:**
  - `cumulative_risk_score`: Normalized numerical score representing overall risk (e.g., $0.0$ to $100.0$).
  - `risk_level`: Standardized risk classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `aggregated_confidence`: Aggregated confidence metric derived from contributing findings ($0.0$ to $1.0$).

- **Evidence & Attribution Payload:**
  - `contributing_finding_ids`: Ordered array of immutable `finding_id` references from ADR-017 that contributed to the score.
  - `risk_dimension_breakdown`: Key-value map detailing score contributions per risk dimension.
  - `assessment_summary`: Human-readable, deterministic explanation of the risk score evaluation.

> **Risk Assessment Immutability**  
> Once generated, a Behavioral Risk Assessment is immutable. Assessments are derived historical evidence and must never be modified in place. As new findings arrive or temporal decay occurs, updated risk evaluations are represented by generating new risk assessment records. This preserves deterministic replay, forensic integrity, and complete auditability.

## 4. Behavioral Risk State vs. Risk Assessment

To maintain architectural clarity, the platform distinguishes between historical assessments and active state:

```text
Behavioral Telemetry (ADR-015/016)
        ↓
Behavioral Finding (ADR-017)
        ↓
Behavioral Risk Assessment (Historical Immutability - ADR-018)
        ↓
Current Behavioral Risk State (Derived Active Posture - ADR-018)
```

- **Behavioral Risk Assessment:** An immutable, timestamped historical record of risk evaluation at moment $T_k$. Preserved permanently in audit evidence.
- **Current Behavioral Risk State:** A transient, derived posture object representing the active cumulative risk level of an ongoing session or agent. Used by [ADR-019: Behavioral Enforcement](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement.md) to trigger policy overrides when risk thresholds are breached.

## 5. Risk Lifecycle

Behavioral Risk Assessments and Risk States progress through a conceptual lifecycle:

```text
Generated ──> State Updated ──> Consumed by Enforcement ──> Archived
```

1. **Generated:** Immutably instantiated following finding aggregation and scoring.
2. **State Updated:** Updates the active `Current Behavioral Risk State` for the target session/agent.
3. **Consumed by Enforcement:** Delivered to ADR-019 to evaluate whether risk threshold escalations require policy overrides.
4. **Archived:** Preserved alongside session audit evidence for historical SOC trend analysis.

## 6. Multi-Dimensional Risk Taxonomy

The Risk Engine evaluates risk across six canonical dimensions:

1. **Session Risk:** Cumulative risk score calculated across all findings within a single active `session_id`.
2. **Agent Risk:** Aggregate historical risk posture associated with a specific Enterprise Agent identity (`agent_id`) across sessions.
3. **Identity & Authority Risk:** Risk derived from anomalous role usage, credential discovery attempts, or scope escalation.
4. **Resource Risk:** Risk derived from target resource sensitivity, resource diversity, and data access entropy.
5. **Operational Risk:** Risk derived from execution velocity, recursive call frequency, and denial accumulation.
6. **Multi-Agent Risk (Future - ADR-021):** Risk derived from inter-agent delegation chains, subagent spawning, and cross-agent trust boundaries.

## 7. Scoring Model & Temporal Decay Architecture

The Risk Engine applies a deterministic, technology-agnostic scoring model:

- **Weighted Finding Aggregation:** Each finding category and severity tier carries a deterministic weight factor. Cumulative risk is computed by aggregating weighted findings.
- **Confidence Aggregation:** Finding confidence scores ($C_{\text{finding}}$) are mathematically composed into an overall assessment confidence metric ($C_{\text{assessment}}$), ensuring low-confidence findings do not artificially inflate risk scores.
- **Temporal Decay:** Older findings experience deterministic decay over time. As time elapses without new findings, the contribution of historical findings to active session risk decays according to configured half-life parameters.
- **Score Normalization & Threshold Mapping:** Raw aggregate scores are normalized to a standardized scale ($0.0$ to $100.0$) and mapped to discrete risk tiers (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

## 8. Confidence Model

The platform distinguishes between finding confidence and assessment confidence:

$$\text{Finding Confidence (ADR-017)} \longrightarrow \text{Confidence Aggregation (ADR-018)} \longrightarrow \text{Assessment Confidence (ADR-018)}$$

- **Finding Confidence (ADR-017):** Derived by individual detection rules during pattern matching (e.g., exact sequence match = $1.0$).
- **Assessment Confidence (ADR-018):** Aggregated across all contributing findings. Multiple independent finding sources increase overall assessment confidence, whereas isolated low-confidence findings yield lower assessment confidence.

---

# Trust Boundaries & Access Model

The Risk Engine operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│               Behavioral Detection Engine (ADR-017)                      │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Read-Only Findings Stream - Tenant Isolated)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Behavioral Risk Engine                              │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │           Deterministic Risk Scoring & Posture Engine             │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Risk Assessments & Risk State)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│     Behavioral Enforcement (ADR-019) │  AgentSecOps Console (ADR-020)  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary & Execution Guarantees

- **Read Access:** Reads immutable findings from the Behavioral Detection Engine (ADR-017). Cannot modify, delete, or alter findings or telemetry.
- **Write Access:** Emits immutable **Behavioral Risk Assessments** and publishes active **Current Behavioral Risk State** objects for consumption by ADR-019 and ADR-020.
- **Multi-Tenant Isolation:** Risk evaluation enforces strict multi-tenant boundary checks (`tenant_id`). Risk scoring and posture aggregation cannot cross tenant boundaries.
- **No Direct Enforcement:** The Risk Engine has zero connection to live tool execution backends and cannot issue enforcement actions (`SUSPEND`, `DENY`, `BLOCK`). Enforcement executes strictly through the Runtime Security Pipeline via ADR-019.

---

# Availability & Fail-Degraded Philosophy

The Risk Engine adheres to the fail-silent/fail-degraded operational philosophy established in ADR-015, ADR-016, and ADR-017:

> **Risk Availability Philosophy**  
> Behavioral risk scoring supports dynamic posture tracking and automated policy overrides. If the Risk Engine experiences an unexpected component failure, scoring timeout, or state calculation backlog, the Runtime Security Pipeline continues operating safely and enforcing Zero Trust security decisions. Behavioral risk tracking may become temporarily degraded, but request-level authorization and policy enforcement remain fully functional and un-delayed.

---

# Benefits

- **Cumulative Threat Visibility:** Quantifies accumulating session risk across multi-turn workflows that individual single-request checks cannot detect.
- **Deterministic & Explainable:** Every risk score maps directly to contributing finding IDs, weights, and confidence metrics, ensuring zero black-box scoring.
- **Dynamic Posture Tracking:** Maintains real-time `Current Behavioral Risk State` enabling responsive enforcement overrides (ADR-019).
- **Replay Consistency:** Guarantees identical risk scores whether evaluating live stream findings or conducting retrospective forensic replay.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **State Maintenance:** Maintaining real-time `Current Behavioral Risk State` across long-running sessions requires caching state objects in memory.
- **Decay Tuning:** Half-life temporal decay parameters require careful baseline calibration to prevent risk scores from decaying prematurely during slow attack sequences.

## Alternatives Considered

### Option A: Evaluate Risk Synchronously in Pipeline
Calculate cumulative session risk directly inside `RuntimeService` during request authorization.
- **Rejected:** Adds latency to every tool call, couples request authorization to complex multi-finding scoring, and risks stalling tool execution if risk evaluation fails.

### Option B: Use LLMs to Score Behavioral Risk
Deploy an LLM ("risk evaluator agent") to inspect findings and output natural language risk judgements.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). LLMs introduce non-determinism, un-auditable risk scores, high latency, and vulnerability to prompt injection.

### Option C: Perform Risk Calculation Inside Detection Engine
Combine detection rule scanning (ADR-017) and risk score aggregation (ADR-018) into a single monolithic component.
- **Rejected:** Violates Single Responsibility Principle. Detection discovers evidence; Risk measures cumulative significance. Separating them allows independent evolution of rule scanners and scoring models.

---

# Scope

### In Scope (ADR-018)
- Deterministic Risk Engine architecture and scoring pipeline.
- Transient Risk Context abstraction.
- Behavioral Risk Assessment schema definition and immutability invariant.
- Distinction between historical Risk Assessments and active Current Behavioral Risk State.
- Multi-dimensional risk taxonomy across session, agent, resource, and identity scopes.
- Scoring model, temporal decay, and confidence aggregation semantics.
- Read-only trust boundaries and multi-tenant isolation.
- Fail-degraded operational philosophy.

### Out of Scope (Deferred to Future ADRs)
- **Telemetry Generation & Emission:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Event Persistence & Storage:** Owned by [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md).
- **Stateful Detection Rules & Findings:** Owned by [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md).
- **Enforcement Actions & Policy Overrides:** Owned by [ADR-019: Behavioral Enforcement](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement.md).
- **SOC Risk Dashboards:** Owned by [ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md).

---

# Consequences

## Positive
- Enables dynamic, risk-aware security governance across autonomous enterprise agent lifespans.
- Maintains strict explainability and deterministic reproducibility for security audits.
- Preserves the performance and reliability of single-request runtime authorization.

## Negative
- Requires maintaining transient risk state objects for active agent sessions.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to cumulative risk scoring across agent lifespans.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; risk evaluation logic is strictly non-LLM, deterministic platform code.
- **Principle 3 – Deterministic Security Enforcement:** Preserved; risk scores feed into deterministic enforcement models (ADR-019).
- **Principle 4 – Explicit Trust Boundaries:** Enforced via read-only finding access and isolated risk state publishing.
- **Principle 8 – Complete Auditability:** Enhanced by linking every risk assessment to exact contributing finding IDs.

---

# Related Documents

- [ADR-001: Zero Trust Security Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-001-zero-trust-security-model.md)
- [ADR-002: LLM as Untrusted Intent Parser](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-002-llm-untrusted-intent-parser.md)
- [ADR-004: Deterministic Security Pipeline](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-004-deterministic-security-pipeline.md)
- [ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md)
- [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md)
- [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md)
- [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md)
