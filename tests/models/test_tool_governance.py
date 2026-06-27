from app.models.tool_risk_level import ToolRiskLevel
from app.models.tool_governance import ToolGovernance


def test_tool_governance_defaults() -> None:
    governance = ToolGovernance(
        risk_level=ToolRiskLevel.LOW,
    )

    assert governance.risk_level == ToolRiskLevel.LOW
    assert governance.required_permissions == []
    assert governance.owner is None
    assert governance.approval_required is False


def test_tool_governance_custom_values() -> None:
    governance = ToolGovernance(
        risk_level=ToolRiskLevel.HIGH,
        required_permissions=["files:read"],
        owner="security-team",
        approval_required=True,
    )

    assert governance.risk_level == ToolRiskLevel.HIGH
    assert governance.required_permissions == ["files:read"]
    assert governance.owner == "security-team"
    assert governance.approval_required is True