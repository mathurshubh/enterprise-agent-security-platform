# ADR-025: Management-Plane Authorization

**Status:** Accepted

**Date:** 2026-09-18

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Implemented in v0.16.0-dev (`require_roles` applied at every router mount, `require_execution_identity`, sandbox-local scenario identity)
- Resolves findings H-2 and M-3 from the post-v0.16 adversarial security review

---

# Context

[ADR-008](ADR-008-enterprise-management-api.md) stated that the Management API would "reuse the platform's JWT authentication mechanism while enforcing authorization scopes independent of Runtime API execution." Authentication shipped. Authorization did not.

**H-2 — management plane authorization missing.** `require_roles()` existed in `app/api/auth.py` and no router applied it. Every authenticated principal was equal on the management and scenario planes, whatever its role:

```text
[EXPOSED] AGENT role -> GET /api/v1/findings          = 200
[EXPOSED] AGENT role -> GET /api/v1/risk-assessments  = 200
[EXPLOIT] ANALYST POST /api/scenarios/BEN-001/execute = 200
```

**M-3 — scenario role gate and identity.** The scenario plane applied no role gate, and scenario activity was attributed to `"agent-1"`, the platform's default registered agent.

The runtime plane was different in kind rather than better: it carried its own authorization logic inline in the route handler, written as two denials — an identity mismatch for `AGENT` principals, and a refusal for `ANALYST`. `ADMIN` matched neither and fell through the gap, which made administrative impersonation an accident of structure rather than a decision anyone recorded.

Two changes since the review altered what a correct answer looks like:

- **M2a** put scenario execution in a throwaway sandbox ([ADR-013](ADR-013-scenario-runner-service-boundaries.md) isolation amendment). A scenario can no longer mutate live state, which removes the escalation that made analyst scenario execution an exploit.
- **M2b** ([ADR-024](ADR-024-agent-enforcement-state.md)) made enforcement agent-scoped. Activity attributed to an agent accumulates into that agent's posture and can contain it. Executing "as" an agent therefore became the ability to generate behavioural evidence against a subject one does not own.

---

# Decision

Authorization is applied at the API boundary, at the same place authentication already was, and the platform distinguishes three controls that a single term such as "RBAC" would collapse.

## Invariants

1. **Every published route belongs to a plane with a declared role set.** A router mounted without one is a policy omission, not a default-open surface.
2. **Execution identity and administrative identity are not implicitly interchangeable.** Authority to manage an agent is not authority to act as one.
3. **A route may narrow its plane, never widen it.** Mount-level and route-level dependencies are composed as an intersection.
4. **Authorization is evaluated before any resource lookup**, so a refusal cannot report whether the target exists.
5. **Authentication precedes authorization.** A request without a valid principal is refused as unauthenticated, even where no role would have qualified.
6. **Scenario execution is permitted to operators and isolated from live state.** The permission is only sound while the isolation holds; they are asserted together.

## Three distinct controls

These are separate mechanisms answering separate questions, and documentation should not merge them:

| Control | Question | Mechanism |
|:---|:---|:---|
| Plane authorization | Which roles may enter this API surface at all? | `require_roles` at the router mount |
| Execution identity | Which agent may an `AGENT` principal operate as? | `require_execution_identity` on the runtime route |
| Scenario isolation | Can scenario execution affect live security state? | Sandboxed pipeline (ADR-013), unchanged here |

## Mechanism

Each router is mounted with the widest role set its plane admits. FastAPI composes router-level and route-level dependencies additively, so the effective permission of a route is the intersection of both:

```text
mount-level dependency   →  the widest role set this plane admits
route-level dependency   →  narrowing, where one capability is more privileged
```

A route can therefore only ever narrow the plane it belongs to. Adding a route cannot silently grant access its plane does not already allow, and the failure mode of forgetting a route-level gate is a route no more permissive than its plane.

```text
runtime      AGENT             + require_execution_identity
scenarios    ANALYST, ADMIN
management   ANALYST, ADMIN    + ADMIN on reinstatement
health       public
```

`require_roles` depends on `get_current_principal`, so authentication still runs first and an unauthenticated request is refused with `401` before any role is considered.

## Role matrix

| Capability | AGENT | ANALYST | ADMIN |
|:---|:---:|:---:|:---:|
| Execute own runtime | ✓ | — | — |
| Execute as another agent | — | — | — |
| Read evidence: findings, sessions, risk, audit | — | ✓ | ✓ |
| Read enforcement state and history | — | ✓ | ✓ |
| Read catalogues: agents, tools, detection rules, info | — | ✓ | ✓ |
| List and view scenarios | — | ✓ | ✓ |
| Execute scenarios | — | ✓ | ✓ |
| Reinstate a contained agent | — | — | ✓ |

**The management plane is operator-facing.** An `AGENT` principal is a workload, not an operator, and has no management-plane access at all — including to its own governance evidence. Agent self-service, if a product need ever appears, should be a deliberate capability with a resource-scoped authorization model rather than a by-product of role gating.

**No principal may execute as another agent.** `ADMIN` previously could. Administrators evaluate agents through the scenario sandbox instead. If legitimate administrative execution-on-behalf-of is ever required, it belongs in an explicitly attributed delegation capability with actor-versus-execution-identity semantics ([ADR-021](ADR-021-multi-agent-governance.md)), not as a residue of the basic runtime route.

## The sandbox is the isolation boundary; the identity is not

These are separate controls and the distinction matters, because the scenario permission granted above is only sound while the isolation holds:

```text
Scenario execution
      │
      ├── sandbox services and state
      ├── sandbox audit, session and finding records
      ├── sandbox-local identity
      │
      X   no path to live enforcement state
      │
      ▼
Live agent status, posture, findings, sessions, execution authority
```

The isolation boundary is the throwaway pipeline (ADR-013): a scenario run owns its own agent, session, findings, risk, audit, tool and execution-grant state, and emits no behavioural telemetry. The sandbox-local identity removes a namespace collision within that boundary; it does not create it, and renaming an identifier would not isolate anything on its own.

They are independently verifiable, and measured as such. Wiring the runner to the live pipeline while the role gate stays correct fails three corpus tests; widening the role gate while the sandbox stays intact fails four; doing both fails seven. Neither control masks the other, which is what distinguishes this pair from the runtime plane's two role layers below.

## Identity claims

`JWTClaims.agent_id` is mandatory for every principal, so operator tokens carry it as a placeholder. The token contract is unchanged; its interpretation is fixed:

- `agent_id` is authoritative as an **execution identity** only for `AGENT` principals.
- It is **not** the resource scope of an `ANALYST` or `ADMIN` principal.
- Placeholder values such as `admin-agent` are not authorization subjects. An `ADMIN` token minted with `agent_id="admin-agent"` cannot execute as `admin-agent` either; the refusal is about the role.

## Resource authorization is deferred, not designed away

The review separated role, resource and administrative authorization. Because no role holds partial visibility of the management plane — `AGENT` has none, `ANALYST` and `ADMIN` have all of it — **resource-scoped authorization has no subject in this decision and no code here**. Building the mechanism now would mean untested machinery with no consumer.

The rule it must follow when it arrives is recorded now, while the reasoning is fresh: where a principal is permitted a resource *class* but not a specific *instance*, the response is `404`, not `403`, so that the response cannot distinguish "exists but forbidden" from "does not exist". Until then, the enumeration property is satisfied structurally: mount-level gates run before any handler, so no route authorizes after a lookup.

---

# Alternatives Considered

## Option A: Apply `require_roles` to each route individually

Rejected. Twelve management routes, three scenario routes and one runtime route each carrying their own gate makes a forgotten decorator an open route, and the omission is invisible in review. Mounting the gate makes the plane the unit of policy and the failure mode a route no more permissive than its plane.

## Option B: Enforce authorization in middleware

Rejected. Middleware sees paths, not routes, so policy would be expressed as path matching maintained in parallel with the router — two sources of truth that drift silently. Dependencies are resolved by the same router that owns the route.

## Option C: Allow an `AGENT` principal to read its own governance evidence

Rejected for this milestone. Every management evidence endpoint is a collection, so "own data" requires per-resource filtering on every route — the resource-scoped model deferred above — and a filtered `200` is indistinguishable from an authorized empty result. Nothing in the runtime path requires it. Deliberate self-service remains available later as a designed capability.

## Option D: Retain administrative impersonation on the runtime route

Rejected. Under ADR-024, activity attributed to an agent feeds that agent's posture and can contain it, so impersonation is the ability to shape a subject's containment while the audit trail records the principal as `ADMIN` and the behaviour as the agent's. Making that safe requires actor-versus-execution-identity semantics the platform does not have, and delegation is out of scope.

## Option E: Restructure the JWT claims so `agent_id` is absent for operators

Rejected. The semantic awkwardness is real, but changing the token contract invalidates every issued token and every issuing path for a naming improvement. A documented interpretation rule achieves the security property at no compatibility cost.

## Option F: Keep the pending invariant that `ANALYST` is refused scenario execution

Rejected, deliberately and with the reasoning recorded. That invariant was written before M2a, when a scenario drove the live pipeline; the threat model has always described attack scenario evaluation as an analyst capability. Retaining a denial because it was written earlier would preserve an implementation accident as though it were a security property. The invariant is **rewritten, not deleted**, to state the permission together with the isolation that makes it safe.

## Option G: Keep `"agent-1"` as the scenario identity

Rejected. The sandbox shares no state with the live runtime and the scenario response carries no agent field, so nothing was misreported to an API caller. But the records a run produces — session events, findings and audit events inside the sandbox — were attributed to a name that also belongs to a real registered agent, which is ambiguous for anything that reads them. A sandbox-local identifier makes the isolation visible in the data rather than only in the architecture.

---

# Consequences

## Positive

- H-2 and M-3 are closed. Pending security-corpus invariants fall from 13 to 7.
- `app/api/runtime.py` makes no security decision. Policy sits at the API boundary rather than mixed into request handling.
- Adding a router to an unlisted prefix fails a corpus regression, so the plane model cannot be bypassed by growth.
- Administrative authority and execution authority are separable, which is the prerequisite for designing delegation rather than inheriting it.

## Negative

- `ADMIN` loses a capability it previously had. Administrative validation of an agent now runs through the scenario sandbox, which is isolated and therefore cannot reproduce a live agent's accumulated posture.
- Local development against the reinstatement route requires `EASP_DEV_TOKEN_ROLE=ADMIN`; `scripts/dev-start.sh` defaults to `ANALYST`.
- The runtime plane's role gate and `require_execution_identity`'s own role check are mutually redundant: each refuses a non-`AGENT` principal, so neither can be killed by a single mutation. The redundancy is retained deliberately — the dependency stays correct if applied to a route outside the runtime mount — and is verified by a combined mutation.

## Residual Risks

- **Operator roles are undifferentiated.** `ANALYST` and `ADMIN` see the same evidence. Any future need for partial visibility requires the deferred resource-scoped model.
- **No tenancy.** Roles are global to the process; there is no notion of an operator scoped to a subset of agents.
- **Placeholder identity claims persist.** `agent_id` remains mandatory for operator principals, so the invariant that it is not an authorization subject is maintained by rule and test rather than by the schema.
- **Scenario resource consumption.** An `ANALYST` may execute scenarios repeatedly. Prompt-mode scenarios call a model provider, so the cost and load boundary is a quota concern, not an authorization one.

---

# Scope

This decision covers plane authorization, execution identity binding, scenario role gating and the sandbox identity.

It does not introduce resource-scoped authorization, tenancy, delegation or impersonation ([ADR-021](ADR-021-multi-agent-governance.md)), changes to the JWT schema, execution-outcome reporting semantics, state retention or eviction, or a general resource abstraction. Those remain with their own decisions.
