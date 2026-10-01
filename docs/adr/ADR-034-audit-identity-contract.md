# ADR-034: Audit Identity Contract

**Status:** Accepted

**Date:** 2026-10-02

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- **Implemented** in Slice 1c (PR #216, `main @ 01e9542`): `audit_events` carries the three identity facts, holds no cross-table foreign key, and enforces the row-level check. `SqlAuditEvidenceRepository` runs the shared `AuditEvidenceRepository` contract alongside the in-memory adapter.
- The reconciliation detection described in §2.5 is a **follow-on obligation created by this decision and is not implemented**. Nothing currently detects an audit record naming an unregistered identity.
- Governance-state snapshots (§6) and operator attribution (§2.6) are **open decisions**, not deferred implementation work.

---

## 1. Context

`AuditEvent` records that a security decision was made ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)). Since the tool-identity work it has recorded tool identity as three separate facts: what the request named, and what the deterministic pipeline resolved — family, then concrete version ([ADR-023](ADR-023-execution-authorization-grants.md), [ADR-033](ADR-033-tool-catalog-contract.md)).

The durable schema did not match. It held one identity column, declared it `NOT NULL` against a nullable domain field, carried neither the requested identity nor the resolved version, and had a `principal` column with no domain field and no producer.

The `NOT NULL` mismatch was the consequential one. The runtime pipeline refuses some requests at a trust boundary before any tool resolution occurs, emitting an event with no resolved identity at all. [ADR-030](ADR-030-durable-state-repository-architecture.md) requires the pipeline to fail closed when an audit event cannot be persisted, and the pipeline's audit writes are unguarded — so a failed audit write denies the request. The schema could not store the most security-relevant record, and attempting to store it would have denied the request for naming a tool that does not exist.

With `tools` now keyed `(tool_id, version)` and the runtime tables carrying composite references, the question of whether audit should follow became unavoidable, and could not be answered by consistency alone.

## 2. Decision

### 2.1 Audit evidence is historical evidence, not a referential-integrity participant

`audit_events` participates in the evidence plane, not the runtime control plane. This is the governing statement from which the rest follows.

### 2.2 Three identity facts, separately recorded

| Field | Nullability | Meaning |
|---|---|---|
| `requested_tool_id` | required | What crossed the trust boundary, recorded as received. **Never validated against anything.** |
| `tool_id` | nullable | The resolved family, where resolution occurred. |
| `tool_version` | nullable | The resolved concrete implementation, where one was established. |

`requested_tool_id` is deliberately unconstrained: a request naming a nonexistent or malformed tool is precisely the case worth auditing, and it must be recordable. NULL in either resolved field is a **recorded fact** — no resolution occurred — not missing data.

### 2.3 No cross-table foreign keys

`audit_events` holds no foreign key to `tool_families` or `tools`. This is a decision, not an omission, and it is asserted by test rather than left to convention.

Because a failed audit write denies the request, any write-time constraint depending on another table's state becomes a denial path on the authorization pipeline. A registry row absent for any reason — write ordering, an unregistration between resolution and the audit write, replication lag — would deny an unrelated request. `ON DELETE RESTRICT` would invert the dependency further still, letting retained evidence block tool-family deletion.

The load-bearing property this preserves:

> A request can be denied at the trust boundary and its denial evidence still durably recorded, without requiring the requested tool to exist.

### 2.4 Constraints express intra-record validity only

One check is permitted and present:

```sql
CHECK (tool_version IS NULL OR tool_id IS NOT NULL)
```

It mirrors the domain validator — a concrete version cannot resolve without its family — and is satisfiable from the row alone.

A check, trigger or function consulting `tools` or `tool_families` is **prohibited**. It would turn current control-plane state into a prerequisite for recording history, which is what §2.1 forbids.

### 2.5 Detection, not enforcement

An audit record naming an identity absent from the registry is detected by reconciliation and **reported**, never refused. A dangling reference is evidence about the past, not corruption: the registry may legitimately have changed since the decision was recorded.

Reconciliation must report only, and must never block the runtime.

### 2.6 Attribution is not implied

`principal` is removed as schema residue: no domain field, no API exposure, no producer. Adding it to the domain because the database contained the column would reverse the authority direction. Operator or requester attribution, if required, arrives as its own contract decision with defined provenance and semantics.

### 2.7 Self-containment

Interpreting any stored identity requires **no join**. This is what keeps a record's meaning immune to later registry change, and it is the property that makes §2.3 safe rather than merely convenient.

## 3. Rationale

Audit is structurally different from the runtime control plane, so consistency with it is the wrong objective. Referential integrity protects against a referenced row never having existed; audit's requirement is the opposite — that what was recorded remains interpretable even after the referenced object changes or disappears. Self-containment delivers that, and removes the need for the guarantee an FK would have provided.

## 4. Alternatives Considered

### 4.1 Composite foreign key to `tools`, matching the runtime tables

Rejected. It makes evidence recording depend on control-plane state, and because audit failure is fail-closed, that is a denial path. Mutation testing makes the cost concrete: adding the foreign key fails eleven tests, because ordinary evidence recording then requires the registry to be populated first.

### 4.2 Nullable foreign key, enforced only when the identity is present

Rejected. A composite reference is `MATCH SIMPLE` and is therefore unchecked whenever a component is NULL, so it would be vacuous on exactly the refused paths while appearing to constrain them — and where it did apply, it would reintroduce the denial path.

### 4.3 Backfilling `requested_tool_id` from the existing `tool_id`

Rejected. They are different facts. Copying one into the other would assert that the request named what the pipeline resolved. The migration refuses to run against a populated table instead.

## 5. Consequences

### Positive

- Evidence recording cannot fail because of control-plane state, so it cannot become an authorization failure.
- Boundary refusals — the records most worth keeping — are storable.
- A stored record's meaning is fixed at write time.

### Negative

- Referential correctness between audit and the registry is not guaranteed by the database.
- The detection that compensates for that does not yet exist (§2.5).

### Risks and Mitigations

- **Risk:** the absent foreign keys are read as an oversight and "corrected". **Mitigation:** a `security_invariant` test asserts that `audit_events` has no foreign keys, and this ADR records why.
- **Risk:** divergence between evidence and registry goes unnoticed while reconciliation is unimplemented. **Mitigation:** tracked as an obligation of this decision, not as general backlog.

## 6. Security Considerations

- Audit remains an evidence surface and is never an authorization input.
- Append-only semantics and immutability are unchanged ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)); this ADR changes only what identity a record asserts.
- Whether a record must also capture **governance state at decision time** — risk level, enablement, capability profile — so that historical interpretation does not depend on current governance either, is a broader evidence-design question and is explicitly **not decided here**. Identity integrity does not require it.
