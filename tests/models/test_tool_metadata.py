from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel


def test_tool_metadata_creation() -> None:
    metadata = ToolMetadata(
        identity=ToolIdentity(
            tool_id="file_read",
            name="File Read Tool",
            description="Read a file",
        ),
        governance=ToolGovernance(
            risk_level=ToolRiskLevel.LOW,
            required_permissions=["file.read"],
        ),
        capability=ToolCapability(
            category="filesystem",
            reads_files=True,
        ),
        operational=ToolOperational(),
    )

    assert metadata.identity.tool_id == "file_read"
    assert metadata.identity.name == "File Read Tool"
    assert metadata.identity.description == "Read a file"

    assert (
        metadata.governance.risk_level
        == ToolRiskLevel.LOW
    )

    assert (
        metadata.governance.required_permissions
        == ["file.read"]
    )

    assert metadata.capability.category == "filesystem"
    assert metadata.capability.reads_files is True

    assert metadata.operational.enabled is True