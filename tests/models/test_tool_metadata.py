from app.models.tool_metadata import ToolMetadata


def test_tool_metadata_creation() -> None:
    metadata = ToolMetadata(
        tool_id="file_read",
        name="File Read Tool",
        description="Read a file",
        category="filesystem",
        risk_level="medium",
        required_permissions=["file.read"],
    )

    assert metadata.tool_id == "file_read"
    assert metadata.category == "filesystem"
    assert metadata.risk_level == "medium"
    assert metadata.required_permissions == ["file.read"]

    schema = ToolMetadata.model_json_schema()

    assert (
        schema["properties"]["tool_id"]["description"]
        == "Unique tool identifier."
    )