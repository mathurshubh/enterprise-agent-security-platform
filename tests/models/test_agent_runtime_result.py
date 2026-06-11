from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseType,
)


def test_agent_runtime_result_creation() -> None:
    result = AgentRuntimeResult(
        decision="ALLOW",
        response_type=ResponseType.MONITOR,
        output="notes",
    )

    assert result.decision == "ALLOW"
    assert (
        result.response_type
        == ResponseType.MONITOR
    )
    assert result.output == "notes"