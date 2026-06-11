from app.models.attack_scenario import AttackScenario
from app.models.risk_assessment import RiskLevel



def test_normal_agent_scenario():
    scenario = AttackScenario(
        scenario_id="scenario-1",
        name="Normal Agent Behavior",
        session_id="session-1",
        agent_id="agent-1",
        tool_sequence=["file_read"],
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    assert scenario.name == "Normal Agent Behavior"
    assert scenario.tool_sequence == ["file_read"]
    assert scenario.expected_findings == []
    assert scenario.expected_risk_level == RiskLevel.LOW



def test_excessive_denial_scenario():
    scenario = AttackScenario(
        scenario_id="scenario-2",
        name="Excessive Denials",
        session_id="session-2",
        agent_id="agent-1",
        tool_sequence=[
            "file_delete",
            "file_delete",
            "file_delete",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
    )

    assert scenario.expected_findings == [
        "EXCESSIVE_DENIALS"
    ]
    assert scenario.expected_risk_level == RiskLevel.MEDIUM
    assert len(scenario.tool_sequence) == 3



def test_mixed_behavior_scenario():
    scenario = AttackScenario(
        scenario_id="scenario-3",
        name="Mixed Agent Behavior",
        session_id="session-3",
        agent_id="agent-1",
        tool_sequence=[
            "file_read",
            "file_delete",
            "file_delete",
            "file_delete",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
    )

    assert scenario.tool_sequence[0] == "file_read"
    assert scenario.expected_findings == [
        "EXCESSIVE_DENIALS"
    ]
    assert scenario.expected_risk_level == RiskLevel.MEDIUM
