from pathlib import Path

import pytest

from app.runtime.filesystem_resource_identity import (
    FilesystemResourceIdentityError,
    FilesystemResourceIdentityResolver,
)
from app.tools.file_read_tool import FileReadTool


def test_existing_target_is_canonical_workspace_relative_posix_identity(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "nested").mkdir(parents=True)
    (workspace / "secrets.txt").write_text("secret", encoding="utf-8")
    resolver = FilesystemResourceIdentityResolver(workspace)

    assert resolver.canonicalize("./nested/../secrets.txt") == "secrets.txt"
    assert resolver.canonicalize(str(workspace / "secrets.txt")) == "secrets.txt"


def test_relative_parent_segments_normalize_but_cannot_escape_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "nested").mkdir(parents=True)
    resolver = FilesystemResourceIdentityResolver(workspace)

    assert resolver.canonicalize("nested/../new.txt") == "new.txt"
    with pytest.raises(FilesystemResourceIdentityError, match="escapes the workspace"):
        resolver.canonicalize("../outside.txt")


def test_nonexistent_target_is_checked_from_strictly_resolved_existing_ancestor(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    resolver = FilesystemResourceIdentityResolver(workspace)

    assert resolver.canonicalize("new/sub/file.txt") == "new/sub/file.txt"

    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FilesystemResourceIdentityError, match="outside the workspace"):
        resolver.canonicalize("escape/new.txt")


def test_internal_symlink_resolves_to_its_target_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "secrets.txt"
    target.write_text("secret", encoding="utf-8")
    (workspace / "alias.txt").symlink_to(target)
    resolver = FilesystemResourceIdentityResolver(workspace)

    assert resolver.canonicalize("alias.txt") == "secrets.txt"


def test_symlink_to_outside_workspace_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (workspace / "escape.txt").symlink_to(outside / "secret.txt")
    resolver = FilesystemResourceIdentityResolver(workspace)

    with pytest.raises(FilesystemResourceIdentityError, match="outside the workspace"):
        resolver.canonicalize("escape.txt")


def test_absolute_outside_path_is_rejected_and_absolute_inside_path_converts(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("notes", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    resolver = FilesystemResourceIdentityResolver(workspace)

    assert resolver.canonicalize(str(workspace / "notes.txt")) == "notes.txt"
    with pytest.raises(FilesystemResourceIdentityError, match="outside the workspace"):
        resolver.canonicalize(str(outside))


def test_absolute_parent_traversal_out_of_workspace_is_rejected(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    resolver = FilesystemResourceIdentityResolver(workspace)

    with pytest.raises(FilesystemResourceIdentityError):
        resolver.canonicalize(str(workspace / ".." / "workspace" / "new.txt"))


def test_non_posix_separator_is_rejected_as_ambiguous(tmp_path: Path) -> None:
    resolver = FilesystemResourceIdentityResolver(tmp_path)

    with pytest.raises(FilesystemResourceIdentityError, match="POSIX separators"):
        resolver.canonicalize("nested\\secrets.txt")


def test_existing_case_alias_uses_filesystem_entry_spelling(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    actual = workspace / "SecretS.txt"
    actual.write_text("secret", encoding="utf-8")
    resolver = FilesystemResourceIdentityResolver(workspace)
    alias = workspace / "secrets.txt"

    canonical = resolver.canonicalize("secrets.txt")
    if alias.exists():
        assert canonical == "SecretS.txt"
    else:
        assert canonical == "secrets.txt"


def test_execution_rechecks_symlink_identity_after_authorization(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "inside.txt").write_text("inside", encoding="utf-8")
    (outside / "outside.txt").write_text("outside", encoding="utf-8")
    link = workspace / "link.txt"
    link.symlink_to(workspace / "inside.txt")
    resolver = FilesystemResourceIdentityResolver(workspace)
    authorized_identity = resolver.canonicalize("link.txt")
    assert authorized_identity == "inside.txt"

    target = workspace / "inside.txt"
    target.unlink()
    target.symlink_to(outside / "outside.txt")
    tool = FileReadTool(str(workspace))
    with pytest.raises(ValueError, match="outside the workspace"):
        tool.read(authorized_identity)


def test_tool_requires_canonical_identity_at_execution(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("notes", encoding="utf-8")
    tool = FileReadTool(str(workspace))

    assert tool.read("notes.txt") == "notes"
    with pytest.raises(ValueError, match="identity changed"):
        tool.read("./notes.txt")
