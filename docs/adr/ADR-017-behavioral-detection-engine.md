# ADR-017: Behavioral Detection Engine

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-017 Review)
- Implementation: Deferred (No production code modified; technology-agnostic analysis architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established Behavioral Intelligence as an observational subsystem operating alongside the Runtime Security Pipeline to govern multi-step autonomous agent behavior over extended execution lifespans.

[ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) defined the non-blocking telemetry event taxonomy, producers, and asynchronous dispatch mechanisms.

[ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md) established the authoritative, append-only security evidence repository and session timeline model.

To analyze historical telemetry records and identify multi-step threat patterns across agent execution lifespans, the platform requires a dedicated, deterministic evaluation capability—the **Behavioral Detection Engine**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

Detection is strictly a deterministic, compiled platform capability. The LLM has no authority, involvement, or influence over detection rule evaluation, pattern matching, or security finding generation.

---

# Problem Statement

Single-request security controls (such as request-level authorization and prompt scanning) evaluate tool invocations in isolation. However, sophisticated autonomous agent exploits often manifest across extended operational windows as sequences of individually permissible actions (e.g., incremental filesystem crawling followed by sensitive file reading and external network posting).

Without a dedicated Behavioral Detection Engine:

- **Invisible Multi-Step Attack Chains:** Threat sequences spanning multiple tool calls or sessions would go undetected by single-turn request filters.
- **Conflation of Detection and Enforcement:** Coupling threat analysis directly to request execution would introduce latency and violate component separation of concerns.
- **Non-Deterministic Analysis Risks:** Attempting to detect behavioral anomalies using probabilistic LLMs or unexplainable AI models would introduce non-determinism, false positives, and un-auditable security decisions.
- **Inability to Perform Forensic Sequence Correlation:** Security operations teams would lack structured, rule-attributed finding artifacts mapping specific historical events to identified threat behaviors.

Therefore, the platform requires a deterministic, read-only Behavioral Detection Engine.

---

# Architectural Direction

The platform introduces the **Behavioral Detection Engine** as an observational analysis subsystem operating within the Deterministic Platform Zone:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│              Behavioral Event Store Subsystem (ADR-016)                 │
│                 (Authoritative Security Evidence)                       │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Read-Only Event History Stream / Queries)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Behavioral Detection Engine                           │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Event Stream Reader  │──>│ Detection Context Assembly              │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Stateful Rule Evaluation Engine        │  │
│                             └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Behavioral Correlation & Synthesis     │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Behavioral Findings Stream)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│     Downstream Subsystem Consumers (Finding Consumption Layer)          │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Behavioral Risk Engine│──>│ AgentSecOps Investigation Workbench    │  │
│  │      (ADR-018)       │   │               (ADR-020)                │  │
│  └──────────────────────┘   └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

The Behavioral Detection Engine answers one question:

> **"Given this immutable behavioral history, what specific threat or policy-relevant behaviors have occurred?"**

It does **not** evaluate whether a live request should be allowed or denied. Authorization belongs strictly to the Runtime Security Pipeline, risk scoring belongs to [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md), and enforcement belongs to [ADR-019: Behavioral Enforcement](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement.md). Detection produces **Behavioral Findings** and nothing else.

---

# Architectural Principles

1. **Deterministic Evaluation:** Detection rules are purely algorithmic and deterministic. Given identical historical event inputs, the Detection Engine must always produce identical behavioral findings.
2. **Historical Read-Only Analysis:** Detection operates strictly on historical evidence read from the Behavioral Event Store (ADR-016). It never inspects uncommitted runtime state and never modifies historical events or session timelines.
3. **Observational Isolation:** Detection generation is side-effect-free with respect to live request execution. The Detection Engine does not authorize requests, deny requests, modify parameters, or execute tools.
4. **Stateful Sequence Correlation:** Detection correlates event sequences across single-session timelines and multi-session historical windows, deriving transient analytical state without writing back to the Event Store.
5. **Complete Explainability:** Every generated finding must be fully explainable, identifying the exact rule triggered, the contributing historical event IDs, and the exact evidence rationale.
6. **Replay Consistency:** Running the Detection Engine during a forensic session replay (ADR-016) produces the exact same set of findings as live stream analysis.
7. **Independent Rule Evaluation:** Detection rules execute independently. The outcome or evaluation of one rule cannot mutate, suppress, or interfere with another rule's evaluation logic.

---

# Design Constraints

The Behavioral Detection Engine observes strict scope limits:

- **Must Not Generate Telemetry:** Event creation and envelope formatting are owned exclusively by ADR-015.
- **Must Not Store Raw Events:** Event persistence, indexing, and retention are owned exclusively by ADR-016.
- **Must Not Calculate Aggregate Risk Scores:** Combining findings into cumulative session risk scores is owned by ADR-018 (Behavioral Risk Engine).
- **Must Not Execute Enforcement Actions:** Throttling, session holding, agent isolation, and suspension are owned by ADR-019 (Behavioral Enforcement).
- **Must Not Perform LLM Reasoning:** Rule logic, sequence matching, and anomaly evaluation must remain strictly non-LLM based.
- **Technology-Agnostic Design:** Defines rule evaluation models, finding schemas, lifecycle phases, and trust boundaries without mandating specific rule languages, query engines, or database technologies.

---

# Decision

The platform adopts the **Behavioral Detection Engine** as the canonical detection architecture for Behavioral Intelligence.

This decision establishes seven core architectural capabilities:

1. **Deterministic Rule Engine Architecture:** Stateful sequence analysis and evaluation semantics.
2. **Behavioral Findings Schema:** Standardized data representation for derived threat evidence.
3. **Finding Lifecycle:** Conceptual state progression from observation to archival.
4. **Correlation Engine Model:** Intra-session, inter-session, and agent-scoped correlation boundaries.
5. **Detection Rule Taxonomy:** Categorization of detection patterns across enterprise threat vectors.
6. **Explainability & Evidence Mapping:** Strict linking of findings to supporting historical telemetry events.
7. **Fail-Degraded Availability Model:** Isolated detection failure mechanics protecting runtime pipeline execution.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns single-request authorization, policy checks, and tool execution decisions. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async telemetry emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, session timelines, and replay queries. |
| **Behavioral Detection Engine (ADR-017)** | Owns stateful rule evaluation, sequence analysis, correlation, and **Behavioral Findings** generation. |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative risk scoring and behavioral assessments (consumes Findings). |
| **Behavioral Enforcement (ADR-019)** | Owns policy overrides and enforcement actions (executes through Pipeline). |
| **AgentSecOps Console (ADR-020)** | Owns finding visualization, alert workflows, and investigation workbenches. |
| **Behavioral Governance (Future ADRs)** | Owns governance policies operating on historical findings and evidence. |

---

# Detailed Architectural Specifications

## 1. Detection Pipeline Architecture & Detection Context

The detection pipeline evaluates historical telemetry through five sequential phases:

```text
Behavioral History (ADR-016) ──> Detection Context ──> Rule Evaluation ──> Sequence Correlation ──> Behavioral Findings
```

1. **Event Stream Query (Behavioral History):** The Detection Engine consumes committed telemetry events from the Event Store (ADR-016) via live streams or windowed sequence queries.
2. **Detection Context Assembly:** Constructs a transient, read-only analytical context representing the operational window, relevant historical events, session summaries, prior findings, and temporal boundaries required for evaluation.
3. **Rule Evaluation:** Evaluates active detection rules (sequence, frequency, threshold, temporal) against the transient Detection Context.
4. **Sequence Correlation:** Correlates findings across single-session timelines or multi-session agent execution histories to identify compound threat patterns.
5. **Behavioral Finding Generation:** Synthesizes derived **Behavioral Findings** containing rule metadata, severity, confidence, and contributing event evidence.

> **Detection Context Abstraction**  
> The **Detection Context** is an ephemeral, read-only analytical view derived from immutable Behavioral History. It is created solely for rule evaluation, is never persisted into the Behavioral Event Store, and never modifies historical telemetry events. It cleanly separates immutable evidence storage from analytical rule execution.

## 2. Behavioral Finding Schema & Concept

A **Behavioral Finding** is a canonical, derived architectural artifact representing an observed security pattern:

- **Metadata Envelope:**
  - `finding_id`: Unique UUID identifier for the behavioral finding.
  - `rule_id`: Identifier of the specific detection rule that fired (e.g., `DET_REC_ENUM_001`).
  - `rule_version`: Version string of the active detection rule schema (e.g., `1.0`).
  - `timestamp`: UTC timestamp when the finding was generated.

- **Classification Envelope:**
  - `finding_category`: Taxonomy category (e.g., `RESOURCE_ENUMERATION`, `TOOL_ABUSE`).
  - `severity`: Standardized severity tier (`INFORMATIONAL`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `confidence`: Calculated rule match confidence score ($0.0$ to $1.0$).

- **Context Envelope:**
  - `agent_id`: Affected Enterprise Agent identifier.
  - `session_id`: Primary execution session identifier where the pattern occurred.
  - `tenant_id`: Multi-tenant organization identifier.

- **Evidence & Attribution Payload:**
  - `contributing_event_ids`: Ordered array of immutable telemetry `event_id` references from ADR-016 that triggered the rule.
  - `summary`: Human-readable, deterministic explanation of the observed behavior.
  - `evidence_context`: Key-value map of evidence metadata (e.g., accessed file path sequence, call velocity metrics).

> **Behavioral Finding Immutability**  
> Once generated, a Behavioral Finding is immutable. Findings are derived evidence and must never be modified in place. Changes in analytical understanding, lifecycle progression, investigation status, or downstream processing are represented through new lifecycle artifacts, derived records, or related metadata rather than mutating an existing finding. This preserves deterministic replay, forensic integrity, and complete auditability.

## 3. Finding Lifecycle

Behavioral Findings transition through a conceptual lifecycle:

```text
Observed ──> Generated ──> Correlated ──> Consumed by Risk Engine ──> Archived
```

1. **Observed:** Pattern detected during historical event evaluation.
2. **Generated:** Immutably instantiated and assigned a unique `finding_id`.
3. **Correlated:** Evaluated against multi-finding correlation rules across active session windows.
4. **Consumed by Risk Engine:** Delivered to ADR-018 to evaluate cumulative session risk score escalation.
5. **Archived:** Stored alongside session investigation records for historical compliance and SOC review.

## 4. Detection Rule Categories

The Detection Engine evaluates seven canonical categories of behavioral threat rules:

1. **Policy Deviation Rules:** Identifying near-miss policy attempts, repeated parameter validation failures, or unauthorized resource path probes.
2. **Resource Access Rules:** Detecting systematic resource enumeration, directory traversal, credential discovery, or data staging across filesystem/API targets.
3. **Tool Usage Rules:** Identifying recursive tool call loops, excessive execution frequency, unauthorized tool call sequences (`file_read` → `web_post`), or tool parameter abuse.
4. **Identity & Authority Rules:** Flagging anomalous role claim usage, unexpected agent identity transitions, or permission scope exploration.
5. **Session Behavior Rules:** Detecting anomalous session lifespans, inactive planning loops, goal drift indicators, or long-horizon covert operations.
6. **Agent Coordination Rules (Future):** Identifying multi-agent delegation abuse, subagent spawning loops, or cross-agent trust exploitation (ADR-021).
7. **Baseline Anomaly Rules:** Detecting statistical deviations from established historical behavioral baselines for specific agent roles.

## 5. Correlation Model

Behavioral correlation evaluates event relationships across three distinct spatial and temporal scopes:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Behavioral Correlation Scopes                        │
│                                                                         │
│  ┌─────────────────────────┐   ┌─────────────────────────────────────┐  │
│  │ Intra-Session Scope     │   │ Inter-Session (Agent) Scope         │  │
│  │ (Single session timeline│──>│ (Historical execution across        │  │
│  │  events: sequence/rate) │   │  multiple sessions for single agent)│  │
│  └─────────────────────────┘   └──────────────────┬──────────────────┘  │
│                                                   │                     │
│                                                   ▼                     │
│                                ┌─────────────────────────────────────┐  │
│                                │ Multi-Agent Scope (ADR-021)         │  │
│                                │ (Cross-agent collaboration chains)  │  │
│                                └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Intra-Session Correlation:** Correlates sequential events within a single `session_id` (e.g., detecting rapid-fire tool call loops within 60 seconds).
- **Inter-Session Correlation:** Correlates patterns across multiple historical sessions for a specific `agent_id` (e.g., detecting an agent attempting resource enumeration across multiple distinct sessions over several days).
- **Multi-Agent Correlation (Future - ADR-021):** Correlates patterns across interacting agent networks (e.g., Agent-A reading credentials and passing context to Agent-B to exfiltrate data).

---

# Trust Boundaries & Access Model

The Detection Engine operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│              Behavioral Event Store Subsystem (ADR-016)                 │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Read-Only Event Queries - Tenant Isolated)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Behavioral Detection Engine                           │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │          Deterministic Detection & Correlation Engine             │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Behavioral Findings Stream)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│     Behavioral Risk Engine (ADR-018)  │  AgentSecOps Console (ADR-020)   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary & Execution Guarantees

- **Read Access:** Reads immutable events from the Behavioral Event Store (ADR-016). Cannot modify, delete, or write back events to the Event Store.
- **Write Access:** Writes generated **Behavioral Findings** to the internal finding stream/store for consumption by the Behavioral Risk Engine (ADR-018) and AgentSecOps Console (ADR-020).
- **Multi-Tenant Isolation:** Detection rule evaluation enforces strict multi-tenant boundary checks (`tenant_id`). Event queries and sequence correlations cannot cross tenant boundaries.
- **No Direct Enforcement:** The Detection Engine has zero connection to live tool execution backends and cannot issue enforcement actions (`SUSPEND`, `DENY`, `BLOCK`). Enforcement executes strictly through the Runtime Security Pipeline via ADR-019.

---

# Availability & Fail-Degraded Philosophy

The Detection Engine adheres to the fail-silent/fail-degraded operational philosophy established in ADR-015 and ADR-016:

> **Detection Availability Philosophy**  
> Behavioral detection supports stateful threat identification and risk scoring. If the Detection Engine experiences an unexpected component failure, rule evaluation timeout, or backlog lag, the Runtime Security Pipeline continues operating safely and enforcing Zero Trust security decisions. Behavioral detection capabilities may become temporarily degraded, but request-level authorization and policy enforcement remain fully functional and un-delayed.

---

# Benefits

- **Multi-Step Threat Visibility:** Identifies complex attack chains, resource enumeration, and tool abuse across multi-turn agent execution lifespans.
- **Deterministic & Explainable:** Every finding maps directly to specific rule IDs and supporting historical event IDs, ensuring zero black-box non-determinism.
- **Observational Separation:** Decouples heavy sequence analysis from synchronous request execution, preserving runtime pipeline performance.
- **Replay Consistency:** Guarantees identical finding outputs whether analyzing live stream telemetry or conducting retrospective forensic replay.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Derived Finding Volume:** Generating granular findings for complex sessions increases overall storage and analytical indexing requirements.
- **Sequence State Tracking:** Correlating multi-session patterns for long-running agents requires maintaining stateful correlation windows in memory/cache.

## Alternatives Considered

### Option A: Evaluate Detection Rules Synchronously in Pipeline
Run behavioral sequence detection rules directly inside `RuntimeService` during request execution.
- **Rejected:** Introduces severe latency to every tool call, couples request execution to stateful sequence matching, and risks stalling tool execution if rule evaluation fails.

### Option B: Use LLMs for Behavioral Anomaly Detection
Deploy an LLM ("security analyst agent") to inspect session transcripts and judge whether agent behavior is malicious.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). LLMs introduce non-determinism, halluncinated findings, high latency, un-auditable security decisions, and vulnerability to prompt injection.

### Option C: Perform Detection Inside Executable Tools
Require individual tools to maintain internal sequence detection rules and call counters.
- **Rejected:** Violates Single Responsibility Principle, pollutes executable tool logic, and prevents cross-tool sequence correlation (`file_read` → `web_post`).

---

# Scope

### In Scope (ADR-017)
- Deterministic Detection Engine architecture and evaluation pipeline.
- Transient Detection Context abstraction.
- Behavioral Finding schema definition, lifecycle phases, and finding immutability invariant.
- Correlation model across intra-session, inter-session, and agent boundaries.
- Seven canonical detection rule categories.
- Explainability, evidence attribution, and replay consistency invariants.
- Read-only trust boundaries and multi-tenant isolation.
- Fail-degraded operational philosophy.

### Out of Scope (Deferred to Future ADRs)
- **Telemetry Generation & Emission:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Event Persistence & Storage:** Owned by [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md).
- **Cumulative Risk Scoring Algorithms:** Owned by [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md).
- **Enforcement Actions & Overrides:** Owned by [ADR-019: Behavioral Enforcement](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement.md).
- **SOC Finding Visualizations:** Owned by [ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md).

---

# Consequences

## Positive
- Enables deep, multi-step threat detection across long-horizon enterprise agent workflows.
- Maintains strict explainability and deterministic reproducibility for security audits.
- Preserves the performance and reliability of single-request runtime authorization.

## Negative
- Requires maintaining stateful correlation windows for active agent sessions.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to stateful sequence detection across agent lifespans.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; detection logic is strictly non-LLM, deterministic platform code.
- **Principle 3 – Deterministic Security Enforcement:** Preserved; findings feed into deterministic risk and enforcement models.
- **Principle 4 – Explicit Trust Boundaries:** Enforced via read-only event store access and isolated findings output.
- **Principle 8 – Complete Auditability:** Enhanced by linking every finding to exact contributing historical event IDs.

---

# Related Documents

- [ADR-001: Zero Trust Security Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-001-zero-trust-security-model.md)
- [ADR-002: LLM as Untrusted Intent Parser](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-002-llm-untrusted-intent-parser.md)
- [ADR-004: Deterministic Security Pipeline](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-004-deterministic-security-pipeline.md)
- [ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md)
- [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md)
- [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md)
