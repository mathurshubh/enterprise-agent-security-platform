"""Controls on accumulation-dependent detection, at the trust boundary.

`EXCESSIVE_DENIALS` is the platform's only accumulation-dependent detector: it
reports an agent whose cumulative `DENY` decisions reach the threshold within the
evaluation window, where the three content rules fire on a single request each.
Detection that depends on accumulation can fail in two opposite directions, and a
test for either one alone is satisfied by the other's failure:

    reports the threshold when the behaviour occurred      under-detection
    reports nothing when it did not                        over-detection

Both matter as security properties. Under-detection is a missed containment
signal. Over-detection drives a legitimate agent toward containment on evidence
it did not earn, which the threat model records as a distinct attack.

The two negative controls are separate because they fail to different mutations:
one pins the threshold boundary, the other pins that only denials count toward
it. Each survives the mutation the other catches.

Exercised end to end rather than by calling `DetectionService` directly:

    POST /agents/{id}/execute -> JWT -> RuntimeService -> DetectionService
                              -> RiskService -> response

The detector's inputs are assembled from a request the caller controls, so a
service-level test would verify the rule in isolation from the path that feeds
it. These drive the mounted application with a real signed token, and assert on
the authoritative stores the production singletons own.

Scope. These controls pin what the detector does. They say nothing about which
aggregation unit it *should* use — that question is open, and no test here
presumes an answer to it.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import findings_service, risk_aggregator
from app.main import app
from app.models.jwt_claims import Role
from app.services.detection_service import EXCESSIVE_DENIAL_THRESHOLD
from tests.conftest import auth_headers, register_test_agent

client = TestClient(app)

# Crossed with margin, so a pass cannot come from sitting exactly on the boundary.
DENIAL_COUNT = EXCESSIVE_DENIAL_THRESHOLD * 2

# The agents below are approved for `file_read` only, making `directory_list` a
# deterministic authorization denial that carries no content finding. That keeps
# these controls measuring accumulation rather than the single-event rules.
DENIED_TOOL = "directory_list"
ALLOWED_TOOL = "file_read"


def agent_for(tag: str) -> tuple[str, dict]:
    """Register an agent dedicated to one control, and return it with its headers.

    Enforcement posture accumulates per agent across sessions (M2b), so a control
    that asserts a quiet agent must not share one with a control that deliberately
    drives it to a threshold.
    """
    agent_id = register_test_agent(f"accumulation-{tag}", approved_tools=[ALLOWED_TOOL])
    return agent_id, auth_headers(agent_id=agent_id, role=Role.AGENT)


def threshold_findings(agent_id: str) -> list:
    return [
        finding
        for finding in findings_service.list_findings(agent_id=agent_id)
        if finding.rule_name == "EXCESSIVE_DENIALS"
    ]


@pytest.mark.security_invariant
def test_invariant_accumulated_denials_produce_the_threshold_finding() -> None:
    """The documented behaviour produces the evidence it is documented to produce.

    Under-detection here is silent: the requests are denied either way, so the
    only observable difference is evidence that was never recorded and a posture
    that never moved.
    """
    agent_id, headers = agent_for("positive")

    for _ in range(DENIAL_COUNT):
        response = client.post(
            f"/agents/{agent_id}/execute",
            headers=headers,
            json={"session_id": "accumulation-positive", "tool_id": DENIED_TOOL},
        )

        assert response.status_code == 200
        assert response.json()["decision"] == "DENY", "the control must produce denials"

    assert threshold_findings(agent_id) != []
    assert risk_aggregator.get_posture(agent_id).risk_score > 0


@pytest.mark.security_regression
def test_denials_below_the_threshold_produce_no_finding() -> None:
    """Specificity at the boundary, as the counterpart to the control above.

    The two controls fail to opposite mutations, which is why neither is
    sufficient alone: weakening the threshold so the detector reports any denial
    is invisible to the positive control, and reaching the threshold one short is
    the case where that weakening first becomes observable.
    """
    agent_id, headers = agent_for("below")

    for _ in range(EXCESSIVE_DENIAL_THRESHOLD - 1):
        response = client.post(
            f"/agents/{agent_id}/execute",
            headers=headers,
            json={"session_id": "accumulation-below", "tool_id": DENIED_TOOL},
        )

        assert response.status_code == 200
        assert response.json()["decision"] == "DENY"

    assert threshold_findings(agent_id) == []
    assert risk_aggregator.get_posture(agent_id).risk_score == 0


@pytest.mark.security_regression
def test_allowed_traffic_does_not_accumulate_toward_the_threshold() -> None:
    """Only denials count toward the threshold.

    Asserted at the same volume as the positive control, because the decision
    filter is what separates the two: were it dropped, ordinary approved traffic
    would accumulate toward a containment signal it never earned.
    """
    agent_id, headers = agent_for("allowed")

    for _ in range(DENIAL_COUNT):
        response = client.post(
            f"/agents/{agent_id}/execute",
            headers=headers,
            json={"session_id": "accumulation-allowed", "tool_id": ALLOWED_TOOL},
        )

        assert response.status_code == 200
        assert response.json()["decision"] == "ALLOW"

    assert threshold_findings(agent_id) == []
    assert risk_aggregator.get_posture(agent_id).risk_score == 0
