"""Governance projection for a tool family (D-1).

Authorization is family-scoped: an agent is approved for a tool, not for one of its
versions. Policy attributes, however, are declared on concrete versions. This is the
deterministic projection that bridges the two without selecting a version.
"""

from pydantic import BaseModel, ConfigDict

from app.models.tool_risk_level import ToolRiskLevel


class ToolFamilyGovernance(BaseModel):
    """The governance attributes policy evaluates for a family.

    ``risk_level`` is the most restrictive level across **all registered versions** of the
    family, ordered by ``ToolRiskLevel.severity``. Two consequences are deliberate:

    - It is not a chosen version. A family whose versions are LOW and CRITICAL projects
      CRITICAL, and authorization still resolves no implementation — that happens at
      containment, where the version is known.
    - It aggregates registered versions, not enabled ones. Reading enablement here would
      let disabling a version change an authorization outcome, which would make an
      operational action look like a change to what the agent is permitted to request.
      Enablement stays a containment concern.
    """

    model_config = ConfigDict(frozen=True)

    tool_id: str
    risk_level: ToolRiskLevel
