# ADR-031: Execution Grant and Approval Control Plane

**Status:** Proposed

**Date:** 2026-09-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Proposed for `v0.16.0` (Phase 1 Architecture Foundation)
- Formalizes the control-plane resumption lifecycle for `REQUIRE_APPROVAL` responses emitted by the runtime security pipeline ([ADR-004](ADR-004-deterministic-security-pipeline.md), [ADR-019](ADR-019-behavioral-enforcement-engine.md), [ADR-023](ADR-023-execution-authorization-grants.md)).

---

# Context

The runtime security pipeline terminates with one of three deterministic outcomes: `ALLOW`, `DENY`, or `APPROVAL_REQUIRED`.

When behavioral detection or policy rules identify elevated risk that exceeds autonomous thresholds but permits supervised execution, the response engine emits `REQUIRE_APPROVAL`. The pipeline halts tool execution, sets `Decision.APPROVAL_REQUIRED`, and records an audit event.

However, the platform currently lacks an architectural control-plane mechanism to resolve and resume pending approvals:

1. **The Re-Prompting Trap (Severe Anti-Pattern):**
   A naive implementation might prompt a human operator in the management UI, and upon approval, re-submit the original user prompt to the agent runtime.
   This is architecturally unacceptable:
   - LLM generation is non-deterministic; re-running the prompt may generate different tool invocations or parameters.
   - An adversary could exploit the re-prompting window with indirect prompt injection or race-condition parameter tampering.
   - It destroys audit provenance: the resumed execution is not causally linked to the original evaluated decision.
2. **Missing State Lifecycle:**
   Without a formal grant lifecycle, approvals risk being executed multiple times (replay attack), executed after policy changes, or left orphaned indefinitely.
3. **Execution vs. Authorization Semantics:**
   A clear distinction must exist between authorizing an execution attempt and the external side-effect outcome of that execution.

---

# Decision

The platform establishes an **Execution Grant and Approval Control Plane** governing human-in-the-loop authorization resumption.

```text
Runtime Pipeline emits REQUIRE_APPROVAL
                   │
                   ▼
         Create ExecutionGrant
         (state=PENDING, bounded TTL)
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   APPROVED    REJECTED     EXPIRED
 (by Operator) (by Operator)(TTL Timeout)
       │           │           │
       ▼           ▼           ▼
 Atomic Claim  DENY Exit   DENY Exit
       │
       ▼
   CONSUMED ──► Exactly-Once Execution Attempt (ADR-023)
                      │
                      ▼
               Audit Record (Success / Failure)
```

## 1. Execution Grant Domain Model

An `ExecutionGrant` represents an immutable, bound authority token permitting a single execution attempt of a specific tool invocation:

```python
class GrantState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"

class ExecutionGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    grant_id: str
    session_id: str
    agent_id: str
    tool_id: str
    
    # Internal canonical execution parameters required by the runtime tool executor.
    # Kept strictly within the runtime/control plane; distinct from bounded Scenario Evidence DTOs.
    execution_parameters: dict[str, Any]

    # Bound authorization and risk context
    originating_audit_event_id: str
    risk_score: int
    required_response: str
    enforcement_epoch: int

    state: GrantState
    created_at: datetime
    expires_at: datetime
    approved_by: str | None = None
    consumed_at: datetime | None = None
```

## 2. The Grant Binding Invariant

> **Core Invariant:** An approved grant is NOT a new authorization decision. It is a frozen continuation of the authorization decision that produced it.

When `REQUIRE_APPROVAL` is triggered, the runtime pipeline freezes:
- The exact target `tool_id` and parsed `execution_parameters`.
- The originating `session_id`, `agent_id`, and `audit_event_id`.
- The calculated `risk_score` and `enforcement_epoch`.

Approval by a human operator does **not** re-evaluate authorization or re-invoke the policy engine. The human operator decides exclusively whether to permit the execution of this exact, frozen authority context.

## 3. Lifecycle State Machine & Canonical Terminology

The grant lifecycle progresses through well-defined, auditable states:

```text
PENDING
   ├── APPROVED
   │      └── CONSUMED  (Atomic claim for execution attempt)
   ├── REJECTED         (Operator denial)
   └── EXPIRED          (TTL timeout)
```

1. **`PENDING`:** Created automatically by the runtime pipeline when `REQUIRE_APPROVAL` is returned. Awaiting human operator review.
2. **`APPROVED`:** An authorized human operator reviewed the frozen context and granted permission to execute. Populates `approved_by`.
3. **`REJECTED`:** An authorized human operator reviewed the context and denied permission. The grant terminates; no execution occurs.
4. **`EXPIRED`:** The grant reached its TTL (`now() >= expires_at`) while in `PENDING` status. Transitions automatically to `EXPIRED` and fails closed.
5. **`CONSUMED`:** The runtime execution engine claimed the grant for an execution attempt. This is a terminal state; populates `consumed_at`.

> **Terminology Note:** The domain model and persistence repository use `CONSUMED` as the terminal execution state. The action of claiming the grant performs the atomic CAS transition `APPROVED -> CONSUMED`. The repository rejects informal transitions or undefined states (such as `CLAIMED` or `REVOKED`) with `InvalidGrantTransitionError`.

## 4. Atomic Claim & Execution Semantics

A critical failure mode exists around grant consumption:
- If a grant is marked consumed *after* tool execution, a crash between tool execution and state update permits replay attacks.
- If a grant is marked consumed *before* tool execution, a failure during tool execution leaves the grant consumed without the side-effect having occurred.

To resolve this, the platform establishes the following invariant:

> **Execution Boundary Invariant:** `CONSUMED` means that the platform has irrevocably authorized this grant for its single execution attempt. It does NOT mean the tool execution definitely succeeded.

### The Atomic Transition
Resumption follows an atomic compare-and-set claim pattern under row-level locking (`SELECT ... FOR UPDATE`):

```python
repo.transition_grant(
    grant_id=grant_id,
    from_state=GrantState.APPROVED,
    to_state=GrantState.CONSUMED,
    consumed_at=now(),
) -> bool
```

1. If two concurrent requests attempt to resume the same approved grant, the database enforces an atomic transition. Exactly one request transitions the grant to `CONSUMED` and proceeds to execution; the second receives `False` and halts immediately.
2. The claiming process invokes `DefaultToolExecutor` using the single-use execution grant token ([ADR-023](ADR-023-execution-authorization-grants.md)).
3. Whether the tool execution succeeds, fails, or throws a network timeout is recorded in the resulting **Runtime and Audit Evidence**, not in the grant state.
4. Exactly-once authorization is guaranteed; external tool side-effects cannot be replayed through the same grant.

## 5. Zero Untrusted Re-Prompting

Under no circumstances is the original user prompt or LLM intent parsing re-executed upon approval. The tool executor receives `grant.execution_parameters` directly. This eliminates:
- Non-deterministic prompt completions altering arguments.
- Prompt injection payload re-evaluation.
- Execution parameters diverging from what the human operator reviewed.

## 6. Audit Trail & Provenance Attribution

Every grant state transition generates a dedicated, correlated `AuditEvent` recorded in the append-only audit repository:
- `GRANT_CREATED`: Emitted when `REQUIRE_APPROVAL` halts the pipeline, referencing the `grant_id`.
- `GRANT_APPROVED` / `GRANT_REJECTED`: Emitted when an operator acts, recording `approved_by` and operator timestamp.
- `GRANT_EXPIRED`: Emitted when a grant times out without operator intervention.
- `GRANT_CONSUMED`: Emitted when the runtime claims the grant for execution, binding the resulting tool execution audit event to the originating `session_id` and initial request `audit_event_id`.

---

# Rationale

1. **Fail-Closed by Design:** Grants default to `PENDING` with a short TTL (default: 15 minutes). If an operator does not act, or if a service replica crashes, the grant expires safely.
2. **Protection Against Replay:** A grant can be claimed for execution exactly once. Re-submitting an already consumed grant is rejected immediately by the repository's atomic state transition.
3. **Defense Against Prompt Non-Determinism:** Freezing canonical execution parameters ensures that what was checked and approved is precisely what executes.
4. **Separation of Presentation and Authority:** While the Scenario Evidence Contract ([ADR-012](ADR-012-scenario-execution-domain-model.md)) exposes a bounded presentation DTO, `ExecutionGrant` remains an internal control-plane authority token with full execution fidelity.

---

# Alternatives Considered

## 1. Synchronous Blocking (Long-Polling / WebSockets)
- **Approach:** Hold the HTTP request open while awaiting human approval.
- **Why Rejected:** Fragile over enterprise networks, load balancers, and container restarts. Timeouts lead to orphaned executions or connection drops. Asynchronous grant creation with atomic resumption is robust across network boundaries and server restarts.

## 2. Re-evaluating Authorization on Resumption
- **Approach:** Run the policy engine again when the operator approves.
- **Why Rejected:** Violates temporal determinism. Policy changes made between initial evaluation and human approval could cause the execution to behave differently than the operator intended. The human approves the specific decision context that halted.

---

# Consequences

## Positive
- Eliminates the control-plane gap for `REQUIRE_APPROVAL` responses.
- Guarantees exactly-once authorization attempt semantics without replay risk.
- Preserves complete forensic attribution across human approval workflows.
- Eliminates prompt injection vulnerabilities during execution resumption.

## Negative
- Requires storage and state management for active approval grants (`ApprovalGrantRepository`).
- Adds operational overhead: operators must review pending grants before TTL expiry.

## Risks & Mitigations
- **Risk:** Clock skew across multi-instance clusters causes premature or delayed grant expiration.
  - *Mitigation:* Grant expiration checks rely on database server timestamps rather than local replica clocks.
- **Risk:** An approved grant is claimed, but the tool executor crashes before calling the external system.
  - *Mitigation:* `CONSUMED` records that the single execution attempt was authorized. If the tool execution failed, the failure is recorded in the audit trail, and the operator or agent must initiate a new request if retry is desired.

---

# Security Considerations

- **Role-Based Access for Approvals:** Only identities with the `ADMIN` or `OPERATOR` plane authorization role ([ADR-025](ADR-025-management-plane-authorization.md)) are permitted to transition a grant to `APPROVED` or `REJECTED`. Agents cannot approve their own grants.
- **Parameter Tampering Prevention:** `ExecutionGrant` is deeply frozen (`frozen=True`) and persisted in the durable store. Operators cannot alter execution parameters during approval; they may only approve or reject the exact evaluated grant.
