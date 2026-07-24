# ADR-016: Behavioral Event Store & Data Model

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-016 Review)
- Implementation: Deferred (No production code modified; technology-agnostic persistence architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established Behavioral Intelligence as an observational subsystem operating alongside the Runtime Security Pipeline to govern multi-step autonomous agent behavior over extended execution lifespans.

[ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) defined the non-blocking event taxonomy, envelope schemas, producers, and asynchronous dispatcher for emitting behavioral telemetry events from the Deterministic Platform Zone.

To transform transient telemetry streams into actionable intelligence, the platform requires an authoritative, append-only persistence layer—the **Behavioral Event Store & Data Model**.

The Behavioral Event Store is not merely a database or logging system; it is the **authoritative security evidence repository**, the **single source of truth for behavioral investigations**, and the **foundation for deterministic forensic reconstruction**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

The Behavioral Event Store is strictly a deterministic, compiled platform capability. The LLM has no access, write authority, or influence over historical event persistence, storage schemas, or record integrity.

---

# Problem Statement

Telemetry events emitted by ADR-015 arrive as an asynchronous stream. Without a structured, immutable persistence architecture:

- **Loss of Historical Behavioral Evidence:** In-flight events would remain transient, rendering multi-session trend analysis and retrospective forensics impossible.
- **Inability to Perform Stateful Detection:** Stateful sequence detection rules ([ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md)) and cumulative risk scoring ([ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md)) require querying historical execution sequences across session boundaries.
- **Risk of History Tampering:** Storing telemetry in mutable database structures risks accidental or malicious record overwrites, destroying audit provenance and security evidence integrity.
- **Forensic Replay Deficits:** Without session-centric event ordering and deterministic reconstruction semantics, security investigators cannot accurately replay past agent execution lifespans.

Therefore, the platform requires a dedicated, append-only Behavioral Event Store and conceptual Data Model.

---

# Architectural Direction

The platform introduces the **Behavioral Event Store & Data Model** as the authoritative persistence subsystem within the Deterministic Platform Zone:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                 Behavioral Telemetry Dispatcher                         │
│                            (ADR-015)                                    │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Immutable Telemetry Stream)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Behavioral Event Store Subsystem                       │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Ingestion & Sequencing│──>│ Append-Only Behavioral Event Store      │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Behavioral Session Timelines & Indexes │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Read-Only Event Queries)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│      Downstream Subsystem Consumers (Read-Only Query Layer)             │
│                                                                         │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────┐  │
│  │ Behavioral Detection │  │ Behavioral Risk Engine│  │ AgentSecOps   │  │
│  │      (ADR-017)       │  │      (ADR-018)       │  │   (ADR-020)   │  │
│  └──────────────────────┘  └──────────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

The Behavioral Event Store acts as an append-only historical record and security evidence repository. It ingests versioned telemetry events from ADR-015, assigns deterministic sequence ordering per session, builds logical behavioral timelines, and exposes read-only retrieval interfaces for downstream detection engines, risk scoring services, and SOC investigation harnesses.

---

# Architectural Principles

1. **Append-Only Immutability:** Historical behavioral events are recorded exclusively as append-only records. Stored events are never modified, updated in-place, or overwritten. Corrections or state transitions are recorded by appending new events.
2. **Deterministic Replayability:** Given an identical, ordered behavioral history stored for a session, any forensic replay harness must reconstruct the exact sequence of agent requests, security evaluations, tool executions, and governance outcomes.
3. **Session-Centric Domain Modeling:** Behavior is inherently temporal. The Behavioral Event Store organizes data around long-horizon execution sessions (`session_id`), establishing causal links between requests, evaluations, and outcomes.
4. **Separation of History and Current State:** The Behavioral Event Store records historical behavioral transitions. It does not manage transient agent credentials, active runtime memory, or policy configuration state.
5. **Tamper-Evident Integrity & Provenance:** Stored events preserve origin provenance (`trace_id`, `producer_id`) and structural integrity, guaranteeing that historical security evidence remains verifiable.

> **Event Store Availability Philosophy**  
> Event Store availability supports Behavioral Intelligence, stateful detection, and forensic analytics. The Runtime Security Pipeline continues deterministic security enforcement even if Event Store persistence becomes temporarily degraded or unavailable. Behavioral capabilities may degrade gracefully, but request-level authorization and policy enforcement remain fully functional.

---

# Design Constraints

The Behavioral Event Store observes strict architectural boundaries:

- **Must Not Produce Telemetry (Telemetry Decoupling):** Event creation, envelope formatting, and initial dispatch are owned exclusively by ADR-015.
- **Must Not Evaluate Detection Rules (Detection Decoupling):** Evaluating sequence patterns, anomalies, and threat rules is owned by ADR-017 (Behavioral Detection Engine).
- **Must Not Calculate Risk Scores (Risk Decoupling):** Aggregate risk scoring and confidence decay calculations are owned by ADR-018 (Behavioral Risk Engine).
- **Must Not Execute Enforcement (Enforcement Decoupling):** Dynamic throttling, session holding, and agent suspension are owned by ADR-019 (Behavioral Enforcement).
- **Technology-Agnostic Design:** The ADR defines logical structures, relationship hierarchies, indexing concepts, and retrieval contracts without mandating specific database engines, storage hardware, or SQL/NoSQL vendor technologies.

---

# Decision

The platform adopts the **Behavioral Event Store & Data Model** as the canonical persistence architecture for Behavioral Intelligence.

This decision establishes seven core architectural capabilities:

1. **Append-Only Persistence Architecture:** Immutable storage mechanics preserving raw behavioral history and security evidence.
2. **Behavioral Session Model:** Logical grouping of events by session lifecycle boundaries.
3. **Behavioral Timeline Model:** Multi-dimensional chronological ordering of session events.
4. **Behavioral Replay Architecture:** Forensic reconstruction mechanisms for auditing agent behavior.
5. **Event Integrity & Provenance:** Cryptographic-neutral guarantees for evidence verification.
6. **Logical Indexing Strategy:** Multi-key index requirements for high-throughput querying.
7. **Tiered Retention Architecture:** Operational, compliance, and archival lifecycle management.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns event creation, policy checks, and execution decisions. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async stream emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, session timeline indexing, deterministic replay retrieval, and retention governance. |
| **Behavioral Detection Engine (ADR-017)** | Owns stateful rule evaluation and findings generation (reads Event Store). |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative risk scoring and behavioral assessments (reads Event Store & Findings). |
| **Behavioral Enforcement (ADR-019)** | Owns policy overrides and enforcement actions (executes through Pipeline). |
| **Behavioral Governance (Future ADRs)** | Owns governance policies operating on historical evidence. Does not own persistence. |

---

# Core Architectural Capabilities

## 1. Event Lifecycle & Read Consistency

A behavioral telemetry event progresses through six distinct architectural phases:

```text
Ingestion ──> Validation & Sequencing ──> Append-Only Persistence ──> Indexing ──> Query Access ──> Retention Archival
```

1. **Ingestion:** Telemetry Dispatcher (ADR-015) delivers a versioned telemetry event to the Event Store ingestion boundary.
2. **Validation & Sequencing:** The Event Store validates envelope schema conformity, assigns a monotonic sequence number scoped to the `session_id`, and verifies event metadata.
3. **Append-Only Persistence:** The event is written to immutable storage. Once written, the event cannot be edited or deleted.
4. **Indexing:** Logical indexes (`session_id`, `agent_id`, `timestamp`, `event_type`) are updated asynchronously to enable fast lookups.
5. **Query Access:** The event becomes available to read-only query interfaces for detection rules (ADR-017), risk scoring (ADR-018), and SOC replay (ADR-020).
6. **Retention Archival:** Based on policy, mature events transition from operational storage to long-term compliance storage or immutable archival.

> **Read Consistency Invariant**  
> Consumers observe immutable historical records. Once a telemetry event is committed to the Behavioral Event Store, future reads will return the identical logical event. Behavioral replay is deterministic because committed history never changes.

## 2. Behavioral Session Model

The **Behavioral Session** is the primary organizational boundary for behavioral analysis:

- **Session Initialization (`SESSION_STARTED`):** Establishes a unique `session_id`, binding the execution context to an authenticated Enterprise Agent (`agent_id`), tenant (`tenant_id`), and initial risk baseline.
- **Session Sequence Monotonicity:** Every event within a session receives a strictly increasing, contiguous sequence integer ($1, 2, 3, \dots, N$). This guarantees unambiguous event ordering regardless of distributed system clock skew.
- **Session Termination (`SESSION_ENDED`):** Formally closes the session timeline, computing session summary metadata (total tool calls, policy denial count, cumulative duration).

## 3. Behavioral Timeline Model

The Event Store structures session events into four logical timeline representations:

1. **Chronological Master Timeline:** Comprehensive, time-ordered sequence of all events recorded during an agent's execution lifespan.
2. **Tool Invocation Timeline:** Isolated sequence tracking requested capabilities, parameter targets, execution start times, latencies, and completion statuses.
3. **Security Evaluation Timeline:** Dedicated trace of all authorization queries, policy evaluations, threat scans, and risk score outputs.
4. **Resource Access Timeline:** Focused view tracking every target filesystem path, database table, API endpoint, or external resource accessed during the session.

## 4. Behavioral Replay Architecture

Replayability is a core requirement for security auditing and forensic investigation:

- **Deterministic Reconstruction:** Reading a session's stored events in sequence order enables a forensic harness to reconstruct the exact system state, decision outcomes, tool calls, and security evaluations at any point in past execution time ($T_k$).
- **Replay Scope Boundaries:** Replay reconstructs observed agent behavior, security decisions, policy evaluations, and execution timelines.
- **Side-Effect-Free Invariant:** Replay does **not** re-execute live tools, re-authorize requests, modify historical event records, or generate new runtime security decisions. Behavioral replay is strictly observational and side-effect-free.
- **State Reconstruction Without External Dependencies:** Because telemetry envelope payloads capture parameters, evaluation decisions, and outcome metadata, session replay does not require re-executing live tools or querying external APIs.

## 5. Behavioral Snapshots

While the Behavioral Event Store maintains the canonical, append-only historical record, future platform components (such as stateful detection engines or SOC dashboards) may derive point-in-time behavioral snapshots:

- **Derived Artifacts:** Behavioral snapshots represent computed agent state aggregated at a specific moment in execution time.
- **Non-Mutating Behavior:** Snapshots are purely derived read artifacts. They **never** replace, modify, or overwrite underlying historical telemetry events.
- **Canonical Primacy:** If a discrepancy arises between a derived snapshot and stored telemetry events, the immutable Behavioral Event Store remains the authoritative source of truth.
- **Scope Isolation:** Snapshot generation, caching algorithms, and state materialization mechanics are outside the scope of ADR-016 and belong to downstream analytical components.

## 6. Event Integrity & Provenance

To guarantee that historical event data remains trustworthy as security evidence:

- **Immutable Write Guarantee:** Storage mechanisms enforce append-only semantics. In-place updates (`UPDATE`) and row deletions (`DELETE`) are prohibited at the storage boundary.
- **Origin Provenance:** Every event records its producing component (`producer_id`), distributed trace context (`trace_id`), and correlation context (`correlation_id`).
- **Sequence Integrity Verification:** Monotonic sequence gaps or out-of-order sequence insertion attempts trigger automated storage integrity alerts.

## 7. Data Classification & Sensitivity Management

Behavioral events stored within the platform carry explicit security classifications to govern access, retention, and inspection:

- **Operational Telemetry:** Execution timing, tool resolution, and pipeline routing metrics.
- **Sensitive Context:** Resource target paths, parameter hashes, and identity context.
- **Restricted Audit Records:** Policy violation details, authorization denial traces, and threat finding findings.
- **Compliance-Sensitive Evidence:** Complete forensic timelines preserved under regulatory or legal hold.

Data classification is an explicit architectural concern of the Behavioral Event Store. Downstream query interfaces and storage engines must preserve classification metadata to enforce role-based inspection boundaries without altering event contents.

---

# Event Relationships (Conceptual Data Model)

The Event Store organizes data according to a hierarchical, technology-agnostic conceptual model:

```text
Enterprise Tenant (tenant_id)
└── Enterprise Agent Identity (agent_id)
    └── Execution Session (session_id)
        └── Session Execution Sequence (monotonic sequence_number)
            └── Transaction Context (trace_id / correlation_id)
                ├── [1] Tool Invocation Requested
                ├── [2] Authorization Checked
                ├── [3] Policy Evaluated
                ├── [4] Threat Scanned
                ├── [5] Decision Finalized (ALLOW / DENY / HOLD)
                └── [6] Tool Execution Completed / Failed
```

### Logical Relationships

- **Tenant to Agent (1 : N):** An enterprise tenant contains multiple registered Enterprise Agents.
- **Agent to Session (1 : N):** An agent executes across multiple independent operational sessions over time.
- **Session to Event (1 : N):** A session contains an ordered sequence of immutable telemetry events.
- **Trace to Event Group (1 : N):** A single tool invocation request (`trace_id`) groups related pipeline evaluation events (Auth, Policy, Decision, Outcome).

---

# Event Retrieval Architecture

The Event Store exposes specialized read-only query patterns designed for downstream consumers:

1. **Session Timeline Queries:** Retrieve all events for a given `session_id`, sorted by `sequence_number`. (Used by Behavioral Replay & Session Intelligence).
2. **Recent Sequence Pattern Queries:** Retrieve the last $K$ events for an active `session_id` or `agent_id`. (Used by ADR-017 for stateful sequence detection).
3. **Cumulative Metrics Queries:** Retrieve aggregated counters (denials, resource access entropy, tool call velocity) for a window $T$. (Used by ADR-018 for risk scoring).
4. **Transaction Trace Queries:** Retrieve all pipeline evaluation events matching a specific `trace_id` or `correlation_id`. (Used by SOC Analysts for single-request deep dives).

---

# Retention Strategy

The Event Store implements a three-tier retention architecture to balance performance, storage cost, and compliance requirements:

```text
Operational Storage (High Speed) ──> Compliance Storage (Extended Read) ──> Archival Storage (Immutable Backup)
```

1. **Operational Tier (Hot):** High-speed storage optimized for real-time reads by detection rules (ADR-017) and active risk scoring (ADR-018). Holds active and recently ended sessions.
2. **Compliance Tier (Warm):** Cost-optimized queryable storage for forensic investigations, SOC analysis, and regulatory reporting. Holds historical sessions for standard enterprise retention windows.
3. **Archival Tier (Cold):** Highly compressed, append-only long-term backup for legal hold and regulatory compliance.

> **Data Lifecycle Invariant**  
> Expiration or archiving of event data must follow explicit enterprise retention policies. Event deletion is handled via lifecycle partition dropping in cold storage, never via individual record mutation.

---

# Indexing Strategy

To support high-throughput, low-latency queries without sacrificing write performance, the Event Store defines five primary logical indexes:

1. **Session Index (`session_id`, `sequence_number`):** Primary index for session ordering and deterministic replay.
2. **Agent Timeline Index (`agent_id`, `timestamp`):** Index for cross-session agent history analysis.
3. **Trace Index (`trace_id`, `correlation_id`):** Index for transaction-level correlation across pipeline components.
4. **Event Type Taxonomy Index (`event_type`, `timestamp`):** Index for system-wide threat pattern mining.
5. **Tenant Isolation Index (`tenant_id`, `session_id`):** Index enforcing multi-tenant data boundaries.

---

# Trust Boundaries & Multi-Tenant Isolation

The Event Store operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Behavioral Telemetry Dispatcher                      │
│                                (ADR-015)                                │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     │ (Write-Only Telemetry Stream)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Behavioral Event Store Subsystem                    │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     Append-Only Persistence                       │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Tenant-Isolated Read-Only Queries)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        Detection (ADR-017)  │  Risk (ADR-018)  │  AgentSecOps (ADR-020) │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary & Multi-Tenant Guarantees

- **Write Access:** Restricted exclusively to the internal Telemetry Dispatcher (ADR-015). No external client, API caller, or LLM model provider can write directly to the Event Store.
- **Read Access:** Restricted to authorized platform subsystems (`Behavioral Detection Engine`, `Behavioral Risk Engine`, `AgentSecOps Console`) via read-only interfaces.
- **Multi-Tenant Isolation:** Behavioral histories are strictly tenant-isolated (`tenant_id`). Replay operations cannot cross tenant boundaries, retrieval queries cannot cross tenant boundaries, and indexes enforce strict tenant isolation boundaries.
- **Mutation Prohibition:** Storage engine access permissions explicitly revoke `UPDATE`, `MODIFY`, and `DELETE` operations for runtime query roles.

---

# Benefits

- **Uncompromising History Integrity:** Append-only mechanics guarantee that historical agent behavior records remain immutable and tamper-evident security evidence.
- **Deterministic Forensic Replay:** Session-centric ordering enables exact timeline reconstruction for incident response.
- **Optimized for Stateful Analytics:** Multi-key logical indexing enables rapid lookups for sequence detection (ADR-017) and cumulative risk scoring (ADR-018).
- **Technology-Agnostic Architecture:** Clear separation of domain models from underlying database vendors ensures long-term infrastructure flexibility.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Storage Volume Growth:** Storing granular, un-mutated event sequences requires scalable persistence capacity over time (mitigated by tiered retention).
- **Index Maintenance Overhead:** Maintaining multi-key indexes for rapid timeline queries requires storage and memory allocations.

## Alternatives Considered

### Option A: In-Memory Event Buffering without Persistence
Buffer events in RAM for live detection and discard them when the session ends.
- **Rejected:** Completely eliminates forensic replayability, prevents cross-session agent profiling, and violates enterprise audit compliance requirements.

### Option B: Mutable Database Records with In-Place Updates
Update existing database rows as session state changes (e.g., updating a session summary row).
- **Rejected:** In-place updates destroy historical execution sequences, prevent deterministic replay, and introduce race conditions in multi-threaded runtime environments.

### Option C: LLM-Summarized Event Logs
Use an LLM to generate periodic natural language summaries of agent activity and store only the summaries.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). Summarization loses exact parameters, execution timings, and decision outcomes, destroying deterministic auditability.

---

# Scope

### In Scope (ADR-016)
- Append-only persistence architecture and event lifecycle.
- Behavioral Session Model and session ordering semantics.
- Multi-dimensional Timeline Model.
- Behavioral Replay Architecture and Behavioral Snapshots concept.
- Event integrity, provenance, and tamper-resistance principles.
- Technology-agnostic conceptual data model and relationships.
- Event retrieval query patterns and multi-tenant isolation principles.
- Tiered retention strategy and logical indexing requirements.

### Out of Scope (Deferred to Future ADRs)
- **Telemetry Emission & Taxonomy:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Stateful Detection Rules & Algorithms:** Owned by [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md).
- **Cumulative Risk Scoring Algorithms:** Owned by [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md).
- **Enforcement & Override Mechanics:** Owned by [ADR-019: Behavioral Enforcement](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement.md).
- **SOC Investigation Dashboards:** Owned by [ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md).

---

# Consequences

## Positive
- Provides a robust, append-only historical foundation for all Behavioral Intelligence components.
- Guarantees forensic replayability for enterprise SOC investigations.
- Establishes clear read/write trust boundaries protecting audit records from tampering.

## Negative
- Requires storage capacity planning for high-volume enterprise telemetry streams.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to historical persistence and event integrity guarantees.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; event persistence and storage models are strictly non-LLM.
- **Principle 3 – Deterministic Security Enforcement:** Supported; historical event data allows reproducible detection and risk analysis.
- **Principle 4 – Explicit Trust Boundaries:** Enforced via read-only interfaces and write-isolated telemetry boundaries.
- **Principle 8 – Complete Auditability:** Fully realized through immutable session timelines and deterministic replay.

---

# Related Documents

- [ADR-001: Zero Trust Security Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-001-zero-trust-security-model.md)
- [ADR-002: LLM as Untrusted Intent Parser](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-002-llm-untrusted-intent-parser.md)
- [ADR-004: Deterministic Security Pipeline](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-004-deterministic-security-pipeline.md)
- [ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md)
- [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md)
