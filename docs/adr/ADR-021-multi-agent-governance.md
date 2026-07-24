# ADR-021: Multi-Agent Governance

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Pending ADR-021 Review)
- Implementation: Deferred (No production code modified; technology-agnostic multi-agent governance architecture)

---

# Context

[ADR-014: Behavioral Intelligence and Autonomous Agent Governance](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) established Behavioral Intelligence as an observational subsystem operating alongside the Runtime Security Pipeline to govern multi-step autonomous agent behavior over extended execution lifespans.

[ADR-015](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md) through [ADR-019](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md) defined non-blocking telemetry, append-only persistence, deterministic threat detection, cumulative risk scoring, and automated enforcement overrides for individual Enterprise Agents.

[ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md) established the operational control plane for SOC visibility, investigation replay, and human-in-the-loop approvals.

As enterprise AI deployments scale from single-turn assistants to complex networks of collaborating autonomous agents (agent groups, delegation chains, subagent orchestration), security boundaries must extend across inter-agent interactions—establishing **Multi-Agent Governance**.

The foundational platform principle remains absolute:

> **The LLM is an untrusted intent parser.**

Multi-Agent Governance is strictly a deterministic, compiled platform capability. The LLM has no authority, access, or involvement in inter-agent trust evaluation, delegation policy enforcement, capability boundary checks, or collaboration authorization.

---

# Problem Statement

Single-agent security controls evaluate requests within the boundary of a single authenticated agent identity. However, modern autonomous systems deploy multiple collaborating agents that delegate sub-tasks, share context, spawn background subagents, and pass tool parameters across agent boundaries.

Without a dedicated Multi-Agent Governance Architecture:

- **Privilege Amplification via Delegation:** A low-privilege agent could delegate a task to a high-privilege agent, effectively escalating its permissions to execute unauthorized operations.
- **Implicit Trust Exploit Vector:** Assuming that inter-agent communications within an agent group are inherently trusted allows an adversary who compromises a single agent to compromise the entire multi-agent ecosystem.
- **Loss of Cross-Agent Attribution:** Multi-turn task delegations across chains of agents (Agent-A → Agent-B → Agent-C) would lack unified audit provenance, making it impossible to identify which root agent initiated a security violation.
- **Conflation of Orchestration and Security Governance:** Relying on framework-level orchestrators to enforce security constraints introduces non-deterministic governance and vendor lock-in.

Therefore, the platform requires an independent, framework-agnostic Multi-Agent Governance Architecture.

---

# Architectural Direction & Core Distinction

The platform introduces **Multi-Agent Governance** as the enterprise security control boundary governing interactions between collaborating autonomous AI agents:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│              Third-Party Agent Orchestration Frameworks                 │
│              (decides: planning, routing, execution order)              │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Inter-Agent Collaboration Request)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Multi-Agent Governance Layer                           │
│                                                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │ Request Ingestion    │──>│ Governance Context Assembly            │  │
│  └──────────────────────┘   └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Trust & Relationship Evaluator         │  │
│                             └───────────────────┬────────────────────┘  │
│                                                 │                       │
│                                                 ▼                       │
│                             ┌────────────────────────────────────────┐  │
│                             │ Monotonic Delegation & Policy Engine   │  │
│                             └───────────────────┬────────────────────┘  │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
                                                  │ (Collaboration Decision)
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Runtime Security Pipeline                              │
│         (Sole Execution Boundary Intercepting Inter-Agent Calls)        │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │ (ALLOW Only)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             Secure Inter-Agent Communication / Execution                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Governance vs. Orchestration

A fundamental architectural boundary distinguishes the security platform from agent frameworks:

> **The platform does NOT orchestrate agents; the platform governs them.**

- **External Orchestration Frameworks decide:** Task decomposition, execution ordering, reasoning paths, prompt routing, subagent spawning, and agent-to-agent message passing.
- **Enterprise Agent Security Platform decides:** Whether inter-agent interaction is permitted, trust relationship validation, delegation authority bounds, capability isolation, cross-agent policy evaluation, and inter-agent audit attribution.

The architecture remains completely framework-agnostic. It governs multi-agent interactions regardless of the underlying execution or orchestration framework.

---

# Core Question & Platform Progression

Multi-Agent Governance shifts the platform focus from protecting a single agent to governing distributed autonomous agent ecosystems:

- Behavioral Intelligence asks: *"What happened?"*
- AgentSecOps asks: *"What should operators do?"*
- Multi-Agent Governance asks: **"Should these agents be allowed to collaborate?"**

The complete single-responsibility progression across the platform is established as:

$$\text{Behavioral History (ADR-016)} \longrightarrow \text{Detection Context (ADR-017)} \longrightarrow \text{Behavioral Findings (ADR-017)} \longrightarrow \text{Risk Context (ADR-018)} \longrightarrow \text{Behavioral Risk Assessment (ADR-018)} \longrightarrow \text{Current Behavioral Risk State (ADR-018)} \longrightarrow \text{Enforcement Context (ADR-019)} \longrightarrow \text{Behavioral Enforcement Decision (ADR-019)} \longrightarrow \text{Current Enforcement State (ADR-019)} \longrightarrow \text{Multi-Agent Governance Context (ADR-021)} \longrightarrow \text{Collaboration Decision (ADR-021)} \longrightarrow \text{Runtime Security Pipeline} \longrightarrow \text{Secure Agent Collaboration}$$

Every layer owns exactly one responsibility. No responsibility overlap is permitted.

---

# Architectural Principles

1. **Zero Trust Between Agents:** No implicit trust exists between autonomous agents. Every inter-agent communication, parameter transfer, or task delegation is independently authenticated and authorized.
2. **Least Privilege Collaboration:** Agents may collaborate only when an explicit, deterministic enterprise policy permits the interaction.
3. **Monotonic Delegation Invariant (Strict Non-Amplification):** Delegated authority must always be a strict subset of the delegating agent's capabilities. A delegated agent can **never** acquire greater privileges than the delegating agent.
4. **Capability Isolation:** Each agent retains its own isolated capability boundary. Collaboration never merges, pools, or elevates permissions across agent identities.
5. **Deterministic Governance Evaluation:** Collaboration decisions are strictly policy-driven and deterministic. Given identical agent identities, delegation scopes, and enterprise policies, the platform always produces identical collaboration decisions.
6. **Complete Cross-Agent Traceability:** Every inter-agent interaction records full attribution (initiating agent, delegating chain, target agent, requested capability, decision, rationale, trace ID).
7. **Framework-Agnostic Isolation:** Governance controls operate at the platform layer, protecting enterprise resources regardless of external agent orchestration technologies.

---

# Design Constraints

Multi-Agent Governance observes strict scope limits:

- **Must Not Orchestrate Tasks:** Execution scheduling, task routing, and workflow planning are owned by external agent frameworks.
- **Must Not Perform LLM Reasoning:** Trust evaluations, delegation checks, and policy matching must remain strictly non-LLM based.
- **Must Not Modify Telemetry or Findings:** Raw event persistence (ADR-016) and threat findings (ADR-017) remain immutable derived evidence.
- **Must Not Bypass Single-Request Authorization:** Inter-agent collaboration permissions operate in addition to, never instead of, request-level authorization (RBAC/ABAC).
- **Technology-Agnostic Design:** Defines governance contexts, trust models, delegation schemas, and collaboration decisions without mandating specific networking protocols, message queues, or orchestration vendors.

---

# Decision

The platform adopts **Multi-Agent Governance** as the canonical security architecture for multi-agent autonomous systems.

This decision establishes seven core architectural capabilities:

1. **Multi-Agent Pipeline Architecture:** Governance Context assembly, trust evaluation, and collaboration decision generation.
2. **Transient Governance Context Abstraction:** Derived analytical workspace isolating inter-agent evaluation.
3. **Canonical Multi-Agent Domain Model:** Standardized concepts for Agent Relationships, Agent Groups, and Delegations.
4. **Monotonic Delegation Model:** Invariant enforcing strict privilege reduction across delegation chains.
5. **Trust Relationship Matrix:** Explicit classification of inter-agent trust domains.
6. **Collaboration Decision Schema:** Standardized representation of multi-agent governance outcomes.
7. **Fail-Closed Availability Model:** Fail-safe isolation protecting platform security during governance outages.

---

# Component Ownership Matrix

| Subsystem / Layer | Architectural Ownership |
| :--- | :--- |
| **Runtime Security Pipeline** | Owns single-request authorization, physical request interception, and executing **Collaboration Decisions**. |
| **Telemetry Dispatcher (ADR-015)** | Owns event routing, queue buffering, and async telemetry emission. |
| **Behavioral Event Store (ADR-016)** | Owns event persistence, event immutability, and cross-agent trace queries. |
| **Behavioral Detection Engine (ADR-017)** | Owns multi-agent threat pattern analysis and cross-agent sequence detection. |
| **Behavioral Risk Engine (ADR-018)** | Owns cumulative multi-agent risk scoring and cross-session posture tracking. |
| **Behavioral Enforcement Engine (ADR-019)** | Owns policy overrides and single-agent containment actions. |
| **AgentSecOps Control Plane (ADR-020)** | Owns operational visibility, SOC workflows, investigation replay, and manual approvals. |
| **Multi-Agent Governance (ADR-021)** | Owns inter-agent trust evaluation, delegation policies, communication scopes, and **Collaboration Decisions**. |

---

# Detailed Architectural Specifications

## 1. Multi-Agent Pipeline Architecture

The multi-agent governance pipeline evaluates inter-agent requests through six sequential phases:

```text
Inter-Agent Request ──> Governance Context ──> Relationship Evaluation ──> Trust & Delegation Check ──> Collaboration Decision ──> Runtime Security Pipeline
```

1. **Inter-Agent Request Ingestion:** Intercepts an attempted interaction (message, delegation, subagent spawn, shared context) between Initiating Agent ($A_I$) and Target Agent ($A_T$).
2. **Governance Context Assembly:** Constructs a transient, read-only analytical context containing participating agent profiles, active risk states, tenant boundaries, and delegation parameters.
3. **Relationship Evaluation:** Checks whether an explicit **Agent Relationship** or **Agent Group** definition permits interaction between $A_I$ and $A_T$.
4. **Trust & Delegation Check:** Evaluates trust tiers and verifies that requested delegation capabilities satisfy the Monotonic Delegation Invariant.
5. **Collaboration Decision Generation:** Instantiates an immutable **Collaboration Decision** (`ALLOW_COLLABORATION`, `DENY_COLLABORATION`, `RESTRICTED_DELEGATION`).
6. **Pipeline Execution:** Delivers the decision to the Runtime Security Pipeline to permit or block inter-agent communication.

## 2. Multi-Agent Governance Context

To establish a clean architectural abstraction separating inter-agent requests from policy execution, the Multi-Agent Governance layer constructs a transient **Governance Context**:

- **Ephemeral & Read-Only:** Derived, transient analytical view created solely for the duration of collaboration evaluation.
- **Derived from Active State:** Constructed from active agent identities, `Current Behavioral Risk State` (ADR-018), `Current Enforcement State` (ADR-019), and enterprise multi-agent policies.
- **Non-Persisted:** Never written back into the Behavioral Event Store (ADR-016).
- **No Historical Authority:** Does not serve as historical security evidence; provides a transient evaluation workspace.
- **No Direct State Mutation:** Cannot modify agent credentials, risk scores, or telemetry events.

Conceptually, the Governance Context encapsulates initiating agent identity, target agent identity, requested delegation scope, trust relationship metadata, communication boundary constraints, and tenant isolation context (`tenant_id`).

## 3. Canonical Multi-Agent Architectural Concepts

Multi-Agent Governance defines six core domain concepts:

1. **Agent Relationship:** A governed, policy-defined association between two Enterprise Agent identities establishing permitted interaction channels.
2. **Agent Group:** A logical, governed collection of Enterprise Agents authorized to collaborate under shared ecosystem boundaries (e.g., "Financial Analysis Swarm").
3. **Delegation:** An explicit, bounded transfer of task authority from Initiating Agent ($A_I$) to Target Agent ($A_T$).
4. **Collaboration Decision:** A canonical, derived architectural artifact representing the outcome of a multi-agent governance evaluation.
5. **Governance Policy:** Enterprise rules defining allowable trust levels, delegation scopes, and capability boundaries between agents.
6. **Communication Scope:** Explicitly defined interaction boundaries governing message types, shared memory access, and parameter payload transfers between agents.

## 4. Monotonic Delegation Model & Privilege Monotonicity

Privilege amplification is one of the severe threat vectors in multi-agent systems. ADR-021 establishes an absolute architectural invariant governing delegation:

```text
Initiating Agent Capabilities (Scope A)
        │
        ▼ (Delegation Must Be a Strict Subset)
Delegated Capability Scope (Scope D ⊆ Scope A)
        │
        ▼ (Enforced by Governance Policy)
Target Agent Operational Scope (Effective Scope = Target Scope ∩ Scope D)
```

> **Monotonic Delegation Invariant**  
> Delegated authority must be a strict subset of the delegating agent's capabilities:  
> $$\text{Scope}_{\text{Delegated}} \subseteq \text{Scope}_{\text{Initiating}}$$  
> A target agent receiving a delegated task can **never** execute tools, access resources, or perform operations beyond the initiating agent's explicit permissions. Privilege amplification is strictly prohibited. If Target Agent $A_T$ possesses higher privileges than Initiating Agent $A_I$, $A_T$ operates strictly under the restricted subset $\text{Scope}_{\text{Initiating}}$ for the duration of the delegated task.

## 5. Trust Relationships Taxonomy

Multi-Agent Governance evaluates five canonical trust relationship tiers:

1. **Trusted:** Explicitly verified, high-trust relationship permitting full capability delegation within policy bounds.
2. **Restricted:** Limited trust relationship enforcing mandatory parameter sanitization and capability restrictions on inter-agent calls.
3. **Delegated:** Temporary, single-task relationship where authority is explicitly scoped and time-bound.
4. **Temporary:** Short-lived, ephemeral relationship established for a single execution session.
5. **Isolated:** Zero-trust isolation tier where all inter-agent communication, delegation, and context sharing are strictly blocked.

## 6. Collaboration Decision Schema & Immutability

A **Collaboration Decision** is a canonical, derived architectural artifact representing an evaluated inter-agent governance decision:

- **Metadata Envelope:**
  - `decision_id`: Unique UUID identifier for the collaboration decision.
  - `schema_version`: Version string of the multi-agent policy schema (e.g., `1.0`).
  - `timestamp`: UTC timestamp when the decision was generated.

- **Context Envelope:**
  - `initiating_agent_id`: Identifier of the agent requesting collaboration ($A_I$).
  - `target_agent_id`: Identifier of the target collaborating agent ($A_T$).
  - `agent_group_id`: Optional identifier of the governing agent group.
  - `tenant_id`: Multi-tenant organization identifier.

- **Governance Payload:**
  - `collaboration_decision`: Outcome tier (`ALLOW_COLLABORATION`, `DENY_COLLABORATION`, `RESTRICTED_DELEGATION`).
  - `effective_capability_scope`: Explicit array of permitted tool/resource capabilities for the interaction.
  - `triggering_policy_id`: Identifier of the multi-agent policy rule evaluated.
  - `rationale`: Human-readable, deterministic explanation of the decision.

> **Collaboration Decision Immutability**  
> Once generated, a Collaboration Decision is immutable. Decisions are derived historical evidence and must never be modified in place. Updated collaboration determinations are represented by generating new decision records.

---

# Trust Boundaries & Multi-Tenant Isolation

Multi-Agent Governance operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│              Third-Party Agent Orchestration Framework                  │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                            │ (Inter-Agent Request - Untrusted Envelope)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Governance Layer                         │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │      Deterministic Trust, Relationship & Delegation Engine        │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ (Collaboration Decisions - Tenant Isolated)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Runtime Security Pipeline                             │
│         (Sole Component Intercepting & Enforcing Communication)         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary & Multi-Tenant Guarantees

- **No Cross-Tenant Collaboration:** Inter-agent collaboration across enterprise tenant boundaries (`tenant_id`) is strictly prohibited by default. Cross-tenant interactions require explicit, cryptographic-neutral enterprise policy opt-in.
- **Independent Agent Validation:** Every participating agent in a multi-agent chain is independently authenticated against the Tool Registry and identity provider.
- **Execution Isolation:** Multi-Agent Governance evaluates collaboration decisions but relies on the Runtime Security Pipeline to intercept and enforce inter-agent communications.

---

# Availability & Fail-Closed Philosophy

Multi-Agent Governance adheres to a fail-closed operational philosophy for inter-agent interactions:

> **Multi-Agent Governance Fail-Closed Philosophy**  
> Multi-Agent Governance provides inter-agent trust evaluation, delegation control, and collaboration boundaries. If the Multi-Agent Governance layer experiences an unexpected component failure, policy evaluation timeout, or decision error, new inter-agent collaboration requests and delegations **fail closed (are denied)**. Single-agent execution, single-request authorization, telemetry, storage, detection, risk scoring, and single-agent enforcement continue operating with 100% functionality.

---

# Benefits

- **Prevents Privilege Amplification:** Monotonic delegation guarantees low-privilege agents cannot exploit high-privilege agents to bypass security controls.
- **Zero Trust Inter-Agent Security:** Eliminates implicit trust in multi-agent swarms, securing enterprise systems against compromised internal agents.
- **Framework-Agnostic Architecture:** Governs multi-agent systems regardless of whether they are built on CrewAI, AutoGen, LangGraph, or custom internal orchestrators.
- **Complete End-to-End Traceability:** Maintains full audit attribution across complex multi-agent delegation chains back to root initiating agents.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Delegation Evaluation Latency:** Evaluating inter-agent trust relationships and capability scope intersections introduces microsecond evaluation overhead per delegation request.
- **Policy Management:** Defining explicit agent group boundaries and delegation matrix rules requires administrative policy management for complex multi-agent ecosystems.

## Alternatives Considered

### Option A: Rely on Orchestration Frameworks for Security
Allow third-party agent frameworks (CrewAI, AutoGen, LangGraph) to manage inter-agent permissions and trust internally.
- **Rejected:** Violates Zero Trust. External frameworks treat security as an afterthought, lack deterministic policy controls, permit implicit trust, and introduce severe vendor lock-in.

### Option B: Merge All Agent Permissions into a Shared Swarm Identity
Assign a single, combined RBAC role to an entire group of collaborating agents.
- **Rejected:** Violates Least Privilege and Capability Isolation. Merging permissions allows any compromised subagent to access all resources across the entire swarm.

### Option C: Use LLMs to Judge Inter-Agent Trust
Deploy an LLM ("trust evaluator agent") to inspect inter-agent messages and decide whether collaboration is safe.
- **Rejected:** Violates ADR-002 ("The LLM is an untrusted intent parser"). LLMs introduce non-deterministic trust decisions, un-auditable delegation approvals, and vulnerability to indirect prompt injection across agent communications.

---

# Scope

### In Scope (ADR-021)
- Framework-agnostic Multi-Agent Governance architecture and evaluation pipeline.
- Transient Multi-Agent Governance Context abstraction.
- Monotonic Delegation Model enforcing strict privilege non-amplification.
- Canonical domain concepts (Agent Relationships, Agent Groups, Delegations, Collaboration Decisions).
- Trust relationships taxonomy across five tiers.
- Cross-agent auditability and multi-tenant isolation principles.
- Fail-closed operational philosophy for inter-agent requests.

### Out of Scope
- **Agent Task Orchestration & Planning:** Owned by external third-party agent frameworks.
- **Telemetry Emission:** Owned by [ADR-015: Behavioral Telemetry Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-015-behavioral-telemetry-architecture.md).
- **Event Persistence:** Owned by [ADR-016: Behavioral Event Store & Data Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-016-behavioral-event-store-and-data-model.md).
- **Detection Rules:** Owned by [ADR-017: Behavioral Detection Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-017-behavioral-detection-engine.md).
- **Risk Scoring:** Owned by [ADR-018: Behavioral Risk Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-018-behavioral-risk-engine.md).
- **Single-Agent Enforcement:** Owned by [ADR-019: Behavioral Enforcement Engine](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-019-behavioral-enforcement-engine.md).
- **SOC Operations:** Owned by [ADR-020: Agent Security Operations](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md).

---

# Consequences

## Positive
- Completes the Enterprise Agent Security Platform architecture for multi-agent autonomous systems.
- Prevents privilege escalation and implicit trust exploitation in agentic swarms.
- Preserves complete framework independence and Zero Trust auditability.

## Negative
- Requires maintaining inter-agent relationship policies for multi-agent enterprise deployments.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to inter-agent communication and task delegation.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; multi-agent governance logic is strictly non-LLM, deterministic platform code.
- **Principle 3 – Deterministic Security Enforcement:** Extended to inter-agent collaboration authorization.
- **Principle 4 – Explicit Trust Boundaries:** Enforced across agent identity boundaries and agent groups.
- **Principle 8 – Complete Auditability:** Realized across multi-agent delegation chains.

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
- [ADR-020: Agent Security Operations (AgentSecOps)](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-020-agent-security-operations.md)
