# ADR-028: Audit Evidence Ownership and Lifecycle

**Status:** Accepted

**Date:** 2026-09-21

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Decision record.
- Implements the `M4-AUDIT` track of [ADR-027](ADR-027-state-lifecycle-decomposition.md).
- **Attribution capture implemented** (first slice); bounded lifecycle, immutability enforcement, durability and tamper-evidence remain open. See the gap table below.

---

# Context

[ADR-027](ADR-027-state-lifecycle-decomposition.md) decomposed finding M-4 and left audit evidence as the one store whose direction was a durable lifecycle rather than eviction. It recorded that **no ADR owns audit persistence** and named [ADR-016](ADR-016-behavioral-event-store-and-data-model.md) as the architectural home.

Reviewing that conclusion turned up two things it did not account for.

**ADR-016 is `Proposed`, not `Accepted`**, dated 2026-07-24, with implementation deferred and no Event Store code in the repository. ADR-027 is Accepted, so as written it makes an accepted decision depend on a proposal. Advancing ADR-016 to Accepted as a side effect of an audit decision would approve a substantially broader architecture — seven capabilities spanning replay, indexing, provenance and tiered retention — that has not had its own review.

**The audit record is not sufficient to be the evidence record.** Three representations of the same security decision exist, and none is both complete and adequate:

| | `AuditEvent` | `SessionEvent` | `BehavioralEvent` |
|:---|:---|:---|:---|
| Coverage | every decision | every decision | every decision |
| Originating session | **absent** | present | present |
| Resource, parameter hash, risk level, principal | absent | absent | present |
| Eviction | none | pruned at the detection horizon | dropped on queue saturation |
| Retention mechanism | in-memory list | in-memory heap | **not retained** |

`AuditEvent` carries `event_id`, `agent_id`, `tool_id`, `decision` and `timestamp`. It is written on every exit from the runtime pipeline — the two boundary refusals and the evaluated path — so its coverage is complete. It also cannot say which session a decision belonged to, and once session events pass the retention horizon established in M5-B.4, **no durable record attributes a security decision to the execution that produced it.**

Behavioural telemetry carries everything that attribution needs. It is also lossy by construction (`dropped_events_count`), is retained nowhere once dispatched, and has no production subscriber.

---

# Decision

## 1. What constitutes audit evidence

Audit evidence is the **authoritative record that a security decision was made**, retained so that the decision can later be examined, attributed and relied upon.

It is distinguished from behavioural telemetry by purpose rather than by content:

```text
                    Security decision
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
       audit evidence              behavioral telemetry
       authoritative                observational
       durable                      potentially lossy
       complete coverage            best effort
             │                           │
             └─────────────┬─────────────┘
                           │
                   different purposes
```

**Telemetry must not become the audit source of truth.** That it carries richer fields is not an argument for promoting it: it is explicitly permitted to drop events under saturation, which is correct for an observational stream and disqualifying for evidence. A record that may be absent cannot establish that a decision occurred.

## 2. Ownership

**This ADR owns the audit evidence lifecycle.** ADR-027 identified the gap and named an architectural home; this decision takes ownership rather than extending a proposal to cover it.

```text
ADR-028 owns                         ADR-016 may provide
    audit evidence definition            future persistence architecture
    ownership                            telemetry / event-store implementation
    attribution                          tiering and partitioning mechanisms
    lifecycle
    independence from shorter-lived state
```

ADR-016 can later be accepted, revised or superseded without invalidating these requirements.

ADR-016 is referenced, not depended upon. Its tiered Operational → Compliance → Archival model, and its lifecycle invariant that *"event deletion is handled via lifecycle partition dropping in cold storage, never via individual record mutation"*, are the right shape for evidence, and an implementation should adopt them if ADR-016 is accepted. If it is revised or superseded, the requirements below stand independently: **they constrain any persistence architecture rather than assuming one.**

## 3. Required properties of audit evidence

1. **Complete coverage.** Every final security decision produces a record. Already satisfied: every exit from the runtime pipeline writes one, including both boundary refusals.
2. **Attribution.** *Audit evidence for a security decision must contain sufficient execution context to attribute that decision to its originating execution and session.* Stated semantically rather than as a field list, so the schema can evolve without weakening the requirement. `session_id` is the current implementation of it, and is **currently absent** — see the gap below.
3. **Immutability.** A record is not modified or removed after it is written. Currently true by the absence of any mutator rather than by construction, and unasserted.
4. **Independence from evictable state.** Evidence must not depend for its meaning on state governed by a shorter lifecycle. An audit record whose interpretation requires an unpruned session event is not durable evidence, whatever its own retention.
5. **Bounded operational memory without destroying the record.** Growth is bounded by moving evidence out of operational memory, never by deleting it. Retention and archival are distinct concerns: the first question is preservation over the required lifecycle, not expiry.

Properties 2 and 4 are related and **separately testable**, and neither implies the other:

```text
attribution fails            independence fails
    AuditEvent                   AuditEvent
      ✓ decision                   ✓ session reference
      ✗ session reference          ↓
                                 SessionEvent
    "which execution              ✗ retained
     produced this?"               ↓
                               "what did this
                                decision mean?"
```

A record can carry a session reference and still violate independence, if understanding the decision requires session state that has since been evicted.


## 4. Lifecycle responsibility

The audit evidence lifecycle is owned here; its **implementation** belongs to whichever persistence architecture the platform adopts.

Terminal session state does not affect audit evidence. A session ending, being tombstoned, or having its events pruned changes nothing about records of decisions taken within it — which is exactly why property 2 matters, since attribution cannot be recovered from a session plane that has moved on.

## 5. The current implementation is a gap, not a satisfaction of this decision

`AuditEvent` is **not** the canonical audit record. It is currently the only non-evicting **retained** representation of a security decision, and it remains **incomplete as security evidence**, though less so than when this decision was written.

"Retained" is deliberate: `AuditService` holds an in-memory list, so nothing about audit evidence is durably stored today. The distinction matters because establishing what durability means for evidence is part of what this decision exists to do, and describing process memory as persistence would assume the answer.

| Property | Status |
|:---|:---|
| Complete coverage | **Satisfied** |
| Attribution to originating execution and session | **Satisfied** — M4-AUDIT attribution capture |
| Immutability | **Incidental** — no mutator exists; nothing asserts it |
| Independence from evictable state | **Satisfied for the current evidence definition** — attribution is carried in the record, and `AuditService` holds no reference to the session plane |
| Bounded operational memory | **Not satisfied** — no retention, no archival, ~581 MB per million records |

Recording this as a gap was deliberate. Describing the existing log as satisfying an evidence contract it did not satisfy would have made the decision unfalsifiable and left the attribution defect invisible behind an accepted ADR.

### Attribution capture (first implementation slice)

`AuditEvent` now carries the originating `session_id`, **required rather than optional**: an optional field would permit an unattributed record to be written, and nothing later could repair it. The field is populated from the request the runtime is evaluating at all three producers — the evaluated path and both boundary refusals — and surfaced by the management plane.

This slice was taken first, ahead of retention and durability, because it is the only part of M4-AUDIT with an irreversible information-loss boundary: **retention preserves evidence that was captured; it cannot recover context that was never captured.** Every decision recorded before it is permanently unable to say which execution produced it.

Attribution and independence are covered by separate corpus invariants, including that attribution outlives the session events it describes and that `AuditService` holds no reference to `SessionService`.

Independence is satisfied **for the current evidence definition**, and the qualification matters. The property is about whether the record's meaning depends on shorter-lived or evictable state — not about whether the record carries every piece of forensic context. `resource`, `parameter_hash` and `risk_level` are absent from `AuditEvent`; their absence does not violate independence, because this decision does not require them. They may become evidence requirements later, and that would be a change to the definition rather than a defect against this one.

**Bounded operational memory, immutability enforcement, durability and tamper-evidence remain open**, in that order of dependence.

---

# Alternatives Considered

## Option A: Advance ADR-016 to Accepted with audit in scope

**Considered because** ADR-027 already named it the architectural home, and one persistence architecture is better than two.

**Rejected because** ADR-016 is a Proposed architecture covering seven capabilities well beyond audit. Accepting it to settle audit ownership would approve replay, indexing, provenance and tiered-retention claims that have not been reviewed on their own evidence. ADR-016 can be accepted, revised or superseded on its own terms, with this decision as an input.

## Option B: Amend ADR-016 in place and leave it Proposed

**Considered because** it keeps audit lifecycle in the document that defines the persistence model, without advancing its status.

**Rejected because** an Accepted decision (ADR-027) would then depend on requirements living in a proposal. The requirements need a status of their own, independent of whether that architecture is adopted.

## Option C: Treat behavioural telemetry as the audit source of truth

**Considered because** `BehavioralEvent` already carries session, resource, parameter hash, risk level and principal — everything attribution requires, and more than the audit record holds.

**Rejected because** the telemetry dispatcher drops events under queue saturation by design and persists nothing. Richness is not authority. A stream permitted to lose records cannot establish that a decision occurred, and promoting it would convert a correct observational design into an incorrect evidentiary one.

## Option D: Apply a retention policy to `AuditEvent` as it stands

**Considered because** it is the most direct reading of M-4 and would bound the measured growth immediately.

**Rejected because** it would bound a record that cannot support forensic attribution, fixing the smallest of the four problems while making the largest permanent. Retention on an insufficient record produces less evidence, not better-governed evidence.

## Option E: Reconstruct audit evidence from other state, as M4-RISK does for assessments

**Considered because** the preceding milestone established exactly that pattern for derived state.

**Rejected because** the asymmetry is the point. A risk assessment is a deterministic function of findings and can be rebuilt; an audit record is the evidence that something happened and has no source to be rebuilt from. Session events are evicted and telemetry is lossy, so there is nothing to reconstruct from even in principle.

---

# Consequences

## Positive

- Audit evidence has an owner, with requirements that constrain any persistence architecture rather than presupposing one.
- The attribution defect is named. It was invisible while audit was treated as a store to be bounded rather than evidence to be specified.
- Telemetry and audit are separated by purpose, which forecloses the plausible-looking mistake of promoting the richer stream.
- An Accepted decision no longer depends on a Proposed one.

## Negative

- A fifth ADR now participates in the persistence story, and the relationship between this decision and ADR-016 must be kept coherent as that architecture is reviewed.
- Requirements are stated that the implementation does not meet, so the repository carries a documented gap until an implementation decision closes it.

## Residual Risks

- **Audit growth is unmitigated.** Approximately 581 MB per million records, growing with request volume. This decision does not bound it; an implementation must.
- **Attribution remains impossible** for any decision whose session events have been pruned. Records written before an implementation lands cannot be retroactively attributed — the context was never captured.
- **Immutability is incidental.** Nothing prevents a future contributor from adding a mutator, and no test would object.
- **Evidence integrity and tamper-evidence are known residual gaps.** This decision establishes lifecycle and attribution requirements; it does not establish an integrity mechanism. The appropriate ownership and implementation mechanism remain subject to a future security-evidence decision.

  ```text
  ADR-028 answers          does not answer
      what must exist          how to prove cryptographically
      who owns it              that a record was not modified
      how long it lives
      what context it carries
      what state its meaning may depend upon
  ```

---

# Non-decisions

This ADR does **not**:

- change `AuditEvent`, `AuditService`, or any write path;
- add `session_id` or any other field to the audit record;
- introduce retention, archival or eviction for audit evidence;
- select or adopt a persistence technology;
- accept, revise or supersede ADR-016;
- alter behavioural telemetry, session-event retention, or findings;
- implement immutability enforcement, evidence-integrity or tamper-evidence guarantees.

Each is an implementation decision that this one constrains, to be taken and reviewed separately. The requirements above are requirements, not controls.

---

# Scope

This decision establishes what audit evidence is, who owns its lifecycle, what properties it must have, and where the current implementation falls short.

`M4-AUDIT` is therefore **decided but not implemented**. ADR-027's status table is updated to point at this decision rather than at an ADR-016 amendment. The `SESSION-LIFECYCLE` track is unaffected and remains open.
