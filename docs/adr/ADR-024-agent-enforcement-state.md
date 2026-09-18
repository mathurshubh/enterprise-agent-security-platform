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

## Components

| Component | Answers | Location |
|---|---|---|
| `AgentEnforcementState` | Is this agent contained, why, and from when does evidence count? | `app/models/agent_enforcement.py` |
| `EnforcementTransition` | How did it get there, and who decided? | `app/models/agent_enforcement.py` |
| `AgentRiskPosture` | What does the agent's accumulated behaviour mean for enforcement? | `app/models/agent_risk_posture.py` |
| `AgentService` | Authority on agent status and its history | `app/services/agent_service.py` |
| `SessionService` | Authority on session ownership | `app/services/session_service.py` |
| `ExecutionAuthority` | May this agent obtain execution authority at all? | `app/runtime/execution_authority.py` |
| `EnforcementCoordinator` | Administrative recovery | `app/services/enforcement_coordinator.py` |

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

# Related Documents

- [ADR-013: ScenarioRunner Service Boundaries](ADR-013-scenario-runner-service-boundaries.md) — scenario isolation amendment
- [ADR-018: Behavioral Risk Engine](ADR-018-behavioral-risk-engine.md)
- [ADR-019: Behavioral Enforcement Engine](ADR-019-behavioral-enforcement-engine.md) — this decision implements a minimal first slice
- [ADR-023: Execution Authorization Grants](ADR-023-execution-authorization-grants.md)
- [Threat Model](../security/threat-model.md)
- [Adversarial Regression Corpus](../../tests/security/README.md)
