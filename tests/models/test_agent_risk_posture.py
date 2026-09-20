"""Unit tests for AgentRiskPosture and PostureState models (M5-B)."""

import pytest
from pydantic import ValidationError

from app.models.agent_risk_posture import AgentRiskPosture, PostureState
from app.models.finding import Severity
from app.models.risk_assessment import RiskLevel


class TestAgentRiskPostureModel:
    def test_posture_state_enum_has_only_three_approved_states(self) -> None:
        """PostureState contains strictly UNINITIALIZED, HEALTHY, STALE."""
        assert set(PostureState) == {
            PostureState.UNINITIALIZED,
            PostureState.HEALTHY,
            PostureState.STALE,
        }

    def test_default_posture_fields(self) -> None:
        """Default fields initialize cleanly with all severities mapped to zero."""
        posture = AgentRiskPosture(agent_id="agent-1")
        assert posture.agent_id == "agent-1"
        assert posture.state == PostureState.HEALTHY
        assert posture.risk_score == 0
        assert posture.risk_level == RiskLevel.LOW
        assert posture.finding_count == 0
        assert posture.baseline_at is None
        assert posture.baseline_sequence == 0
        assert posture.last_applied_sequence == 0
        assert posture.posture_version == 1
        assert posture.counts_by_rule == {}
        assert posture.counts_by_severity == {
            Severity.LOW: 0,
            Severity.MEDIUM: 0,
            Severity.HIGH: 0,
            Severity.CRITICAL: 0,
        }

    def test_model_is_frozen(self) -> None:
        """AgentRiskPosture is immutable."""
        posture = AgentRiskPosture(agent_id="agent-1")
        with pytest.raises(ValidationError):
            posture.risk_score = 50

    def test_backwards_compatibility_instantiation(self) -> None:
        """Legacy instantiation with positional/keyword parameters works seamlessly."""
        posture = AgentRiskPosture(
            agent_id="agent-1",
            risk_score=50,
            risk_level=RiskLevel.HIGH,
            finding_count=2,
        )
        assert posture.agent_id == "agent-1"
        assert posture.risk_score == 50
        assert posture.risk_level == RiskLevel.HIGH
        assert posture.finding_count == 2
        assert posture.state == PostureState.HEALTHY
        assert posture.posture_version == 1
