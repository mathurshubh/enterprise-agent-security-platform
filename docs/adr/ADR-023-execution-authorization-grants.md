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

An immutable, canonical description of one operation: `tool_id`, `resource`, and parameters.

- Parameters are held as `(name, value)` pairs sorted by name, however the model is constructed, so operations that differ only in mapping order are equal.
- Names must be non-empty and unique; values must be strings. Anything else is rejected rather than coerced, so two different operations cannot share a binding.
- `resource` is the `path` parameter when present. An explicit resource that contradicts it is rejected, and `RuntimeService` records that request as `DENY` with telemetry error code `EXECUTION_BINDING_INVALID` rather than authorizing an ambiguous target.

A binding carries no authority. Constructing one proves nothing.

### ExecutionGrant

A frozen record of `grant_id`, `authority_id`, `binding`, `issued_at`, `expires_at` and an HMAC-SHA256 `signature` over the canonical serialisation of every other field. `decision` is typed as the literal `ALLOW`, so a grant cannot represent any other outcome.

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

# Related Documents

- [ADR-003: Runtime Security Orchestrator](ADR-003-runtime-security-orchestrator.md)
- [ADR-004: Deterministic Security Pipeline](ADR-004-deterministic-security-pipeline.md)
- [ADR-005: Tool Registry](ADR-005-tool-registry.md)
- [ADR-006: Resource-Aware Authorization](ADR-006-resource-aware-authorization.md)
- [ADR-013: ScenarioRunner Service Boundaries](ADR-013-scenario-runner-service-boundaries.md)
- [Threat Model](../security/threat-model.md)
- [Adversarial Regression Corpus](../../tests/security/README.md)
