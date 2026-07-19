# ADR-010: Scenario Execution Architecture

**Status:** Accepted

**Date:** 2026-07-19

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Approved
- Implementation: Pending (PR #59)

---

# Context

The platform has an established Scenario Framework that defines reusable security scenarios as immutable content artifacts (`AttackScenario`). These scenarios describe expected runtime behavior and security outcomes.

The platform now requires the ability to execute these scenarios against the deterministic security pipeline to validate:

- prompt parsing and tool selection
- authorization and policy enforcement
- detection rule coverage
- risk assessment accuracy
- response recommendation correctness

Without a dedicated execution architecture, scenario execution could be implemented in multiple inconsistent ways:

- directly inside `RuntimeService`, polluting the security pipeline with test harness logic
- as ad-hoc scripts outside the platform, losing access to shared state and audit trails
- through the Management API, violating the read-only management plane boundary (ADR-008)

---

# Decision Drivers

- **Zero Trust Alignment:** Preserve the deterministic runtime security boundary of `RuntimeService` as defined in ADR-003 and ADR-004.
- **Observability Isolation:** Maintain the read-only observability constraints of the Enterprise Management API as defined in ADR-008.
- **Architectural Simplicity:** Keep the initial execution model synchronous and direct, avoiding speculative asynchronous queuing.
- **Incremental Extensibility:** Enable future evolution (asynchronous jobs, execution history logging, multi-agent runs) without requiring a core redesign.

---

# Decision

The platform introduces `ScenarioRunnerService` as a dedicated orchestration layer for scenario execution.

`ScenarioRunnerService` is responsible for:

- Loading `AttackScenario` definitions
- Determining the execution mode (`ExecutionMode`)
- Executing scenarios through the appropriate runtime path
- Collecting `RuntimeResult` outputs
- Grading execution outcomes against expected assertions
- Producing `ScenarioExecution` and `ScenarioExecutionResult` objects

`ScenarioRunnerService` must never perform security decisions. All authorization, policy evaluation, detection, risk assessment, response recommendation, and audit recording remain the exclusive responsibility of `RuntimeService`.

Two execution modes are supported:

### 1. Prompt Execution Mode
```text
AttackScenario → AgentRuntimeService → LLM Intent Parser → RuntimeService
```
Used to validate end-to-end behavior: prompt parsing, tool selection, and the deterministic security pipeline.

### 2. Tool Sequence Execution Mode
```text
AttackScenario → RuntimeService (direct)
```
Used to validate deterministic security controls (authorization, policy, detection, response) in isolation, bypassing the LLM.

## Execution Flow Diagram

```text
                     ScenarioRunnerService
                              │
              ┌───────────────┴───────────────┐
              │                               │
        Prompt Mode                    Sequence Mode
              │                               │
    AgentRuntimeService                       │
              │                               │
        LLM Provider                          │
              │                               │
              └───────────┬───────────────────┘
                          │
                   RuntimeService
                          │
           ┌──────────────┼──────────────┐
           │              │              │
    Authorization    Detection      Risk Assessment
           │              │              │
      Policy Engine  Detection Engine  Response Service
                          │
                    Audit Service
```

Scenario execution endpoints belong to the Runtime API plane. The Enterprise Management API (ADR-008) remains strictly read-only.

---

# Rationale

## Separation of Orchestration and Security
`RuntimeService` is the deterministic security pipeline orchestrator (ADR-003). Embedding scenario orchestration, assertion logic, or test harness concerns inside `RuntimeService` would violate the Single Responsibility Principle and increase the risk of security regressions. `ScenarioRunnerService` acts as a pure test runner that delegates all security decisions to the trusted pipeline.

## Dual Execution Modes
Prompt execution validates the complete agent loop including LLM behavior. Tool sequence execution validates the deterministic pipeline in isolation. Supporting both modes allows the platform to validate different security properties independently.

## Runtime API Placement
ADR-008 establishes that the Management API is a read-only observability plane. Scenario execution invokes tools, calls LLM providers, and generates audit events — these are runtime operations. Placing execution endpoints on the Runtime API preserves this boundary.

---

# Alternatives Considered

## Embed Execution in RuntimeService
Allow `RuntimeService` to accept scenario objects and grade results internally.
### Rejected
This couples test harness logic with the security pipeline, increasing complexity and the risk of security regressions. `RuntimeService` should remain a focused security orchestrator.

## Execute via Management API
Expose `POST /api/v1/scenarios/{id}/run` on the Management API.
### Rejected
This violates ADR-008. The Management API must never execute tools or invoke LLM providers.

## External Test Scripts
Run scenarios via standalone Python scripts outside the platform.
### Rejected
External scripts cannot access shared in-memory state (sessions, audit events, agent registry). Results would be invisible to the Management Console and dashboard.

---

# Consequences

## Positive
- Clean separation between security decisions and test orchestration
- Both execution modes available from a single service
- Execution results flow through shared state and appear in audit logs
- `RuntimeService` remains focused and deterministic
- Future execution backends can be added without modifying the security pipeline

## Negative
- Additional service to maintain
- Prompt execution depends on LLM provider availability
- Two execution paths require separate test coverage

## Risks
- `ScenarioRunnerService` could accumulate business logic over time if responsibilities are not carefully maintained
- Prompt-mode execution introduces LLM non-determinism into scenario outcomes

---

# Out of Scope

This ADR intentionally does not define:
- Execution persistence or database storage
- Execution history querying interfaces
- Execution REST APIs (covered in ADR-010 implementation updates and subsequent PRs)
- Asynchronous execution, scheduling, or background worker queues
- Telemetry, OpenTelemetry integrations, or metric dashboards
- Frontend user interfaces or UI timelines

---

# Security Considerations

`ScenarioRunnerService` is an orchestration layer, not a trusted security component.

It must never:
- Perform authorization decisions
- Bypass `RuntimeService`
- Suppress or modify detection findings
- Override response recommendations
- Fabricate audit events

All security decisions flow exclusively through `RuntimeService`.

Scenario executions use isolated session identifiers to prevent cross-contamination with production sessions.

Execution endpoints require authentication and belong to the Runtime API trust boundary.

---

# Future Evolution

- **Asynchronous Execution:** The execution flow can be adapted to asynchronous task queues (e.g. Celery) without changing the service responsibility boundaries.
- **Persistence:** The outputs (`ScenarioExecution`, `ScenarioExecutionResult`) can be mapped directly to a persistent database layer for historical reporting.
- **Telemetry:** Execution spans can be instrumented with OpenTelemetry to track execution times and policy latency across both execution modes.
- **Framework Integrations:** Results can be mapped to external taxonomies (MITRE ATLAS, OWASP LLM Top 10) to generate live security coverage reports.

---

# Architectural Principles Affected
- Principle 1 – Zero Trust by Default
- Principle 3 – Deterministic Security Decisions
- Principle 4 – Explicit Trust Boundaries
- Principle 11 – Separation of Responsibilities
- Principle 16 – Security Through Composition

---

# Related Documents
- ADR-003: Runtime Security Orchestrator
- ADR-004: Deterministic Security Pipeline
- ADR-008: Enterprise Management API
- ADR-011: Scenario Execution Lifecycle
- ADR-012: Scenario Execution Domain Model
- ADR-013: ScenarioRunner Service Boundaries

---

# Architecture Status

**Status:** FROZEN  
**Approved:** 2026-07-19  

This ADR defines the approved architecture for the Scenario Execution Framework.  

Future architectural modifications require:
- Architectural justification
- ADR update
- Implementation impact analysis
