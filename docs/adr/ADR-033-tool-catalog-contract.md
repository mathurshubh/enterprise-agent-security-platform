# ADR-033: Tool Catalog Contract

**Status:** Accepted

**Date:** 2026-10-02

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Contract **accepted**; the durable model it projects from is **implemented** (`tool_families` + `tools(tool_id, version)` with version-level `governance_enabled`, [ADR-030](ADR-030-durable-state-repository-architecture.md)).
- The catalog API projection itself is **not yet implemented**. `GET /api/v1/tools` currently returns one row per registered `(tool_id, version)` from `ToolRegistry`, maps `id` from `tool_id`, and exposes no governance state. This ADR is the contract that work must satisfy, not a description of current behaviour.

---

## 1. Context

Tool identity in this platform is three-layered: the identity a request names, the family-scoped governance identity authorization evaluates, and the concrete implementation that executes ([ADR-023](ADR-023-execution-authorization-grants.md)). Enablement is version-scoped while authorization is family-scoped.

The management plane exposes a tool catalog to the enterprise security console ([ADR-009](ADR-009-enterprise-security-console.md), [ADR-025](ADR-025-management-plane-authorization.md)). Its grain had never been decided. The API returned one resource per concrete version, the console identified resources by `tool_id` alone, and ADR-009's wording ("registered tools, version metadata") admits either reading. Two enabled versions of one family would therefore have collided on a client-side identity that the server never intended as unique.

Separately, the catalog's only enablement filter read `ToolDescriptor.enabled` — a registry flag set at registration and never cleared — while governance enablement lives in `ToolOperational.enabled`, persisted through `ToolService` to `ToolRepository`. The catalog could not express that a version was governance-disabled.

## 2. Decision

### 2.1 The catalog is concrete-version-level

Each registered `(tool_id, version)` is an independent catalog resource. A family-level resource cannot represent two versions holding different operational state without nested version objects or a second projection, and enablement, implementation identity and execution identity are all version-scoped.

### 2.2 Catalog identity is composite; `tool_id` remains the family identity

```text
id          "file_read@2.0.0"   concrete catalog resource identity
tool_id     "file_read"         family identity
version     "2.0.0"             concrete version
```

The API carries the composite `id` itself rather than leaving clients to construct identity from presentation fields. `tool_id` is **not** redefined as a version identifier to satisfy a client's key requirements; it remains the unit an agent is approved for.

The composite identifier is a projection, not stored state. Persisting it would create a second source of truth for a value derivable from the primary key.

### 2.3 Governance state is projected from the governance repository

Three concepts remain distinct and must never be collapsed into one ambiguous `enabled`:

```text
ToolRegistry                 executable registration / implementation inventory
ToolService / ToolRepository durable governance and operational state
GET /tools                   security-console projection
```

`ToolDescriptor.enabled` is **not** authoritative governance state. A catalog that reports registry availability as governance state overstates the capability available to an operator, which is a misrepresentation risk in exactly the surface operators consult during an incident.

### 2.4 The family carries no version or governance state

`ToolFamily` holds identity and provenance only.

- **No `current_version`.** There is no canonical-version concept in the enforcement model, and "current" has no meaning when several enabled versions are intentionally registered. It would become a hidden version-selection mechanism, contradicting the principle that concrete execution identity is never inferred or silently selected.
- **No family `risk_level`.** Family risk is a projection over registered versions (`ToolService.get_family_governance`). Storing it would create a value that can drift from its own inputs.
- **No family activation flag.** Enablement is version-scoped; a second activation dimension has no defined meaning when the two disagree.

Family-level presentation metadata may be added when the domain grows a genuinely family-level concept. It does not exist today: `name` and `description` sit on `ToolIdentity` beside `version`, so they are version-scoped facts.

### 2.5 The catalog is observational

`GET /tools` does not select a version, and **is never an authorization source**. Catalog visibility must not become an input to any security decision.

## 3. Rationale

The console's family-level keying was an implementation artifact, not a contract, and choosing the grain to match it would have let a client-side detail define a server contract. Deciding the other way aligns the read path with the identity semantics the enforcement path already uses, so one concept does not have two meanings either side of the API boundary.

## 4. Alternatives Considered

### 4.1 Family-level resources with nested versions

Rejected. It requires a second projection to express per-version operational state, and it makes the common case — listing what is actually registered and enabled — the nested one.

### 4.2 Reporting registry availability as enablement

Rejected. It is the status quo, and it is the misrepresentation this ADR exists to end.

### 4.3 Leaving clients to build identity from `tool_id` + `version`

Rejected. It reproduces the collision this contract corrects, in every future client independently.

## 5. Consequences

### Positive

- One identity model across the enforcement and read paths.
- Operators can see governance state, which is the catalog's purpose.
- Multi-version registration becomes expressible rather than latently broken.

### Negative

- A breaking change to the management API's resource identity.
- The catalog read path gains a dependency on the governance repository.

### Risks and Mitigations

- **Risk:** the catalog's governance dependency is mistaken for an authorization path. **Mitigation:** §2.5 is explicit, and authorization does not read this surface.

## 6. Security Considerations

- The catalog is a read-side projection. It evaluates no policy and grants nothing.
- Exposing `implementation_id` through the management plane is **not** decided here. [ADR-032](ADR-032-runtime-tool-execution-isolation.md) establishes it as execution identity, which does not by itself make it appropriate operator-facing detail. That requires its own decision.
