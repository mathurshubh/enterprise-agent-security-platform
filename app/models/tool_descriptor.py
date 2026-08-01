"""ToolDescriptor — Passive runtime registration data object."""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.tool_metadata import ToolMetadata
from app.tools.base_tool import BaseTool


class ToolDescriptor(BaseModel):
    """Passive runtime registration object encapsulating tool metadata, execution handles, and state.

    Descriptive data container holding registration information. Tool execution and handle
    instantiation are handled exclusively by ToolExecutor.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    metadata: ToolMetadata = Field(description="Descriptive identity and governance metadata.")
    instance: BaseTool | None = Field(
        default=None, description="Instantiated BaseTool instance if registered directly."
    )
    factory: Callable[..., BaseTool] | None = Field(
        default=None, description="Factory callable for lazy tool resolution."
    )
    tool_class: type[BaseTool] | None = Field(
        default=None, description="Class reference of the tool implementation."
    )
    enabled: bool = Field(default=True, description="Whether the tool is enabled for runtime resolution.")
    registration_state: Literal["REGISTERED", "UNREGISTERED", "DEPRECATED"] = Field(
        default="REGISTERED", description="Lifecycle state of the registration."
    )

    @property
    def tool_id(self) -> str:
        return self.metadata.identity.tool_id

    @property
    def version(self) -> str:
        return self.metadata.identity.version
