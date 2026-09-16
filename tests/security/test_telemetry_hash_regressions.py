"""M-6 — Telemetry parameter hashing is stable correlation, not confidentiality.

Review evidence (74e8c51)::

    [WEAKNESS] parameter_hash brute-forced from a four-entry dictionary
               -> recovered 'secrets.txt'

``compute_parameter_hash`` is an unsalted SHA-256 over canonicalised JSON. That
is exactly right for correlating identical invocations, and it does not prevent
offline guessing when the parameter space is small — which is the normal case
for file paths and tool arguments.

This is not a cryptographic break. SHA-256 behaves correctly here; the mismatch
is between the primitive chosen and the data-minimisation property the model
docstring claims.
"""

import pytest

from app.models.telemetry.behavioral_event import compute_parameter_hash

CANDIDATE_PARAMETERS = ["notes.txt", "secrets.txt", "config.txt"]


def _recover(target_hash: str) -> str | None:
    for candidate in CANDIDATE_PARAMETERS:
        if compute_parameter_hash({"path": candidate}) == target_hash:
            return candidate
    return None


@pytest.mark.security_regression
def test_parameter_hash_is_order_independent() -> None:
    """Canonicalisation works as designed: key order does not change the digest."""
    assert compute_parameter_hash({"path": "a", "mode": "r"}) == compute_parameter_hash(
        {"mode": "r", "path": "a"}
    )


@pytest.mark.security_baseline
def test_baseline_low_entropy_parameter_is_recoverable_from_a_small_dictionary() -> None:
    """A three-entry guess list recovers the hashed parameter."""
    target = compute_parameter_hash({"path": "secrets.txt"})

    assert _recover(target) == "secrets.txt"


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="M-6: hashing is unsalted, so dictionary recovery succeeds; keyed hashing is not implemented",
)
def test_invariant_parameter_hash_resists_dictionary_recovery() -> None:
    target = compute_parameter_hash({"path": "secrets.txt"})

    assert _recover(target) is None
