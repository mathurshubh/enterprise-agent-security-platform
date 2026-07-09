from pydantic import BaseModel


class SecurityControlReferenceResponse(BaseModel):
    """Management API representation of a security framework control mapping."""

    framework: str
    control_id: str
    title: str
    version: str


class DetectionRuleResponse(BaseModel):
    """Management API representation of a registered detection rule.

    Exposes RuleMetadata only.  Executable DetectionRule objects are never
    returned through the management plane.
    """

    name: str
    category: str
    description: str
    controls: list[SecurityControlReferenceResponse]
