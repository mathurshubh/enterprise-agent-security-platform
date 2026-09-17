"""ExecutionBinding canonicalisation and consistency (ADR-023)."""

import pytest
from pydantic import ValidationError

from app.models.execution_binding import (
    RESOURCE_PARAMETER,
    ExecutionBinding,
    ExecutionBindingValidationError,
    canonicalize_parameters,
)


class TestCanonicalisation:
    def test_parameter_order_does_not_change_the_binding(self) -> None:
        first = ExecutionBinding.from_operation(
            "file_read", {"path": "notes.txt", "mode": "r"}
        )
        second = ExecutionBinding.from_operation(
            "file_read", {"mode": "r", "path": "notes.txt"}
        )

        assert first == second
        assert first.canonical_json() == second.canonical_json()

    def test_parameters_are_stored_sorted_by_name(self) -> None:
        binding = ExecutionBinding.from_operation(
            "file_read", {"z": "1", "a": "2", RESOURCE_PARAMETER: "notes.txt"}
        )

        assert [name for name, _ in binding.parameters] == ["a", "path", "z"]

    def test_direct_construction_is_canonicalised_as_well(self) -> None:
        binding = ExecutionBinding(
            tool_id="file_read",
            parameters=(("mode", "r"), ("encoding", "utf-8")),
        )

        assert binding.parameters == (("encoding", "utf-8"), ("mode", "r"))

    def test_canonical_json_is_an_exact_stable_representation(self) -> None:
        binding = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})

        assert binding.canonical_json() == (
            '{"parameters":[["path","notes.txt"]],'
            '"resource":"notes.txt","tool_id":"file_read"}'
        )

    def test_absent_parameters_bind_to_an_empty_tuple(self) -> None:
        assert canonicalize_parameters(None) == ()
        assert ExecutionBinding.from_operation("file_read").parameters == ()

    @pytest.mark.parametrize(
        "value", [1, 1.5, None, True, ["notes.txt"], {"nested": "x"}, b"notes.txt"]
    )
    def test_non_string_values_are_rejected_not_coerced(self, value) -> None:
        with pytest.raises(ExecutionBindingValidationError):
            ExecutionBinding.from_operation("file_read", {"path": value})

    @pytest.mark.parametrize("name", ["", 1])
    def test_invalid_parameter_names_are_rejected(self, name) -> None:
        with pytest.raises(ExecutionBindingValidationError):
            ExecutionBinding.from_operation("file_read", {name: "notes.txt"})

    def test_duplicate_parameter_names_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionBinding(
                tool_id="file_read",
                parameters=(("mode", "a"), ("mode", "b")),
            )

    def test_empty_tool_id_cannot_be_bound(self) -> None:
        with pytest.raises(ExecutionBindingValidationError):
            ExecutionBinding.from_operation("", {"path": "notes.txt"})


class TestResourceProjection:
    def test_resource_is_derived_from_the_resource_parameter(self) -> None:
        binding = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})

        assert binding.resource == "notes.txt"

    def test_explicit_resource_without_the_parameter_is_preserved(self) -> None:
        binding = ExecutionBinding.from_operation("file_read", resource="notes.txt")

        assert binding.resource == "notes.txt"
        assert binding.parameters == ()

    def test_agreeing_resource_and_parameter_are_accepted(self) -> None:
        binding = ExecutionBinding.from_operation(
            "file_read", {"path": "notes.txt"}, resource="notes.txt"
        )

        assert binding.resource == "notes.txt"

    def test_contradictory_resource_and_parameter_are_rejected(self) -> None:
        with pytest.raises(ExecutionBindingValidationError, match="contradicts"):
            ExecutionBinding.from_operation(
                "file_read", {"path": "secrets.txt"}, resource="notes.txt"
            )

    def test_contradiction_is_rejected_on_direct_construction_too(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionBinding(
                tool_id="file_read",
                resource="notes.txt",
                parameters=(("path", "secrets.txt"),),
            )

    def test_resource_participates_in_equality(self) -> None:
        with_resource = ExecutionBinding.from_operation("file_read", resource="notes.txt")
        without_resource = ExecutionBinding.from_operation("file_read")

        assert with_resource != without_resource


class TestImmutability:
    def test_binding_cannot_be_mutated_after_construction(self) -> None:
        binding = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})

        with pytest.raises(ValidationError):
            binding.tool_id = "directory_list"
