# ADR-024: Agent Enforcement State

**Status:** Accepted

**Date:** 2026-09-18

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Implemented in v0.16.0-dev (`AgentEnforcementState`, `AgentRiskPosture`, session ownership, execution-issuance gate, `EnforcementCoordinator`)
- Resolves findings H-3, H-4 and M-5 from the post-v0.16 adversarial security review, and NEW-002 from the follow-up review

---

# Context

[ADR-003](ADR-003-runtime-security-orchestrator.md) and [ADR-004](ADR-004-deterministic-security-pipeline.md) make `RuntimeService` the single authority for security decisions, and [ADR-023](ADR-023-execution-authorization-grants.md) binds each decision to the operation it authorized. The post-v0.16 review showed that the *containment* those decisions produced was not enforced at all.

**H-3 — posture reset by rotation.** Cumulative risk accumulated under a caller-supplied `session_id`. Presenting a new identifier presented a new agent:

```text
session A: injection            → HIGH, APPROVAL_REQUIRED
session B: same agent, benign   → LOW, ALLOW
```

**H-4 — advisory containment.** A `SUSPEND_AGENT` response downgraded one decision and was then discarded. `PolicyEngine` had always denied a suspended agent, but nothing ever wrote that status, so the next request was evaluated as though nothing had happened.

**M-5 — unowned sessions.** `SessionService.create_session()` had no caller. A session identifier was a label chosen by the caller, owned by no one.

An independent adversarial review of the completed enforcement work then found **NEW-002**: once enforcement became agent-scoped, unowned sessions became an integrity problem rather than untidiness. An agent could write into another agent's session, and the evidence gathered there would be attributed to the victim and drive the victim's containment.

---

# Decision

Enforcement state belongs to the **agent**, is **monotonic** from the runtime's perspective, and is derived only from evidence whose attribution is trustworthy.

## Invariants

1. **Accumulation scope and enforcement scope are related but distinct.** The session assessment remains session-scoped for reporting and attribution; enforcement is derived from the agent's accumulated posture.
2. **Rotation cannot relax enforcement.** A fresh `session_id` for the same agent inherits that agent's posture.
3. **Containment is a state transition, not a recommendation.** A final `SUSPEND_AGENT` writes `AgentStatus.SUSPENDED` and withdraws the agent's execution authority.
4. **Runtime enforcement is one-way.** The runtime may contain an agent; only an authorized administrative workflow returns one to service.
5. **A session is security-owned by exactly one agent** for its lifetime. A request from any other agent is refused before any session state is read or written.
6. **Refusal at a trust boundary is not an assessment.** Such a result reports no risk and no response, and names the boundary that refused it.
7. **Administrative status remains superior to dynamic posture.** `Agent.status` governs administrative lifecycle (`ACTIVE`, `DISABLED`), while `AgentEnforcementState` governs dynamic runtime posture (`ACTIVE`, `SUSPENDED`). An administrative `DISABLED` agent is non-executable; dynamic enforcement produces no transitions and creates no dynamic state for a `DISABLED` agent.
8. **Persisted epoch is the authoritative concurrency version.** `AgentEnforcementState.epoch` is persisted directly on the entity, never derived from audit history. Every committed transition advances `epoch` by exactly $+1$.
9. **Atomic compare-and-set state and ledger commit.** State mutation and transition ledger append occur in a single atomic transaction. Stale epochs (`persisted_epoch != expected_epoch`) or invalid increments (`new_state.epoch != expected_epoch + 1`) reject the transition and commit neither state nor transition.
10. **Fail-closed posture authority.** If the enforcement state repository is unavailable or partitioned, upstream authorization fails closed (`Decision.DENY`), records structured audit failure, short-circuits downstream checks, and issues no execution grant.

> **Namespace integrity.** The monotonic values named here belong to distinct security namespaces, each with one authoritative allocator. They are never compared with, or substituted for, one another. See *Monotonic Security-State Namespace Integrity* in [docs/ai/ARCHITECTURE_PRINCIPLES.md](../ai/ARCHITECTURE_PRINCIPLES.md), which is authoritative for this rule.

## Components

| Component | Answers | Location |
|---|---|---|
| `AgentEnforcementState` | Is this agent contained, why, under which epoch, and from when does evidence count? | `app/models/agent_enforcement.py` |
| `EnforcementTransition` | How did it get there, and who decided? | `app/models/agent_enforcement.py` |
| `AgentRiskPosture` | What does the agent's accumulated behaviour mean for enforcement? | `app/models/agent_risk_posture.py` |
| `AgentService` | Authority on agent status and its history | `app/services/agent_service.py` |
| `SessionService` | Authority on session ownership | `app/services/session_service.py` |
| `ExecutionAuthority` | May this agent obtain execution authority at all? | `app/runtime/execution_authority.py` |
| `EnforcementCoordinator` | Administrative recovery | `app/services/enforcement_coordinator.py` |
| `EnforcementStateRepository` | Authoritative persistence for dynamic posture and atomic CAS epochs | `app/repositories/interfaces/enforcement_state_repository.py` |

## Enforcement pipeline

```text
request ─▶ session ownership ─▶ authorization ─▶ detection ─▶ evidence
                  │                                              │
            not the owner                                        ▼
                  │                                      agent posture
                  ▼                                              │
        DENY, SESSION_BINDING_INVALID                     response decision
        (no event, no evidence, no posture,                       │
         no enforcement, no grant)                   SUSPEND_AGEN─┴─▶ contain
```

## Evidence eligibility

Detection rules stamp `Finding.created_at` deterministically so findings are reproducible, which means it cannot separate historical evidence from evidence recorded after a reinstatement. `FindingsService` therefore records **when it accepted** each finding, and enforcement counts only evidence recorded after the agent's `enforcement_baseline_at`. Reinstatement resets enforcement eligibility, never security history: every finding remains recorded and listed.

## Execution authority

Suspension closes a per-agent **issuance gate** and revokes that agent's outstanding grants, atomically inside the authority. Revoking alone would leave a window in which a request that had already passed authorization obtained authority immediately afterwards. A revoked grant is refused as `REVOKED`, distinct from `CONSUMED`, so refusals stay attributable. `DefaultToolExecutor` is unchanged: agent state does not leak into the executor.

## Recovery

```text
RuntimeService ──▶ contain                       (automated security response)
EnforcementCoordinator ──▶ recover               (ADMIN, reason, attributed)
```

Reinstatement transitions the agent's status first, then reopens the issuance gate. The two stores are independent and cannot roll back together, so the contract is **convergence, not atomicity**:

| Outcome | Status | Issuance | Meaning |
|---|---|---|---|
| Success | ACTIVE | open | reported only when both hold |
| Partial failure | ACTIVE | closed | fail-closed: nothing executes; surfaced as `ReinstatementIncompleteError`, never as success |
| Retry | ACTIVE | open | `resume_issuance` runs unconditionally, so a retry repairs the asymmetry |

Grants revoked during containment stay revoked: reinstatement restores the ability to obtain authority, not the authority itself.

---

# Rationale

**Scoping enforcement to the agent is parity, not escalation.** An agent that keeps one session already accumulated posture indefinitely. Keying on the agent makes rotation equivalent to staying, which is precisely the property H-3 lacked.

**Containment that is not enforced is worse than none.** It produces audit evidence describing a suspension that never happened.

**Ownership must be authoritative, never inferred.** Detection previously attributed a session's denial aggregate to the agent of the earliest denial. Grouping is now by session *and* agent, but that is defence in depth: the primary control is that a non-owner's request never becomes evidence at all.

**Recovery is a different trust flow from containment.** Containment is an automated response to evidence; recovery requires an authenticated, authorized, attributed human action. Routing both through one component would make the architecture symmetrical at the cost of that distinction.

---

# Alternatives Considered

## Option A: Keep session-scoped enforcement, restrict session creation
**Rejected.** An attacker may still create sessions; only the cost changes.

## Option B: Make `RiskAssessment` itself agent-scoped
**Rejected.** Its `session_id` shapes an existing API and the console contract, and reporting genuinely is session-oriented. A separate `AgentRiskPosture` keeps both meanings intact.

## Option C: Re-check agent status inside `DefaultToolExecutor`
**Rejected.** It would give the executor a second decision input and blur ADR-023's split between decision authority and execution enforcement. The issuance gate achieves the same containment inside the authority.

## Option D: Compare the reinstatement baseline against `Finding.created_at`
**Rejected after measurement.** Rule findings carry a deterministic epoch timestamp, so this suppressed every future finding as well, leaving a reinstated agent permanently unenforceable.

## Option E: Route suspension through the coordinator too
**Rejected.** Suspension is generated by the runtime pipeline from evidence; recovery is an administrative act. Symmetry is not the objective.

---

# Consequences

## Positive

- An agent cannot escape accumulated posture by presenting a new session identifier.
- A contained agent is denied at the policy stage and can obtain no execution authority.
- Every containment records what triggered it; every recovery records who authorized it and why.
- One agent cannot contribute evidence to another agent's posture.
- A refusal at a trust boundary is distinguishable from a benign evaluation.

## Negative

- Posture accumulates without decay, so an agent stays constrained until an operator reinstates it. Time-based decay belongs to [ADR-018](ADR-018-behavioral-risk-engine.md).
- Enforcement assessment scans the agent's findings per request, which is linear in stored evidence. Bounded state remains finding M-4.
- Tests that need a quiet agent must use their own agent rather than a shared one, because accumulation is now real.

---

# Security Considerations

## Residual Risks

- **Session identifier squatting.** While callers choose identifiers, an agent can claim one another agent intended to use. That denies the victim *that identifier* and never yields ownership of an established session, access to its evidence, or influence over another agent's posture. Server-issued unpredictable identifiers close it.
- **In-flight execution.** Revocation cannot reach a request that has already passed grant verification and entered tool execution.
- **Process-lifetime durability.** Enforcement state is in memory; a restart clears containment. Persistence is [ADR-016](ADR-016-behavioral-event-store-and-data-model.md).
- **Decision and audit under concurrency.** A request may be audited `ALLOW` and then obtain no grant because the gate closed between the two. The execution boundary stays closed; the audit record is the inconsistency.
- **In-process callers.** `ToolRegistry.get()` still returns an executable tool to code inside the process, as ADR-023 records.

## Scope

This decision does not introduce management-plane authorization. Reinstatement is role-gated because it is a privileged mutation; every other management route still enforces authentication only (finding H-2). The enforcement-history endpoint is read-only governance visibility, not evidence of RBAC.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust by Default:** extended from the request to the agent's standing.
- **Principle 3 – Deterministic Security Decisions:** containment follows deterministically from recorded evidence.
- **Principle 7 – Later stages may only increase restrictions:** now true across requests, not only within one.
- **Principle 8 – Defense in Depth:** ownership at the runtime boundary and again at the evidence store.

---

# Amendment — Agent Lifecycle Formalization (F-09)

*Status of this amendment: Proposed. Dated 2026-10-03. Origin: F-09 (Adversarial Review
Adjudication, Follow-up Backlog), following the adjudication of Finding 4. ADR-024 remains
Accepted.*

## A.1 Context

`AgentStatus` defines `REGISTERED`, `ACTIVE`, `SUSPENDED` and `DISABLED`, but this ADR described
the administrative lifecycle as `ACTIVE` / `DISABLED` and did not define `REGISTERED`. The policy
denied only `SUSPENDED` and `DISABLED`, so `REGISTERED` — the model default — was executable by
omission, and any state added later would have been executable by default. Invariants 3 and 7
were also in tension: invariant 7 assigns dynamic posture to `AgentEnforcementState`, while
invariant 3 has containment write `AgentStatus.SUSPENDED`.

No production activation bypass existed when this was decided: every application-level agent was
created `ACTIVE` and no registration endpoint existed (Finding 4 adjudication). This amendment
defines the lifecycle contract before agents become externally provisionable and before durable
agent persistence is implemented ([ADR-030](ADR-030-durable-state-repository-architecture.md)).

## A.2 Two independently authoritative planes

| Plane | States | Authority | Version (namespace) | History |
|---|---|---|---|---|
| Administrative | `REGISTERED`, `ACTIVE`, `DISABLED` | Administrative-state record | `administrative_version` | Administrative ledger |
| Enforcement | `NOT_SUSPENDED`, `SUSPENDED` | `AgentEnforcementState` | `AgentEnforcementState.epoch` | Enforcement ledger |

Neither plane may reuse the other's version. `administrative_version` is a new monotonic
namespace with its own allocator (see *Monotonic Security-State Namespace Integrity* in
[docs/ai/ARCHITECTURE_PRINCIPLES.md](../ai/ARCHITECTURE_PRINCIPLES.md)). No transaction spans both
planes; safety does not require one (A.4).

`Agent.status` is a materialized projection of the effective lifecycle state derived from the two
authoritative planes: `REGISTERED`, `ACTIVE` and `DISABLED` originate in the administrative plane,
`SUSPENDED` in the enforcement plane. It is never authoritative for either plane. Inability to
establish the authoritative state of either plane fails closed.

## A.3 Administrative lifecycle

- `REGISTERED` — the agent is known to the platform and **not** in service. Non-executable.
- `ACTIVE` — the agent is in service. The only executable administrative state.
- `DISABLED` — terminal administrative state. Non-executable.

Transitions:

| Transition | Meaning | Authorization |
|---|---|---|
| create → `REGISTERED` | Registration: the agent becomes known. Grants no authority. | `ADMIN` ([ADR-025](ADR-025-management-plane-authorization.md) amendment), attributed |
| `REGISTERED` → `ACTIVE` | Activation: the agent enters service. | `ADMIN` (ADR-025 amendment), attributed |
| `REGISTERED`/`ACTIVE` → `DISABLED` | Disablement. | `ADMIN` (ADR-025 amendment), attributed |

There is no transition out of `DISABLED`. A future re-enable would be a separately defined,
separately authorized transition; reinstatement is never that transition.

Every agent, including the platform's default agent and agents created by the scenario runtime,
enters service through registration followed by an explicit, system-authorized activation. The two
are distinct lifecycle events even when performed consecutively. Direct construction of an
`ACTIVE` agent is permitted only as test setup.

## A.4 Execution invariant (supersedes the status deny-list)

> An agent may obtain execution authority only when its authoritative administrative state is
> `ACTIVE` **and** its authoritative enforcement state is `NOT_SUSPENDED`. Each condition is
> evaluated independently against its authoritative source and fails closed if it cannot be
> established. Any unknown, unsupported or unclassified lifecycle state is non-executable.

Execution is granted by the presence of both conditions, never inferred from the absence of a
deny condition. Because each condition fails closed independently, administrative and enforcement
transitions may commit in either order without creating an executable window.

Lifecycle-caused denials carry stable, machine-readable reason codes, independent of message text:

| Condition | Code |
|---|---|
| Administrative state `REGISTERED` | `AGENT_NOT_ACTIVE` |
| Administrative state `DISABLED` | `AGENT_DISABLED` |
| Enforcement state `SUSPENDED` | `AGENT_SUSPENDED` |

## A.5 Enforcement plane, restated

Invariant 3 is restated: containment is a state transition in the enforcement plane. It does not
mutate administrative lifecycle state. A final `SUSPEND_AGENT` sets the enforcement state to
`SUSPENDED` and withdraws execution authority; the effective result is reflected in the
`Agent.status` projection.

Invariant 7 is amended to read, for the relationship between the planes:

- Dynamic enforcement posture is maintained independently of administrative lifecycle.
  Dynamic enforcement may create a new containment state for an agent that is not `DISABLED`.
  A `DISABLED` agent cannot acquire execution authority through any enforcement transition.
  Clearing an existing suspension through reinstatement remains permitted for a `DISABLED`
  agent; reinstatement changes enforcement posture only and does not alter administrative
  lifecycle state.

Suspension remains a runtime enforcement action generated from security evidence; there is no
administrative suspend operation (ADR-025 amendment A.3).

Reinstatement is an enforcement-plane transition only. It clears the current suspension, advances
the enforcement epoch by exactly +1, establishes a new enforcement baseline, and **leaves the
current administrative state unchanged**. It never performs activation, and activation never
performs reinstatement. A reinstated `REGISTERED` agent remains `REGISTERED`; an agent disabled
while suspended remains `DISABLED` after reinstatement. Reinstating a `DISABLED` agent is
permitted and clears the suspension only; the agent remains non-executable.

## A.6 Concurrency

Each plane's transitions are serialized by a durable compare-and-set on that plane's version: a
stale expected version rejects the transition and commits neither state nor ledger entry.
Process-local locks may reduce contention but are never the correctness mechanism.

## A.7 Execution authority

Execution issuance is open only when both planes permit execution (A.4). Issuance state is derived
from, or tracked per, plane; no single-plane operation — including reinstatement — may reopen
issuance while the other plane forbids execution.

A transition that removes execution authority (leaving `ACTIVE`, or entering `SUSPENDED`) closes
issuance and revokes the agent's outstanding unconsumed grants, as suspension already does.
Activation and edits to descriptive agent configuration are not grant-freshness events. A grant
already being executed cannot be retroactively stopped by a lifecycle change (existing residual
risk).

The executor does not independently re-authorize lifecycle state; lifecycle authorization occurs
at decision and authority issuance, with post-issuance invalidation governed by the
execution-authority revocation contract (rejected Option C stands).

## A.8 Evidence

- **Successful transitions** are authoritative only in their plane's append-only ledger, committed
  atomically with the state change under the version compare-and-set. They are not duplicated into
  `AuditEvent`.
- **Ledger entries** record: entry id, agent id, action, structured actor, reason, previous and new
  state in that plane's vocabulary, version before and after in that plane's namespace
  (`administrative_version_before` / `_after`, or `enforcement_epoch_before` / `_after`),
  timestamp, and a mandatory correlation id. Enforcement entries also record the trigger.
- **Refused lifecycle attempts** are recorded in a dedicated, append-only administrative audit
  record in the evidence plane
  ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md) §6,
  [ADR-034](ADR-034-audit-identity-contract.md) §8). They never enter a ledger. `AuditEvent`
  remains tool-request evidence and is unchanged.
- **Actors** are structured `{type, id}` with controlled types (`human`, `system`, `runtime`) and
  reserved system identifiers (bootstrap; scenario runtime). Actor type and identity are never a
  single overloaded string.
- **Correlation:** every transition and refused attempt carries a correlation id; system-initiated
  operations generate one per transition.
- Lifecycle evidence is not `SessionEvent` evidence. Ledgers are immutable after commit and follow
  the audit-evidence retention and governance controls (ADR-028) and least-privilege repository
  access (ADR-030). Telemetry lifecycle events remain non-authoritative.

## A.9 Deployment preconditions (ADR-030)

Before a multi-instance production composition is supported:

1. Execution-grant issuance validates the authoritative enforcement epoch against durable
   enforcement state.
2. Issuance closure and revocation of outstanding unconsumed grants are durable or shared across
   the deployment; process-local revocation is not the sole correctness mechanism.

These are preconditions, not defects of the current single-process composition.

## A.10 Dependencies and consequences

- **ADR-030:** a SQL administrative-state store and ledger meeting A.6 and A.8 (version CAS, atomic
  append, `CHECK` constraint on administrative values); an `AgentRepository` whose create path
  yields `REGISTERED`; production composition per A.9.
- **ADR-025:** management-plane authorization for registration, activation and disablement.
- **ADR-028 / ADR-034:** define the administrative audit record.
- **Architecture principles:** add `administrative_version` to the namespace table.
- **Amends in this ADR:**
  - Invariant 3: containment no longer writes administrative state (A.5).
  - Invariant 7 retains its purpose, separating administrative lifecycle from dynamic posture, with
    corrected vocabularies: administrative `REGISTERED`, `ACTIVE`, `DISABLED`; enforcement-only
    `NOT_SUSPENDED`, `SUSPENDED`. `ACTIVE` is exclusively an administrative-plane state.
    `DISABLED` remains administratively terminal and non-executable; enforcement may clear an
    existing suspension for a `DISABLED` agent, but no enforcement transition may make it
    executable.
- **Implementation consequences (not part of this amendment):** the status deny-list in
  `PolicyEngine`; `reinstate_agent` precondition and target state; `EnforcementCoordinator`
  reinstatement/repair success conditions; bootstrap and scenario agent creation; the
  `ExecutionAuthority` single-flag issuance gate; the `EnforcementTransition` vocabulary and missing
  epoch fields.

---

# Related Documents

- [ADR-013: ScenarioRunner Service Boundaries](ADR-013-scenario-runner-service-boundaries.md) — scenario isolation amendment
- [ADR-018: Behavioral Risk Engine](ADR-018-behavioral-risk-engine.md)
- [ADR-019: Behavioral Enforcement Engine](ADR-019-behavioral-enforcement-engine.md) — this decision implements a minimal first slice
- [ADR-023: Execution Authorization Grants](ADR-023-execution-authorization-grants.md)
- [Threat Model](../security/threat-model.md)
- [Adversarial Regression Corpus](../../tests/security/README.md)
