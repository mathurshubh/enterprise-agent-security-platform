# ADR-035: Execution Evidence and Capability Durability

**Status:** Accepted

**Date:** 2026-10-02

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- **Not implemented.** This ADR locks three contracts; no persistence for execution evidence or capability definitions exists yet. `ExecutionReceipt` is recorded on the production path but held in a bounded in-memory store ([ADR-032](ADR-032-runtime-tool-execution-isolation.md) §12), and `CapabilityApplicability` does not exist in any form.
- The physical schema is **deliberately not decided here** (§7).
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

1. Capability definitions referenced by execution evidence **must be durable**.
2. Historical definitions are **immutable**.
3. Capability content is identified by a **cryptographic digest** of that content.
4. A digest **resolves deterministically to exactly one** historical capability definition.
5. **Mutable runtime profile registration is not the historical authority.** `InMemoryCapabilityProfileRegistry` is a runtime lookup, and this ADR reclassifies it as such.
6. Capability content must be **sufficient to interpret the historical authorization boundary** — what the execution was permitted to do, not merely which set was named.

The invariant that makes a receipt's digest reference safe is therefore:

```text
digest  →  exactly one immutable capability definition
```

and not:

```text
profile_id  →  mutable capability definition
```

`ExecutionCapabilities.compute_digest` already digests the full effective capability set — filesystem, environment, network and resources, including `required_controls`, whose omission was previously corrected precisely because "the digest is what a receipt carries as evidence of the confinement an execution ran under." `destinations` and `allowed_destinations` are kept synchronized at construction, so digesting the latter covers both.

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

`SqlApprovalGrantRepository` does not persist `capability_profile_id` or `capability_digest`, and `execution_grants` has no columns for them. An `ExecutionGrant` is a frozen continuation of an evaluated decision, so an approval resumed after a restart cannot establish the capability binding it was issued under.

This is a real gap and it is **not part of this decision**. The questions differ: evidence asks *can we reconstruct what authority governed an execution afterwards*, while the grant asks *can an outstanding continuation be safely resumed*. They are adjacent lifecycle boundaries, and the grant question is recorded here as a dependency this decision surfaces rather than absorbed into it.

## 7. Deliberately not decided

The **physical identity and schema** are open. Two viable shapes exist:

- `capability_digest` as the primary identity of an immutable definition — cleaner for evidence integrity;
- `capability_profile_id` plus an immutable revision — closer to the existing domain concept.

The immutability and historical-resolvability invariants above are locked. Which representation carries them follows a full review of the capability models and repository interfaces, not this ADR.

Also out of scope: retention and archival policy (D-E1.7), artifact attestation (`implementation_id` remains logical provenance only, per ADR-032), and the production switch from in-memory to SQL repositories.

## 8. Consequences

### Positive

- A historical execution's permitted confinement becomes reconstructable from durable state alone.
- Capability definitions stop being silently mutable.
- Version-scoped applicability lets a new tool version carry different confinement.
- Evidence loss becomes a governed retention event rather than a capacity side effect.

### Negative

- A durable capability store is new persistence surface with its own lifecycle.
- Version-scoped applicability requires a declaration per concrete version, replacing a convention that needed none.

### Risks and Mitigations

- **Risk:** the digest is treated as self-describing evidence. **Mitigation:** D-C1.6 requires the definition to be sufficient to interpret the boundary; the digest alone is a reference plus integrity proof.
- **Risk:** applicability is consulted during investigation, silently reinterpreting history. **Mitigation:** D-C2.4 to D-C2.6 state the direction of authority explicitly.
- **Risk:** eviction semantics are carried into the durable store unchanged. **Mitigation:** D-E1.6 prohibits it.

## 9. Security Considerations

- Historical evidence must never depend on current control-plane state. This extends to capability semantics the property [ADR-034](ADR-034-audit-identity-contract.md) established for audit identity.
- Fail-closed execution semantics are unchanged: `STARTED` evidence remains a precondition for execution, and an evidence store failure denies rather than proceeds.
- Immutability of capability definitions is an **integrity** property, not a confidentiality one. Capability content is a confinement specification; `ExecutionCapabilities` already refuses secret-bearing environment keys at construction, which is what keeps durable definitions from accumulating credential material.
