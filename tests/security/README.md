# Adversarial Security Regression Corpus

## Purpose

This corpus preserves the attack paths reproduced during the post-v0.16 security
review as durable, executable tests. Before it existed, the probes lived only in
an ephemeral scratchpad, which meant the project could assert that a fix had
landed but could not demonstrate that the corresponding attack had ever worked.

The corpus exists to support one workflow:

```text
Attack → Reproduce → Measure → Fix → Regression → Re-run → Evidence
```

It is intentionally capturing the **pre-remediation** security state. A passing
corpus does not mean the platform is secure; at this baseline it means the
documented weaknesses still behave exactly as the review recorded them.

## Baseline

| Item | Value |
|---|---|
| Commit | `74e8c51` |
| Branch | `main` |
| Backend tests at baseline | 372 passing |
| Ruff | clean |
| Review date | 2026-09-16 |

## Test classification

Three markers describe what each test is for. They are registered in
`pytest.ini`.

| Marker | Meaning | Behaviour today |
|---|---|---|
| `security_baseline` | Reproduces a confirmed weakness | Passes — it documents current behaviour |
| `security_invariant` | States the contract a hardening milestone must establish | `xfail(strict=True)` until the fix lands, then the `xfail` is removed and the marker is kept, so `-m security_invariant` lists every contract — pending and enforced |
| `security_regression` | Protects a control that is already correct | Passes and must keep passing |

`security_invariant` tests use `strict=True` deliberately. While the weakness
exists the test reports `xfail` and CI stays green. The moment a hardening
milestone makes one pass, pytest reports `XPASS` and **fails the suite**, which
forces the author to delete the marker and convert the test into a permanent
assertion. That transition is the evidence the milestone produced.

Baseline tests are the mirror image: when a fix lands they begin to fail, and
the failure is the signal to promote them.

### Two cases the markers do not signal

Both were found during M3 and are worth checking for in every milestone.

**A test that stays green while its claim goes stale.** The signal only fires when
a fix changes the asserted value. A test asserting something incidental — that a
helper is callable, or that a role still receives `200` — keeps passing while the
docstring around it becomes false, and the corpus then carries a claim nobody has
verified. M3 had three: the "the RBAC helper is unused" baseline, the
enforcement-visibility test, and the analyst scenario baseline. They have to be
found by reading, not by running.

**An invariant whose premise a later milestone removes.** An invariant states a
security property, not an immutable historical choice. M-3 asserted that `ANALYST`
must be refused scenario execution, which was correct while a scenario drove the
live pipeline; M2a sandboxed scenario execution and the escalation it guarded
against ceased to exist. The invariant was **rewritten rather than deleted**, to
state the permission together with the isolation that makes it safe, with the
reversal and its cause recorded in the test. Deleting it would have erased the
finding; keeping it unchanged would have preserved an implementation accident as
though it were a security property.

## Findings covered

| ID | Finding | Current status | Future invariant |
|---|---|---|---|
| H-1 | Committed default JWT secret | **Fixed** — invariants enforced | Missing secret fails closed; legacy-signed tokens rejected |
| H-2 | Management plane RBAC missing | **Fixed** — invariants enforced (ADR-025) | Every plane declares a role set; no plane admits a role it does not declare |
| H-3 | Risk posture resets on session rotation | **Fixed** — invariants enforced (ADR-024) | Posture cannot be relaxed by rotating an identifier |
| H-4 | Suspension is advisory | **Fixed** — invariants enforced (ADR-024) | `SUSPEND_AGENT` writes durable state |
| H-5 | Decision/execution divergence | **Fixed** — invariants enforced (ADR-023) | Executed parameters must match authorized parameters |
| H-6 | Detection evasion | Reproduced (1 of 11 detected) | Normalisation-addressable variants detected |
| M-1 | Prefix-based path containment | Reproduced | Canonical resolved-path containment |
| M-2 | API cannot express a resource | **Fixed** — invariants enforced (ADR-023) | API carries the authorized resource |
| M-3 | Scenario identity and role gate | **Fixed** — invariants enforced (ADR-025) | Operators may execute scenarios; execution stays isolated and its identity is sandbox-local |
| M-4 | Unbounded state growth | Reproduced | Bounded or evictable state |
| M-5 | Sessions not established or owned | **Fixed** — invariants enforced (ADR-024) | Server-established session ownership |
| M-6 | Unsalted parameter hashing | Reproduced | Keyed hashing where confidentiality is required |

## Controls established after the baseline

Some controls were introduced because a later milestone would otherwise turn an
accounting defect into a security problem. They are covered by
`security_regression` tests, which must keep passing.

| Control | Milestone | Regression test |
|---|---|---|
| A crossed denial threshold is counted once per session, so unrelated traffic cannot inflate cumulative risk into a false containment action | M2a | `test_denial_threshold_is_counted_once_per_session` |
| Scenario execution runs in an isolated pipeline and cannot mutate live agent, session, findings, risk, audit or telemetry state | M2a | `tests/services/test_scenario_sandbox.py` |
| One agent cannot contribute evidence to another agent's enforcement posture through a session it does not own (NEW-002, found by an independent review of M2b) | M2b | `test_invariant_another_agent_cannot_poison_a_session`, `tests/services/test_session_ownership.py` |
| No principal may execute as an agent other than itself, and a refused attempt leaves the target's findings, posture, session events and status unchanged | M3 | `TestImpersonationProducesNoEvidence` in `tests/api/test_plane_authorization.py` |
| A route narrows its plane's role set but can never widen it, so adding a route cannot grant access its plane does not already allow | M3 | `TestRouteNarrowingIsAnIntersection` |
| The scenario execution response exposes no agent identity, so adding attribution later cannot reintroduce a live one | M3 | `test_the_scenario_response_exposes_no_agent_identity` |
| Scenario permission and scenario isolation are separate controls: the sandbox is the boundary, and the sandbox-local identity removes a namespace collision within it rather than creating it. Widening the role gate and losing the sandbox are independently detected | M3 | `test_invariant_analyst_may_execute_scenarios_in_isolation`, `test_invariant_scenario_activity_is_never_attributed_to_a_live_agent` |
| A request refused at a trust boundary reports no risk assessment and no response, so a refusal cannot be read as a benign evaluation | M2b | `TestRefusalContract` |
| Runtime enforcement is one-way: no runtime path reinstates an agent or reopens grant issuance | M2b | `tests/services/test_enforcement_coordinator.py` |

## Execution

Run the whole suite:

```bash
.venv/bin/python -m pytest -q
```

Run only the corpus:

```bash
.venv/bin/python -m pytest tests/security -q
```

Select by classification:

```bash
.venv/bin/python -m pytest tests/security -m security_baseline -q
.venv/bin/python -m pytest tests/security -m security_invariant -q -rx
```

`-rx` prints the reason attached to each expected failure, which reads as a list
of the contracts still outstanding.

## Interpretation

* A green corpus at this baseline means the weaknesses are unchanged.
* An `XPASS` failure means a security contract started holding — promote the
  test by removing the `xfail` marker in the same PR that fixed it.
* A failing `security_baseline` test means current behaviour changed; confirm it
  changed for the intended reason before updating the expectation.
* A failing `security_regression` test means a control that used to work has
  regressed. Treat it as a defect, not as a test to update.

## Isolation rules

The corpus shares a process with the rest of the suite, so it follows three
rules to avoid disturbing existing tests:

1. Findings that involve mutable agent, session, risk or audit state build an
   isolated pipeline through the `build_runtime` fixture. `AgentService` has no
   writer, so suspending the shared `agent-1` could never be undone.
2. Tests that must exercise the HTTP boundary use read-only requests where
   possible, unique session identifiers, and delta assertions rather than
   absolute collection counts.
3. The corpus never calls `clear()` on a shared service.

## Not represented here

Three items from the review could not be expressed cleanly as tests without
changing production code, which is out of scope for this corpus:

* **H-1 startup failure.** Now enforced. `app.api.dependencies` resolves the
  signing key at import time, so the `ConfigurationError` raised by
  `get_jwt_secret_key()` *is* the application's startup failure, and the
  invariant asserts it directly.
* **H-4 positive control.** `PolicyEngine` correctly denies an already-suspended
  agent. That is covered by `tests/policy/test_policy_engine.py` and is not
  duplicated; the gap is the missing writer, which is what this corpus records.
* **ADR-015 documentation contradiction.** The delivery-semantics and
  backpressure sections of ADR-015 now describe different behaviour. That is a
  documentation fix and is deliberately left for a separate focused change.
