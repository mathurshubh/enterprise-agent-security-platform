"""Tests for ADR-031 ExecutionGrant domain model and deep parameter immutability."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.execution_grant import (
    ALLOWED_GRANT_TRANSITIONS,
    ExecutionGrant,
    GrantState,
)


def _sample_grant(**kwargs: Any) -> ExecutionGrant:
    now = datetime.now(timezone.utc)
    defaults = {
        "grant_id": "grant-test-1",
        "session_id": "session-test-1",
        "agent_id": "agent-test-1",
        "tool_id": "file_read",
        "execution_parameters": {
            "path": "/etc/sensitive.conf",
            "nested": {"depth": 1, "items": ["a", "b", "c"], "flags": {"safe": True}},
        },
        "originating_audit_event_id": "audit-test-1",
        "risk_score": 75,
        "required_response": "REQUIRE_APPROVAL",
        "enforcement_epoch": 0,
        "state": GrantState.PENDING,
        "created_at": now,
        "expires_at": now + timedelta(minutes=15),
        "approved_by": None,
        "consumed_at": None,
    }
    defaults.update(kwargs)
    return ExecutionGrant(**defaults)


class TestExecutionGrantImmutability:
    """Rigorous verification of ADR-031 ExecutionGrant deep immutability."""

    def test_top_level_model_mutation_is_rejected(self) -> None:
        grant = _sample_grant()
        with pytest.raises(ValidationError):
            grant.state = GrantState.APPROVED  # type: ignore[misc]

        with pytest.raises(ValidationError):
            grant.approved_by = "operator-alice"  # type: ignore[misc]

    def test_execution_parameters_top_level_mutation_is_rejected(self) -> None:
        grant = _sample_grant()
        with pytest.raises(TypeError):
            grant.execution_parameters["path"] = "/etc/modified.conf"  # type: ignore[index]

        with pytest.raises(TypeError):
            grant.execution_parameters["new_key"] = "tampered"  # type: ignore[index]

    def test_execution_parameters_nested_dict_mutation_is_rejected(self) -> None:
        grant = _sample_grant()
        nested = grant.execution_parameters["nested"]
        with pytest.raises(TypeError):
            nested["depth"] = 99  # type: ignore[index]

        with pytest.raises(TypeError):
            nested["flags"]["safe"] = False  # type: ignore[index]

    def test_execution_parameters_nested_list_mutation_is_rejected(self) -> None:
        grant = _sample_grant()
        items = grant.execution_parameters["nested"]["items"]
        assert isinstance(items, tuple)
        with pytest.raises(TypeError):
            items[0] = "tampered"  # type: ignore[index]

    def test_defensive_copy_on_construction_prevents_external_mutation(self) -> None:
        raw_list = ["original_item"]
        raw_nested = {"items": raw_list}
        raw_params = {"path": "/var/log", "nested": raw_nested}

        grant = _sample_grant(execution_parameters=raw_params)

        # Mutate the source data after grant creation
        raw_list.append("injected_item")
        raw_nested["depth"] = 2
        raw_params["path"] = "/etc/shadow"
        raw_params["injected_key"] = "dangerous"

        # The grant's internal state must remain completely unmutated
        assert grant.execution_parameters["path"] == "/var/log"
        assert "injected_key" not in grant.execution_parameters
        assert grant.execution_parameters["nested"]["items"] == ("original_item",)
        assert "depth" not in grant.execution_parameters["nested"]

    def test_deepcopy_and_model_copy_isolation(self) -> None:
        """Controlled deep copy produces distinct isolated instances without mutating copy._deepcopy_dispatch."""
        import copy
        from types import MappingProxyType

        # Invariant: MappingProxyType is not globally registered in copy._deepcopy_dispatch
        assert MappingProxyType not in copy._deepcopy_dispatch

        grant = _sample_grant()

        # Model copy (deep=True)
        copied1 = grant.model_copy(deep=True)
        assert copied1 is not grant
        assert copied1.grant_id == grant.grant_id
        assert copied1.execution_parameters == grant.execution_parameters

        # Copy with update
        copied2 = grant.model_copy(update={"state": GrantState.APPROVED}, deep=True)
        assert copied2 is not grant
        assert copied2.state == GrantState.APPROVED

        # Standard library copy.deepcopy
        copied3 = copy.deepcopy(grant)
        assert copied3 is not grant
        assert copied3.grant_id == grant.grant_id

        # MappingProxyType remains unmutated in copy._deepcopy_dispatch
        assert MappingProxyType not in copy._deepcopy_dispatch


class TestExecutionGrantSerialization:
    """Verify serialization and roundtrip of deeply frozen ExecutionGrant."""

    def test_model_dump_returns_standard_mutable_dict_for_json(self) -> None:
        grant = _sample_grant()
        dumped = grant.model_dump()
        assert isinstance(dumped["execution_parameters"], dict)
        assert isinstance(dumped["execution_parameters"]["nested"]["items"], list)

    def test_model_dump_json_roundtrip(self) -> None:
        grant = _sample_grant()
        json_str = grant.model_dump_json()
        assert "file_read" in json_str
        assert "/etc/sensitive.conf" in json_str

        reconstituted = ExecutionGrant.model_validate_json(json_str)
        assert reconstituted.grant_id == grant.grant_id
        assert reconstituted.execution_parameters["path"] == "/etc/sensitive.conf"
        # Reconstituted grant must also be deeply immutable
        with pytest.raises(TypeError):
            reconstituted.execution_parameters["path"] = "/mutated"  # type: ignore[index]


class TestExecutionGrantStateLifecycle:
    """Verify ADR-031 state semantics and allowed transitions."""

    def test_grant_states_taxonomy(self) -> None:
        expected = {"PENDING", "APPROVED", "REJECTED", "EXPIRED", "CONSUMED"}
        assert {s.value for s in GrantState} == expected

    def test_allowed_grant_transitions_table(self) -> None:
        expected = {
            (GrantState.PENDING, GrantState.APPROVED),
            (GrantState.PENDING, GrantState.REJECTED),
            (GrantState.PENDING, GrantState.EXPIRED),
            (GrantState.APPROVED, GrantState.CONSUMED),
        }
        assert ALLOWED_GRANT_TRANSITIONS == expected

    def test_consumed_at_and_approved_by_semantics(self) -> None:
        now = datetime.now(timezone.utc)
        consumed_time = now + timedelta(minutes=5)
        grant = _sample_grant(
            state=GrantState.CONSUMED,
            approved_by="operator-sec",
            consumed_at=consumed_time,
        )
        assert grant.state == GrantState.CONSUMED
        assert grant.approved_by == "operator-sec"
        assert grant.consumed_at == consumed_time
