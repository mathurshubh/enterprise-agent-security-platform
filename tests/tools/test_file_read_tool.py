

import pytest

from app.tools.file_read_tool import FileReadTool


def test_read_existing_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    notes_file = workspace / "notes.txt"
    notes_file.write_text(
        "Security platform notes",
        encoding="utf-8",
    )

    tool = FileReadTool(str(workspace))

    result = tool.read("notes.txt")

    assert result == "Security platform notes"


def test_read_missing_file_raises_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = FileReadTool(str(workspace))

    with pytest.raises(FileNotFoundError):
        tool.read("missing.txt")


def test_path_traversal_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = FileReadTool(str(workspace))

    with pytest.raises(
        ValueError,
        match="Access outside workspace",
    ):
        tool.read("../../etc/passwd")


def test_reading_directory_raises_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    nested_directory = workspace / "nested"
    nested_directory.mkdir()

    tool = FileReadTool(str(workspace))

    with pytest.raises(
        ValueError,
        match="Not a file",
    ):
        tool.read("nested")