from pydantic import BaseModel, ConfigDict, Field


class DetectionContext(BaseModel):
    """Immutable runtime inputs evaluated by detection rules."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(
        min_length=1,
        description="Runtime session identifier for generated findings.",
    )
    agent_id: str = Field(
        min_length=1,
        description="Runtime agent identifier for generated findings.",
    )
    user_prompt: str = Field(
        default="",
        description="Untrusted user prompt or task input.",
    )
    model_output: str = Field(
        default="",
        description="Untrusted model output available for evaluation.",
    )
    tool_output: str = Field(
        default="",
        description="Untrusted tool output available for evaluation.",
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    def text_inputs(
        self,
    ) -> tuple[str, ...]:
        return (
            self.user_prompt,
            self.model_output,
            self.tool_output,
        )
