# ADR-023: Execution Authorization Grants

**Status:** Accepted

**Date:** 2026-09-17

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Implemented in v0.16.0-dev (`ExecutionBinding`, `ExecutionGrant`, `ExecutionAuthority`, executor-side enforcement in `DefaultToolExecutor`, resource-aware HTTP decision requests)
- Resolves findings H-5 and M-2 from the post-v0.16 adversarial security review

---

# Context

[ADR-003](ADR-003-runtime-security-orchestrator.md) and [ADR-004](ADR-004-deterministic-security-pipeline.md) establish `RuntimeService` as the single authority for security decisions. The post-v0.16 adversarial review showed that authority was advisory rather than enforced.

**H-5 — decision/execution divergence.** `RuntimeService.execute()` evaluated a `resource` string, while execution later received an independent `parameters` mapping. Nothing required the two to describe the same operation. The review reproduced the exploit directly:

```text
authorize file_read(notes.txt)    → ALLOW
execute   file_read(secrets.txt)  → protected content returned
```

Containment held only because `AgentRuntimeService` happened to pass the same dictionary to both stages. Every other caller — the scenario runner, a future MCP adapter, a background worker — would inherit the bypass.

**M-2 — API resource omission.** The HTTP `ExecuteRequest` had no field for the resource or parameters being evaluated, so resource-aware policy ([ADR-006](ADR-006-resource-aware-authorization.md)) could not apply to requests arriving through the main API.

A decision was also reusable without limit. Nothing prevented one authorization from executing the same operation repeatedly, including after cumulative risk had escalated.

---

# Decision

Separate *what was authorized* from *the authority to execute it*, and enforce the relationship at the execution boundary.

## Invariants

1. **Authorization of one operation must not authorize execution of a different operation.**
2. **Only a final `ALLOW` decision may produce an execution grant.**
3. **The executor does not trust a caller's claimed binding.** It trusts only a valid grant issued by the execution authority, and the requested operation must exactly match the grant's binding.
4. **Every refusal fails closed** before the tool is instantiated or executed, and a refused attempt never consumes the grant.

Grants key on the *final decision*, not the response type. Response types map onto final decisions:

| Response type | Risk level | Final decision | Grant |
|---|---|---|---|
| `MONITOR` | LOW | `ALLOW` | Issued |
| `ALERT` | MEDIUM | `ALLOW` | Issued |
| `REQUIRE_APPROVAL` | HIGH | `APPROVAL_REQUIRED` | None |
| `SUSPEND_AGENT` | CRITICAL | `DENY` | None |
| any, with authorization or policy denial | — | `DENY` | None |

## Components

| Component | Answers | Location |
|---|---|---|
| `ExecutionBinding` | *What* was authorized | `app/models/execution_binding.py` |
| `ExecutionGrant` | *Authority* to execute that binding | `app/models/execution_grant.py` |
| `ExecutionAuthority` | Issues and verifies grants | `app/runtime/execution_authority.py` |
| `RuntimeService` | Was this operation authorized? | Decision authority |
| `DefaultToolExecutor` | Is this exactly the operation that was authorized? | Execution enforcement authority |

### ExecutionBinding

An immutable, canonical description of one operation: `tool_id`, `tool_version`, `resource`, and parameters.

- Parameters are held as `(name, value)` pairs sorted by name, however the model is constructed, so operations that differ only in mapping order are equal.
- Names must be non-empty and unique; values must be strings. Anything else is rejected rather than coerced, so two different operations cannot share a binding.
- `resource` is the `path` parameter when present. An explicit resource that contradicts it is rejected, and `RuntimeService` records that request as `DENY` with telemetry error code `EXECUTION_BINDING_INVALID` rather than authorizing an ambiguous target.
- `tool_version` is the version of the **resolved tool descriptor**, never a value a caller supplies. A tool's identity is its id together with its version, so a binding names one concrete implementation rather than a tool by name. `ToolRegistry.resolve()` yields exactly one version: an omitted version resolves only when a single version is registered, and otherwise refuses rather than selecting one by registration order.
- A tool that cannot be resolved to one concrete version produces no binding. That is an enforceability fact, not a permission one, so authorization is still evaluated and recorded; the request is refused at the containment gate with `final_decision = DENY` and no grant is issued. Approval of a `tool_id` and the existence of a registered executable implementation of it are different facts.

Every field of the binding is security-relevant, so every field participates both in the signed canonical serialisation and in exact-match verification. Signing coverage and verification coverage are separate properties: a field present in the signature but absent from the match check would defeat a forged binding while still admitting a genuinely issued grant presented against a different operation. A version mismatch is refused as `TOOL_MISMATCH` — the requested tool identity differs from the authorized one.

A binding carries no authority. Constructing one proves nothing.

### ExecutionGrant

A frozen record of `grant_id`, `authority_id`, `agent_id`, `session_id`, `binding`, `issued_at`, `expires_at` and an HMAC-SHA256 `signature` over the canonical serialisation of every other field. `decision` is typed as the literal `ALLOW`, so a grant cannot represent any other outcome.

`agent_id` and `session_id` are the authoritative execution identity (v0.17.1). They are supplied to `ExecutionAuthority.issue()` by the pipeline, which has already authenticated the agent and settled session ownership, and they are covered by the signature. Consumers therefore read execution identity from the verified grant rather than from a `RuntimeContext`, which is unsigned caller input and carries request correlation only. `verify_grant` additionally cross-checks the grant's identity against the authority's own issuance record, which holds independently of the signature.

This brings the in-memory runtime grant to parity with the persisted `ExecutionGrant` of [ADR-031](ADR-031-execution-grant-approval-control-plane.md), which has always carried both fields. A caller context whose identity contradicts the grant is refused as `IDENTITY_MISMATCH` before the grant is consumed.

### ExecutionAuthority

The sole issuer and verifier of grants for one process. It holds a random per-process signing key, a time-to-live (30 seconds by default), and a registry of outstanding grants.

## Grant Lifecycle

```text
ToolInvocation / ExecuteRequest
        │
        ▼
ExecutionBinding.from_operation(...)      contradictory binding → DENY, no grant
        │
        ▼
Authorization → Policy → Detection → Risk → Response → final decision
        │
        ├── final decision ≠ ALLOW → no grant
        │
        └── final decision = ALLOW
                │
                ▼
        ExecutionAuthority.issue()        grant registered as outstanding
                │
                ▼
        RuntimeResult.authorization
                │
                ▼
        DefaultToolExecutor.execute_descriptor(descriptor, parameters, grant)
                │
                ├── verify authority, signature, expiry, single use
                ├── require exact tool, resource and parameter match
                ├── consume the grant
                ├── instantiate the tool
                └── execute

Unconsumed grants are pruned when they expire.
```

## Revocation Semantics

**A grant represents authorized execution under the governance state observed at issuance, subject to immediate revocation by agent containment and bounded by its TTL.**

Revocation is asymmetric, and the asymmetry is the decision:

| Change after issuance | Effect on outstanding grants |
|---|---|
| Agent suspended | **revoked immediately** — `suspend_issuance` closes the gate and revokes in one lock hold |
| Agent reinstated | revoked grants stay revoked; reinstatement restores the ability to obtain authority, not the authority itself |
| Tool governance-disabled | none — effective for grants issued afterwards |
| Tool version unregistered | none — effective for grants issued afterwards |
| Capability profile altered | none — effective for grants issued afterwards |
| Enforcement epoch advanced | gates *issuance* via CAS; does not revoke |

Suspension is the containment action the detection pipeline produces, so a delay there would leave a hole in the enforcement loop. An operator disabling a tool can tolerate the grant TTL; a containment decision cannot.

### The TTL is the compensating control

`MAX_GRANT_TTL_SECONDS = 30.0` therefore bounds how long a governance change other than agent suspension can remain ineffective. It is a security policy parameter, not an implementation default, and `ExecutionAuthority` refuses a longer TTL rather than clamping it — a caller asking for a wider window has a different security model in mind, and silently narrowing it would hide the disagreement.

### Accepted residual risk

Stale non-containment governance authority may be exercised until an outstanding grant expires. Accepted, bounded by the TTL above.

### Why not re-check at claim time

Re-validating the governance plane when a grant is claimed would make claiming a second authorization, with the tool and capability services in its dependency path, and would turn their availability into execution availability. It would also require defining why `ALLOW` at issuance and `DENY` at claim is expected rather than anomalous. That is a separate capability — continuous revocation — warranted only if a requirement for sub-second administrative revocation is established. It is not an extension of this decision.

---

## Failure Behaviour

Every refusal raises `ExecutionBindingError`, a `PermissionError` deliberately distinct from `ToolExecutionError`: a refusal means the platform declined to run the tool, not that the tool failed while running.

| Reason | Condition | Grant consumed |
|---|---|---|
| `NO_AUTHORITY` | Executor is not bound to an execution authority | — |
| `MISSING_GRANT` | No grant presented | — |
| `MALFORMED_GRANT` | Presented object is not an `ExecutionGrant` | No |
| `FOREIGN_AUTHORITY` | Grant issued by a different authority | No |
| `INVALID_SIGNATURE` | Hand-crafted or tampered grant | No |
| `EXPIRED` | Grant presented at or after `expires_at` | No |
| `CONSUMED` | Grant already used, or never issued by this authority | No |
| `TOOL_MISMATCH` | Requested tool differs from the binding | No |
| `RESOURCE_MISMATCH` | Requested resource differs from the binding | No |
| `PARAMETER_MISMATCH` | Requested parameters differ from the binding | No |
| `IDENTITY_MISMATCH` | Caller context contradicts the grant's agent or session, or the grant's identity differs from the authority's issuance record | No |
| `INVALID_REQUEST` | Requested parameters cannot form a binding | No |

A disabled tool is rejected before the grant is examined. Once a grant has been verified and consumed, it stays consumed even if the tool then fails.

## HTTP API

`POST /agents/{agent_id}/execute` accepts optional `resource` and `parameters` so resource-aware policy evaluates the operation actually being requested. The endpoint remains **decision-only**: it never executes a tool and never returns a grant. Grants are in-process authority and do not leave the platform.

---

# Rationale

**Two independent invariants are stronger than one.** `RuntimeService` answers whether an operation was authorized; `DefaultToolExecutor` independently answers whether the operation in front of it is exactly that one. A defect in how a caller wires the two stages now produces a refusal instead of an unauthorized execution.

**A plain binding would only move the problem.** If the executor accepted a binding object, any caller could construct `ExecutionBinding(tool_id="file_read", resource="secrets.txt", ...)` and present it. The signature makes authority unforgeable by other components.

**Single use and expiry close the gaps a signature leaves.** Without them, one authorization could execute an operation repeatedly, or long after cumulative risk had escalated.

**A random per-process key is correct here.** This deliberately differs from the JWT signing key hardened under finding H-1, where a random key would invalidate every token on restart and diverge across instances. Grants live only in memory, never cross a process boundary and expire within seconds, so a restart *should* invalidate every outstanding grant.

---

# Alternatives Considered

## Option A: Keep Caller Convention

Rely on callers passing the same parameters to authorization and execution.

**Rejected.** This is the behaviour H-5 exploited. It is correct only for callers that happen to be written carefully, and it fails silently.

## Option B: Plain Structural Binding

Return an `ExecutionBinding` in `RuntimeResult` and have the executor compare against it.

**Rejected.** The binding is forgeable by any component holding a reference to the executor.

## Option C: Signed Grant Without Replay Protection

Sign the binding, but allow a grant to be used repeatedly until it expires.

**Rejected.** One authorization could execute an operation many times, and a grant could outlive the risk posture it was issued under.

## Option D: Configured or Persistent Signing Key

Provision the grant key like the JWT secret.

**Rejected.** It adds operational burden and secret-management risk to a credential that should never outlive the process that issued it.

## Option E: Execute Tools Over HTTP

Let the runtime endpoint execute authorized operations and return their output.

**Rejected.** It would add remote file reads to the API surface without a corresponding security requirement. The endpoint stays decision-only.

## Option F: Consume a Grant on a Mismatched Attempt

Burn a grant the first time it is presented with the wrong operation.

**Rejected.** It turns a refused, logged attempt into denial of service against the legitimate holder while adding no protection: a mismatched attempt already executes nothing, and the grant still authorizes only its own binding.

---

# Consequences

## Positive

- An `ALLOW` decision can execute exactly one operation, exactly once, within a short window.
- A new execution path cannot bypass authorization by construction: an executor with no authority, or no valid grant, runs nothing.
- Resource-aware policy applies to requests arriving through the HTTP API.
- Telemetry on the HTTP path now carries the evaluated resource and parameter hash.

## Negative

- Every executor that runs tools must be bound to the issuing authority; unit tests that stub the runtime must issue real grants.
- The authority holds bounded in-memory state. Decision-only HTTP requests issue grants that are never consumed; they are pruned on expiry, so outstanding state is bounded by request rate multiplied by the time-to-live.

---

# Security Considerations

## Residual Risks

- **In-process callers.** `ToolRegistry.get()` still returns an executable `BaseTool`, so code already running inside the platform process can call `execute()` directly. This decision closes the confused-deputy path between components; it is not a defence against malicious code inside the process, which a Python runtime cannot enforce. Requiring tools themselves to verify grants is a candidate for later hardening.
- **Duplicate operation models.** `ToolExecutionRequest` and `ToolInvocationContext` predate this decision and are unused by the execution path. They are left in place to avoid unrelated refactoring and should not be adopted as alternatives to `ExecutionBinding`.

## Out of Scope

Session identity, cumulative risk scoping, persistent suspension, management-plane authorization, detection normalisation and filesystem containment remain separate security boundaries.

---

# Architectural Principles Affected

- **Principle 1 – Zero Trust by Default:** extended to the boundary between decision and execution.
- **Principle 3 – Deterministic Security Decisions:** decisions are now bound to the exact operation they evaluated.
- **Principle 8 – Defense in Depth:** execution enforcement is independent of decision-making.
- **Principle 10 – Security Before Tool Execution:** made structurally enforceable rather than conventional.

---

# Amendment: Execution Inside the Boundary (v0.17.2)

**Status:** Proposed

**Date:** 2026-09-27

**Amends:** Option E under *Alternatives Considered*, which rejected letting the runtime endpoint execute authorized operations, and the *HTTP API* section that records the endpoint as decision-only.

## Context

Option E was rejected on a specific premise: it *"would add remote file reads to the API surface without a corresponding security requirement."* Two things have changed that premise.

**A requirement now exists.** [ADR-032](ADR-032-runtime-tool-execution-isolation.md) §12 establishes execution evidence as the authoritative record of what the execution boundary observed. [ADR-026](ADR-026-materialized-risk-projection-and-enforcement-epochs.md) records NEW-003 as open: no production path supplies an evidence store, because no production path executes a tool into state the platform retains. Evidence cannot be recorded for an execution that never happens inside the boundary.

**The current model rests on a caller's assertion.** `ExecuteRequest` accepts `tool_output` as an *input*, and `DetectionContext` scans it. On that path the platform decides partly from what the caller says the execution produced. The weakness is not hypothetical: `AgentRuntimeService`, the only component that actually executes a tool, passes `tool_output=""`, so on the executing path detection sees no output at all, while on the non-executing path it scans output the platform never observed.

Option E's rejection remains correct about the API *response*: returning file contents over HTTP adds a remote-read capability the platform does not need. This amendment separates that concern from execution itself.

## Decision

**Execution is permitted inside the boundary. The API remains free of remote file reads.**

The HTTP endpoint becomes an additional *ingress* to the existing execution authority, never a new authority and never a generic remote tool-execution interface.

```text
Agent (authenticated, acting as itself)
      │
      ▼
RuntimeService ── authentication · session binding · authorization
      │           detection · risk · response
      ▼
ExecutionAuthority.issue()          ← sole origin of execution authority
      │
      ▼
DefaultToolExecutor ── verify grant · verify capability binding · consume
      │
      ▼
ProcessToolExecutionSandbox
      │
      ▼
ExecutionReceipt                    ← what the boundary observed
      │
      ▼
receipt metadata returned to the caller
```

### Invariants

1. **No bypass of execution authority.** API-level execution occurs only through authorization → grant issuance → capability binding → sandbox. HTTP adds no path that reaches a tool without a verified, consumed grant.
2. **The caller selects a tool, never an implementation.** `tool_id` is a registered tool checked against the agent's approved tools. `implementation_id` is derived from the registered tool object and is not request-reachable; the child runtime packages production implementations only (ADR-032, v0.17.1).

   Execution parameters are supplied through the existing `ExecuteRequest.parameters` contract and remain bound into the signed execution context; this amendment does not introduce a new parameter model. The sandbox never receives mutable, independently supplied parameters from the HTTP layer after grant issuance.
3. **Grants do not leave the platform.** Unchanged. The caller never receives a grant, and grant issuance remains the single site in `RuntimeService`.
4. **The response carries receipt metadata, not tool output.** `receipt_id`, status, duration and `output_digest`. No file contents, no raw output. This is what preserves Option E's original objection.
5. **Evidence records; it does not authorize.** An `ExecutionReceipt` never establishes that an execution was permitted. The grant is authoritative for authorization; the receipt is authoritative for what happened.
6. **Execution identity is unchanged.** `require_execution_identity` already enforces `role is AGENT ∧ principal.agent_id == agent_id`, so a principal cannot execute as another agent. Provenance derives from the verified grant (v0.17.1).
7. **Caller-supplied output ceases to be authoritative.** Where the platform executes, the sandbox result is the observation. `tool_output` is retained for compatibility on non-executing requests but is no longer a basis for treating a caller's report as observed fact. Deprecating or removing the field is an API migration, deliberately not coupled to this trust-semantics decision.

### Three distinct records

| Record | Answers | Trust role |
|---|---|---|
| `AuthorizationResult` | Was this operation permitted? | decision |
| `ExecutionGrant` | Which one authorized attempt may cross the boundary? | authority |
| `ExecutionReceipt` | What happened when it crossed? | evidence |

## Bounded execution

Execution is synchronous within the capability's declared limits: `wall_clock_timeout_seconds`, `max_cpu_seconds`, `max_memory_bytes` and `max_output_bytes` (ADR-032 §9.4). The endpoint introduces no unbounded request.

**Caller disconnect does not revoke or cancel an already-consumed execution grant.** Execution continues within the declared sandbox limits and produces terminal execution evidence independently of HTTP response delivery. The HTTP connection lifecycle is not the execution lifecycle: a client closing its socket must not be able to create ambiguous execution state. The receipt, not the HTTP response, is the durable record of the attempt — which is why evidence wiring is a precondition of this amendment rather than a follow-on.

The lifecycle, in the order the executor already implements (ADR-032 §6, steps 7–8):

```text
verify grant → consume grant → STARTED receipt → sandbox execution
    → terminal receipt → HTTP response
```

STARTED evidence is recorded before the sandbox is invoked, so a failure to record it prevents execution (ADR-032 N3-3). Execution is never followed by "record it later", which would reproduce the forensic gap NEW-003 exists to close.

## Consequences

- The platform guards a real agent execution rather than a reported one.
- The executing path produces authoritative execution evidence, including an output digest. **This amendment does not feed post-execution output back into the existing detection decision**; post-execution detection would constitute a separate pipeline-stage decision. Detection, risk and response run before grant issuance and reach a final decision; execution and its receipt follow that decision and never retroactively change it.
- The API surface becomes more privileged. It is contained by the v0.17 isolation boundary and by invariants 1–4 above; it does not become a generic executor.
- NEW-003 becomes wiring with a real consumer rather than an abstract capability.
- Receipt retention must be bounded before anything writes to the store in a long-running process.
- **[ADR-013](ADR-013-scenario-runner-service-boundaries.md) Amendment M2a is unchanged.** Scenario execution stays synthetic and isolated and must not enter management state. This amendment creates the production execution surface M2a deliberately declined to make the scenario runner.

  | Execution | Classification | Management state |
  |---|---|---|
  | Live runtime | Production | Yes |
  | Scenario runner | Synthetic | No |

- **F-007 is unchanged.** The in-process `ToolRegistry` → `BaseTool.execute()` surface remains a documented residual risk (see *Residual Risks* above); this amendment adds no new in-process caller.

## Status of this amendment

`Proposed`, deliberately. It establishes the architectural direction; it does not approve or scope a v0.17.2 implementation. The execution API contract and the evidence wiring are reviewed separately, and this amendment moves to `Accepted` at that point.

---

# Related Documents

- [ADR-003: Runtime Security Orchestrator](ADR-003-runtime-security-orchestrator.md)
- [ADR-004: Deterministic Security Pipeline](ADR-004-deterministic-security-pipeline.md)
- [ADR-005: Tool Registry](ADR-005-tool-registry.md)
- [ADR-006: Resource-Aware Authorization](ADR-006-resource-aware-authorization.md)
- [ADR-013: ScenarioRunner Service Boundaries](ADR-013-scenario-runner-service-boundaries.md)
- [Threat Model](../security/threat-model.md)
- [Adversarial Regression Corpus](../../tests/security/README.md)
