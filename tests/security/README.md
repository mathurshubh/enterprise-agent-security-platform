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

## Findings covered

| ID | Finding | Current status | Future invariant |
|---|---|---|---|
| H-1 | Committed default JWT secret | **Fixed** — invariants enforced | Missing secret fails closed; legacy-signed tokens rejected |
| H-2 | Management plane RBAC missing | Reproduced | Role gating plus caller scoping |
| H-3 | Risk posture resets on session rotation | Reproduced | Posture cannot be relaxed by rotating an identifier |
| H-4 | Suspension is advisory | Reproduced | `SUSPEND_AGENT` writes durable state |
| H-5 | Decision/execution divergence | **Fixed** — invariants enforced (ADR-023) | Executed parameters must match authorized parameters |
| H-6 | Detection evasion | Reproduced (1 of 11 detected) | Normalisation-addressable variants detected |
| M-1 | Prefix-based path containment | Reproduced | Canonical resolved-path containment |
| M-2 | API cannot express a resource | **Fixed** — invariants enforced (ADR-023) | API carries the authorized resource |
| M-3 | Scenario identity and role gate | Reproduced | Caller identity preserved and role enforced |
| M-4 | Unbounded state growth | Reproduced | Bounded or evictable state |
| M-5 | Sessions not established or owned | Reproduced | Server-established session ownership |
| M-6 | Unsalted parameter hashing | Reproduced | Keyed hashing where confidentiality is required |

## Controls established after the baseline

Some controls were introduced because a later milestone would otherwise turn an
accounting defect into a security problem. They are covered by
`security_regression` tests, which must keep passing.

| Control | Milestone | Regression test |
|---|---|---|
| A crossed denial threshold is counted once per session, so unrelated traffic cannot inflate cumulative risk into a false containment action | M2a | `test_denial_threshold_is_counted_once_per_session` |
| Scenario execution runs in an isolated pipeline and cannot mutate live agent, session, findings, risk, audit or telemetry state | M2a | `tests/services/test_scenario_sandbox.py` |

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
