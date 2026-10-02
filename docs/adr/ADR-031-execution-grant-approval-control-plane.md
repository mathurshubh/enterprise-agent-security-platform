# ADR-031: Execution Grant and Approval Control Plane

**Status:** Accepted

**Date:** 2026-09-24 (amended 2026-10-02)

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- **Adopted, not implemented.** The capability is now a decided platform capability rather than a proposal, subject to the amendment in §7.
- Nothing drives this lifecycle today. `ExecutionAuthority.issue()` returns `None` for any decision other than `ALLOW`, so `APPROVAL_REQUIRED` currently produces no grant at all; no service constructs an `ExecutionGrant`; and the `ApprovalGrantRepository` singleton is instantiated in the composition root without being injected anywhere. The domain model, both repository adapters, their shared contract tests and the frontend's `PendingApproval` type all exist unused.
- Scaffolding existing at three layers is not evidence the decision was taken. §7 is what takes it.
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
    REVOKED = "REVOKED"      # amended §7.4

class ExecutionGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    grant_id: str
    session_id: str
    agent_id: str

    # Concrete tool identity. ``tool_id`` alone names a family and does not identify an
    # implementation, so the version is part of the frozen authority (amended §7.2).
    tool_id: str
    tool_version: str

    # The confinement the operator reviewed. Referenced by digest rather than snapshotted;
    # ADR-035 D-C1 makes the referenced definition immutable (amended §7.2).
    capability_profile_id: str
    capability_digest: str
    
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
- The exact target `tool_id`, the concrete `tool_version`, and parsed `execution_parameters`.
- The `capability_profile_id` and `capability_digest` that govern the execution.
- The originating `session_id`, `agent_id`, and `audit_event_id`.
- The calculated `risk_score` and `enforcement_epoch`.

The version and the capability binding were added by amendment (§7.2). Without the version,
a continuation named a family and the executed implementation would not be the one reviewed.
Without the capability binding, the frozen authority carried no statement of the confinement
the operator approved — the record would say what was permitted to run, and not what it was
permitted to do.

Approval by a human operator does **not** re-evaluate authorization or re-invoke the policy engine. The human operator decides exclusively whether to permit the execution of this exact, frozen authority context.

## 3. Lifecycle State Machine & Canonical Terminology

The grant lifecycle progresses through well-defined, auditable states:

```text
PENDING
   ├── APPROVED
   │      ├── CONSUMED  (Atomic claim for execution attempt)
   │      ├── EXPIRED   (Continuation lifetime elapsed — amended §7.3)
   │      └── REVOKED   (Security invalidation — amended §7.4)
   ├── REJECTED         (Operator denial)
   ├── EXPIRED          (Approval window elapsed)
   └── REVOKED          (Security invalidation — amended §7.4)
```

1. **`PENDING`:** Created automatically by the runtime pipeline when `REQUIRE_APPROVAL` is returned. Awaiting human operator review.
2. **`APPROVED`:** An authorized human operator reviewed the frozen context and granted permission to execute. Populates `approved_by`.
3. **`REJECTED`:** An authorized human operator reviewed the context and denied permission. The grant terminates; no execution occurs.
4. **`EXPIRED`:** A bounded lifetime elapsed without the continuation being claimed — the approval window while `PENDING`, or the continuation lifetime while `APPROVED` (§7.3). Transitions automatically and fails closed.
5. **`CONSUMED`:** The runtime execution engine claimed the grant for an execution attempt. This is a terminal state; populates `consumed_at`.
6. **`REVOKED`:** Security invalidation withdrew the continuation before it was claimed (§7.4). Terminal, and never reversible.

Two amendments to this machine:

`APPROVED` is **not** a resting state. As originally specified, `EXPIRED` was reachable only
from `PENDING`, so an approved continuation that was never claimed remained claimable without
limit — a larger stale-authority window than the one bounded at 30 seconds for ephemeral
grants. An approved continuation now expires under its own lifetime (§7.3).

`REVOKED` is now a defined state. The original terminology note rejected it as an undefined
state, which could not coexist with the platform invariant that a suspended agent holds no
outstanding executable authority once a continuation survives the process that created it
(§7.4).

> **Terminology Note:** The domain model and persistence repository use `CONSUMED` as the terminal execution state for a claimed grant. The action of claiming performs the atomic CAS transition `APPROVED -> CONSUMED`. The repository rejects informal or undefined transitions (such as `CLAIMED`) with `InvalidGrantTransitionError`. `REVOKED` is a defined state per §7.4; `CLAIMED` remains undefined.

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

**Requirement:** every continuation state transition must produce attributable, append-only
audit evidence — creation, operator approval or rejection, expiry, revocation, and the claim.
Operator actions must attribute to the acting principal; the claim must bind the resulting
execution evidence to the originating `session_id` and request `audit_event_id`.

**Representation is deliberately not specified here.** This ADR originally named event types
`GRANT_CREATED`, `GRANT_APPROVED`, `GRANT_REJECTED`, `GRANT_EXPIRED` and `GRANT_CONSUMED`, but
`AuditEvent` has no event-type dimension — it carries a `Decision`, which cannot express a
grant transition. Those names exist nowhere in the implementation. How such evidence is
represented is a separate audit-event taxonomy decision, deliberately kept out of this
amendment so that it does not silently widen the identity contract locked in
[ADR-034](ADR-034-audit-identity-contract.md).

---

## 7. Amendment — Approval Continuation Semantics

Added 2026-10-02. This amendment adopts the capability and settles the semantics that the
original decision left open. It changes no part of the `ALLOW` path: a final `ALLOW` still
produces an ephemeral `RuntimeExecutionGrant` and executes, unchanged.

### 7.1 The continuation is not executable authority

```text
APPROVAL_REQUIRED
      │
      ▼
durable approval continuation      ← a frozen authorization artifact
      │
      │  monotonic continuation validation
      ▼
new ephemeral RuntimeExecutionGrant ← the executable authority, bounded as ever
      │
      ▼
execution ──► ExecutionReceipt
```

A persisted continuation is **never** itself a bearer of execution authority. Execution
authority remains the ephemeral grant of [ADR-023](ADR-023-execution-authorization-grants.md),
whose signing key is random per process precisely so that a restart invalidates every
outstanding grant rather than preserving one. Claiming a continuation therefore **re-mints**
cryptographic authority; it does not restore it.

That distinction is what keeps the durable store from becoming a long-lived token vault. The
continuation records what was approved; the ephemeral grant is what executes, and it is still
short-lived and process-local.

### 7.2 Frozen authority includes the version and the capability binding

`(tool_id, tool_version)`, `capability_profile_id` and `capability_digest` are **required**
elements of the frozen authority, not optional annotations. The capability definition is
referenced by digest rather than copied, which is sound only because
[ADR-035](ADR-035-execution-evidence-and-capability-durability.md) D-C1 makes the referenced
definition immutable and durably resolvable. **This amendment therefore depends on D-C1**: a
digest reference into a mutable registry would record which confinement was approved while
losing what it permitted.

### 7.3 An approved continuation expires

No approved continuation remains executable indefinitely. Its lifetime is **distinct from the
ephemeral grant's TTL**: the 30-second ceiling in ADR-023 bounds how long a governance change
other than agent suspension can remain ineffective for in-memory authority, and a human
approval window is measured in minutes or hours. Reusing that number would make the capability
unusable; inheriting its *reasoning* unexamined would leave the longer window unbounded.

The concrete duration is a later policy and configuration decision. The invariant locked here
is only that a bounded continuation lifetime exists and that elapsing it fails closed.

### 7.4 Continuations are subject to security invalidation, monotonically

A persisted continuation is reachable by containment. The platform invariant that a
`SUSPENDED` agent holds no outstanding executable authority applies across the restart
boundary, not only within the process that issued the authority.

Revocation is **monotonic**: `REVOKED` is terminal, and reinstating an agent does not resurrect
an invalidated continuation. This is the same rule ADR-023 applies to ephemeral grants —
reinstatement returns the ability to obtain authority, not the authority itself.

`REVOKED` is kept distinct from the ephemeral grant's refusal reason of the same name rather
than merged with it, because the two describe different objects with different lifetimes.

### 7.5 Continuation validation is monotonic

> **Continuation Validation Invariant:** a continuation check may only subtract authority,
> never add or substitute it. Validation may refuse to mint; it may never mint something other
> than what was approved.

Validation reaches exactly two outcomes — mint the approved authority, or fail closed. It may
establish that a continuation is expired, already consumed, revoked, that its approving
enforcement epoch has been superseded, that its capability definition is no longer resolvable,
or that its concrete tool identity no longer exists. Each of those can only deny.

It may **not**:

| Observation | Prohibited response |
|---|---|
| approved tool version unavailable | select a different version |
| approved capability unresolvable | substitute the currently applicable profile |
| policy changed since approval | re-evaluate and widen, narrow or rewrite the approved authority |
| agent state changed | execute as a different agent or scope |

| Operation | May broaden or substitute authority? |
|---|---|
| Fresh authorization | Yes, subject to policy |
| Continuation validation | **No** |
| Minting an ephemeral grant from a valid continuation | **No** |
| Execution | **No** |

**Epoch invalidation is permitted; policy re-evaluation is not.** Comparing a continuation's
approving `enforcement_epoch` against the current epoch and refusing on mismatch is a
revocation predicate with one possible effect — denial. Re-running the policy engine is a
second authorization decision, which §"Alternatives Considered" already rejected for violating
temporal determinism, and which [ADR-023](ADR-023-execution-authorization-grants.md) rejected at
claim time for making execution availability depend on the governance plane's availability.

The distinction is not stylistic. A monotonic predicate cannot reach an outcome the operator
did not review; an evaluation can. Each predicate does still add a dependency whose
unavailability becomes execution unavailability, so the set is chosen deliberately rather than
expanded for completeness.

### 7.6 What this amendment does not decide

- **Which portion of the continuation must be durable**, and the persistence and reconstruction
  guarantees — the grant-durability decision, now well defined because the continuation is.
- **The continuation lifetime's concrete duration** (§7.3).
- **Audit representation** for continuation transitions (§6) — a separate taxonomy decision.
- **The operator-facing API and UI.** The frontend's `PendingApproval` type exists and is
  referenced by nothing; no approval endpoint exists in the management plane.

---

# Rationale

1. **Fail-Closed by Design:** A continuation rests in `PENDING` under a bounded approval window, and in `APPROVED` under a bounded continuation lifetime (§7.3). If an operator does not act, or a service replica crashes, it expires safely rather than remaining claimable. Both durations are policy, deliberately not fixed by this ADR.
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
- **No Durable Bearer Authority:** a persisted continuation is not executable authority (§7.1). Execution authority remains the process-local, short-lived ephemeral grant, so compromising the durable store does not yield a usable execution token.
- **Containment Crosses the Restart Boundary:** agent suspension invalidates outstanding continuations, and reinstatement does not restore them (§7.4).
- **No Authority Substitution:** continuation validation is monotonic (§7.5). An approved authority can be refused but never silently replaced by a newer tool version, a different capability profile, or a re-evaluated policy outcome.
