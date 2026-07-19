# ADR-011: Scenario Execution Lifecycle

**Status:** Accepted

**Date:** 2026-07-19

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Approved
- Implementation: Pending (PR #59)

---

# Context

The Scenario Execution Architecture (ADR-010) introduces `ScenarioRunnerService` as an orchestration layer for executing security scenarios against the deterministic runtime pipeline.

Every execution requires a well-defined lifecycle that captures the system-level state of an execution from initiation through completion or failure.

The lifecycle must be minimal enough for the current synchronous execution model while remaining extensible for future asynchronous processing.

Design decisions include:

- How many lifecycle states to introduce
- Whether to distinguish between "created but not started" and "actively running"
- Whether to include states for queued, cancelled, or timed-out executions
- How the lifecycle evolves when asynchronous execution is introduced

---

# Decision Drivers

- **System Simplicity:** Minimize the state space for synchronous runs to keep the execution logic simple and maintainable.
- **Observability:** Ensure every state is observable, actionable, and reflects real-time system status.
- **Traceability:** Explicitly separate infrastructure failure states from security assertion failures.
- **Future Compatibility:** Allow seamless extension to asynchronous execution without modifying core state transition logic.

---

# Decision

The execution lifecycle consists of three states defined in the `ExecutionStatus` enum.

```text
  ┌──────────┐
  │ RUNNING  │
  └────┬─────┘
       │
   ┌───┴───┐
   ▼       ▼
┌─────────┐  ┌────────┐
│COMPLETED│  │ FAILED │
└─────────┘  └────────┘
```

### 1. RUNNING
The execution is in progress. The security pipeline is actively processing the scenario.
This is the entry state. Execution enters `RUNNING` immediately when `ScenarioRunnerService.run()` is invoked.

### 2. COMPLETED
The security pipeline executed to completion. Grading assertions were evaluated.
A `COMPLETED` execution may have passed or failed its security assertions. The pass/fail outcome is captured separately in `ScenarioExecutionResult`, not in the lifecycle status.

`COMPLETED` means the system succeeded in producing a result, regardless of whether the scenario's security expectations were met.

### 3. FAILED
A system-level error prevented the execution from completing. Examples include:
- LLM provider unavailable or rate-limited
- Unhandled exception in the security pipeline
- Missing service dependency
- Invalid scenario configuration

A `FAILED` execution has no `ScenarioExecutionResult`. The error details are captured in `ScenarioExecution.error_message`.

---

## No CREATED State
The lifecycle intentionally does not include a `CREATED` state.

In synchronous execution, creation and execution are the same operation. A `CREATED` state would exist for zero milliseconds before transitioning to `RUNNING`. States that cannot be meaningfully observed, queried, or acted upon add complexity without value.

`CREATED` becomes meaningful only when execution is decoupled from creation — for example, when a task queue or scheduler exists between the request and the execution.

---

## No QUEUED, PENDING, CANCELLED, or TIMED_OUT States
These states are intentionally deferred.

| State | When to Introduce |
|:------|:-------------------|
| `QUEUED` / `PENDING` | When an asynchronous task queue or worker pool is introduced |
| `CANCELLED` | When execution supports user-initiated cancellation |
| `TIMED_OUT` | When execution enforces wall-clock deadlines |

Premature states create dead code paths, untestable branches, and misleading domain models. Each state should be introduced only when the infrastructure that produces it exists.

---

# Rationale

## Minimal State Machine
Every state in a state machine should satisfy three criteria:
1. **Reachable** — there exists a valid transition into the state.
2. **Observable** — external consumers can query and act on the state.
3. **Actionable** — the state enables a meaningful decision or operation.

For synchronous execution, only `RUNNING`, `COMPLETED`, and `FAILED` satisfy all three criteria.

## Separation of System Status and Security Outcome
The lifecycle captures whether the system succeeded or crashed. It does not capture whether the scenario's security assertions passed or failed.

This separation is important because a `COMPLETED` execution with failed assertions is fundamentally different from a `FAILED` execution:
- `COMPLETED` with failed assertions means the security pipeline produced a result that did not match expectations. This is a detection gap or policy misconfiguration.
- `FAILED` means the system could not produce any result. This is an infrastructure issue.

Mixing these concerns into a single status would obscure the root cause of failures.

## Future Extensibility
The `ExecutionStatus` enum can be extended with additional states without modifying existing transitions:
```text
Future: QUEUED → RUNNING → COMPLETED | FAILED | TIMED_OUT
                    ↑
              CANCELLED (from QUEUED)
```
The existing `RUNNING → COMPLETED | FAILED` transitions remain unchanged when asynchronous execution is introduced.

---

# Alternatives Considered

## Include CREATED as Initial State
Introduce `CREATED → RUNNING → COMPLETED | FAILED`.
### Rejected
In synchronous execution, `CREATED` exists for zero milliseconds. It cannot be observed or acted upon. It adds a state transition that must be tested but provides no operational value.

## Include Full Async Lifecycle Now
Introduce `QUEUED`, `PENDING`, `CANCELLED`, and `TIMED_OUT` alongside the synchronous states.
### Rejected
These states require infrastructure (task queues, worker pools, cancellation APIs, deadline enforcement) that does not exist yet. Introducing the states without the infrastructure creates dead code paths and misleading domain models.

## Single Terminal State
Use only `COMPLETED` as the terminal state, with an error field to distinguish success from failure.
### Rejected
This requires every consumer to check both the status and the error field to determine the outcome. Separate terminal states (`COMPLETED` vs `FAILED`) make the domain semantics explicit at the type level.

---

# Consequences

## Positive
- Minimal state machine with no dead states
- Clear separation between system status and security outcomes
- Naturally extensible for asynchronous execution
- Every state is reachable, observable, and actionable

## Negative
- No pre-execution state for request tracking before execution begins
- Cannot represent queued or pending executions until async infrastructure exists

## Risks
- If asynchronous execution is introduced without updating this ADR, the lifecycle may be extended inconsistently

---

# Out of Scope

This ADR intentionally does not define:
- Async task dispatchers, brokers, or workers
- Cancellation REST APIs or handlers
- Timeout limits or scheduler configurations
- Client-side polling or web socket updates

---

# Security Considerations

The execution lifecycle does not affect security decisions. It captures system-level execution metadata only.

`FAILED` executions must never be treated as security approvals. A system failure should result in a conservative security posture (fail-closed), not implicit permission.

---

# Future Evolution

- **Queue State Transition:** Asynchronous queues will introduce a `QUEUED` state transitioning to `RUNNING`.
- **Cancellation Flow:** User cancellation will introduce a transition path from `QUEUED` to `CANCELLED`.
- **Timeout Monitoring:** Worker monitors will transition a long-running execution from `RUNNING` to `TIMED_OUT`.

---

# Architectural Principles Affected
- Principle 3 – Deterministic Security Decisions (lifecycle does not influence security outcomes)
- Principle 11 – Separation of Responsibilities (system status vs. security assertions)

---

# Related Documents
- ADR-010: Scenario Execution Architecture
- ADR-012: Scenario Execution Domain Model
- ADR-013: ScenarioRunner Service Boundaries
