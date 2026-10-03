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

## 7. Amendment (2026-10-03) — Session events are evidence too

**Scope:** `session_events` only, and only its references to the tool registry. Prompted by adversarial review Finding 2 ([adjudication](../security/reviews/2026-10-03-adversarial-review-adjudication.md)). Implemented by migration `0007`.

### 7.1 The decision this amends

Sections 1 and 4.1 describe the runtime tables as carrying composite references to `tools`, and this ADR deliberately left `session_events` with them. Migration `0004` gave `session_events` two references, `tool_id` → `tool_families` and `(tool_id, tool_version)` → `tools`, and kept the family one for a sound reason: the composite reference is `MATCH SIMPLE` and vacuous whenever `tool_version` is NULL, so the family reference was the only thing enforcing that a refused event names a registered family. That decision and its rationale stand as the record of what was decided; `0004` is not rewritten.

### 7.2 Why it is reversed

| | |
|---|---|
| **Previous assumption** | A refused event names a registered family. |
| **Actual runtime semantics** | `RuntimeService` records `SessionEvent.tool_id` as the family the request *named*, before and regardless of whether it exists. A request for an unregistered tool is denied by authorization and then recorded with that name. |
| **Required evidence semantics** | Refusal evidence must be recordable regardless of registry membership. |

Under the previous constraint, in SQL mode, the denial of a request for an unregistered tool failed to record with `IntegrityError`. The request still failed closed — nothing executed — but the denial was lost, and denials are what excessive-denial detection counts. Probing for tools that do not exist therefore produced no detection evidence. The constraint protected no consumer: no reader of `SessionEvent` treats `tool_id` as a registry reference.

### 7.3 Decision

`session_events` are evidence records and must remain recordable independently of current tool-registry membership. Tool-registry referential integrity is not a prerequisite for recording a session event, and retained events must not block registry deletion.

- `session_events` holds **no** foreign key to `tool_families` or `tools`.
- The integrity of the event stream itself is unchanged and still enforced by the database: the `sessions` and `agents` ownership references, per-session and per-agent sequence uniqueness, and positive-sequence checks.
- `tool_id` remains the literal family the request named and `tool_version` the resolved, governance-enabled version or NULL. Values are not canonicalized or re-resolved.
- Whether to record the requested and resolved family separately, as `audit_events` does (§2.2), is **not decided here** and remains a separately tracked item.
- The `0007` downgrade refuses, before changing the schema, if any stored event names an unregistered family or version. Evidence is never deleted or rewritten to satisfy a restored constraint.

### 7.4 Consequences

- A request for a nonexistent tool is denied and its event recorded on every repository adapter.
- Referential correctness between session events and the registry is not guaranteed by the database. As with §2.5, detecting it is a reconciliation query, not a constraint.
- A `security_invariant` test asserts both halves: no tool-registry reference, and the retained ownership and sequencing constraints.

## 8. Amendment (Proposed, 2026-10-03) — Administrative audit identity (F-09)

*Status of this amendment: Proposed. Scope: `AdministrativeAuditEvent`
([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md) §6). §§2–7 and `audit_events` are
unchanged. ADR-034 remains Accepted.*

### 8.1 Same contract, separate record

`AdministrativeAuditEvent` is audit evidence, not a referential-integrity participant (§2.1). It
holds **no foreign key** to `agents`, administrative state, enforcement state, or any other
control-plane table (§2.3). Its constraints express intra-record validity only (§2.4), and
interpreting it requires no join (§2.7).

It is a separate record rather than a widened `AuditEvent`. `AuditEvent` keeps its required
`session_id` and `requested_tool_id`. Making them optional to accommodate administrative events
would weaken the tool-request contract this ADR establishes, and a synthetic session or tool would
assert facts that did not occur.

Lifecycle ledgers ([ADR-024](ADR-024-agent-enforcement-state.md) amendment A.8) are authoritative
audit evidence under ADR-028 §6 despite not being `AuditEvent` rows; "audit evidence" is not
synonymous with the `audit_events` table, and lifecycle operations are never forced into the
tool-request schema.

### 8.2 Identity facts

| Field | Nullability | Meaning |
|---|---|---|
| `requested_agent_id` | required | The agent the operation named, recorded as received and **never validated**. A refused operation naming a nonexistent agent is evidence and must be recordable. |
| `attempted_action` | required | `REGISTER`, `ACTIVATE`, `DISABLE`, `SUSPEND` or `REINSTATE`. |
| `plane` | required | `administrative` or `enforcement`: the plane the action belongs to. |
| `observed_state` | nullable | The state of that plane at decision time, in that plane's vocabulary; NULL when the agent was not found. A recorded fact, not a reference. |
| `expected_administrative_version` | nullable | The expected administrative lifecycle generation supplied by the operation, when applicable. NULL for enforcement-plane operations. |
| `observed_administrative_version` | nullable | The observed administrative lifecycle generation at decision time, when applicable. NULL for enforcement-plane operations. |
| `expected_enforcement_epoch` | nullable | The expected enforcement generation supplied by the operation, when applicable. NULL for administrative-plane operations. |
| `observed_enforcement_epoch` | nullable | The observed enforcement generation at decision time, when applicable. NULL for administrative-plane operations. |
| `refusal_code` | required | Stable, machine-readable reason, independent of message text: at minimum `UNAUTHORIZED`, `VERSION_CONFLICT`, `ILLEGAL_TRANSITION`, `AGENT_NOT_FOUND`. |

The version fields are namespace-specific. For an `administrative` record, the
`*_administrative_version` fields may be populated and the `*_enforcement_epoch` fields are NULL;
for an `enforcement` record, the converse applies. An administrative audit record never compares,
aliases, or substitutes one namespace for the other.

### 8.3 Attribution (the contract decision §2.6 anticipated)

§2.6 removed `principal` as schema residue and deferred operator attribution to "its own contract
decision with defined provenance and semantics". For administrative evidence, that decision is:

- **Structured actor** `{type, id}`, with `type` in `human`, `system`, `runtime`. Type and identity
  are separate fields and never one overloaded string.
- **Provenance.** A `human` actor's `id` is derived from the authenticated principal established by
  the platform's trusted authentication boundary, never from a request body or caller-supplied
  actor field. `system` and `runtime` identifiers are reserved, assigned only by platform code
  paths (including bootstrap and scenario/runtime enforcement paths), and cannot be supplied by a
  caller.
- **Correlation.** `correlation_id` is required: the inbound request id where one exists, otherwise
  generated per operation.

This applies to administrative evidence only. It does not reintroduce `principal` on
`AuditEvent`; attribution of tool requests remains outside this amendment.

### 8.4 Detection, not enforcement

As §2.5: a record naming an agent absent from the registry is reported by reconciliation, never
refused, and reconciliation never blocks an administrative operation.
