from pathlib import Path
from typing import Any

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.tools.base_tool import BaseTool


class FileReadTool(BaseTool):
    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id="file_read",
                name="File Read",
                description="Read files from the workspace",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:read"],
            ),
            capability=ToolCapability(
                category="filesystem",
                reads_files=True,
            ),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.read(parameters["path"])

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
