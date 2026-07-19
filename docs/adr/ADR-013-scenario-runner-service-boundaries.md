# ADR-013: ScenarioRunner Service Boundaries

**Status:** Accepted

**Date:** 2026-07-19

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Approved
- Implementation: Pending (PR #59)

---

# Context

The Scenario Execution Architecture (ADR-010) introduces three services that participate in scenario execution:

- `RuntimeService` — the deterministic security pipeline
- `AgentRuntimeService` — the agent execution loop
- `ScenarioRunnerService` — the scenario orchestration layer

Without explicit service boundary definitions, responsibilities may overlap over time. In particular:

- `ScenarioRunnerService` could accumulate security decision logic that belongs in `RuntimeService`
- `AgentRuntimeService` could duplicate detection or authorization logic
- `RuntimeService` could absorb test harness or orchestration concerns

This ADR defines the exact responsibilities of each service and the boundaries between them.

---

# Decision Drivers

- **Zero Trust Authority:** Preserve `RuntimeService` as the single authoritative decision maker for security evaluations.
- **Single Responsibility Principle:** Keep core security enforcement decoupled from testing execution harnesses and LLM agent parsing logic.
- **Incremental Abstraction:** Avoid premature protocol definitions until multiple concrete implementations exist.

---

# Decision

## RuntimeService
`RuntimeService` is the single authoritative component for all security decisions.

Responsibilities:
- **Authorization** — determine whether an agent is permitted to invoke a tool
- **Policy Evaluation** — evaluate platform policies against the execution context
- **Detection** — run detection rules against the execution context and content
- **Risk Assessment** — score the risk level based on detected findings
- **Response Recommendation** — recommend a response action based on risk assessment
- **Audit Recording** — record audit events for every security decision
- **Session Recording** — record session events for execution timeline tracking

`RuntimeService` must never:
- Parse natural language prompts
- Invoke LLM providers
- Execute tools
- Perform scenario orchestration
- Evaluate scenario assertions

`RuntimeService` accepts a single tool invocation context and produces a `RuntimeResult` containing the security decision, findings, risk assessment, and response recommendation.

---

## AgentRuntimeService
`AgentRuntimeService` coordinates the agent execution loop.

Responsibilities:
- Accept natural language queries
- Invoke the LLM provider to parse intent into tool invocations
- Pass tool invocations through `RuntimeService` for security evaluation
- Execute approved tools through the Tool Registry
- Return `AgentRuntimeResult` containing the decision, response type, and tool output

`AgentRuntimeService` must never:
- Perform authorization decisions
- Evaluate detection rules
- Assess risk
- Recommend response actions
- Record audit events directly
- Evaluate scenario assertions

`AgentRuntimeService` delegates all security decisions to `RuntimeService` through the `RuntimeExecutor` protocol.

---

## ScenarioRunnerService
`ScenarioRunnerService` orchestrates scenario execution and evaluates outcomes.

Responsibilities:
- Accept an `AttackScenario` and determine the execution mode (`ExecutionMode`)
- For prompt-based scenarios: delegate to `AgentRuntimeService`
- For tool-sequence scenarios: delegate to `RuntimeService`
- Collect execution results from the appropriate service
- Grade execution outcomes against scenario expectations
- Produce `ScenarioExecution` metadata and `ScenarioExecutionResult` assertions
- Construct structured mismatch diagnostics

`ScenarioRunnerService` must never:
- Perform authorization decisions
- Evaluate detection rules
- Assess risk
- Recommend response actions
- Record audit events
- Invoke LLM providers directly
- Execute tools directly
- Modify or suppress security pipeline outputs

`ScenarioRunnerService` is a pure orchestration and evaluation layer. It reads security pipeline outputs and compares them against expected values. It never influences those outputs.

## Boundary Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                  ScenarioRunnerService                          │
│                                                                 │
│  Owns: Execution strategy, grading, assertions, results        │
│  Trust: Untrusted orchestration layer                          │
│                                                                 │
│    ┌──────────────────────┐    ┌──────────────────────┐        │
│    │ AgentRuntimeService  │    │    RuntimeService     │        │
│    │                      │    │    (Direct Mode)      │        │
│    │ Owns: LLM parsing,   │    │                      │        │
│    │ tool execution       │    │                      │        │
│    │                      │    │                      │        │
│    │    ┌─────────────┐   │    │                      │        │
│    │    │RuntimeService├──┼────┤  Owns: Authorization  │        │
│    │    │(via Protocol)│   │    │  Policy, Detection,  │        │
│    │    └─────────────┘   │    │  Risk, Response,      │        │
│    │                      │    │  Audit, Session       │        │
│    └──────────────────────┘    │                      │        │
│                                │  Trust: Trusted       │        │
│                                │  security authority   │        │
│                                └──────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

## Responsibility Matrix

| Concern | RuntimeService | AgentRuntimeService | ScenarioRunnerService |
|:--------|:-:|:-:|:-:|
| Authorization | ✅ | — | — |
| Policy Evaluation | ✅ | — | — |
| Detection | ✅ | — | — |
| Risk Assessment | ✅ | — | — |
| Response Recommendation | ✅ | — | — |
| Audit Recording | ✅ | — | — |
| Session Recording | ✅ | — | — |
| LLM Intent Parsing | — | ✅ | — |
| Tool Execution | — | ✅ | — |
| Execution Strategy | — | — | ✅ |
| Grading / Assertions | — | — | ✅ |
| Result Construction | — | — | ✅ |

No responsibility appears in more than one service.

---

# Rationale

## Single Security Authority
`RuntimeService` is the only component that makes security decisions (ADR-003, ADR-004). This invariant must be preserved regardless of how many orchestration layers exist above it. If `ScenarioRunnerService` or `AgentRuntimeService` were to duplicate authorization or detection logic, the platform would have multiple inconsistent security enforcement points.

## Orchestration Without Authority
`ScenarioRunnerService` coordinates execution but has no authority over security outcomes. It reads results and grades them. This is analogous to a test harness: it invokes the system under test and asserts on the outputs, but it never modifies the system's behavior.

## Direct Dependency on AgentRuntimeService
`ScenarioRunnerService` depends directly on `AgentRuntimeService` for prompt execution. No `AgentExecutor` abstraction is introduced because only one implementation exists today.

Following the incremental architecture principle established in the codebase, protocols are extracted when a second implementation appears. The existing `RuntimeExecutor` protocol in `AgentRuntimeService` was introduced specifically because tests required a `StubRuntimeService` — not speculatively.

When additional agent implementations exist (multi-agent, alternative providers), the protocol will be extracted at that point.

---

# Alternatives Considered

## Merge ScenarioRunnerService into RuntimeService
Allow `RuntimeService` to accept scenarios and grade results.
### Rejected
This violates the single responsibility principle. `RuntimeService` is a security pipeline, not a test orchestrator. Merging these concerns increases complexity, couples test logic with production security enforcement, and makes `RuntimeService` harder to reason about.

## Introduce AgentExecutor Protocol Now
Define an `AgentExecutor` protocol that `AgentRuntimeService` implements, and have `ScenarioRunnerService` depend on the protocol.
### Rejected
With only one implementation, the protocol adds indirection without benefit. Premature abstractions increase maintenance burden and may not match the interface shape needed by future implementations. Extract when the second implementation appears.

## Allow ScenarioRunnerService to Record Audit Events
Let `ScenarioRunnerService` write execution metadata to the audit service.
### Rejected
Audit recording is the responsibility of `RuntimeService`. `ScenarioRunnerService` should not have write access to the audit trail. Execution metadata (`ScenarioExecution`, `ScenarioExecutionResult`) is a separate concern from security audit events.

---

# Consequences

## Positive
- Zero responsibility overlap between services
- `RuntimeService` remains the single security authority
- `ScenarioRunnerService` can be tested independently with mock services
- Clear trust boundaries between orchestration and security
- Service responsibilities are explicitly documented and enforceable

## Negative
- Three services participate in scenario execution, increasing the number of integration points
- Direct dependency on `AgentRuntimeService` means prompt-mode testing requires either a real LLM provider or a stub (which would trigger protocol extraction)

## Risks
- If service boundaries are not enforced through code review, responsibilities may drift over time
- Future multi-step scenarios may require additional orchestration logic in `ScenarioRunnerService`

---

# Out of Scope

This ADR intentionally does not define:
- `ToolRegistry` or filesystem tool execution logic
- Alternative multi-agent execution libraries
- LLM response parser regex patterns or validation structures

---

# Security Considerations

The service boundary design preserves the Zero Trust architecture.

`RuntimeService` is trusted infrastructure. It is the only component that makes security decisions.

`AgentRuntimeService` is a coordination layer. It delegates all security decisions to `RuntimeService` through the `RuntimeExecutor` protocol.

`ScenarioRunnerService` is untrusted orchestration. It reads security pipeline outputs but cannot influence them. Even if `ScenarioRunnerService` is compromised or contains bugs, it cannot bypass authorization, suppress detections, or fabricate audit events.

This layered trust model ensures that security enforcement remains deterministic and centralized regardless of how many orchestration layers exist above `RuntimeService`.

---

# Future Evolution

- **Abstracting Agent Execution:** When new agent orchestrators are introduced, `AgentRuntimeService` and the alternatives will be wrapped in an `AgentExecutor` protocol.
- **Secure Mocking:** Unit tests can inject mock `AgentExecutor` implementations to test the runner's prompt grading logic without hitting live external models.

---

# Architectural Principles Affected
- Principle 1 – Zero Trust by Default
- Principle 3 – Deterministic Security Decisions
- Principle 4 – Explicit Trust Boundaries
- Principle 8 – Defense in Depth
- Principle 11 – Separation of Responsibilities
- Principle 16 – Security Through Composition

---

# Related Documents
- ADR-003: Runtime Security Orchestrator
- ADR-004: Deterministic Security Pipeline
- ADR-008: Enterprise Management API
- ADR-010: Scenario Execution Architecture
- ADR-011: Scenario Execution Lifecycle
- ADR-012: Scenario Execution Domain Model
