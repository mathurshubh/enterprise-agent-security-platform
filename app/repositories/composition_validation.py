"""Durable composition validation (ADR-030 L.6 requirement 1).

> A composition must not make a store durable while it holds a reference into a volatile
> namespace. Durable enforcement with in-memory findings is not a valid durable-security
> topology.

The rule exists because a watermark reference carries cursor semantics: consumers ignore
records at or below the watermark. A durable watermark pointing into a volatile allocator
therefore suppresses detection after a restart -- the allocator restarts at zero while the
watermark remembers a high position, so every new record is treated as already covered.

Checked at composition time rather than at first use. A partial durable topology is not a
condition that degrades gracefully; it is one whose symptom is silently missing detection,
which is exactly the kind of failure that must be refused where it is created.
"""

from dataclasses import dataclass
from typing import Any


class DurableCompositionError(ValueError):
    """Raised when a composition pairs a durable store with a volatile namespace.

    A ``ValueError`` for the same reason ``RepositoryCompositionError`` is: callers already
    handling the factory's composition failures keep working.
    """


def is_durable(repository: Any) -> bool:
    """Whether this adapter survives a process restart.

    Decided by adapter identity rather than by a declared attribute, because an attribute
    is a claim an adapter makes about itself and durability is a property of what it
    writes to. A repository that is neither is treated as volatile: the conservative
    reading, since mistaking volatile for durable is the direction that suppresses
    detection.
    """
    return type(repository).__name__.startswith("Sql")


@dataclass(frozen=True)
class NamespaceReference:
    """One row of the L.6 reference table, as data the validator can check.

    ``referenced_attribute`` is None where the referenced namespace has no repository at
    all. That is not an omission in this table -- it is the finding. A namespace with no
    repository is unconditionally volatile, so any durable referencing store is invalid.
    """

    referencing_attribute: str
    referencing_record: str
    referenced_namespace: str
    referenced_attribute: str | None
    allocator_description: str


# ADR-030 L.6, current references. The state-stamp row is deliberately absent: it carries
# no cursor semantics, so its integrity requirement is restoration non-regression alone and
# nothing about it constrains a composition.
L6_REFERENCES: tuple[NamespaceReference, ...] = (
    NamespaceReference(
        referencing_attribute="enforcement_repository",
        referencing_record="agent_enforcement_state.baseline_evidence_sequence",
        referenced_namespace="Finding.evidence_sequence",
        referenced_attribute=None,
        allocator_description=(
            "FindingsService, in process memory; there is no findings repository"
        ),
    ),
    NamespaceReference(
        referencing_attribute="enforcement_repository",
        referencing_record="agent_enforcement_state.baseline_agent_sequence",
        referenced_namespace="SessionEvent.agent_sequence",
        referenced_attribute="session_repository",
        allocator_description="agent_sequence_counters, owned by the session repository",
    ),
    NamespaceReference(
        referencing_attribute="approval_grant_repository",
        referencing_record="approval_continuations.enforcement_epoch",
        referenced_namespace="AgentEnforcementState.epoch",
        referenced_attribute="enforcement_repository",
        allocator_description="the enforcement state repository",
    ),
)


def validate_durable_composition(container: Any) -> None:
    """Refuse a composition that makes a store durable over a volatile namespace.

    Raises:
        DurableCompositionError: naming every offending reference at once rather than the
            first. An operator fixing a topology needs the whole list; reporting one at a
            time turns a composition problem into a guessing game.
    """
    violations: list[str] = []

    for ref in L6_REFERENCES:
        referencing = getattr(container, ref.referencing_attribute, None)
        if referencing is None or not is_durable(referencing):
            continue

        referenced = (
            None
            if ref.referenced_attribute is None
            else getattr(container, ref.referenced_attribute, None)
        )
        if referenced is not None and is_durable(referenced):
            continue

        violations.append(
            f"  - {ref.referencing_record} is durable but references "
            f"{ref.referenced_namespace}, whose allocator is volatile "
            f"({ref.allocator_description})."
        )

    if violations:
        raise DurableCompositionError(
            "Invalid durable composition (ADR-030 L.6): a durable store must not "
            "reference a volatile namespace.\n"
            + "\n".join(violations)
            + "\n\nA durable watermark over a volatile allocator suppresses detection "
            "after a restart: the allocator restarts at zero while the watermark "
            "remembers a high position, so new records are treated as already covered. "
            "Make the referenced namespaces durable, or compose the whole platform "
            "in memory."
        )
