from pydantic import BaseModel, Field


class PlatformCapabilities(BaseModel):
    """Immutable model representing runtime-discovered platform capabilities."""

    tools: set[str] = Field(
        default_factory=set,
        description="Set of registered executable tool IDs.",
    )
    content_detection_rules: set[str] = Field(
        default_factory=set,
        description="Set of single-event content detection rule names.",
    )
    behavioral_detection_rules: set[str] = Field(
        default_factory=set,
        description="Set of session behavioral detection rule names.",
    )

    @property
    def all_detection_rules(self) -> set[str]:
        """Return union of content detection rules and behavioral detection rules."""
        return self.content_detection_rules | self.behavioral_detection_rules
