# ADR-026: Materialized Risk Projection and Enforcement Epoch Architecture

**Status:** Accepted

**Date:** 2026-09-21

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Implemented in v0.16.0-dev (`AgentRiskAggregate`, `RiskAggregator`, `BaselineWatermark`, evidence sequencing, posture reconciliation)
- Verification established separately in the security corpus (#146)

---

# Context

[ADR-024](ADR-024-agent-enforcement-state.md) made enforcement agent-scoped: a decision is derived from the agent's accumulated posture rather than from one session. It derived that posture by scanning `FindingsService` on every request. That is correct and it does not scale, so the enforcement hot path now reads a per-agent **materialized projection** instead.

The change is not only a performance change. Before it, the value enforcement was derived from was recomputed from authoritative evidence at the moment of the decision, so it could not disagree with that evidence. Now it can. The platform therefore acquired a state it did not previously have:

```text
before   "this agent's posture is X"                     (recomputed, always current)
after    "this agent's posture is X"           HEALTHY
         "this agent's posture may be wrong"   STALE / UNINITIALIZED
```

The second is not a degraded version of the first. *"We do not currently know how risky this agent is"* is a different claim from *"this agent is low risk"*, and the platform must not silently convert one into the other. A cache that serves a stale value returns slightly old data; a security projection that serves a stale value authorizes execution on the strength of evidence it has not seen.

This ADR records what the projection is, what authority it carries, and what happens when it cannot be trusted.

---

# Decision

## 1. The projection is derived state, never authoritative evidence

`Finding` remains the authoritative record of what a detection rule observed, and `FindingsService` remains its sole owner. `AgentRiskAggregate` is a **materialized security projection**: a bounded summary of that evidence, existing so that runtime authorization has O(1) access to enforcement state rather than scanning the evidence store per request.

Two consequences follow, and both are load-bearing:

- **The projection may be discarded and rebuilt at any time** without loss, because everything in it is derivable from findings plus the current enforcement watermark. This is what makes reconciliation a valid repair rather than a guess.
- **The projection may never be the only record of anything.** It holds counts and scores, not finding references, so nothing is retrievable from it that is not retrievable from the evidence store. A projection that accumulated unique state would be authoritative in fact whatever this document called it.

## 2. An untrustworthy projection authorizes nothing

Posture carries an explicit lifecycle state, and only one of its values is usable for a decision:

| State | Meaning | Effect on authorization |
|:---|:---|:---|
| `HEALTHY` | summarises all evidence after the baseline | usable |
| `UNINITIALIZED` | no projection has been built for this agent | reconcile first |
| `STALE` | evidence was missed, or ingestion failed | reconcile first |

Reconciliation is attempted, not assumed to succeed. **If it fails, the request is refused.**

This is the platform's first availability-driven denial, so its reporting contract matters as much as its decision. A failed reconciliation reports **no** risk assessment, **no** posture, **no** response action and **no** execution grant, with `refusal_reason = POSTURE_RECONCILIATION_FAILED` — the contract a session-binding refusal already follows (ADR-024).

Neither alternative was acceptable:

- Reporting a synthetic `LOW` would let a consumer read "we could not determine this agent's risk" as "this agent was assessed and found harmless." That is the precise confusion this ADR exists to prevent.
- Reporting a synthetic `CRITICAL` would put fabricated evidence into the security record and could contain an agent on the strength of an availability failure, making a projection defect indistinguishable from agent misbehaviour.

An unknown posture is not a risk level. It is the absence of one, and it is reported as such.

## 3. Reconciliation belongs to the runtime, and cannot move a baseline

Reconciliation runs on the security execution path, under the per-agent coordination lock, and rebuilds the projection from authoritative findings and the **stored** enforcement watermark.

It explicitly **never establishes or advances a baseline**. Reconciliation is repair — restoring agreement between the projection and the evidence — whereas establishing a baseline is a governance act that changes which evidence is eligible to enforce at all. Collapsing the two would make a projection failure a route to discarding an agent's accumulated risk, turning a repair mechanism into an enforcement bypass.

```text
reconciliation  reads    findings + stored watermark   -> rebuilds projection
reinstatement   captures new watermark                 -> establishes an epoch
```

Only administrative reinstatement (ADR-024) creates an epoch.

## 4. An enforcement epoch is one atomic watermark

`BaselineWatermark` couples `baseline_at` and `baseline_sequence` into a single frozen value captured during reinstatement.

They are one value because they are one boundary. Held separately, a timestamp and a sequence could be written at different moments or read inconsistently, and the two halves would disagree about which evidence belongs to the new epoch — evidence after the sequence but before the timestamp, or the reverse, would be eligible under one test and not the other. The atomic watermark makes "which epoch does this evidence belong to" a question with exactly one answer.

Findings before the baseline **remain authoritative evidence and stay readable**; they simply no longer enforce. That is what makes reinstatement possible without erasing history: an agent returns to service without the evidence that contained it immediately containing it again, and without that evidence being destroyed.

## 5. `evidence_sequence` is authoritative for ordering, and gaps are failures

`FindingsService` assigns every accepted finding a strictly monotonic per-agent sequence, and is the only component permitted to do so. Sequence `0` means unassigned and is never valid input to the projection.

The projection's cursor must advance **contiguously**. A finding arriving beyond the next expected sequence means evidence was missed, and the projection transitions to `STALE` rather than advancing past the gap.

Skipping is not an option available to a security projection. Advancing the cursor over a gap would discard whatever the missing sequence carried — possibly the finding that would have contained the agent — and the projection would then report `HEALTHY` while summarising evidence it never saw. A gap is the projection detecting its own incompleteness, which is exactly the condition it must not conceal.

## 6. Authority for a security decision

```text
Authoritative evidence  (FindingsService)
        │
        ▼
  Risk projection
        │
        ├── HEALTHY ──────────────► Runtime authorization
        │
        └── STALE / UNINITIALIZED
                 │
                 ▼
          Reconciliation  (runtime, per-agent lock, stored watermark)
                 │
          ┌──────┴──────┐
          ▼             ▼
       HEALTHY        failure
          │             │
          ▼             ▼
    authorization    FAIL CLOSED
```

The projection is on the authorization path but is never the authority. Evidence is authoritative; the projection is a bounded view of it whose health determines whether it may be used at all.

**Projection divergence is a security condition, not a cache-consistency or performance condition.** It is classified, detected and reported as such, and it denies.

---

# Two redundancies this architecture creates

Both are recorded here rather than resolved silently, because each is an alternate or unreachable path through security-critical code, and a decision either way is substantive.

## The legacy `RiskService` fallback

`RuntimeService._assess_agent_posture` retains a branch that scans findings directly when no `RiskAggregator` is supplied — the pre-M5-B behaviour, kept for partially constructed runtimes.

Measured position:

- `app/api/dependencies.py` always supplies a `RiskAggregator`, so **production never executes it**.
- The security corpus did not supply one until #146, so **every corpus enforcement test executed it** while production executed the projection path. The enforcement invariants of ADR-024 were being revalidated against a path production no longer used.
- Since #146 the corpus supplies one too, so the branch is now unexercised by both.

That second point is the argument. This is not dormant code that went unnoticed; it is a code path that **silently captured the project's entire assurance mechanism** for the duration of one milestone, and did so without any test failing. An alternate security execution path whose selection is implicit in constructor arguments will be taken again the next time wiring is incomplete, and nothing will say so.

**The architectural rule this establishes:** production runtime must not silently select an alternate security posture implementation based on incomplete dependency wiring. Which implementation enforces is a property of the architecture, not of how thoroughly a caller populated a constructor.

Applied to the fallback:

- Production wiring supplies a `RiskAggregator`.
- The security corpus now supplies one too.
- The fallback is therefore unreachable in both validated paths.
- Retaining it leaves a second posture-authority implementation in the codebase.
- Future incomplete wiring could silently bypass the projection-health semantics this ADR establishes — which is precisely what already happened to the corpus.

**Decision: deprecate, and remove in a separate change.** Backward compatibility for partially constructed runtimes is not worth a second, quieter implementation of enforcement posture. A runtime constructed without the services enforcement requires should fail to construct rather than enforce differently.

Removal is deferred deliberately, so that this ADR records an architectural decision rather than combining one with implementation cleanup.

## The B-5 pre-baseline guard is conditionally subsumed by B-3

`AgentRiskAggregate.apply_finding` carries two guards that both reject evidence by sequence:

```text
B-5   seq <= baseline_sequence       -> historical, skip
B-3   seq <= last_applied_sequence   -> duplicate, no-op
```

Every mutator maintains `last_applied_sequence >= baseline_sequence`: `__init__` and `reset_to_baseline` set them equal, `rebuild_from_findings` sets the cursor to the highest post-baseline sequence or to the baseline when there is none, and incremental application only ever advances it. Therefore `seq <= baseline_sequence` always implies `seq <= last_applied_sequence`, and **B-3 returns first for every input B-5 would have caught**.

Measured: removing B-3 alone fails two tests; removing both fails four; removing B-5 alone fails none. B-5 has an effect only when B-3 is already broken.

**B-5's redundancy is conditional on preservation of the cursor invariant `last_applied_sequence >= baseline_sequence`.** It is not intrinsic to the design. Nothing in the architecture requires that relationship to hold — it holds because every mutator written so far happens to maintain it.

**Decision: retain B-5 as a defence-in-depth invariant**, because it protects the epoch boundary independently if a future lifecycle transition, rebuild, rollback or partial-state operation violates that cursor invariant. In that state B-5 is immediately load-bearing, and it is the guard that keeps a prior epoch's evidence out of a new one. Removing a correct guard because current mutation testing cannot kill it would trade a real safety property for a coverage statistic.

This makes the cursor invariant itself a thing the platform depends on. It is now named and enforced as **CI-1**.

### CI-1 — the cursor never precedes the baseline

> At every externally observable aggregate state, `last_applied_sequence >= baseline_sequence`.

Enforced inside `AgentRiskAggregate` at each of its four sequence-mutating boundaries and again in `snapshot()`. The read boundary matters because the sequence attributes are public: a mutator this class does not know about — a future one, or a caller assigning directly — can reach an invalid state without passing any write-side check, and every consumer reads through `snapshot()`.

**The violation is reported, never repaired.** Clamping the cursor up to the baseline would produce a plausible-looking projection and silently invalidate the reasoning below, which is the failure this invariant exists to surface.

A violated CI-1 is treated as an untrustworthy posture and fails closed at the runtime authorization boundary under the existing `POSTURE_RECONCILIATION_FAILED` contract. The underlying event is a projection-integrity violation rather than a failed reconciliation attempt, but the externally meaningful security state is identical — the runtime cannot establish a trustworthy posture from the projection — so the public refusal taxonomy is not widened. Reconciliation is deliberately *not* attempted: a rebuild would produce a consistent projection and conceal that the violation ever occurred.

Layering is preserved. The aggregate detects and reports integrity failures and knows nothing of authorization or refusal contracts; naming what an untrustworthy projection means for a request belongs to the runtime.

Before CI-1 was enforced, an aggregate with `baseline_sequence=50` and `last_applied_sequence=3` reported `HEALTHY` and authorized normally. That state is worse than merely undetected: B-5 skips every finding up to the baseline as historical while the cursor says none of it was applied, so the evidence between the two is discarded rather than summarised, and the projection reports a risk level derived from evidence it silently dropped.

**What CI-1 establishes, and what it does not.** It does not make B-5 permanently redundant. It establishes the condition under which B-5 is currently subsumed:

```text
CI-1 holds  +  B-3 holds   ->   B-5 has no independent observable effect
```

B-5 therefore remains defence in depth precisely because its redundancy depends on CI-1 continuing to hold, and a violation of CI-1 is now itself a fail-closed security condition rather than a silent one.

---

# Adjacent Capability Status

M5-B landed as one change containing several distinct capabilities. Related code existing is not the same as a finding being resolved, and implementation plus tests is not the same as a production capability. Each is therefore mapped to its verified status rather than inferred from the change it arrived in.

| Capability | Implemented | Production-wired | Architectural status |
|:---|:---:|:---:|:---|
| Materialized risk projection | Yes | Yes | M5-B |
| Enforcement epochs / watermarks | Yes | Yes | M5-B |
| Runtime reconciliation | Yes | Yes | M5-B |
| Session-event retention | Yes | Yes | Partial M-4 contribution |
| Execution receipts | Yes | **No** | Does not close NEW-003 |
| Audit / evidence archival | No | N/A | Future persistence work ([ADR-016](ADR-016-behavioral-event-store-and-data-model.md)) |

## Session retention is not M-4 completion

M5-B introduced retention controls for session events, governed by the detection evaluation horizon plus a late-arrival grace rather than by arbitrary capacity — the right basis, because it ties retention to the window detection actually needs.

This addresses **one** bounded in-memory store covered by M-4. It does not establish bounded or archived retention semantics for every store M-4 measures, which are audit events, risk assessments and session events.

The three are not equivalent problems:

- **Session events** are operational working state, bounded by a detection horizon. Done.
- **Risk assessments** are derived reporting state, boundable on similar terms. Open.
- **Audit evidence is not simply another cache to which an eviction policy can be applied.** Security invariant 4 requires an append-only record of every decision, and bounding the audit log by a retention horizon would weaken an existing invariant in order to satisfy a later one. Treating it as a cache could conflict with evidence-preservation requirements. Audit growth belongs with persistence and archival (ADR-016), not with eviction.

M-4 as originally written conflates three stores with different retention semantics. It remains **open and in need of decomposition**, store by store, before any part of it is marked resolved.

## Execution evidence exists in the codebase but is not on the production execution path

`ExecutionEvidenceService` and `ExecutionReconciler` carry their own invariant set (N3-1 … N3-11) and are covered by service tests. They are constructed **only in tests**:

```text
Code exists
   ├── ExecutionEvidenceService
   ├── ExecutionReconciler
   └── ExecutionReceipt
         │
         ▼
Production ToolExecutor
         │
         X   evidence store not supplied
```

`DefaultToolExecutor` accepts an optional evidence store; no production wiring supplies one.

**The existence of implementation and tests does not constitute production execution evidence.** NEW-003 is the inconsistency where a request may be audited `ALLOW` and then obtain no grant, so the audit record claims an execution that never happened. Execution receipts are a plausible mechanism for closing that, but a mechanism no running code path invokes changes nothing about the platform's behaviour.

**NEW-003 remains open** until execution evidence is wired into the production execution boundary and its lifecycle is verified end to end.

---

# Consequences

## Positive

- Enforcement posture is O(1) on the hot path, with authoritative evidence unchanged as the source of truth.
- The platform can now distinguish "not risky" from "not known", and denies on the second.
- The epoch boundary is a single value, so evidence eligibility has one answer rather than two that can disagree.
- Projection state is bounded and holds no finding references, so the hot path cannot grow with evidence volume.

## Negative

- Authorization now depends on the health of derived state. A projection defect denies legitimate traffic — the correct failure direction, but an availability cost that did not previously exist.
- A second consistency mechanism exists between evidence and posture, with its own failure modes and its own repair path.
- Reconciliation is a full rebuild from authoritative findings, so the scan M5-B removed from the hot path returns on the repair path. This is acceptable because repair is rare and correctness matters more there than latency, but it is a real cost under a pathological STALE rate.

## Security-corpus parity becomes a standing requirement

**Security-invariant fixtures MUST exercise the same security decision path and the same required dependencies as production.**

This is stated as a requirement rather than a lesson because it has now failed twice, in the same way, in one milestone:

```text
M5-B projection
    production       -> RiskAggregator supplied
    security corpus  -> initially missing, corpus ran the legacy fallback
                     -> corrected in M5-B.1 (#146)

M4 session retention
    production       -> DetectionRetentionPolicy supplied
    security corpus  -> initially missing, pruning was not exercised
                     -> corrected in M5-B.4
```

That is a repeatable class of verification failure, not an isolated mistake. When production and corpus wiring diverge, the corpus keeps passing and reports assurance it is no longer providing — the failure is silent by construction, because nothing about a green suite indicates which implementation produced it.

One limit is worth stating explicitly: **fixture parity is not production parity.** It is evidence that the corpus exercises the production architecture. It is not evidence that production itself is correctly wired, which remains a separate question answered by production wiring tests and review.

## Residual Risks

- **Audit and risk-assessment growth remain unbounded.** Session-event retention is now exercised by the corpus (M5-B.4), and its isolation from security-authoritative state is enforced there. The other two stores M-4 measures have no lifecycle, and audit is not a store an eviction policy can be applied to without weakening security invariant 4.
- **Reconciliation cost under sustained divergence** is unbounded relative to evidence volume for the affected agent.
- **Durability.** Projections, baselines and sequences are process-local. A restart loses the projection, which is recoverable by reconciliation, and loses the enforcement state it reconciles against, which is not (ADR-024, ADR-016).
- **Sequence assignment is single-process.** `FindingsService` is the sole sequence authority; a multi-process deployment needs a distributed sequence authority before this design holds.

---

# Disposition

| Finding | Decision | Follow-on |
|:---|:---|:---|
| Legacy `RiskService` fallback | Deprecate and remove | Separate production change |
| B-5 pre-baseline guard | Retain as defence-in-depth | Done — CI-1 enforced (M5-B.3) |
| Session-event retention | Keep as an M5-B contribution | M-4 decomposition |
| Execution receipts | Implemented capability, not a production feature | Wire the production execution path |
| Corpus / production fixture parity | Standing requirement | Done — retention parity closed (M5-B.4) |
| M-4 | Remains open, decomposed store by store | Define per-store lifecycle semantics |
| NEW-003 | Remains open | Production evidence wiring plus corpus verification |

Each follow-on is an independently reviewable change. None is made by this ADR.

---

# Scope

This decision covers the materialized risk projection, posture lifecycle states, reconciliation authority, the enforcement epoch watermark, evidence sequencing, and the fail-closed dependency of authorization on projection health.

It does not remove the legacy fallback, alter the B-5 guard, resolve M-4 or NEW-003, introduce persistence, or change detection, risk weights, response semantics, or the authorization model established in [ADR-025](ADR-025-management-plane-authorization.md). Each is recorded above as a decision or an open status to be actioned as its own change.
