"""ExecutionBinding — the canonical description of what an authorization covers (ADR-023).

An ExecutionBinding answers one question: *which exact operation* the runtime
security pipeline evaluated. It carries no authority of its own. Authority to
execute a binding is conferred only by an ``ExecutionGrant`` issued by the
``ExecutionAuthority``.

Canonicalisation rules
----------------------
* Parameters are stored as ``(name, value)`` pairs sorted by name, whichever way the
  model is constructed, so requests that differ only in mapping order are equal.
* Names must be non-empty and unique; values must be strings, matching the
  ``ToolInvocation`` contract. Anything else is rejected rather than coerced,
  because coercion would let two different operations share one binding.
* ``resource`` is the ``RESOURCE_PARAMETER`` value when that parameter is present.
  An explicit resource that contradicts it is rejected.
"""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

RESOURCE_PARAMETER = "path"


class ExecutionBindingValidationError(ValueError):
    """Raised when a requested operation cannot be expressed as one consistent binding."""


def canonicalize_parameters(
    parameters: Mapping[str, Any] | None,
) -> tuple[tuple[str, str], ...]:
    """Return parameters as name-sorted ``(name, value)`` pairs, rejecting non-string data."""
    if parameters is None:
        return ()

    if not isinstance(parameters, Mapping):
        raise ExecutionBindingValidationError("parameters must be a mapping")

    pairs: list[tuple[str, str]] = []
    for name, value in parameters.items():
        if not isinstance(name, str) or not name:
            raise ExecutionBindingValidationError(
                "parameter names must be non-empty strings"
            )
        if not isinstance(value, str):
            raise ExecutionBindingValidationError(
                f"parameter '{name}' must be a string"
            )
        pairs.append((name, value))

    return tuple(sorted(pairs))


class ExecutionBinding(BaseModel):
    """Immutable, canonical description of one tool operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_id: str = Field(min_length=1, description="Tool the operation targets.")
    resource: str | None = Field(
        default=None,
        description="Resource the operation acts on, evaluated by resource-aware policy.",
    )
    parameters: tuple[tuple[str, str], ...] = Field(
        default=(),
        description="Name-sorted (name, value) parameter pairs.",
    )

    @field_validator("parameters")
    @classmethod
    def _canonical_parameter_order(
        cls,
        value: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        names = [name for name, _ in value]
        if any(not name for name in names):
            raise ValueError("parameter names must be non-empty")
        if len(names) != len(set(names)):
            raise ValueError("parameter names must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def _resource_agrees_with_resource_parameter(self) -> "ExecutionBinding":
        declared = dict(self.parameters).get(RESOURCE_PARAMETER)
        if declared is not None and self.resource != declared:
            raise ValueError(
                f"resource must equal the '{RESOURCE_PARAMETER}' parameter when it is present"
            )
        return self

    @classmethod
    def from_operation(
        cls,
        tool_id: str,
        parameters: Mapping[str, Any] | None = None,
        resource: str | None = None,
    ) -> "ExecutionBinding":
        """Build the canonical binding for a requested operation.

        Raises:
            ExecutionBindingValidationError: if the operation is malformed or its
                explicit resource contradicts its resource parameter.
        """
        canonical = canonicalize_parameters(parameters)
        declared = dict(canonical).get(RESOURCE_PARAMETER)

        if resource is not None and declared is not None and resource != declared:
            raise ExecutionBindingValidationError(
                f"explicit resource contradicts the '{RESOURCE_PARAMETER}' parameter"
            )

        try:
            return cls(
                tool_id=tool_id,
                resource=resource if resource is not None else declared,
                parameters=canonical,
            )
        except ValidationError as exc:
            raise ExecutionBindingValidationError(
                "operation cannot be expressed as an execution binding"
            ) from exc

    @property
    def parameters_dict(self) -> dict[str, str]:
        return dict(self.parameters)

    def canonical_json(self) -> str:
        """Deterministic serialisation used when signing grants."""
        return json.dumps(
            {
                "parameters": [list(pair) for pair in self.parameters],
                "resource": self.resource,
                "tool_id": self.tool_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
