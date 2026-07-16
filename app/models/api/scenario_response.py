from pydantic import BaseModel


class ScenarioResponse(BaseModel):
    """Management API representation of a registered attack scenario."""

    scenario_id: str
    name: str
    description: str
    category: str
    severity: str
    prompt: str
    expected_tools: list[str]
    expected_detection_rules: list[str]
    expected_response: str
    tags: list[str]
    enabled: bool
