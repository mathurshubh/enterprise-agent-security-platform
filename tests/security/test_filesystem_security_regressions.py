"""M-1 — Workspace containment uses string prefixes rather than path containment.

Review evidence (74e8c51)::

    [ESCAPED] sibling .bak               -> 'LOOT::demo_workspace.bak'
    [ESCAPED] symlink -> prefixed sib    -> 'LOOT::demo_workspace.bak'
    [ESCAPED] dir listing of sibling     -> ['loot.txt']
    [blocked] parent escape / absolute / symlink-outside / null byte / deep traversal

``str(target).startswith(str(workspace))`` admits any sibling directory whose
name extends the workspace name, which is exactly how backup and rotation
conventions name directories.

Controls that already hold are kept here as regression coverage. The plain
``../../etc/passwd`` and ``../../`` cases already exist in ``tests/tools`` and
are not duplicated.
"""

import os
from pathlib import Path

import pytest

from app.tools.directory_list_tool import DirectoryListTool
from app.tools.file_read_tool import FileReadTool

SIBLING_MARKER = "CORPUS_SIBLING_VALUE"
OUTSIDE_MARKER = "CORPUS_OUTSIDE_VALUE"


@pytest.fixture
def prefixed_layout(tmp_path: Path) -> Path:
    """workspace/ beside workspace.bak/ and an unrelated outside/ directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("benign", encoding="utf-8")
    (workspace / "nested").mkdir()

    sibling = tmp_path / "workspace.bak"
    sibling.mkdir()
    (sibling / "loot.txt").write_text(SIBLING_MARKER, encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(OUTSIDE_MARKER, encoding="utf-8")

    return workspace


@pytest.mark.security_baseline
def test_baseline_sibling_prefix_directory_is_readable(prefixed_layout: Path) -> None:
    """A sibling sharing the workspace name prefix is treated as inside it."""
    tool = FileReadTool(str(prefixed_layout))

    assert tool.read("../workspace.bak/loot.txt") == SIBLING_MARKER


@pytest.mark.security_baseline
def test_baseline_sibling_prefix_directory_is_listable(prefixed_layout: Path) -> None:
    tool = DirectoryListTool(str(prefixed_layout))

    assert tool.list_directory("../workspace.bak") == ["loot.txt"]


@pytest.mark.security_baseline
def test_baseline_symlink_into_prefixed_sibling_is_followed(
    prefixed_layout: Path,
) -> None:
    """A symlink whose target resolves into the prefixed sibling also escapes."""
    link = prefixed_layout / "link_to_sibling"
    os.symlink(str(prefixed_layout.parent / "workspace.bak"), str(link))

    tool = FileReadTool(str(prefixed_layout))

    assert tool.read("link_to_sibling/loot.txt") == SIBLING_MARKER


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="M-1: containment compares string prefixes instead of resolved path containment (M5)",
)
def test_invariant_sibling_prefix_read_is_refused(prefixed_layout: Path) -> None:
    tool = FileReadTool(str(prefixed_layout))

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.read("../workspace.bak/loot.txt")


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="M-1: containment compares string prefixes instead of resolved path containment (M5)",
)
def test_invariant_sibling_prefix_listing_is_refused(prefixed_layout: Path) -> None:
    tool = DirectoryListTool(str(prefixed_layout))

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.list_directory("../workspace.bak")


@pytest.mark.security_regression
def test_absolute_path_outside_workspace_is_refused(prefixed_layout: Path) -> None:
    tool = FileReadTool(str(prefixed_layout))
    outside = prefixed_layout.parent / "outside" / "secret.txt"

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.read(str(outside))


@pytest.mark.security_regression
def test_symlink_pointing_outside_workspace_is_refused(prefixed_layout: Path) -> None:
    link = prefixed_layout / "link_outside"
    os.symlink(str(prefixed_layout.parent / "outside" / "secret.txt"), str(link))

    tool = FileReadTool(str(prefixed_layout))

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.read("link_outside")


@pytest.mark.security_regression
def test_deep_nested_traversal_is_refused(prefixed_layout: Path) -> None:
    tool = FileReadTool(str(prefixed_layout))

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.read("nested/../../outside/secret.txt")


@pytest.mark.security_regression
def test_null_byte_in_path_is_rejected(prefixed_layout: Path) -> None:
    tool = FileReadTool(str(prefixed_layout))

    with pytest.raises(ValueError):
        tool.read("notes.txt\x00.png")


@pytest.mark.security_regression
def test_absolute_directory_outside_workspace_is_refused(
    prefixed_layout: Path,
) -> None:
    tool = DirectoryListTool(str(prefixed_layout))

    with pytest.raises(ValueError, match="Access outside workspace"):
        tool.list_directory(str(prefixed_layout.parent / "outside"))
