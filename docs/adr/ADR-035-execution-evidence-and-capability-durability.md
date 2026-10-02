# ADR-035: Execution Evidence and Capability Durability

**Status:** Accepted

**Date:** 2026-10-02 (D-C1 refined and its physical representation decided 2026-10-02)

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- **Not implemented.** This ADR locks three contracts; no persistence for execution evidence or capability definitions exists yet. `ExecutionReceipt` is recorded on the production path but held in a bounded in-memory store ([ADR-032](ADR-032-runtime-tool-execution-isolation.md) §12), and `CapabilityApplicability` does not exist in any form.
- Capability **identity and physical representation** are both decided (§3). Retention policy remains open (§7).
- Grant durability is a **dependent decision**, not part of this one (§6).

---

## 1. Context

Three records establish three different facts about one authorized execution, and the platform already keeps them separate:

| Record | Establishes |
|---|---|
| Authorization decision ([ADR-004](ADR-004-deterministic-security-pipeline.md)) | what the deterministic pipeline decided |
| `ExecutionGrant` ([ADR-031](ADR-031-execution-grant-approval-control-plane.md)) | what executable authority was issued |
| `ExecutionReceipt` ([ADR-032](ADR-032-runtime-tool-execution-isolation.md) §12) | what the trusted execution boundary observed |

The receipt's identity and provenance are already sound. It derives identity exclusively from the validated grant, records `tool_id`, `tool_version` and `implementation_id` literally, and stores the `capability_profile_id` and `capability_digest` that governed the execution. Interpreting any of that requires no lookup against the tool registry — the property [ADR-034](ADR-034-audit-identity-contract.md) established for audit identity, holding here as well.

What is not sound is the lifecycle around it.

**A digest is not content.** A receipt records `capability_digest = <hash>`, which proves *which* capability set governed an execution and detects tampering. It cannot answer *what that set permitted*. Answering that requires resolving the digest to a capability definition, and the only store holding definitions is `InMemoryCapabilityProfileRegistry`, which assigns by `capability_profile_id`:

```python
self._profiles[capabilities.capability_profile_id] = capabilities
```

The `ExecutionCapabilities` object is frozen; the mapping is not. The same profile id can later resolve to different content, the previous content is retained nowhere, and the whole registry is lost on restart. So a receipt can prove it referenced a capability set whose meaning is no longer recoverable. For enterprise forensics that is inadequate: the evidence survives while its interpretation does not.

**Evidence is evicted, not retained.** `_prune_terminal_locked` discards the oldest terminal receipts once a configured bound is exceeded. The bound is deliberate and `STARTED` receipts are exempt, because they are the reconciler's only input. But silent eviction under pressure is the behaviour of an operational cache, not of durable evidence.

**Applicability is a naming convention.** Which capability profile governs a tool is decided by string interpolation at decision time:

```python
profile_id = f"profile-{tool_id}"
```

That is family-scoped, and so contradicts the concrete-version identity established across Slice 1b ([ADR-030](ADR-030-durable-state-repository-architecture.md), [ADR-033](ADR-033-tool-catalog-contract.md)): every version of a family silently inherits one profile, and a new version needing different confinement cannot express it. The convention is also already load-bearing — a tool with no resolvable profile is denied, because "a tool with no capability profile has no containment to execute inside" — so the relationship is a deterministic authorization prerequisite expressed as a derived string rather than declared state.

## 2. Decision D-E1 — Execution Evidence Durability

1. `ExecutionReceipt` **content is unchanged** by this work. Its identity and provenance are already sufficient.
2. Terminal execution evidence becomes **durable**.
3. Interpreting a receipt **must not require live registry state**.
4. Receipt identity and provenance remain **authoritative from the validated execution grant**, never from caller-supplied context.
5. Evidence persistence failure semantics are **preserved as they are**: `STARTED` evidence is a precondition for execution and a store failure fails closed before the sandbox is invoked; a terminal-write failure leaves an open receipt, emits a non-silent integrity signal, and is reconcilable to `UNKNOWN`.
6. **Silent eviction is prohibited** on the durable evidence path.
7. Retention and archival are an **explicit future policy**, not a consequence of capacity.

Point 5 is retained verbatim because it already answers the question it exists for: an execution cannot occur unrecorded, though its *outcome* may be unrecorded and is then explicitly represented. Point 6 exists because eviction is a *second* loss path that failure-mode analysis does not cover — evidence that was successfully written can still disappear.

## 3. Decision D-C1 — Capability Definition Durability

Refined 2026-10-02 after surveying the capability models. The identity question resolved
itself: **`capability_profile_id` participates in the digest** — it is the first key in the
canonical dict — so

```text
capability_digest      →  exactly one capability_profile_id    (the id is digested)
capability_profile_id  →  many digests over time              (each change yields a new one)
```

A digest therefore cannot represent two different profile ids, and a profile id can
legitimately appear across many historical definitions. The digest determines the id while the
id does not determine the digest, which makes the digest a strictly finer and complete
identity. No composite or id-plus-revision key is needed for historical identity.

### D-C1.1 Identity

`capability_digest` is the **sole immutable identity** of a persisted capability definition.
`capability_profile_id` is content-derived metadata, not an independent identity dimension.
This matches the evidence plane, where a receipt already carries the digest.

### D-C1.2 Canonical semantics

Every enforcement-relevant capability field must participate in canonical digest computation,
and reconstruction from the persisted definition must preserve **equivalent enforcement
semantics**.

This closes a fidelity gap rather than restating an existing property. `NetworkCapability`
has two representations of one fact: `destinations` and `allowed_destinations`. A validator
unions the former into the latter and only `allowed_destinations` is digested, so no two
materially different confinements share a digest. But the child payload carries
`network.model_dump()`, which includes `destinations`, and the sandbox guard's `from_dict`
**prefers `destinations`** when non-empty. Where the two disagree, the digest therefore
describes the union while enforcement applies the narrower set:

```text
digest        →  allowed_destinations = A ∪ B
reconstruction →  destinations        = A
```

The direction is restrictive rather than permissive, so nothing executes beyond what the
digest covers, and it is not reachable from production code, which constructs
`NetworkCapability()` as `DISABLED`. It is nevertheless incompatible with a digest that is the
authoritative identity of durable confinement evidence, so the invariant is locked here. Which
remedy satisfies it — removing `destinations` as a separate semantic field, canonicalizing it
into `allowed_destinations`, or otherwise preventing divergence — is left to implementation.

An earlier draft of this ADR stated that synchronization at construction meant digesting
`allowed_destinations` covered both. That is true only when one side is empty, which is the
case `model_post_init` handles; it does not hold when both are supplied and disagree.

### D-C1.3 Immutability

Definitions are **append-only**. An existing digest cannot be overwritten with different
content; identical re-insertion is idempotent. Put-if-absent is an **invariant of the store**,
not an API convenience, giving the core content-addressed property:

> A digest identifies one immutable capability definition for its entire retention lifetime.

`InMemoryCapabilityProfileRegistry` assigns by profile id and so cannot satisfy this. It is
reclassified as a runtime lookup, not the historical authority.

### D-C1.4 Historical resolution

Historical authority resolves **by `capability_digest`**, never through the current mutable
profile registry. This is a deliberate behaviour change:

| | Profile content changes while an authority is outstanding |
|---|---|
| Today | resolve by profile id → digest mismatch → **refuse** |
| Under D-C1.4 | resolve by digest → approved definition retrieved → **proceeds as approved** |

Today's behaviour is *stricter* than [ADR-023](ADR-023-execution-authorization-grants.md)
requires, which locked that governance changes other than agent suspension do not revoke
outstanding authority. Resolving by digest aligns the two.

This removes **mutable-profile drift** as a reason to reinterpret historical authority. It does
not make a stored digest executable indefinitely: a continuation's own validity rules still
apply in full — expiry, consumption, security invalidation, tool identity validity, and the
other monotonic refusal conditions locked in
[ADR-031](ADR-031-execution-grant-approval-control-plane.md) §7.5. And if the historical digest
is **unavailable**, resolution fails closed.

### D-C1.5 Binding verification

Capability binding verification remains mandatory, and the **content digest is the
authoritative comparison**. Profile-id equality is a redundant consistency assertion — digest
equality implies it, since the id is digested — and may remain as a defensive check, but is not
an independent authorization criterion.

The function's meaning changes. It no longer asks "does the mutable registry still match this
authority?" but "does the definition bound to this authority have the exact expected identity
and content?" The load-bearing integrity check becomes:

```text
look up digest X  →  recompute digest(content)  →  must equal X
```

which detects a corrupted or incorrectly populated durable store — a different threat from the
registry drift the original check was written for, and one that persistence introduces.

### D-C1.6 Control-plane separation

`CapabilityApplicability` (§4) and the mutable runtime registry govern **future authorization
only**. Neither can reinterpret or replace an existing digest-bound definition.

```text
Plane                   Identity                              Purpose
current control plane   (tool_id, tool_version) → profile_id  new authorization
historical authority    capability_digest → definition        existing grant / continuation
evidence                capability_digest                     historical interpretation
```

The two planes meet only at issuance.

### D-C1.7 Retention

A definition referenced by retained evidence or by outstanding authority **cannot be deleted**,
which makes the store append-only in practice. Unreferenced definitions still accumulate;
broader retention and archival semantics remain coupled to D-E1.7 rather than separable from it.

### Existing surface and migration

Greenfield: no capability repository exists in any form. The existing read surface is
`resolve_profile` at two call sites — issuance and execution — plus one `exists` check, and the
write surface is `register_profile`, called only from bootstrap. The durable contract is
specified under "Repository contract" below.

**Migration:** nothing to migrate. No table exists, definitions live only in memory and are
rebuilt at bootstrap, so this is clean creation with no backfill guard of the kind migrations
0003 to 0005 required.

### Physical representation

Decided 2026-10-02. The decision is not JSON versus relational columns; it is that **the exact
canonical byte sequence hashed to produce `capability_digest` is the sole reconstruction
authority**.

```text
canonical capability object → canonical JSON bytes → SHA-256 → capability_digest
```

```text
CapabilityDefinition
────────────────────────────────
capability_digest   PRIMARY KEY
canonical_payload   BLOB NOT NULL
created_at          NOT NULL
```

**`BLOB`, not `TEXT` or a JSON column.** The identity is defined over bytes, so no database
text-encoding or JSON-normalization semantics may intervene. A `jsonb` column reorders keys and
normalizes numbers, which would silently break the equality below while appearing to store the
same document. Verification is then literally:

```text
SHA256(canonical_payload) == capability_digest
```

The primary key supplies both uniqueness and the only index resolution needs; lookup is by
digest alone, so no secondary index is required.

**Why the canonical form rather than a model dump.** `ExecutionCapabilities.model_dump_json()`
currently raises `PydanticSerializationError`, because a validator freezes
`environment_variables` to a `mappingproxy`. Storing the canonical form sidesteps that path
entirely, and gains three properties a re-serialized dump would not have: digest re-derivation
is a hash of the stored bytes with no model instantiation; reconstruction fidelity is exact by
definition, since the stored bytes *are* what was digested; and **D-C1.2's `destinations`
divergence closes by construction** — the field is absent from the canonical form, so it cannot
be persisted in conflict, and reconstruction derives it from the digested union. Verified: a
model rebuilt from the canonical form reproduces the original digest exactly, with
`destinations` normalized to the set the digest describes.

Adding a `field_serializer` to repair `model_dump_json()` is **deliberately out of scope**. The
representation does not need it, and including it would widen a persistence contract into the
general serialization behaviour of the model. It is recorded as a separate latent improvement.

**Projections are permitted and are never authority.** Following the pattern already locked for
`tools`, any relational projection is written from the payload in the same statement and never
read during reconstruction:

```text
canonical_payload  ← authoritative
      │
      └── projections → query convenience only
```

The repository reconstructs from the canonical payload, then verifies the digest. The same
enforcement that `tools` uses is required here: a test that corrupts every projection while
leaving the payload unchanged must observe reconstruction unaffected. That is what makes
"never a second source of truth" checkable rather than aspirational.

### Repository contract

```text
resolve_by_digest(digest)
put_if_absent(definition)
exists(digest)
```

**Insertion derives identity from content.** The repository canonicalizes, computes the digest,
and verifies any supplied identity against it. It must not become a
*store-these-bytes-under-this-digest* API, because that would let a caller name content it did
not produce.

**`put_if_absent` distinguishes three cases**, and the third is the reason `ON CONFLICT DO
NOTHING` is the wrong primitive — it would silently accept a hash collision, corrupted input,
corrupted storage, or a programming error as a benign conflict:

| Condition | Outcome |
|---|---|
| digest absent | insert |
| digest present, identical bytes | idempotent success |
| digest present, **different** bytes | **integrity failure** |

**Reads verify.** `SHA256(canonical_payload) != capability_digest` is a content-addressed
**storage integrity** failure and fails closed. This is a different fault from the registry
drift the pre-persistence check was written for (D-C1.5): drift was mutable state diverging,
this is stored bytes not matching their own key.

```text
lookup digest → payload → SHA256(payload) == digest ?
                              ├── no  → fail closed, integrity error
                              └── yes → deserialize → reconstruct ExecutionCapabilities
```

Both operations are single-row and single-statement, so no cross-repository transaction is
required — unlike `ToolRepository`, which must materialise a family anchor in the same
transaction.

### No foreign key from evidence

Evidence holds a **logical** digest reference, with no runtime-enforced foreign key:

```text
ExecutionReceipt.capability_digest  ──logical──▶  CapabilityDefinition
```

This follows the principle locked in [ADR-034](ADR-034-audit-identity-contract.md): evidence
must not acquire a control-plane dependency that can turn evidence persistence into a runtime or
authorization availability dependency.

The historical invariant is preserved without the constraint, by enforcing retention at the
**capability repository** instead:

```text
delete capability X
    ├── referenced by retained evidence or outstanding authority → REJECT
    └── unreferenced → subject to retention policy (D-E1.7)
```

So the evidence plane depends on no referential enforcement, while a referenced definition still
cannot disappear.

## 4. Decision D-C2 — Capability Applicability

1. Applicability is **explicit control-plane state**, declared rather than derived.
2. Applicability is scoped to **`(tool_id, tool_version)`**.
3. It maps a concrete tool version to a capability profile or definition.
4. It is **never consulted to reinterpret historical evidence**.
5. Changing applicability affects **future authorization only**.
6. The **capability identity recorded on a grant or receipt is the historical authority**.

```text
(tool_id, tool_version)
        │
        ▼
CapabilityApplicability          control plane — current configuration
        │
        ▼
capability_profile_id
        │
        ▼
immutable capability definition  evidence plane — historical fact
        │
        ▼
capability_digest
```

Points 4 to 6 carry the weight. Re-pointing `file_read@2.0.0` from profile A to profile B must not change what an existing receipt means. The receipt already names profile A and digest X; its interpretation comes from the immutable definition that X resolves to, never from what applies today. This is the same monotonicity the platform applies to tool identity and audit identity: current configuration does not rewrite recorded history.

Formalizing applicability adds no gate. The absence of an applicable profile already denies.

## 5. Rationale

Evidence durability is not a storage decision with a security footnote; the security property *is* reconstructability. A receipt that survives while the capability set it references becomes unresolvable has preserved the claim and lost the fact, which is worse than an obvious gap because it reads as evidence.

Content addressing resolves this without duplicating capability content on every receipt. Identical capability sets across thousands of executions share one definition, and immutability is what makes the sharing safe.

## 6. Dependent decision — grant durability (D-G1)

`SqlApprovalContinuationRepository` does not persist `capability_profile_id` or `capability_digest`, and `approval_continuations` has no columns for them. An `ApprovalContinuation` is a frozen continuation of an evaluated decision, so an approval resumed after a restart cannot establish the capability binding it was issued under.

This is a real gap and it is **not part of this decision**. The questions differ: evidence asks *can we reconstruct what authority governed an execution afterwards*, while the grant asks *can an outstanding continuation be safely resumed*. They are adjacent lifecycle boundaries, and the grant question is recorded here as a dependency this decision surfaces rather than absorbed into it.

## 7. Deliberately not decided

**Identity is now decided.** The survey behind §3 established that `capability_profile_id`
participates in the digest, so the digest determines the id and the id does not determine the
digest. `capability_digest` is therefore the sole identity (D-C1.1), and the
`profile_id`-plus-revision alternative this ADR originally listed is not merely less clean — it
is unnecessary.

The **physical representation is also now decided** (§3, "Physical representation"): canonical
bytes in a `BLOB` keyed by digest, with non-authoritative projections.

What remains open for the capability plane is only **retention and archival policy**, which is
coupled to D-E1.7 rather than separable from it, and the **`field_serializer`** that would repair
`ExecutionCapabilities.model_dump_json()` — a latent model defect this representation does not
depend on.

Also out of scope: retention and archival policy (D-E1.7), artifact attestation (`implementation_id` remains logical provenance only, per ADR-032), and the production switch from in-memory to SQL repositories.

## 8. Consequences

### Positive

- A historical execution's permitted confinement becomes reconstructable from durable state alone.
- Capability definitions stop being silently mutable.
- Version-scoped applicability lets a new tool version carry different confinement.
- Evidence loss becomes a governed retention event rather than a capacity side effect.
- Outstanding authority stops being refused merely because a mutable profile changed, aligning the capability plane with ADR-023's revocation asymmetry (D-C1.4).
- A persisted definition reconstructs the enforcement semantics its digest describes, closing the `destinations` fidelity gap (D-C1.2).

### Negative

- A durable capability store is new persistence surface with its own lifecycle.
- Binding verification changes meaning: digest comparison stops detecting registry drift, which D-C1.4 removes as a failure mode, and becomes a storage-integrity assertion instead (D-C1.5).
- Version-scoped applicability requires a declaration per concrete version, replacing a convention that needed none.

### Risks and Mitigations

- **Risk:** the digest is treated as self-describing evidence. **Mitigation:** D-C1.6 requires the definition to be sufficient to interpret the boundary; the digest alone is a reference plus integrity proof.
- **Risk:** applicability is consulted during investigation, silently reinterpreting history. **Mitigation:** D-C2.4 to D-C2.6 state the direction of authority explicitly.
- **Risk:** eviction semantics are carried into the durable store unchanged. **Mitigation:** D-E1.6 prohibits it.

## 9. Security Considerations

- Historical evidence must never depend on current control-plane state. This extends to capability semantics the property [ADR-034](ADR-034-audit-identity-contract.md) established for audit identity.
- Fail-closed execution semantics are unchanged: `STARTED` evidence remains a precondition for execution, and an evidence store failure denies rather than proceeds.
- Immutability of capability definitions is an **integrity** property, not a confidentiality one. Capability content is a confinement specification; `ExecutionCapabilities` already refuses secret-bearing environment keys at construction, which is what keeps durable definitions from accumulating credential material.
