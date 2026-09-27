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


# ---------------------------------------------------------------------------
# v0.17.1 — a workspace root is required, never defaulted (F-006, F-006b)
# ---------------------------------------------------------------------------


@pytest.mark.security_invariant
@pytest.mark.parametrize(
    "context",
    [{}, {"workspace_root": None}, {"workspace_root": ""}],
    ids=["absent", "explicitly-none", "empty"],
)
def test_invariant_a_child_wrapper_refuses_to_default_its_workspace(context) -> None:
    """The production child wrappers substituted ``/tmp`` for a missing workspace root.

    A workspace root is the boundary the tool is confined to, so guessing one grants
    access to a directory nobody chose. The explicitly-none case is the one that
    actually occurred: the runner supplies the key as ``None`` when no filesystem
    capability is present, so ``context.get("workspace_root", "/tmp")`` returned
    ``None`` and the tool was constructed with the literal string ``"None"``.
    """
    from app.runtime.sandbox.registry import _run_directory_list, _run_file_read

    with pytest.raises(PermissionError, match="no workspace_root"):
        _run_file_read({"path": "notes.txt"}, context)

    with pytest.raises(PermissionError, match="no workspace_root"):
        _run_directory_list({"path": "."}, context)


@pytest.mark.security_regression
def test_the_child_registry_declares_no_default_workspace() -> None:
    """Guard against reintroduction of the literal default."""
    from pathlib import Path as _Path

    import app.runtime.sandbox.registry as registry_module

    source = _Path(registry_module.__file__).read_text(encoding="utf-8")
    assert 'context.get("workspace_root", "/tmp")' not in source


@pytest.mark.security_invariant
def test_invariant_a_tool_without_a_discoverable_workspace_gets_no_capability_profile(
    build_runtime, security_workspace: Path
) -> None:
    """The parent-side half of the same defect (F-006b).

    ``RuntimeService._create_default_capability_registry`` defaulted
    ``workspace_root`` to ``/tmp``, so a tool whose workspace could not be determined
    received a capability profile confining it to ``/tmp`` — and that profile is what
    configures the sandbox guard, making this the more consequential of the two. The
    tool now gets no profile, and therefore no executable grant.
    """
    from app.models.tool_capability import ToolCapability
    from app.models.tool_governance import ToolGovernance
    from app.models.tool_identity import ToolIdentity
    from app.models.tool_metadata import ToolMetadata
    from app.models.tool_operational import ToolOperational
    from app.models.tool_risk_level import ToolRiskLevel
    from app.registry.tool_registry import ToolRegistry
    from app.tools.base_tool import BaseTool

    class _WorkspacelessTool(BaseTool):
        def __init__(self) -> None:
            self._metadata = ToolMetadata(
                identity=ToolIdentity(
                    tool_id="workspaceless",
                    name="Workspaceless",
                    version="1.0.0",
                    description="No discoverable workspace",
                ),
                governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
                capability=ToolCapability(category="test"),
                operational=ToolOperational(),
            )

        @property
        def metadata(self) -> ToolMetadata:
            return self._metadata

        def execute(self, parameters: dict[str, object]) -> dict[str, object]:
            return {}

    env = build_runtime(workspace=security_workspace)
    registry = ToolRegistry()
    registry.register(_WorkspacelessTool())

    runtime = env.runtime
    original = runtime._tool_registry
    try:
        runtime._tool_registry = registry
        derived = runtime._create_default_capability_registry()
    finally:
        runtime._tool_registry = original

    assert derived.exists("profile-workspaceless") is False


@pytest.mark.security_regression
def test_a_tool_with_a_workspace_still_receives_a_profile_confined_to_it(
    build_runtime, security_workspace: Path
) -> None:
    """The fail-closed rule must not withdraw profiles from ordinary tools."""
    env = build_runtime(workspace=security_workspace)

    caps = env.runtime.capability_registry.resolve_profile("profile-file_read")

    assert caps.filesystem.workspace_root == str(security_workspace.resolve())
    assert caps.filesystem.read_only is True
