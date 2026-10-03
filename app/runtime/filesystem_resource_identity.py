"""Canonical identity and containment checks for workspace filesystem paths."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath


class FilesystemResourceIdentityError(ValueError):
    """Raised when a filesystem resource has no safe canonical workspace identity."""


class FilesystemResourceIdentityResolver:
    """Resolve filesystem requests to workspace-relative POSIX identities.

    Existing targets are resolved through symlinks and must remain in the workspace.
    For nonexistent targets, the nearest existing ancestor is resolved strictly and
    checked before the missing suffix is normalized beneath it. Case aliases of
    existing path components are represented using the spelling returned by the
    filesystem; missing components retain the spelling supplied by the request.
    """

    def __init__(self, workspace_root: str | Path) -> None:
        try:
            configured_root = Path(workspace_root).resolve(strict=True)
            # The configured root is trusted configuration. Avoid scanning its
            # ancestors: they may be outside the process sandbox and are not part
            # of resource identity resolution.
            self.workspace_root = configured_root
        except (OSError, RuntimeError, FilesystemResourceIdentityError) as exc:
            raise FilesystemResourceIdentityError(
                "filesystem workspace root cannot be resolved safely"
            ) from exc
        if not self.workspace_root.is_dir():
            raise FilesystemResourceIdentityError(
                "filesystem workspace root is not a directory"
            )

    def canonicalize(self, path: str) -> str:
        """Return one workspace-relative POSIX identity or reject the request."""
        if not isinstance(path, str) or not path:
            raise FilesystemResourceIdentityError("filesystem path must be non-empty")
        if "\x00" in path:
            raise FilesystemResourceIdentityError("filesystem path contains a null byte")
        if "\\" in path or PureWindowsPath(path).is_absolute():
            raise FilesystemResourceIdentityError(
                "filesystem path must use unambiguous POSIX separators"
            )

        request_path = Path(path)
        if request_path.is_absolute():
            self._validate_absolute_parent_segments(path)
            candidate = request_path
        else:
            self._validate_relative_parent_segments(path)
            candidate = self.workspace_root.joinpath(*PurePosixPath(path).parts)

        try:
            resolved = self._resolve_existing_or_missing(candidate)
            relative = resolved.relative_to(self.workspace_root)
        except (OSError, RuntimeError, ValueError) as exc:
            if isinstance(exc, FilesystemResourceIdentityError):
                raise
            raise FilesystemResourceIdentityError(
                "filesystem path is outside the workspace or cannot be resolved safely"
            ) from exc

        if not relative.parts:
            return "."
        return PurePosixPath(*relative.parts).as_posix()

    def resolve_for_execution(self, identity: str) -> Path:
        """Recheck containment and identity immediately before opening a target."""
        current_identity = self.canonicalize(identity)
        if current_identity != identity:
            raise FilesystemResourceIdentityError(
                "filesystem resource identity changed after authorization"
            )

        target = self.workspace_root.joinpath(*PurePosixPath(identity).parts)
        try:
            return self._resolve_existing(target)
        except FileNotFoundError:
            # The caller can report the ordinary missing-file outcome after the
            # existing-prefix containment check performed by canonicalize().
            raise

    def _resolve_existing_or_missing(self, candidate: Path) -> Path:
        if candidate.exists() or candidate.is_symlink():
            return self._resolve_existing(candidate)

        missing_suffix: list[str] = []
        ancestor = candidate
        while not ancestor.exists() and not ancestor.is_symlink():
            parent = ancestor.parent
            if parent == ancestor:
                raise FilesystemResourceIdentityError(
                    "filesystem path has no resolvable existing ancestor"
                )
            missing_suffix.insert(0, ancestor.name)
            ancestor = parent

        current = self._require_inside(self._resolve_existing(ancestor))
        for component in missing_suffix:
            if component in ("", "."):
                continue
            if component == "..":
                current = current.parent
                self._require_inside(current)
                continue

            next_path = current / component
            if next_path.exists() or next_path.is_symlink():
                current = self._require_inside(self._resolve_existing(next_path))
            else:
                current = next_path
                self._require_inside(current)
        return current

    def _resolve_existing(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        return self._filesystem_spelling(resolved)

    def _require_inside(self, path: Path) -> Path:
        try:
            path.relative_to(self.workspace_root)
        except ValueError as exc:
            raise FilesystemResourceIdentityError(
                "filesystem path resolves outside the workspace"
            ) from exc
        return path

    def _filesystem_spelling(self, path: Path) -> Path:
        """Return actual directory-entry spelling for an existing absolute path.

        ``Path.resolve()`` resolves symlinks and dot segments, but does not promise
        case-normalized spelling on every filesystem. Looking up each existing entry
        makes case-insensitive aliases share the actual target identity. Exact matches
        take precedence; ambiguous non-exact matches fail closed.
        """
        # Establish physical containment before enumerating anything. This also
        # avoids inspecting host directories outside the configured workspace.
        ancestors: list[Path] = []
        current = path
        while True:
            try:
                if os.path.samefile(current, self.workspace_root):
                    break
            except OSError as exc:
                raise FilesystemResourceIdentityError(
                    "cannot verify filesystem path containment safely"
                ) from exc
            parent = current.parent
            if parent == current:
                raise FilesystemResourceIdentityError(
                    "filesystem path resolves outside the workspace"
                )
            ancestors.append(current)
            current = parent

        current = self.workspace_root
        for requested in reversed(ancestors):
            component = requested.name
            candidate = current / component
            try:
                with os.scandir(current) as entries:
                    entry_list = list(entries)
            except OSError as exc:
                raise FilesystemResourceIdentityError(
                    "cannot inspect filesystem path components safely"
                ) from exc

            exact = [entry.name for entry in entry_list if entry.name == component]
            if exact:
                current = current / exact[0]
                continue

            matching: list[str] = []
            for entry in entry_list:
                try:
                    if os.path.samefile(requested, entry.path):
                        matching.append(entry.name)
                except OSError:
                    continue
            if len(matching) != 1:
                raise FilesystemResourceIdentityError(
                    "filesystem path component has ambiguous case identity"
                )
            current = current / matching[0]
        return current

    def _validate_relative_parent_segments(self, path: str) -> None:
        depth = 0
        for component in path.split("/"):
            if component in ("", "."):
                continue
            if component == "..":
                if depth == 0:
                    raise FilesystemResourceIdentityError(
                        "relative filesystem path escapes the workspace"
                    )
                depth -= 1
            else:
                depth += 1

    def _validate_absolute_parent_segments(self, path: str) -> None:
        """Reject parent traversal that leaves a lexically named workspace root.

        Absolute paths outside the configured root are still eligible when their
        resolved target is unambiguously inside it (for example, a path through a
        symlinked workspace alias). An absolute path containing ``..`` that cannot be
        tied lexically to the configured root is ambiguous and refused.
        """
        components = PurePosixPath(path).parts
        root_components = self.workspace_root.parts
        comparable = min(len(components), len(root_components))
        same_prefix = all(
            components[index].casefold() == root_components[index].casefold()
            for index in range(comparable)
        ) and len(components) >= len(root_components)

        if same_prefix:
            self._validate_relative_parent_segments(
                "/".join(components[len(root_components) :])
            )
        elif ".." in components:
            raise FilesystemResourceIdentityError(
                "absolute filesystem path with parent traversal is ambiguous"
            )
