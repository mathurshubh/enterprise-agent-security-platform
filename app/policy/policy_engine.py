from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.tool import Tool, ToolRiskLevel


class PolicyEngine:
    PROTECTED_RESOURCES = {
        "secrets.txt",
    }

    def evaluate(
        self,
        agent: Agent,
        tool: Tool,
        resource: str | None = None,
    ) -> Decision:
        if agent.status in {
            AgentStatus.SUSPENDED,
            AgentStatus.DISABLED,
        }:
            return Decision.DENY

        if (
            agent.risk_tier == RiskTier.LOW
            and tool.risk_level in {
                ToolRiskLevel.HIGH,
                ToolRiskLevel.CRITICAL,
            }
        ):
            return Decision.DENY

        if (
            tool.tool_id == "file_read"
            and resource in self.PROTECTED_RESOURCES
        ):
            return Decision.DENY

        if tool.risk_level == ToolRiskLevel.CRITICAL:
            return Decision.APPROVAL_REQUIRED

        return Decision.ALLOW