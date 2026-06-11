

import pytest

from app.tools.directory_list_tool import (
    DirectoryListTool,
)


def test_list_workspace_contents(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "notes.txt").write_text(
        "notes",
        encoding="utf-8",
    )
    (workspace / "report.txt").write_text(
        "report",
        encoding="utf-8",
    )

    tool = DirectoryListTool(str(workspace))

    result = tool.list_directory(".")

    assert result == [
        "notes.txt",
        "report.txt",
    ]


def test_list_nested_directory(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    nested = workspace / "nested"
    nested.mkdir()
    (nested / "summary.txt").write_text(
        "summary",
        encoding="utf-8",
    )

    tool = DirectoryListTool(str(workspace))

    result = tool.list_directory("nested")

    assert result == ["summary.txt"]


def test_path_traversal_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = DirectoryListTool(str(workspace))

    with pytest.raises(
        ValueError,
        match="Access outside workspace",
    ):
        tool.list_directory("../../")


def test_missing_directory_raises_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = DirectoryListTool(str(workspace))

    with pytest.raises(FileNotFoundError):
        tool.list_directory("missing")