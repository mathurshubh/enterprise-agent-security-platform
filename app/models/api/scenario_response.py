from pydantic import BaseModel


class ScenarioResponse(BaseModel):
    """API representation of a registered attack scenario."""

    scenario_id: str
    name: str
    description: str
    category: str
    severity: str
    prompt: str
    expected_tools: list[str]
    expected_detection_rules: list[str]
    expected_response: str
    expected_risk: str
    expected_findings: list[str]
    tool_sequence: list[str]
    tags: list[str]
    enabled: bool
    version: str = "1.0"
    schema_version: str = "1.0"
