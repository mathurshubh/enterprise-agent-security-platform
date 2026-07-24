# ADR-014: Behavioral Intelligence and Autonomous Agent Governance

**Status:** Proposed

**Date:** 2026-07-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Proposed (Strategic Architectural Direction)
- Implementation: Deferred (No production code modified; current runtime implementation remains unchanged)

---

# Context

The Enterprise Agent Security Platform currently provides deterministic runtime governance for Enterprise AI Agents. The platform enforces Zero Trust security principles across all interactions through an integrated architecture comprising:

- Zero Trust Security Model
- Runtime Security Pipeline
- Deterministic Authorization & Policy Engine
- Threat Detection Engine
- Risk Assessment & Response Engine
- Session Tracking Service
- Immutable Audit Logging Service
- Centralized Tool Registry & Governance

A foundational architectural principle governs the entire platform:

> **The LLM is an untrusted intent parser.**

The LLM must never make security decisions, evaluate authorization policies, calculate risk scores, or determine mitigation responses. All security decisions remain strictly deterministic and are executed outside the LLM in compiled/interpreted platform code.

> **Architectural Shift**  
> Enterprise AI Security is evolving from inspecting isolated single-turn prompts to governing multi-step autonomous behavior over time across complex agent execution lifespans.

---

# Problem Statement

Traditional AI security frameworks focus almost exclusively on single-turn, request-level threat vectors:

- Prompt Injection (Direct and Indirect)
- Jailbreak Payloads
- Toxic Output Generation
- Model Hallucinations

However, enterprise AI is rapidly evolving beyond simple single-turn text interactions toward autonomous, long-running, goal-driven agents capable of:

- Multi-step reasoning and autonomous planning
- Complex tool orchestration and dynamic execution chains
- Direct interaction with internal infrastructure, databases, and APIs
- Long-running, multi-session task execution
- Multi-agent collaboration, delegation, and subagent orchestration

This evolution introduces an entirely new class of security risks. An adversary or misaligned agent may execute individually benign tool calls that, when combined across a long-horizon session, constitute a severe security compromise (e.g., incremental resource enumeration followed by unauthorized data aggregation and exfiltration).

Consequently, enterprise security platforms must evaluate not only **individual requests**, but also **agent behavior over time**.

---

# Architectural Direction

The Runtime Security Pipeline remains the authoritative, deterministic enforcement boundary for all agent actions.

This ADR proposes a new architectural capability—**Behavioral Intelligence**—that operates alongside the existing pipeline as an observational telemetry and assessment subsystem:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Runtime Security Pipeline                            │
│              (Primary Deterministic Enforcement Boundary)               │
│                                                                         │
│  Authorization ──> Policy Engine ──> Threat Detection ──> Risk/Response │
└───────────────────────────┬─────────────────────────────────▲───────────┘
                            │                                 │
                            │ (Runtime Events)                │ (Behavioral Assessments)
                            ▼                                 │
┌─────────────────────────────────────────────────────────────┴───────────┐
│              Behavioral Intelligence Subsystem (Observational)          │
│                                                                         │
│  ┌────────────────────────┐  ┌───────────────────────────────────────┐  │
│  │ Behavioral Event Store │  │ Session Intelligence & Timelines      │  │
│  └───────────┬────────────┘  └───────────────────┬───────────────────┘  │
│              │                                   │                      │
│              ▼                                   ▼                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Behavioral Detection (Outputs: Behavioral Findings)               │  │
│  └───────────────────────────┬───────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Behavioral Risk Engine (Outputs: Behavioral Assessments)          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

Behavioral Intelligence does **not** replace, bypass, or sit in front of the Runtime Security Pipeline. Instead, it operates in parallel: it consumes runtime events generated during tool invocation evaluations, maintains stateful behavioral models, and feeds deterministic behavioral assessments back into the Policy Engine, Threat Detection Engine, Risk Assessment Service, and Response Service to augment enforcement decisions.

---

# Architectural Principles

The proposed architectural evolution reinforces and extends the platform's core design principles:

1. **Zero Trust Architecture Unchanged:** Every runtime transition, tool invocation, and resource parameter request is explicitly authenticated, authorized, analyzed, and audited.
2. **Deterministic Enforcement Boundary:** The Runtime Security Pipeline remains the single, authoritative boundary where security decisions are computed and enforced.
3. **Observational by Design:** Behavioral Intelligence is observational by design. It generates deterministic behavioral assessments but must never authorize requests, deny requests, execute tools, override policy, bypass authorization, or replace deterministic security decisions. Enforcement remains strictly within the Runtime Security Pipeline.
4. **Deterministic and Reproducible Analytics:** All behavioral detections, risk score escalations, and anomaly calculations must be explainable, auditable, and **reproducible**. Given the exact same sequence of runtime events, the platform must produce the identical behavioral assessment.
5. **No LLM Security Authority:** The LLM is never permitted to evaluate behavioral risk, modify policy enforcement, or grant authorization exceptions.

---

# Platform Security Invariant

Behavioral Intelligence may only strengthen deterministic security decisions.

It must never:

- weaken authorization
- override policy denials
- reduce risk
- bypass enforcement
- relax existing security guarantees

Behavioral Intelligence is additive to the Runtime Security Pipeline and cannot reduce existing protections.

---

# Design Constraints

Behavioral Intelligence must strictly observe the following design constraints:

- **Must Not Replace Deterministic Authorization:** Basic agent, role, and permission checks remain mandatory and independent.
- **Must Not Override Policy Denials:** A request denied by explicit resource policies can never be allowed or relaxed by behavioral analysis.
- **Must Not Depend on LLM Reasoning:** Behavioral algorithms and anomaly scoring must remain strictly algorithmic and non-LLM based.
- **Must Not Execute Tools:** Behavioral components cannot instantiate, invoke, or trigger enterprise tools.
- **Must Not Mutate Agent State:** Behavioral evaluation is side-effect-free with respect to agent credentials and governance definitions.
- **Must Never Weaken Existing Security Guarantees:** Behavioral assessments may only increase confidence in restrictive actions (e.g., escalating risk, requiring approvals, or suspending agents). They must never reduce or relax existing security controls.

---

# Decision

The platform adopts **Behavioral Intelligence and Autonomous Agent Governance** as its strategic architectural direction for future platform releases.

To maintain single-responsibility component boundaries, this decision establishes clear architectural roles for observation, analytics, risk evaluation, and enforcement:

### 1. Behavioral Intelligence (Subsystem & Telemetry Orchestration)
The umbrella capability responsible for observing runtime behavior, collecting telemetry streams, correlating runtime events, maintaining stateful session contexts, orchestrating analysis workflows, and providing telemetry to downstream behavioral components. Behavioral Intelligence does not directly calculate behavioral risk or enforce security decisions.

### 2. Behavioral Detection (Detection Engine)
Responsible for sequence analysis, anomaly detection, behavioral rule evaluation, pattern recognition, and multi-step threat identification across agent lifespans.  
*Outputs:* **Behavioral Findings**

### 3. Behavioral Risk Engine (Risk Evaluation)
Responsible for consuming behavioral findings, calculating cumulative behavioral risk scores, performing confidence evaluations, and escalating risk levels over session lifespans.  
*Outputs:* **Deterministic Behavioral Assessments**

### 4. Behavioral Enforcement (Enforcement Layer)
Responsible for consuming deterministic behavioral assessments from the Behavioral Risk Engine to enforce governance decisions—including approval holding, rate throttling, session suspension, agent isolation, tool blocking, and session termination. Behavioral Enforcement executes strictly through the Runtime Security Pipeline.

---

# Proposed Capabilities

## 1. Behavioral Intelligence

Behavioral Intelligence introduces deep observational capabilities across the agent lifecycle:

- **Runtime Behavioral Telemetry:** Standardized event streams capturing tool invocations, parameter values, execution outcomes, and latency.
- **Behavioral Event Generation:** Synthesizing structured security events from raw runtime transitions.
- **Behavioral Event Store:** High-throughput, append-only store for behavioral event streams.
- **Session Timelines:** Chronological tracking of all events within a specific agent session.
- **Tool Invocation Timelines:** Sequential analysis of tool usage patterns across time.
- **Resource Access Timelines:** Detailed tracking of accessed file paths, APIs, and database resources.
- **Investigation Replay:** Ability to step forward and backward through an agent's execution history for forensic analysis.
- **Behavioral Analytics:** Statistical and pattern-based analysis of agent operational baselines.

## 2. Behavioral Detection

Future releases will introduce stateful, multi-step detection rules targeting autonomous behavioral patterns:

- **Excessive Tool Invocation:** Detecting abnormal call rates or rapid-fire execution loops.
- **Recursive Tool Usage:** Identifying self-referential or infinite tool call loops that threaten denial-of-wallet or resource exhaustion.
- **Tool Abuse:** Detecting misuse of authorized tools for unintended operations.
- **Unauthorized Tool Sequences:** Identifying suspicious sequences of tool calls (e.g., `directory_list` → `file_read` → `web_post`).
- **Resource Enumeration:** Detecting systematic crawling of filesystems, databases, or API routes.
- **Unexpected Filesystem Traversal:** Flagging anomalous directory traversal or path navigation outside regular baselines.
- **API Exploration:** Detecting probe-like behavior targeting internal service endpoints.
- **Credential Discovery:** Identifying attempts to locate, read, or parse environment variables, configuration files, or key stores.
- **Goal Drift:** Detecting divergence between original user intent and current agent trajectory.
- **Planning Loops:** Identifying agents stuck in non-productive planning or reasoning loops.
- **Autonomous Persistence:** Detecting attempts by an agent to establish persistent footholds, cron jobs, or background tasks.
- **Behavioral Anomalies:** Statistical deviations from established agent behavior profiles.

## 3. Behavioral Risk Engine

Risk is not static; it evolves throughout the lifetime of an Enterprise Agent session. The Behavioral Risk Engine evaluates cumulative risk indicators including:

- **Tool Invocation Frequency:** Velocity and burst rates of requested capabilities.
- **Resource Diversity:** Entropy and scope of targeted system resources.
- **Authorization Denials:** Accumulation of failed authorization attempts or policy blocks within a session window.
- **Session Duration:** Long-running session lifetime metrics.
- **Sensitive Resource Access:** Proximity and frequency of access to high-value assets.
- **Policy Violations:** Historical tally of near-miss or denied policy evaluations.
- **Behavioral Anomalies:** Anomaly scores generated by behavioral analysis.
- **Historical Behavioral Patterns:** Cross-session baseline comparison for specific agent identities.
- **Cumulative Behavioral Risk:** Continuous aggregate risk scoring that triggers dynamic mitigation responses (e.g., escalating from `MONITOR` to `REQUIRE_APPROVAL` or `SUSPEND_AGENT` as session risk accumulates).

## 4. Session Intelligence

Session Intelligence provides security teams with comprehensive visibility into complex agent operations:

- **Session Timeline:** High-level chronological view of session milestones and transitions.
- **Tool Timeline:** Dedicated visual sequence of tool requests and execution outcomes.
- **Authorization Timeline:** Trace of all authorization queries and policy outcomes.
- **Policy Evaluation Timeline:** Step-by-step record of policy rules evaluated per invocation.
- **Detection Timeline:** Chronological mapping of triggered threat findings over session duration.
- **Risk Evolution:** Continuous graph of risk score trajectory across the session lifespan.
- **Investigation Replay:** Interactive forensic tool allowing security analysts to step through agent execution state changes.

## 5. Agent Security Operations (AgentSecOps)

To support enterprise security teams, future architectural phases will define an operational control plane:

- **Active Agent Sessions:** Real-time dashboard of currently executing Enterprise Agents.
- **High-Risk Agents:** Filtered views highlighting agents exceeding risk thresholds.
- **Behavioral Alerts:** Real-time notifications for critical behavioral anomalies and policy breaches.
- **Runtime Violations:** Centralized queue of blocked tool invocations and security overrides.
- **Tool Usage Analytics:** Enterprise-wide metrics on tool adoption, failure rates, and risk distribution.
- **Investigation Workbench:** Dedicated interface for deep-dive forensic analysis of flagged agent sessions.
- **Risk Trends:** Historical analytics tracking organizational AI risk posture over time.
- **Policy Analytics:** Evaluation of policy effectiveness, hit rates, and rule performance.

## 6. Multi-Agent Governance

As enterprise deployments scale to ecosystems of collaborating AI agents, governance controls must extend across agent boundaries:

- **Agent Identity & Verification:** Strong cryptographic identity and verification for every autonomous agent.
- **Agent-to-Agent Authorization:** Deterministic access controls governing inter-agent communication and task delegation.
- **Trust Relationships:** Explicitly defined trust domains and boundary constraints between specialized agents.
- **Delegation Policies:** Rules governing whether an agent can delegate sub-tasks or spawn sub-agents.
- **Cross-Agent Audit Trails:** Unified transaction logs tracing requests across multi-agent chains.
- **Cross-Agent Behavioral Analysis:** Detecting multi-agent attack patterns (e.g., one agent acting as a scout while another executes restricted actions).

---

# Trust Boundaries

Behavioral Intelligence operates strictly within the **Deterministic Platform Zone**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                            Untrusted Zone                               │
│  User Prompt ──> LLM / Intent Parser ──> Tool Invocation Request        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Deterministic Platform Zone                          │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Runtime Security Pipeline                      │  │
│  │  Authorization ──> Policy Check ──> Threat Scan ──> Decision      │  │
│  └───────────┬───────────────────────────────────────────────▲───────┘  │
│              │                                               │          │
│              │ (Runtime Events)      (Behavioral Assessments)│          │
│              ▼                                               │          │
│  ┌───────────────────────────────────────────────────────────┴───────┐  │
│  │               Behavioral Intelligence Subsystem                   │  │
│  │  Event Store ──> Behavioral Detection ──> Behavioral Risk Engine  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                   Deterministic Enforcement                       │  │
│  │  Policy Engine Overrides ──> Response Service (SUSPEND / APPROVE) │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │ (ALLOW Only)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Secure Execution Zone                          │
│            Tool Registry ──> Executable Tool Code ──> Audit Log         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary Guarantees

1. **Observer Property:** Behavioral Intelligence observes pipeline telemetry; it cannot directly execute tools or modify request parameters.
2. **Monotonic Restriction:** Behavioral assessments generated by the Behavioral Risk Engine can increase enforcement restrictions (e.g., escalating from `ALLOW` to `REQUIRE_APPROVAL` or `SUSPEND_AGENT`), but can **never** relax or bypass an existing authorization denial or policy block.
3. **Stateless Enforcement Isolation:** Core request-level authorization checks remain fast and independent, ensuring baseline security is never delayed by complex behavioral analytics.

---

# Threat Model Evolution

This ADR introduces a new threat category to the platform's security framework:

## Behavioral & Autonomous Agent Threats

Behavioral & Autonomous Agent Threats emerge from the cumulative behavior of an Enterprise Agent across multiple Tool Invocations and sessions rather than from any individual prompt or Tool Invocation.

Unlike single-turn prompt injection—which attacks the natural language parsing layer—behavioral threats exploit autonomous operational agency over time:

- **Agentic Attack Chains:** Executing a sequence of individually permissible actions that collectively form an exploit path.
- **Autonomous Reconnaissance:** Systematically probing filesystems, APIs, and network endpoints to discover high-value targets.
- **Tool Abuse:** Utilizing valid tools in unintended combinations to bypass single-request security controls.
- **Credential Harvesting:** Using file read or search tools to discover and accumulate access tokens, private keys, or passwords.
- **Goal Hijacking:** Subtly redirecting an agent's long-term objective through multi-turn conversational or environment manipulation.
- **Behavioral Policy Evasion:** Pacing tool calls or spreading requests across sessions to evade velocity limits or threshold-based rules.
- **Long-Horizon Autonomous Operations:** Executing covert actions across extended operational windows to avoid real-time detection.
- **Autonomous Persistence:** Attempting to establish persistent execution capabilities (e.g., scheduled jobs, modified scripts) within host environments.
- **Cross-Agent Abuse:** Exploiting inter-agent trust relationships to trick secondary agents into executing unauthorized actions.
- **Autonomous Data Exfiltration:** Slowly staging and trickling sensitive internal data to external endpoints over extended session timelines.

---

# Long-Term Platform Evolution

This ADR establishes the strategic evolutionary roadmap for the Enterprise Agent Security Platform:

```text
Prompt Security
        ↓
Tool Governance
        ↓
Runtime Security
        ↓
Behavioral Intelligence
        ↓
Behavioral Enforcement
        ↓
Multi-Agent Governance
        ↓
Enterprise AI Security Operations
```

Each stage builds upon the deterministic foundation of previous layers, advancing from basic prompt scanning to comprehensive enterprise AI security operations.

---

# Phased Architectural Evolution

Behavioral Intelligence is designed for incremental adoption across future platform releases:

- **Phase 1 – Behavioral Telemetry:** Standardized runtime event emission, session event collection, and basic audit correlations.
- **Phase 2 – Behavioral Analytics:** Session timelines, tool sequence tracking, and retrospective behavioral metrics.
- **Phase 3 – Behavioral Risk:** Cumulative risk scoring engines feeding live telemetry into the Risk Assessment Service.
- **Phase 4 – Behavioral Enforcement:** Automated policy overrides, dynamic throttling, approval holding, and behavioral suspension.
- **Phase 5 – Multi-Agent Governance:** Cross-agent identity verification, delegation policies, and multi-agent threat tracking.
- **Phase 6 – Enterprise AgentSecOps:** Operational SOC dashboard, live agent session monitoring, and investigation replay workbenches.

### Expected Child ADR Boundaries
The detailed technical design for each phase will be formally specified in dedicated future ADRs:
- **Behavioral Telemetry Architecture:** Event schemas, telemetry serialization, and stream ingestion contracts.
- **Behavioral Event Store & Data Model:** Persistent storage schemas, indexing strategies, and retention policies.
- **Behavioral Detection Engine:** Stateful sequence detection rule models, anomaly algorithms, and taxonomy mappings.
- **Behavioral Risk Engine:** Cumulative scoring algorithms, confidence decay models, and risk escalation logic.
- **Behavioral Enforcement & Policy Overrides:** Automated override mechanics, throttling controls, and suspension workflows.
- **AgentSecOps & Session Intelligence:** Operational console interfaces, timeline visualizations, and investigation replay harnesses.
- **Multi-Agent Governance Architecture:** Cryptographic identity verification, delegation policies, and cross-agent threat models.

> **Implementation Guidance Note:**  
> Future implementations should prioritize deterministic rule-based behavioral analysis before introducing optional statistical or machine learning-based anomaly detection. Any future statistical or machine learning-based anomaly detection must remain advisory. Final authorization, policy, risk, and enforcement decisions shall continue to be performed exclusively by deterministic platform components.

---

# Scope

### In Scope (Strategic Direction)
- Defining the architectural vision for Behavioral Intelligence, Behavioral Risk Engine, Session Intelligence, AgentSecOps, and Multi-Agent Governance.
- Establishing trust boundaries, design constraints, platform security invariants, and threat classifications for autonomous agent behavior.
- Documenting long-term platform evolution guidelines.

### Out of Scope (Current Release)
- **No production code changes:** This ADR does not introduce Python code, new services, database schemas, or API endpoints into the codebase.
- **Existing architecture remains unchanged:** Current implementations of `RuntimeService`, `AgentRuntimeService`, `AuthorizationService`, `PolicyEngine`, `DetectionEngine`, `RiskService`, `ResponseService`, `SessionService`, and `AuditService` operate exactly as documented in ADR-001 through ADR-013.
- **No immediate implementation required:** Implementation will occur incrementally in future dedicated release cycles.

---

# Benefits

- **Proactive Autonomous Defense:** Extends security coverage from single-turn prompt checks to complex, multi-step autonomous behavior.
- **Cumulative Risk Awareness:** Enables dynamic security enforcement that adapts as session risk accumulates over time.
- **Deep Operational Visibility:** Provides security analysts with complete forensic timelines and replay tools for complex agent interactions.
- **Multi-Agent Readiness:** Prepares the platform architecture for enterprise environments featuring collaborating agent networks.
- **Preserves Deterministic Security:** Integrates advanced behavioral insights without sacrificing the core requirement for explainable, non-LLM security decisions.

---

# Trade-offs & Alternatives Considered

## Trade-offs

- **Telemetry Storage Overhead:** Maintaining detailed behavioral event stores and session timelines requires persistent database storage.
- **State Management Complexity:** Tracking cumulative risk across long-running sessions introduces state synchronization considerations for multi-node deployments.
- **Threshold Tuning:** Behavioral anomaly detection rules require careful baseline tuning to avoid false positives in complex workflows.

## Alternatives Considered

### Option A: Rely Solely on Single-Request Enforcement
Continue evaluating tool requests purely in isolation without session-level behavioral tracking.
- **Rejected:** Fails to detect multi-step attack chains, goal drift, resource enumeration, and slow data exfiltration.

### Option B: Use LLMs to Evaluate Agent Behavior
Deploy a secondary LLM ("security evaluator agent") to inspect agent session transcripts and judge behavioral risk.
- **Rejected:** Violates core architectural principle ("The LLM is an untrusted intent parser"). LLM evaluators are susceptible to prompt injection, non-determinism, high latency, and lack of explainability.

### Option C: Embed Behavioral Logic Inside Executable Tools
Require individual tools to maintain call counters, sequence rules, and state history internally.
- **Rejected:** Violates Single Responsibility Principle and pollutes tool logic with security orchestration. Governance must remain centralized in the platform runtime.

---

# Consequences

## Positive
- Establishes a clear, long-term architectural vision for enterprise AI agent governance.
- Guides future PRs and release milestones toward behavioral security capabilities.
- Provides a comprehensive framework for addressing emerging autonomous agent threats.
- Enhances platform value for enterprise SOC teams requiring deep visibility and forensic tools.

## Negative
- Increases overall architectural scope for future platform roadmap releases.
- Will require persistent storage backends (database integration) in future implementation phases.

## Risks
- Behavioral anomaly rules could generate noise if baselines are not properly calibrated per agent role.
- Mitigated by ensuring behavioral assessments feed into deterministic, configurable policy thresholds.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust Architecture:** Extended to cover long-horizon behavioral interactions.
- **Principle 2 – LLM as Untrusted Intent Parser:** Reinforced; behavioral analytics are deterministic and external to the LLM.
- **Principle 3 – Deterministic Security Enforcement:** Reinforced; behavioral risk scores feed into deterministic policy evaluation.
- **Principle 4 – Explicit Trust Boundaries:** Behavioral Intelligence is explicitly isolated in the Deterministic Platform Zone.
- **Principle 8 – Complete Auditability:** Enhanced through comprehensive Session Intelligence, reproducibility, and timeline tracking.

---

# Related Documents

- [ADR-001: Zero Trust Security Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-001-zero-trust-security-model.md)
- [ADR-002: LLM as Untrusted Intent Parser](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-002-llm-untrusted-intent-parser.md)
- [ADR-003: Runtime Security Orchestrator](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-003-runtime-security-orchestrator.md)
- [ADR-004: Deterministic Security Pipeline](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-004-deterministic-security-pipeline.md)
- [ADR-005: Tool Registry](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-005-tool-registry.md)
- [ADR-006: Resource-Aware Authorization](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-006-resource-aware-authorization.md)
- [ADR-007: Provider-Agnostic Runtime](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-007-provider-agnostic-runtime.md)
- [ADR-008: Enterprise Management API](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-008-enterprise-management-api.md)
- [ADR-009: Enterprise Security Console](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-009-enterprise-security-console.md)
- [ADR-010: Scenario Execution Architecture](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-010-scenario-execution-architecture.md)
- [ADR-011: Scenario Execution Lifecycle](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-011-scenario-execution-lifecycle.md)
- [ADR-012: Scenario Execution Domain Model](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-012-scenario-execution-domain-model.md)
- [ADR-013: ScenarioRunner Service Boundaries](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/adr/ADR-013-scenario-runner-service-boundaries.md)
- [System Architecture Reference](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/system-architecture.md)
- [Threat Model Reference](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/security/threat-model.md)
