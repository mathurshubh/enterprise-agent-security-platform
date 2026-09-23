"""ADR-017 / ADR-029 §6 — a recorded finding is not modified in place.

ADR-017 requires that *"once generated, a Behavioral Finding is immutable… must never
be modified in place"*, and ADR-029 §6 requires the same of the derived occurrence
evidence a finding carries: the artifact deciding whether a threshold crossing is
still the same one must not be rewritten by the evaluation asking the question.

Neither was enforced. `FindingsService.list_findings` returns the stored records, so
any caller could edit recorded evidence — and as with audit records, nothing named
like a mutator had to exist for that to be possible.

Freezing the model was not a configuration change on its own. `Finding` assigned
`rule_id` to itself in `model_post_init`, which is an in-place mutation of a
constructed record and is what ADR-017 forbids; with the model frozen it raised, and
65 tests failed. That defaulting is now applied during validation instead. Defaulting
an absent value at construction and editing a built record are different operations,
and only the first survives the requirement.

The defaulting cases below are pinned because the conversion had to preserve them
exactly, including the ones the old form left alone.
"""

import pytest
from pydantic import ValidationError

from app.models.finding import Finding, FindingCategory, Severity
from app.services.findings_service import FindingsService


def finding(**overrides) -> Finding:
    fields = dict(
        finding_id="finding-1",
        session_id="session-1",
        agent_id="agent-1",
        rule_name="PROMPT_INJECTION",
        severity=Severity.HIGH,
        category=FindingCategory.PROMPT_INJECTION,
        description="probe",
    )
    fields.update(overrides)
    return Finding(**fields)


class TestRecordedEvidenceCannotBeRewritten:
    @pytest.mark.security_invariant
    def test_invariant_a_stored_finding_cannot_be_edited_through_the_read_path(
        self,
    ) -> None:
        """`list_findings` hands back the stored records themselves."""
        store = FindingsService()
        store.record_finding(finding())

        fetched = store.list_findings()[0]
        with pytest.raises(ValidationError):
            fetched.severity = Severity.LOW

        assert store.list_findings()[0].severity == Severity.HIGH

    @pytest.mark.security_invariant
    def test_invariant_the_occurrence_evidence_cannot_be_rewritten(self) -> None:
        """ADR-029 §6 specifically.

        The detector reads pinned evidence and epoch back from a prior finding to
        decide whether a crossing is still the same one. If those could be edited,
        the artifact answering that question could be altered by the evaluation
        asking it.
        """
        store = FindingsService()
        store.record_finding(
            finding(
                rule_name="EXCESSIVE_DENIALS",
                evidence_event_sequences=(1, 2, 3),
                enforcement_epoch=0,
            )
        )
        stored = store.list_findings()[0]

        with pytest.raises(ValidationError):
            stored.evidence_event_sequences = (7, 8, 9)
        with pytest.raises(ValidationError):
            stored.enforcement_epoch = 5

        assert store.list_findings()[0].evidence_event_sequences == (1, 2, 3)
        assert store.list_findings()[0].enforcement_epoch == 0

    @pytest.mark.security_invariant
    def test_invariant_no_field_of_a_recorded_finding_is_writable(self) -> None:
        stored = finding()

        for field, value in (
            ("finding_id", "forged"),
            ("session_id", "session-2"),
            ("agent_id", "agent-2"),
            ("rule_name", "OTHER"),
            ("rule_id", "OTHER"),
            ("severity", Severity.LOW),
            ("category", FindingCategory.UNKNOWN),
            ("description", "rewritten"),
            ("evidence_sequence", 99),
        ):
            with pytest.raises(ValidationError):
                setattr(stored, field, value)


class TestTheStoreStillAssignsWhatItOwns:
    """Immutability must not block the store from assigning what it is responsible for.

    `FindingsService` sets `evidence_sequence` and `recorded_at` on persistence, via
    `model_copy`. Without these controls, a model that simply could not express change
    would satisfy every invariant above.
    """

    @pytest.mark.security_regression
    def test_persistence_still_assigns_the_evidence_sequence(self) -> None:
        store = FindingsService()

        recorded = store.record_finding(finding())

        assert recorded.evidence_sequence == 1
        assert recorded.recorded_at is not None
        assert store.get_finding("finding-1").evidence_sequence == 1

    @pytest.mark.security_regression
    def test_deriving_a_changed_finding_produces_a_new_one(self) -> None:
        original = finding()

        derived = original.model_copy(update={"severity": Severity.LOW})

        assert derived.severity == Severity.LOW
        assert original.severity == Severity.HIGH
        assert derived is not original


class TestRuleIdDefaultingIsUnchanged:
    """The conversion from `model_post_init` had to preserve behaviour exactly.

    These pin every construction path measured before the change, including the two
    the old form did not touch.
    """

    @pytest.mark.security_regression
    def test_an_absent_rule_id_defaults_to_the_rule_name(self) -> None:
        assert finding().rule_id == "PROMPT_INJECTION"

    @pytest.mark.security_regression
    def test_an_explicitly_supplied_rule_id_wins(self) -> None:
        assert finding(rule_id="EXPLICIT").rule_id == "EXPLICIT"

    @pytest.mark.security_regression
    def test_an_empty_rule_id_is_treated_as_absent(self) -> None:
        assert finding(rule_id="").rule_id == "PROMPT_INJECTION"

    @pytest.mark.security_regression
    def test_defaulting_applies_through_validation_and_round_trip(self) -> None:
        built = finding()

        assert Finding.model_validate(built.model_dump()).rule_id == "PROMPT_INJECTION"

    @pytest.mark.security_regression
    def test_model_copy_still_bypasses_defaulting(self) -> None:
        """Unchanged, and deliberately pinned.

        `model_copy` does not re-validate, so it did not re-derive `rule_id` before
        the conversion and does not now. Recording it prevents a later change to the
        defaulting from silently altering behaviour the store depends on.
        """
        built = finding()

        assert built.model_copy(update={"rule_name": "OTHER"}).rule_id == "PROMPT_INJECTION"
        assert built.model_copy(update={"rule_id": ""}).rule_id == ""

    @pytest.mark.security_regression
    def test_an_absent_rule_id_with_no_rule_name_stays_empty(self) -> None:
        assert finding(rule_name="").rule_id == ""
