from pathlib import Path
from typing import Any

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.tools.base_tool import BaseTool


class DirectoryListTool(BaseTool):
    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id="directory_list",
                name="Directory List",
                description="List files in the workspace",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:list"],
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
    ) -> list[str]:
        return self.list_directory(parameters["path"])

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
