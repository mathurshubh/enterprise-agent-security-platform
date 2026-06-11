import pytest

from app.services.simple_agent import SimpleAgent


def test_read_file_query_returns_file_read_tool() -> None:
    agent = SimpleAgent()

    invocation = agent.decide_tool(
        "read notes.txt"
    )

    assert invocation.tool_id == "file_read"
    assert invocation.parameters == {
        "path": "notes.txt",
    }


@pytest.mark.parametrize(
    "query",
    [
        "list files",
        "show files",
    ],
)
def test_directory_queries_return_directory_tool(
    query: str,
) -> None:
    agent = SimpleAgent()

    invocation = agent.decide_tool(query)

    assert (
        invocation.tool_id
        == "directory_list"
    )
    assert invocation.parameters == {
        "path": ".",
    }


def test_unsupported_query_raises_error() -> None:
    agent = SimpleAgent()

    with pytest.raises(
        ValueError,
        match="Unsupported query",
    ):
        agent.decide_tool(
            "send an email"
        )
