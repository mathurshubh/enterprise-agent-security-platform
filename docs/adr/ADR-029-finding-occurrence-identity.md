# ADR-029: Finding Occurrence Identity and Detection Lifecycle

**Status:** Accepted

**Date:** 2026-09-23

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Decision record for behaviour implemented in `#164`, `#165` and `#166`.
- Closes the Track A defect: a reinstated agent repeating an attack in the same session was answered `ALLOW`.
- The final section is a **review input to [ADR-016](ADR-016-behavioral-event-store-and-data-model.md), not a decision about it.**

---

# Context

[ADR-024](ADR-024-agent-enforcement-state.md) separates what a reinstatement does from what it does not: it resets enforcement **eligibility**, never security **history**. Evidence recorded after the baseline must therefore still count, and ADR-024 rejected a candidate design on exactly that ground — comparing the baseline against `Finding.created_at` was *"rejected after measurement… leaving a reinstated agent permanently unenforceable."*

The platform exhibited that condition anyway, by a different mechanism. Reproduced at the HTTP boundary:

```text
injection            -> DENY, SUSPEND_AGENT, agent SUSPENDED
reinstate            -> 200, ACTIVE
identical injection  -> ALLOW, MONITOR, agent ACTIVE      (same session)
identical injection  -> DENY, SUSPEND_AGENT               (different session)
```

The cause was not deduplication in the findings store, which a mutation disproved. It was that **finding identity named the scope a detection happened in — rule, session, agent, indicator or threshold — and not which occurrence it came from.** Detection repeats for two different reasons, and nothing could tell them apart:

```text
a new occurrence    the condition happened again, on different evidence
a re-derivation     the same occurrence, recomputed by a later request
```

Both directions are security defects. Treating a new occurrence as a re-derivation loses evidence. Treating a re-derivation as new inflates risk on unchanged behaviour, which is what the M2a accounting control exists to prevent.

---

# Decision

## 1. A finding identifies an occurrence

A finding's identity answers *which occurrence produced this*, derived from properties of the history rather than of the moment it is read. Two detections of the same condition are the same finding only when they are the same occurrence.

## 2. Content occurrence identity

Content rules evaluate one request, so each firing is an independent occurrence. Identity includes the **persisted `SessionEvent.sequence_number`** of the triggering event:

```text
(rule, session, agent, indicator, triggering_event_sequence)
```

The sequence, not an ordering position: a position changes when the retained history changes shape, and a persisted sequence does not.

## 3. Accumulation identity is the pinned crossing

A threshold rule re-evaluates the whole session history on every request, so a crossed threshold is re-derived by every later request. Identity is:

```text
(rule, session, agent, threshold, pinned_crossing_evidence, enforcement_epoch)
```

`pinned_crossing_evidence` is the evidence that **established** the crossing, fixed when it was first reported and read back from the prior finding. It is not recomputed from the current window: the in-window set slides continuously under sustained denial while the crossing does not, so recomputing manufactures a new identity on every request.

**The episode rule.** A crossing remains the same occurrence while any of its pinned evidence is still inside the evaluation window **and** the enforcement epoch has not moved on. Otherwise the rule re-arms, and the next crossing is identified by its own evidence.

## 4. The enforcement epoch is evaluated at the occurrence's temporal point

The epoch is evaluated **as of the occurrence's evaluation time**:

```text
epoch(agent, t) = |{ REINSTATE transitions for agent : occurred_at <= t }|
```

It is derived from `AgentService`'s append-only transition history and introduces no new state. Evaluating it at `t` rather than at "now" is the property that makes live evaluation and any future temporal replay agree on the same occurrence.

It is never the agent's *current* epoch. Reading the current epoch would make the identity of a past event depend on when it is looked at, so the same behaviour would produce one finding live and a different one on replay.

Neither existing field could serve. `baseline_sequence` is identical for two recoveries with no evidence recorded between them. `baseline_at` is a wall-clock capture rather than a position in the history being replayed.

## 5. Post-baseline occurrence semantics

A recovery ends the preceding occurrence. Evidence recorded after an enforcement baseline is therefore a new occurrence, receives a fresh `evidence_sequence` and `recorded_at`, and is eligible for enforcement — which is what ADR-024 requires and what the platform previously failed to deliver.

## 6. Derived occurrence evidence is immutable

`Finding` carries `evidence_event_sequences` and `enforcement_epoch`: the evidence its identity was derived from. Once recorded, these are not rewritten by a later evaluation. The artifact that decides whether a crossing is still the same one must not be rewritten by the evaluation asking the question.

These fields are not interchangeable with the proposed forensic model:

```text
evidence_event_sequences   this implementation's derived occurrence evidence,
                           holding SessionEvent.sequence_number

contributing_event_ids     the ADR-017 / ADR-016 future forensic model,
                           holding durable telemetry event identifiers
```

They serve the occurrence lifecycle decided here over retained session events. They neither establish nor remove the future need for `contributing_event_ids`, and adopting that model later is Option D below.

## 7. `record_new_findings` is unchanged

The store continues to skip an identifier it already holds. That behaviour was never wrong; the identity was. With identity naming the occurrence, the skip suppresses exactly re-derivations and admits exactly new occurrences.

This keeps the boundary intact: **detection** determines what constitutes an occurrence, and the **findings store** persists immutable occurrences. The store does not reason about detector lifecycle.

## 8. Current implementation boundary

This decision operates over `SessionService`'s retained events. It does not establish durable forensic evidence, an event store, or a replay harness — none of which exist.

---

# Alternatives Considered

## Option A: Give every detection a distinct identity
**Rejected after measurement.** It breaks the M2a false-containment control: making the accumulation identity per-occurrence caused `test_denial_threshold_is_counted_once_per_session` to fail, because one crossing would be recorded repeatedly and inflate risk toward containment of a legitimate agent. A random or wall-clock discriminator additionally defeats the reproducibility that replay depends on.

## Option B: Episode identity as a universal primitive
**Rejected.** A "content episode" has no natural definition. Defined as one request it is Option's 2 identity under another name; defined as a window it collapses genuinely distinct occurrences, contradicting §2.

## Option C: Baseline-aware deduplication
**Rejected as the general mechanism, viable as a narrow one.**

```text
C can address       the reinstatement / post-baseline boundary

C cannot address    content occurrence identity
                    accumulation re-arm
                    the general occurrence lifecycle
```

Two occurrences inside one enforcement epoch still collapse under C, and a threshold re-arm within an epoch stays invisible. It would have closed the reported defect while leaving the occurrence model unresolved, so it is not the selected general mechanism.

## Option D: Bind findings to durable event identifiers
**Deferred, not rejected.** Closest to ADR-016 §2, and the direction to revisit if the durable event store is implemented. It cannot be adopted now: session events are pruned at the retention horizon, so a durable finding would hold references into evictable state — the dependency [ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md) forbade for audit. It also still requires an episode concept for threshold rules.

## Option E: Maintain mutable episode state in a service
**Rejected.** It creates a new state-management subsystem with its own lifecycle, restart and multi-worker questions. [ADR-017](ADR-017-behavioral-detection-engine.md) already specifies detection state as *"transient analytical state"* derived from inputs that include prior findings, which is what this decision implements instead.

---

# Consequences

## Positive

- A reinstated agent that resumes the behaviour it was contained for is contained again.
- Occurrence identity is reproducible from the history, so identical inputs yield identical findings.
- No new state store, and no change to the findings store's responsibilities.
- The M2a accounting control is preserved unchanged.

## Negative

- `Finding` carries two more fields, and detection takes two more inputs.
- Occurrence identity now depends on `SessionEvent.sequence_number`, so the ordering guarantee from `#165` is load-bearing for identity, not only for reads.
- A sustained attacker produces roughly one accumulation finding per evaluation window. That is correct under the episode rule and under M2a, but means risk accumulates slowly for continuous abuse.

## Residual Risks

- **Two sequence concepts.** `Finding.evidence_sequence` is per-agent; `SessionEvent.sequence_number` is per-session. Similar names, different scopes.
- **`record_findings` replaces in place.** It has no production caller, so §6 holds where it matters, but the divergence exists.
- **The `created_at` fallback.** Post-baseline filtering falls back to `created_at` when `recorded_at` is absent, and content rules pin `created_at` to the Unix epoch. No production path produces such a finding today.

---

# Non-decisions

- **The aggregation unit for `EXCESSIVE_DENIALS`.** Whether denials should accumulate per session, per agent, per agent and window, or per another unit is open and unaffected by this decision.
- **Whether a caller-supplied `session_id` should partition detection at all.**
- **Session lifecycle, ownership and forensic identity.**
- **Durable forensic evidence**, and whether `contributing_event_ids` supersedes §6.

---

# Scope

This ADR is limited to what identifies a finding and how detection distinguishes an occurrence from a re-derivation. It makes no decision about session semantics, aggregation, durable storage, or replay implementation.

---

# Input to ADR-016 Review — Replay Identity and Temporal Replay Constraints

> **Status: review input, not an ADR-016 decision.**
>
> ADR-016 is `Proposed` and unimplemented. Nothing in this section accepts its model, promotes any proposed capability to an implemented one, or establishes a replay contract. It records requirements that **any future replay implementation must satisfy** for the occurrence identity decided above to hold, and which the eventual ADR-016 review should weigh.

**1. Identity reproduction.** ADR-017 requires replay to produce *"the exact same set of findings"* as live analysis. It does not state that finding **identifiers** must be reproduced. Occurrence identity depends on that stronger property, and the gap should be closed explicitly rather than inferred.

**2. Incremental temporal replay.** Windowed detection must be re-evaluated at each ordered event's own temporal position, carrying forward what preceding evaluations produced. A single evaluation against the final retained history is **not replay-equivalent**: measured, a crossing that genuinely occurred produces nothing, because its evidence has aged out of the window by the final moment.

**3. Persisted event sequence.** Replay must preserve `SessionEvent.sequence_number` and must not reconstruct identity from a position in a retrieved list. Measured, the two diverge under out-of-order arrival — positions `[1, 2, 3]` against persisted sequences `[2, 3, 1]`.

**4. Temporal enforcement epoch.** The epoch must be derived as of the replayed event, from the transition history up to that point, never from current agent state.

**5. Proposed-versus-current boundary.** These constraints do not establish ADR-016's durable event store, its forensic guarantees, or any other unimplemented capability. The Track A implementation operates over retained session events and claims nothing beyond that.
