from pathlib import Path


class FileReadTool:
    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    def read(self, relative_path: str) -> str:
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
                f"File not found: {relative_path}"
            )

        if not target_path.is_file():
            raise ValueError(
                f"Not a file: {relative_path}"
            )

        return target_path.read_text(
            encoding="utf-8"
        )