# ADR-012: Scenario Execution Domain Model

**Status:** Accepted

**Date:** 2026-07-19

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Architecture Approved
- Implementation: Pending (PR #59)

---

# Context

The Scenario Execution Architecture (ADR-010) and Execution Lifecycle (ADR-011) require domain models to capture execution metadata and security evaluation outcomes.

The platform must represent:

- What scenario was executed and how
- The system-level status of the execution
- The security outcomes produced by the deterministic pipeline
- Whether those outcomes matched the scenario's expected assertions

Key design decisions include:

- Whether execution metadata and security outcomes belong in a single model or separate models
- What fields are required for observability, debugging, and future dashboard integration
- Whether execution mode should be stored as a first-class field

---

# Decision Drivers

- **Type-Level Correctness:** Define structural invariants such that system failures and security outcome evaluations are logically decoupled at the type level.
- **Observability Data Fidelity:** Ensure all data required for historical dashboards, telemetry, and debugging is captured in the execution record itself.
- **Traceability:** Maintain self-describing execution metadata that is independent of external scenario changes.

---

# Decision

The execution domain model consists of four components.

## 1. ExecutionMode (Enum)

```python
class ExecutionMode(str, Enum):
    PROMPT = "PROMPT"
    TOOL_SEQUENCE = "TOOL_SEQUENCE"
```

Records how a scenario was executed:
- `PROMPT`: Executed through `AgentRuntimeService`, involving LLM intent parsing.
- `TOOL_SEQUENCE`: Executed directly against `RuntimeService` using a predefined tool sequence.

`ExecutionMode` is stored as a field on `ScenarioExecution`. It is not derived at query time.

---

## 2. ExecutionStatus (Enum)

Defined in ADR-011.

```python
class ExecutionStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
```

---

## 3. ScenarioExecution

Captures execution infrastructure metadata.

```python
class ScenarioExecution(BaseModel):
    execution_id: str
    scenario_id: str
    session_id: str
    execution_mode: ExecutionMode
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    result: ScenarioExecutionResult | None = None
    error_message: str | None = None
```

This model answers: When did this run? How was it executed? How long did it take? Did the system succeed or crash?

The `result` field holds a `ScenarioExecutionResult` if and only if `status` is `COMPLETED`. For `FAILED` executions, `result` is `None` and `error_message` is populated.

---

## 4. ScenarioExecutionResult

Captures security evaluation outcomes.

```python
class ScenarioExecutionResult(BaseModel):
    passed: bool
    observed_decision: str
    observed_response: str
    observed_risk_level: str
    observed_findings: list[str]
    mismatches: list[str]
```

This model answers: What did the security pipeline produce? Did it match the scenario's expected outcomes? Where did assertions fail?

The `mismatches` field provides actionable diagnostic output. Example:
```python
mismatches = [
    "decision: expected DENY, observed ALLOW",
    "response: expected SUSPEND_AGENT, observed MONITOR",
]
```

The `passed` field is a convenience derived from: `passed = len(mismatches) == 0`.

---

## Model Relationships

```text
ScenarioExecution (1) ──── (0..1) ScenarioExecutionResult
```

- Every execution has metadata (`ScenarioExecution`)
- Only `COMPLETED` executions have a result (`ScenarioExecutionResult`)
- `FAILED` executions have an `error_message` instead

---

# Rationale

## Why Separate Metadata from Outcomes
A `FAILED` execution has no meaningful security evaluation to report. If metadata and outcomes were combined in a single model, every result field would need to be nullable for `FAILED` executions. This creates ambiguity: does a null `observed_decision` mean "not yet evaluated" or "evaluated and produced nothing"?

Separation makes the invariant explicit at the type level: a `ScenarioExecutionResult` exists if and only if the execution completed successfully.

## Why ExecutionMode is a First-Class Field
Without storing the execution mode, reconstructing how an execution was performed requires inspecting the scenario definition at query time. If scenarios evolve or support multiple execution modes, this reconstruction becomes unreliable.

Storing the mode on each execution makes the record self-describing and supports:
- **Observability:** Dashboards can display prompt vs. sequence execution distributions.
- **Debugging:** Knowing the mode immediately narrows investigation scope.
- **Coverage Reporting:** Prompt executions validate end-to-end coverage; sequence executions validate policy coverage.
- **Metrics:** Execution duration distributions differ significantly between modes.

## Why Mismatches is a List
A simple `passed` boolean provides insufficient diagnostic value. When a scenario fails its assertions, operators need to know which specific assertions failed and what the actual values were. The `mismatches` list provides structured, actionable diagnostic output without requiring operators to manually diff expected vs. observed values.

---

# Alternatives Considered

## Single Unified Model
Combine `ScenarioExecution` and `ScenarioExecutionResult` into a single model with all fields.
### Rejected
This requires every outcome field to be nullable for `FAILED` executions. The domain semantics become ambiguous and consumers must check both status and individual field presence to determine what happened.

## Derive ExecutionMode at Query Time
Do not store `ExecutionMode`. Instead, inspect the scenario definition when querying execution history.
### Rejected
Scenario definitions may change over time. A future scenario might support both execution modes. The execution record should capture what actually happened, not what the scenario currently defines.

## Boolean passed Without Mismatches
Store only a `passed` boolean without detailed mismatch information.
### Rejected
A boolean provides no diagnostic value when assertions fail. Operators need to know which expectations were violated and what the observed values were.

---

# Consequences

## Positive
- Clear type-level invariants between metadata and outcomes
- Self-describing execution records
- Actionable diagnostic output for failed assertions
- Supports future dashboards, metrics, and coverage reporting

## Negative
- Two models instead of one adds some structural complexity
- Consumers must handle the optional `result` field

## Risks
- If additional execution metadata is needed later, `ScenarioExecution` may grow. This is acceptable as long as it remains focused on infrastructure metadata.

---

# Out of Scope

This ADR intentionally does not define:
- Persistent storage schemas (SQL / NoSQL tables)
- Content hashing or scenario version snapshot structures
- Real-time serialization formats (JSON-Schema details)
- Multi-agent orchestration metadata models

---

# Security Considerations

The domain models capture execution outcomes but do not influence security decisions.

`ScenarioExecutionResult` reports what the security pipeline produced. It does not modify, override, or suppress those decisions.

The observed fields are read-only projections of `RuntimeResult` and `ResponseAction` outputs.

---

# Future Evolution

- **Scenario Versioning / Hashing:** A `scenario_version` or `scenario_hash` field can be added to `ScenarioExecution` for immutable traceability once persistent mutable storage is introduced.
- **Asynchronous Execution Progress:** A progress percentage or stage metadata field can be added during async execution loops.
- **Audit Association:** Links to specific `event_id` keys from the audit trail can be embedded into the result details.

---

# Architectural Principles Affected
- Principle 11 – Separation of Responsibilities (metadata vs. security evaluation)
- Principle 3 – Deterministic Security Decisions (models report, never influence, decisions)

---

# Related Documents
- ADR-010: Scenario Execution Architecture
- ADR-011: Scenario Execution Lifecycle
- ADR-013: ScenarioRunner Service Boundaries
