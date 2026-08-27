from unittest.mock import MagicMock

import pytest

from app.agents.enterprise_agent import EnterpriseAgent
from app.agents.ollama_agent import OllamaAgent
from app.agents.simple_agent import SimpleAgent
from app.models.tool_invocation import ToolInvocation


def test_enterprise_agent_abc_contract() -> None:
    """Verify EnterpriseAgent cannot be instantiated directly without implementing abstract members."""
    with pytest.raises(TypeError):
        EnterpriseAgent()  # type: ignore[abstract]


def test_ollama_agent_contract_and_invocation() -> None:
    mock_provider = MagicMock()
    mock_provider.chat.return_value = {
        "tool_id": "file_read",
        "parameters": {"path": "test.txt"},
    }

    agent = OllamaAgent(provider=mock_provider, agent_id="custom-ollama-agent")
    assert agent.agent_id == "custom-ollama-agent"

    invocation = agent.invoke("read test.txt")
    assert isinstance(invocation, ToolInvocation)
    assert invocation.tool_id == "file_read"
    assert invocation.parameters == {"path": "test.txt"}
    mock_provider.chat.assert_called_once_with(OllamaAgent.SYSTEM_PROMPT, "read test.txt")


def test_simple_agent_contract_and_invocation() -> None:
    agent = SimpleAgent(agent_id="custom-simple-agent")
    assert agent.agent_id == "custom-simple-agent"

    invocation = agent.invoke("read demo.txt")
    assert isinstance(invocation, ToolInvocation)
    assert invocation.tool_id == "file_read"
    assert invocation.parameters == {"path": "demo.txt"}
