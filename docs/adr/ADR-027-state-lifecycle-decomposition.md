# ADR-027: State Lifecycle Decomposition (finding M-4)

**Status:** Accepted

**Date:** 2026-09-21

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Decision record. No production code changes.
- **Prerequisite: M5-B.6** — one decision below cannot be acted on until it lands.
- Decomposes finding M-4 from the post-v0.16 adversarial security review.

---

# Context

M-4 recorded that platform state grows without bound or eviction, and measured three in-memory stores together:

```text
[GROWTH] session events 0 -> 300; audit 0 -> 300; risk assessments=300
```

That measurement was correct. The grouping was not. Reviewing the three stores against the same seven questions — what is authoritative, who consumes it, is it security-authoritative or derived, can it be reconstructed, what security property depends on its availability, what happens if it is removed, and is bounded in-memory retention the right control — produced four different answers, because the stores have materially different security semantics.

The finding also missed a store. `M4-S` introduced terminal session tombstones after M-4 was written, and they are unbounded by design.

## What the stores actually are

Measured on `main` at `b94b8d6` (`tracemalloc`, 20,000 records):

| Store | Write semantics | Growth driver | Per record | Per 1M |
|:---|:---|:---|---:|---:|
| Session events | append + prune | requests within the detection horizon | 575 B | 549 MB |
| Risk assessments | **upsert** on `(session_id, agent_id)` | **unique sessions** | 1,176 B | 1,121 MB |
| Audit events | append-only | **requests** | 610 B | 581 MB |
| Terminal tombstones | insert, never removed | terminated sessions | — | unbounded |

Growth was measured directly rather than inferred. Ten requests in one session add **one** assessment and **ten** audit events; ten requests across ten sessions add ten of each. Five hundred sessions created, ended, and then pruned a year forward leave **500 tombstones and 0 session events**.

**The memory numbers do not justify eviction by themselves.** They identify where lifecycle pressure comes from. What may actually be removed is determined by security semantics, and those differ per store.

---

# Decision

M-4 is **decomposed, not closed**. It correctly identified unbounded state, but its original model grouped stores with materially different lifecycle and security semantics. The finding is therefore decomposed into event retention, derived-state materialization, audit evidence persistence, and session-identity lifecycle.

```text
M4 original finding
│
├── M4-EVENT          session-event retention            CLOSED (M5-B.4)
├── M5-B.6            partial-wiring response path       PREREQUISITE
├── M4-RISK           RiskAssessment materialization     Decision A
├── M4-AUDIT          audit evidence lifecycle           Decision B
└── SESSION-LIFECYCLE tombstone / identifier lifecycle   Decision C
```

Four stores, four answers:

```text
Session events      -> bounded retention
Risk assessments    -> do not retain independently; reconstruct
Audit events        -> durable evidence lifecycle
Tombstones          -> security identity lifecycle
```

| Track | Decision | Status | Next action |
|:---|:---|:---|:---|
| Session events | Detection-horizon retention | **Closed** — M5-B.4 | None in M4 |
| Runtime partial wiring | Remove the compatibility security path | **Prerequisite** | M5-B.6 |
| Risk assessments | No independent retention; derived state eligible for removal | **Decided** | Implement after M5-B.6 |
| Audit | Establish explicit evidence lifecycle ownership | **Decided** | Amend ADR-016 |
| Tombstones | Separate lifecycle decision required | **Open** | New session-lifecycle decision |

## Prerequisite — M5-B.6

`RuntimeService.execute` still contains a branch that derives the response action from the **session** `RiskAssessment` when `findings_service` or `agent_service` is absent, instead of from the agent's enforcement posture. Its own comment describes it as compatibility for partially constructed runtimes.

It is reachable. A runtime constructed with the now-mandatory `RiskAggregator` but without those two services produced `APPROVAL_REQUIRED` derived from the session assessment, with `enforcement_posture=None`.

This is the same class of defect [ADR-026](ADR-026-materialized-risk-projection-and-enforcement-epochs.md) addressed for the posture authority, on two other dependencies: **runtime authorization and response decisions must not silently change semantics because required security dependencies are absent.**

**M5-B.6 is not an M4 implementation.** It is tracked separately because it closes an existing runtime security-path defect exposed by the M4 lifecycle analysis; it is a prerequisite to applying Decision A safely, not part of the lifecycle decision itself.

It is recorded here rather than folded into Decision A because the two questions must be answered in order:

```text
Can this state participate in a security decision at all?     <- M5-B.6
        ↓
How long may this derived state live?                         <- Decision A
```

Answering the second while the first is open would classify risk assessments by their intended role rather than their actual one. Both production constructors — `app/api/dependencies.py` and `app/services/scenario_sandbox.py` — already supply both dependencies, so establishing the requirement at the security decision boundary excludes no runtime mode that exists.

## Decision A — Risk assessments are reconstructible derived state

**No independent retention policy is introduced.**

`RiskAssessment` is **derived materialized state**. It is not authoritative security state, and it is reconstructible from findings. It is deliberately not described as a cache: a cache implies an optimization private to its owner, whereas this store is exposed through the management API and consumed by the console, which is why its lifecycle needs deciding at all.

Four properties establish the decision, each measured rather than assumed:

1. **The materialized store does not provide historical assessment semantics.** Its upsert key `(session_id, agent_id)` replaces the prior assessment for that pair. No current consumer has therefore been identified that depends on assessment history from this store.
2. **The assessment is reconstructible from authoritative findings.** Verified: an assessment of `175 / CRITICAL / 4` rebuilt from the same findings produced `175 / CRITICAL / 4`, identical on every field except the observation timestamp. Scoring is a pure function of findings, and findings persist.
3. **No security consumer**, once M5-B.6 removes the partial-wiring path. Detection reads session events and findings; enforcement reads the agent posture projection. Neither consults an assessment.
4. **Reporting consumers only** — `/risk-assessments`, `/risk-assessments/{session_id}`, `/info`, and the console's `useRiskAssessments`. None requires a persistent materialized snapshot.

```text
Findings                          not:   Findings
   │                                        │
   ▼                                        ▼
deterministic reconstruction          RiskAssessment store
   │                                        │
   ▼                                        └── independently retained forever
RiskAssessment view
   ├── /risk-assessments
   ├── /risk-assessments/{id}
   └── /info
```

```text
no historical semantics
        +
no security consumer after M5-B.6
        +
reporting-only consumers
        +
deterministic reconstruction
        ↓
no independent retention requirement
        ↓
materialized store eligible for removal
```

**The materialized store is eligible for removal after M5-B.6**, and that removal is a separate implementation change. This ADR deliberately does not delete it: mixing a lifecycle conclusion with an API and performance change would obscure both.

## Decision B — Audit evidence needs an explicit owner

Audit is the store where memory pressure is real and eviction is not the answer. It grows strictly with request volume at 581 MB per million records, is not reconstructible, and is evidentiary: security invariant 4 requires an append-only record of every decision. Nothing *decides* on it, which makes its security role preservation rather than operation.

**[ADR-016](ADR-016-behavioral-event-store-and-data-model.md) does not currently own it.** This ADR states that explicitly because the opposite was assumed during review and turned out to be false: ADR-016 never mentions `AuditService` or `AuditEvent`, and its component ownership matrix covers telemetry, detection, risk and enforcement, not the audit log. The ADRs that do mention audit (008, 009, 014, 015, 022) all consume it; none owns its lifecycle. **No ADR owns audit persistence today.**

What ADR-016 does supply is the model audit requires — a three-tier Operational → Compliance → Archival architecture whose lifecycle invariant is that *"event deletion is handled via lifecycle partition dropping in cold storage, never via individual record mutation."* That is the correct shape for evidence: bounded operational memory without destroying the record.

**Decision: ADR-016 is the appropriate architectural home, and will be amended to establish the lifecycle model for audit evidence and to define its relationship to the audit event plane.** A second persistence architecture beside it is rejected: fragmented persistence ownership is the condition this programme has been removing elsewhere.

The boundary between this ADR and that amendment is deliberate:

```text
ADR-027   identifies the ownership gap
    ↓     decides ADR-016 is the appropriate architectural home
ADR-016 amendment
    ↓     defines the actual audit lifecycle semantics
```

ADR-027 does not define audit lifecycle details, and does not itself confer ownership. Until the amendment exists, audit persistence remains unowned.

**The first question is preservation, not expiry.** "Audit lifecycle" must not be read as "what TTL should audit events have"; it is "how is audit evidence preserved over its required lifecycle, while operational memory stays bounded". Audit belongs to the evidentiary and compliance plane, not to session telemetry, and retention and archival are distinct concerns within it.

The amendment must establish, before any implementation:

- whether `AuditEvent` is authoritative evidence;
- the evidence-preservation requirement and what "complete" means for it;
- the boundary between operational and durable storage;
- retention and archival tiers;
- deletion semantics, consistent with partition-drop rather than record mutation;
- recovery and reconstruction guarantees;
- lifecycle ownership;
- the relationship between `AuditService` and the persistence layer.

## Decision C — Tombstones are an identity problem, not a retention problem

Terminal session tombstones share a growth driver with risk assessments — session identifier cardinality — and nothing else. **Cardinality is not a sufficient basis for assigning lifecycle semantics.** Grouping them was considered and rejected, because their security semantics are opposite:

| | Risk assessment | Terminal tombstone |
|:---|:---|:---|
| Authority | derived, non-authoritative | **security-authoritative** |
| History | latest value only | terminal, permanent |
| Reconstructible | yes, from findings | **no** |
| If removed | rebuild on read | a terminated identifier can be **rebound** |

The security property is explicit: **tombstone lifecycle must preserve terminal ownership finality and prevent identifier reuse from creating ambiguity or rebinding.** That is why tombstones cannot simply inherit session-event retention — the retention policy governing events is derived from a detection horizon, which has no bearing on how long an identifier must remain unusable.

`M4-S-5` retains tombstones for process lifetime and `M4-S-6` forbids discarding them under capacity pressure, both correctly: evicting one would undo the terminal ownership finality that finding M-5 established (ADR-024).

The consequence is that session-event retention bounds the events and leaves one tombstone per session forever — **the session plane is not bounded; its unbounded component moved from events to tombstones.** That is a sound trade, and it leaves a real architectural question that retention cannot answer:

> How can terminal session ownership remain final without requiring process-lifetime in-memory tombstones?

**Decision: record this as its own architectural follow-up, `SESSION-LIFECYCLE`, not as part of M4-RISK.** Existing process-lifetime tombstone behaviour remains authoritative until that design exists.

Server-issued identifiers are an architectural **input** to that follow-up decision, because the threat model already identifies identifier reuse and rebinding as relevant to the ownership-finality property. This ADR does not establish them as the solution.

---

# Non-decisions

ADR-027 is a decomposition and decision record, not an implementation record. It does **not**:

- remove the `RiskAssessment` materialized store;
- define the final lifecycle or archival policy for audit evidence;
- confer audit lifecycle ownership, which the ADR-016 amendment must do;
- define the lifecycle mechanism for session tombstones;
- establish server-issued session identifiers as the solution to tombstone lifecycle;
- change session-event retention established by M5-B.4;
- implement M5-B.6;
- change runtime authorization or response semantics.

Each architectural direction recorded above is a direction. None of them is an implemented control.

---

# Alternatives Considered

## Option A: One retention mechanism across all state

**Considered because** it is the original M-4 model, and a single mechanism is simpler to build and reason about than four.

**Rejected because** a common retention policy would conflate operational telemetry, derived reporting state, evidentiary state and terminal ownership state. Audit cannot be evicted without weakening security invariant 4, and tombstones cannot be evicted without undoing terminal ownership finality, so a universal mechanism would be either unusable on both or quietly weakening to both.

## Option B: Give risk assessments their own retention policy

**Considered because** assessments are the largest per-record store measured, at 1,121 MB per million, and a retention policy is the mechanism M-4 implied.

**Rejected because** the store provides no historical semantics and is exactly reconstructible, so a retention policy would govern how long to keep derived material that need not be kept at all. Its only justification would be a memory number, which the organizing principle above rules out as a basis.

## Option C: Close M-4 because session events are now bounded

**Considered because** M5-B.4 bounded and verified one of the stores M-4 measured, and the finding is old.

**Rejected because** one of four stores is bounded. Marking the finding resolved would leave audit, assessments and tombstones unaddressed under a closed finding — the false milestone closure ADR-026 was written to prevent.

## Option D: Fold tombstones into M4-RISK because they share a growth driver

**Considered because** the shared driver is real: both stores grow with session identifier cardinality, and a single decision addressing that driver would cover both.

**Rejected because** the two stores have different authority, reconstructibility and security semantics despite sharing a cardinality driver. Grouping by growth driver rather than by security semantics is the same error M-4 made, and it would obscure the actual question, which is identity finality rather than storage volume.

## Option E: Treat ADR-016 as already owning audit

**Considered because** ADR-016 is the platform's persistence architecture and already defines a tiered retention model that fits evidence.

**Rejected because** repository review found no ADR statement assigning audit persistence or lifecycle ownership to ADR-016. It covers the Behavioral Event Store and never mentions `AuditService` or `AuditEvent`. Asserting ownership that does not exist would leave audit persistence unowned while appearing addressed.

## Option F: Establish a separate audit persistence architecture

**Considered because** audit evidence has different consumers and different compliance semantics from behavioural telemetry, which could justify its own architecture.

**Rejected because** the platform would then hold two persistence architectures with overlapping concerns and divided ownership. Amending ADR-016 keeps one.

---

# Consequences

## Positive

- Each store is governed by a mechanism matched to its security semantics rather than to its memory footprint.
- A prerequisite was identified before implementation rather than discovered during it, which is the outcome the review existed to produce.
- A fourth unbounded store, introduced after M-4 was written, is now recorded rather than unnoticed.
- Audit persistence ownership is named as absent, which is actionable, instead of assumed present, which is not.

## Negative

- Four tracks where the finding described one, with more coordination than a single retention milestone.
- Risk assessments and tombstones continue to grow with session cardinality until Decision A is implemented and `SESSION-LIFECYCLE` is designed.
- Audit growth remains unbounded in the current in-memory implementation until the ADR-016 lifecycle decision is implemented. The measured footprint of approximately 581 MB per million records demonstrates that this is an operational scalability concern, but does not by itself establish a production capacity threshold: available process memory, deployment limits, event rate, retention period and the eventual persistence architecture are all unestablished.

## Residual Risks

- **Operational memory remains unbounded in three of four stores.** This ADR decides how each must be addressed; none is addressed by it.
- **Session identifier cardinality is caller-controlled.** Callers still choose identifiers, so the growth driver behind two stores is externally influenced. Server-issued identifiers remain the target model.
- **Decision A's conclusion is conditional.** It holds only once M5-B.6 removes the partial-wiring response path. Implementing it earlier would act on a classification that is not yet true.

---

# Scope

This decision record decomposes finding M-4 and records the lifecycle direction for each store it covers, plus the one it did not.

It implements nothing. It does not remove the materialized assessment store, amend ADR-016, design session-identifier lifecycle, change retention semantics, or alter `AuditService`. Each is recorded as its own reviewable change, and M5-B.6 precedes the first of them.
