# Session and Execution Identity — Investigation Record

**Status:** Evidence / Investigation — **no architectural decision made**

**Date:** 2026-09-23

**Baseline:** `main` at `7a22020`, dependency-aligned, 851 passed / 7 xfailed

**Authors:**
- Shubhankar Mathur

> This document is **non-normative**. It records evidence gathered by read-only
> investigation. It does not decide anything, does not supersede any ADR, and no
> production code, session lifecycle, audit schema or test was changed to produce it.
> The eventual `SESSION-LIFECYCLE` design should reference this record rather than
> re-deriving it; it should not treat any statement here as a decision.

---

## Why this investigation happened

[ADR-027](../adr/ADR-027-state-lifecycle-decomposition.md) decomposed finding M-4 and left `SESSION-LIFECYCLE` open, framed as *"how can terminal session ownership remain final without requiring process-lifetime in-memory tombstones?"* A correction to that ADR established the framing was wrong: the terminal-session machinery has no production path, so finality guards a state the platform never enters.

That reopened a more basic question — what is a session? — and four investigations followed.

---

## Evidence chain

| | Established | Method |
|:---|:---|:---|
| **#1** | `AuditEvent` cannot distinguish two executions sharing a `session_id`. All fields identical except the per-event UUID and timestamp. Audit evidence has **no independent execution identity**. | two session planes writing one audit store |
| **#2** | `request_id` is **per-request**, minted inside `execute()` after `trace_id` is read, so it is neither execution-scoped nor propagated. `ScenarioExecution.execution_id` is the platform's only execution-scoped identity. | code trace |
| **#3** | `session_id` reuse **already occurs in production** on the scenario path. `execution_id` never leaves the scenario layer and reaches no security store. | measured: two runs of TOOL-002 |
| **#4** | The documented forensic unit **is the session**: `(session_id, sequence_number)` replay index, `/sessions/:id` investigation surface. Stated in five ADRs. | document review |

### Investigation #1 — audit ambiguity under identifier reuse

One shared `AuditService`, two independent session planes — what a bounded session lifetime or a process restart produces for a reissued identifier:

```text
audit records under session 'S': 4
  1. event_id=evt-cc6f2f1e…  session=S  agent=agent-1  tool=file_read  decision=ALLOW
  2. event_id=evt-fe649af9…  session=S  agent=agent-1  tool=file_read  decision=ALLOW
  3. event_id=evt-63dc3d57…  session=S  agent=agent-1  tool=file_read  decision=ALLOW
  4. event_id=evt-51ddc2af…  session=S  agent=agent-1  tool=file_read  decision=ALLOW
```

An observer cannot reconstruct which events belong to which execution without timestamp proximity or external knowledge. `event_id` identifies an **event**, not an execution.

### Investigation #2 — is `request_id` the execution boundary?

```python
trace_id = context.request_id if context is not None else None   # line 540
...
if context is None:
    context = RuntimeContext(request_id=f"req-{uuid.uuid4()}", …)  # line 627
```

`RuntimeContext` is constructed in one production place — inside `execute()`, only when no context was supplied. The HTTP runtime route supplies none. So `request_id` is per-request, created late, and **`trace_id` is `None` for every production request**. See the separate finding below.

### Investigation #3 — `ScenarioExecution.execution_id` semantics

```python
execution_id = f"exec-{uuid.uuid4()}"                    # fresh per run
session_id   = f"scenario-run-{scenario.scenario_id}"    # deterministic
```

Measured, two runs of the same scenario:

```text
execution_id  A=exec-f85f0a19…   B=exec-ee3f0cd3…    differs
session_id    A=scenario-run-TOOL-002
              B=scenario-run-TOOL-002                 reused
```

`execution_id` is execution-scoped and shared by all requests in a run **by construction**, but is passed to no runtime call and reaches no session, finding or audit record. Architecturally it appears only in [ADR-012](../adr/ADR-012-scenario-execution-domain-model.md) as a domain field; **no ADR treats it as an authoritative execution identity**.

### Investigation #4 — the forensic requirement

| ADR | Language |
|:---|:---|
| ADR-016 | *"Session Index (`session_id`, `sequence_number`): Primary index for session ordering and deterministic replay"*; *"Reading a session's stored events in sequence order enables a forensic harness to reconstruct the exact system state…"* |
| ADR-017 | *"forensic session replay"* produces identical findings |
| ADR-019 | forensic replay produces identical enforcement decisions |
| ADR-022 | *"Session Investigation Workspace (`/sessions/:id`)… the primary forensic environment"* |

The platform's forensic model is **session-anchored**. The requirement for session-identifier unambiguity originates here, not in the audit schema.

### ADR-016 review input

A later read-only pass over [ADR-016](../adr/ADR-016-behavioral-event-store-and-data-model.md) found the uniqueness requirement is **already written into the proposal** rather than something this investigation adds.

```text
ADR-016 proposal assumption
    session initialization establishes a unique session_id   (§2, Behavioral Session Model)

Current platform evidence
    session identifiers have no platform-wide non-reuse guarantee   (Investigation #3)

Architectural question
    whether session_id must ultimately be the forensic / replay unit
    UNDECIDED
```

ADR-016 §2 states that `SESSION_STARTED` *"establishes a unique `session_id`"*, alongside a `SESSION_STARTED` / `SESSION_ENDED` lifecycle the platform does not implement. Its proposed replay index, `(session_id, sequence_number)`, sits under *Indexing Strategy* and elaborates a decision-level capability; it is **proposed, not normative**, within an ADR whose own status is `Proposed`.

The discrepancy this records is therefore between **an assumption in a proposed ADR** and **currently established platform semantics** — not a requirement imposed on that ADR from outside.

This is an input to the eventual ADR-016 review. It does **not** establish that `session_id` must be the replay-unit identifier, does **not** assert that the current platform has a replay vulnerability — no replay capability exists — and does **not** decide the mechanism by which unambiguity would be achieved.

---

## Architectural requirements identified

**R1 — The forensic unit must be unambiguously identifiable.** This is the primitive requirement.

**R2 — Non-reuse of `session_id` is *one mechanism* for satisfying R1, not the requirement itself.** Recorded this way deliberately: stating it as the requirement would foreclose alternatives before they are evaluated — a composite replay key, an epoch discriminator, an immutable forensic-unit identifier distinct from the caller-supplied one, or a different replay-unit model.

**R3 — Execution identity is a separate concept** from session identity, and exists today only on the scenario path.

**R4 — Audit may eventually need execution attribution.** Open, and dependent on whether reconstruction is session-anchored or execution-anchored.

**R5 — Replay and audit are related but distinct.**

```text
Behavioral Event Store              Audit Store
    └── forensic / replay model         └── authoritative decision evidence
        └── session identity                └── execution / request attribution
```

Both contain `session_id`. **That does not mean they need identical identity semantics**, and assuming they do would introduce exactly the coupling this investigation exists to avoid. ADR-016 defines replay over telemetry envelopes, not over `AuditEvent` — they are different stores with different guarantees.

---

## Options against the requirements

| | R1 unambiguous unit | R3 execution identity | R4 audit attribution | Cost |
|:---|:---:|:---:|:---:|:---|
| Session IDs never reused | ✓ | ✗ | ✗ | permanent state, or uniqueness by construction |
| Server-issued session IDs | collision only | ✗ | ✗ | does not prevent resubmission of an old identifier |
| `execution_id` propagated to audit | ✗ | ✓ | ✓ | no execution concept exists on the runtime path |
| Composite replay key (`session_id` + epoch) | ✓ | ✗ | partial | changes the replay index ADR-016 specifies |
| Bounded audit retention | partial | ✗ | ✗ | orthogonal; open in ADR-028 |

**No single option satisfies R1 and R3 together.** That is itself a finding: they are different problems requiring different mechanisms.

---

## Maturity caveat

Every capability generating R1 is **unimplemented**:

```text
ADR-016  Behavioral Event Store    Proposed, no code in the repository
ADR-022  Session Investigation      not built
         replay harness             does not exist
```

R1 is therefore **architecturally committed intent, not an operating invariant**. Nothing performs session-anchored forensic replay today, and the scenario-path reuse below is real but inert.

This governs prioritization. The proportionate response may be to record the constraint so that whoever implements the event store knows an unambiguous session unit is presumed — rather than changing session lifecycle now to serve a capability that does not exist.

---

## The one actionable defect today

`session_id = f"scenario-run-{scenario.scenario_id}"` is deterministic, for no stated reason, so every re-run of a scenario reuses the identifier.

It is currently harmless because M2a's sandbox gives each run its own `SessionService` **and** its own `AuditService` (ADR-013). The isolation introduced to stop scenarios mutating live state is what masks the collision. **If scenario evidence were ever consolidated into a shared store** — which an audit persistence design might reasonably want, since scenario runs are security-relevant activity — `/sessions/scenario-run-X` would address every run of that scenario, conflated.

**This change is not as small as it looks.** Dependencies on the deterministic identifier, measured:

| Location | Kind |
|:---|:---|
| `app/services/scenario_runner_service.py:72` | the generator itself |
| `tests/services/test_scenario_runner_service.py` ×4 | 3 assertions on hardcoded `scenario-run-{id}` literals, 1 setup value |
| `tests/services/test_scenario_sandbox.py` ×2 | isolation snapshot values on a hardcoded literal, compared later |

No production code outside the generator and no frontend code depends on it. **Six test references** do — three on `assert` lines, one a constructed setup value, two inside a before/after isolation snapshot — and all six would need to read the identifier from the execution result instead of hardcoding it. Any such change should carry targeted regression coverage for scenario session isolation and attribution rather than relying on the existing assertions being updated correctly.

---

## Open questions

1. **Does forensic reconstruction need grouping, or per-event distinguishability?** Investigation #4 established the architecture *assumes* grouping, but no operating consumer exercises it, so the assumption has never been tested against a real investigation workflow.
2. **Must the forensic unit be the session?** R1 requires an unambiguous unit; the architecture currently names the session as that unit. Whether that remains the right choice is undecided.
3. **Does the runtime path need an execution concept at all**, or is the session sufficient for direct `POST /agents/{id}/execute` traffic?
4. **Multi-process ownership.** Two processes would independently believe they own the same identifier; no shared state exists. Unaddressed by any option above.

---

## Separate finding — telemetry correlation is not populated

**`trace_id` is `None` for every production request**, because `RuntimeContext` is constructed after `trace_id` is read and no caller supplies one. The correlation field ADR-015's design relies on is not populated on the production runtime path.

This is recorded here only because Investigation #2 encountered it. **It is deliberately excluded from the session and audit analysis above**, intersects [ADR-015](../adr/ADR-015-behavioral-telemetry-architecture.md), and requires its own investigation. Mixing it into this decision would make the session and audit architecture review less precise.

---

## What was not done

No production code was changed. No session lifecycle, audit schema, detection, risk or test was modified. No ADR was created, amended or superseded. Every measurement in this document was taken by temporarily mutating a file, capturing the result, and restoring it — the working tree was verified clean and the suite green after each.

Two coverage gaps found during the earlier session semantics review remain open and are independent of any lifecycle decision:

- the `agent_id` partition in `EXCESSIVE_DENIALS` has no corpus invariant;
- the risk agent-scope guards have no corpus invariant, and the rebuild-path filter survives removal with zero failures.
