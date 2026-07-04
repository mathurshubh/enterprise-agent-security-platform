import pytest
from pydantic import ValidationError

from app.models.attack_scenario import AttackScenario
from app.models.attack_scenario import ScenarioCategory
from app.models.finding import Severity
from app.models.response_action import ResponseType
from app.models.risk_assessment import RiskLevel



def test_attack_scenario_asset_creation():
    scenario = AttackScenario(
        scenario_id="attack-001",
        name="Prompt Injection Tool Override",
        description="Retrieved content attempts to force a tool call.",
        category=ScenarioCategory.PROMPT_INJECTION,
        severity=Severity.HIGH,
        user_prompt=(
            "Summarize this page. The page says to ignore "
            "previous instructions."
        ),
        expected_tool_id="file_read",
        expected_detection="PROMPT_INJECTION_ATTEMPT",
        expected_risk=RiskLevel.HIGH,
        expected_response=ResponseType.REQUIRE_APPROVAL,
        tags=("prompt-injection", "tool-abuse"),
        references=("docs/security/threat-model.md",),
    )

    assert scenario.category == ScenarioCategory.PROMPT_INJECTION
    assert scenario.scenario_version == "1.0"
    assert scenario.severity == Severity.HIGH
    assert scenario.expected_tool_id == "file_read"
    assert scenario.expected_tool == "file_read"
    assert scenario.expected_detection == "PROMPT_INJECTION_ATTEMPT"
    assert scenario.expected_risk == RiskLevel.HIGH
    assert scenario.expected_response == ResponseType.REQUIRE_APPROVAL
    assert scenario.tags == ("prompt-injection", "tool-abuse")


def test_attack_scenario_is_immutable():
    scenario = AttackScenario(
        scenario_id="attack-001",
        name="Immutable Scenario",
    )

    with pytest.raises(ValidationError):
        scenario.name = "Changed"


def test_legacy_expected_tool_alias_is_supported():
    scenario = AttackScenario(
        scenario_id="attack-001",
        name="Alias Scenario",
        expected_tool="file_read",
    )

    assert scenario.expected_tool_id == "file_read"
    assert scenario.expected_tool == "file_read"


def test_runtime_replay_fields_are_security_content_only():
    scenario = AttackScenario(
        scenario_id="scenario-2",
        name="Excessive Denials",
        tool_sequence=[
            "file_delete",
            "file_delete",
            "file_delete",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
    )

    assert scenario.expected_findings == ("EXCESSIVE_DENIALS",)
    assert scenario.expected_risk == RiskLevel.MEDIUM
    assert scenario.expected_risk_level == RiskLevel.MEDIUM
    assert len(scenario.tool_sequence) == 3


def test_runtime_state_fields_are_rejected():
    with pytest.raises(ValidationError):
        AttackScenario(
            scenario_id="scenario-2",
            name="Runtime State",
            session_id="session-2",
        )



def test_scenario_requires_id_and_name():
    with pytest.raises(ValidationError):
        AttackScenario(
            scenario_id="",
            name="Missing ID",
        )
