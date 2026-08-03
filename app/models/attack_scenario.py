from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.finding import Severity
from app.models.response_action import ResponseType
from app.models.risk_assessment import RiskLevel


class ScenarioCategory(str, Enum):
    """High-level security category for static attack scenario assets."""

    BENIGN = "BENIGN"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    TOOL_ABUSE = "TOOL_ABUSE"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    CROSS_AGENT_TRUST = "CROSS_AGENT_TRUST"
    DENIAL_OF_WALLET = "DENIAL_OF_WALLET"
    RUNTIME_REPLAY = "RUNTIME_REPLAY"
    AUTHORIZATION = "AUTHORIZATION"
    SENSITIVE_DATA = "SENSITIVE_DATA"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    SESSION_BEHAVIOR = "SESSION_BEHAVIOR"
    WORKFLOW_SECURITY = "WORKFLOW_SECURITY"


class WorkflowMetadata(BaseModel):
    """Reserved metadata model for future Workflow-Centric Security validation.

    Note: This is metadata only and is NOT interpreted or evaluated by the
    runtime security pipeline today.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    planning_steps: tuple[str, ...] = Field(default_factory=tuple)
    expected_tool_chain: tuple[str, ...] = Field(default_factory=tuple)
    expected_risk_progression: tuple[str, ...] = Field(default_factory=tuple)
    expected_detections: tuple[str, ...] = Field(default_factory=tuple)


class AttackScenario(BaseModel):
    """Immutable security content artifact for expected agent behavior.

    Attack scenarios describe expected runtime behavior and security
    outcomes without implementing execution, detection, authorization, or
    policy logic. They are reusable across attack replay, regression tests,
    detection validation, demonstrations, MITRE ATLAS mapping, and evaluation
    harnesses.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str = Field(
        min_length=1,
        description="Stable unique identifier for the scenario asset.",
    )
    scenario_version: str = Field(
        default="1.0",
        validation_alias=AliasChoices("scenario_version", "version"),
        description="Version of the static scenario definition.",
    )
    schema_version: str = Field(
        default="1.0",
        description="Schema version for the scenario model definition.",
    )
    name: str = Field(min_length=1)
    description: str = ""
    category: ScenarioCategory = Field(
        default=ScenarioCategory.RUNTIME_REPLAY,
        description="Security category represented by the scenario.",
    )
    severity: Severity = Severity.LOW
    enabled: bool = Field(
        default=True,
        description="Whether this scenario is active for execution.",
    )
    user_prompt: str = Field(
        default="",
        description="Untrusted prompt or task input used by the scenario.",
    )
    expected_tool_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "expected_tool_id",
            "expected_tool",
        ),
        description="Tool identifier expected during scenario evaluation.",
    )
    expected_detection: str | None = None
    expected_risk: RiskLevel = Field(
        default=RiskLevel.LOW,
        validation_alias=AliasChoices(
            "expected_risk",
            "expected_risk_level",
        ),
        description="Expected risk level for the scenario outcome.",
    )
    expected_response: ResponseType = Field(
        default=ResponseType.MONITOR,
        description="Expected response recommendation for the scenario.",
    )
    tags: tuple[str, ...] = Field(default_factory=tuple)
    references: tuple[str, ...] = Field(default_factory=tuple)

    # Represents the expected multi-step execution path for future attack
    # replay scenarios.
    tool_sequence: tuple[str, ...] = Field(default_factory=tuple)

    # Findings describe expected security evidence, not runtime
    # implementation logic.
    expected_findings: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Expected security evidence identifiers.",
    )

    workflow_metadata: WorkflowMetadata | None = Field(
        default=None,
        description="Reserved metadata for future workflow-centric validation.",
    )

    @property
    def expected_risk_level(self) -> RiskLevel:
        return self.expected_risk

    @property
    def expected_tool(self) -> str | None:
        return self.expected_tool_id
