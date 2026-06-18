from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseType,
)
from app.services.agent_runtime_service import (
    AgentRuntimeService,
)


def test_execute_read_query() -> None:
    service = AgentRuntimeService()

    result = service.execute(
        "read notes.txt"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "ALLOW"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert isinstance(
        result.output,
        str,
    )


def test_execute_protected_resource_query() -> None:
    service = AgentRuntimeService()

    result = service.execute(
        "read secrets.txt"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "DENY"

    assert result.output is None


def test_execute_list_query() -> None:
    service = AgentRuntimeService()

    result = service.execute(
        "list files"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "ALLOW"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert isinstance(
        result.output,
        list,
    )

    assert all(
        isinstance(item, str)
        for item in result.output
    )



def test_execute_unsupported_query() -> None:
    service = AgentRuntimeService()

    result = service.execute(
        "send email"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "DENY"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert result.output is None
