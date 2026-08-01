from typing import Protocol

import pytest
from pydantic import ValidationError

from app.models.runtime_context import RuntimeContext, ToolInvocationContext
from app.registry.tool_registry import ToolRegistry
from app.runtime.contracts import (
    ToolExecutorProtocol,
    ToolFactoryProtocol,
    ToolRegistryProtocol,
)


def test_runtime_context_instantiation_and_fields():
    context = RuntimeContext(
        session_id="sess-123",
        request_id="req-456",
        user_id="user-789",
        principal="sec-admin",
        authenticated_agent="agent-1",
        execution_metadata={"env": "prod"},
    )

    assert context.session_id == "sess-123"
    assert context.request_id == "req-456"
    assert context.user_id == "user-789"
    assert context.principal == "sec-admin"
    assert context.authenticated_agent == "agent-1"
    assert context.execution_metadata == {"env": "prod"}


def test_runtime_context_is_immutable():
    context = RuntimeContext(
        session_id="sess-123",
        request_id="req-456",
        user_id="user-789",
        principal="sec-admin",
        authenticated_agent="agent-1",
    )

    with pytest.raises((ValidationError, TypeError)):
        context.session_id = "sess-mutated"


def test_tool_invocation_context_structure():
    runtime_context = RuntimeContext(
        session_id="sess-100",
        request_id="req-200",
        user_id="user-300",
        principal="principal-400",
        authenticated_agent="agent-1",
    )

    inv_context = ToolInvocationContext(
        runtime_context=runtime_context,
        tool_id="file_read",
        resource="/etc/hosts",
        parameters={"path": "/etc/hosts"},
    )

    assert inv_context.tool_id == "file_read"
    assert inv_context.resource == "/etc/hosts"
    assert inv_context.parameters == {"path": "/etc/hosts"}
    assert inv_context.runtime_context.session_id == "sess-100"


def test_runtime_contracts_protocols():
    registry = ToolRegistry()
    assert isinstance(registry, ToolRegistryProtocol)
    assert issubclass(ToolRegistryProtocol, Protocol)
    assert issubclass(ToolFactoryProtocol, Protocol)
    assert issubclass(ToolExecutorProtocol, Protocol)
