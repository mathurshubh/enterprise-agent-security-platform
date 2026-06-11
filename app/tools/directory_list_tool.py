

from pathlib import Path


class DirectoryListTool:
    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    def list_directory(
        self,
        relative_path: str,
    ) -> list[str]:
        target_path = (
            self._workspace / relative_path
        ).resolve()

        if not str(target_path).startswith(
            str(self._workspace)
        ):
            raise ValueError(
                "Access outside workspace is not allowed"
            )

        if not target_path.exists():
            raise FileNotFoundError(
                f"Directory not found: {relative_path}"
            )

        if not target_path.is_dir():
            raise ValueError(
                f"Not a directory: {relative_path}"
            )

        return sorted(
            item.name
            for item in target_path.iterdir()
        )