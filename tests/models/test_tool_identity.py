from app.models.tool_identity import ToolIdentity


def test_tool_identity_creation() -> None:
    identity = ToolIdentity(
        tool_id="file_read",
        name="File Read",
        description="Reads files",
    )

    assert identity.tool_id == "file_read"
    assert identity.name == "File Read"
    assert identity.version == "1.0.0"
    assert identity.description == "Reads files"