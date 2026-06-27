from app.models.tool_capability import ToolCapability


def test_tool_capability_defaults() -> None:
    capability = ToolCapability(
        category="filesystem",
    )

    assert capability.category == "filesystem"
    assert capability.reads_files is False
    assert capability.writes_files is False
    assert capability.network_access is False
    assert capability.shell_access is False


def test_tool_capability_flags() -> None:
    capability = ToolCapability(
        category="filesystem",
        reads_files=True,
        writes_files=True,
    )

    assert capability.reads_files is True
    assert capability.writes_files is True