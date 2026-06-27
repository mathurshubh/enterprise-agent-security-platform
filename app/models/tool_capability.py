from pydantic import BaseModel, Field


class ToolCapability(BaseModel):
    """Security-relevant capabilities exposed by a tool."""

    category: str = Field(
        description="Functional capability category."
    )

    reads_files: bool = False

    writes_files: bool = False

    network_access: bool = False

    internet_access: bool = False

    database_access: bool = False

    shell_access: bool = False