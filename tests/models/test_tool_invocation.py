from app.models.tool_invocation import (
    ToolInvocation,
)


def test_tool_invocation_creation():
    invocation = ToolInvocation(
        tool_id="file_read",
        parameters={
            "path": "notes.txt",
        },
    )

    assert invocation.tool_id == "file_read"
    assert invocation.parameters == {
        "path": "notes.txt",
    }