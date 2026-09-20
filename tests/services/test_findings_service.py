from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.models.finding import Finding, FindingCategory, FindingStatus, Severity
from app.models.watermark import UNASSIGNED_SEQUENCE
from app.services.findings_service import FindingsService


def make_finding(
    finding_id: str = "f-1",
    session_id: str = "sess-1",
    agent_id: str = "agent-1",
    rule_name: str = "PROMPT_INJECTION",
    rule_id: str = "PROMPT_INJECTION",
    severity: Severity = Severity.HIGH,
    category: FindingCategory = FindingCategory.PROMPT_INJECTION,
    status: FindingStatus = FindingStatus.OPEN,
    description: str = "Test prompt injection finding",
    evidence_sequence: int = UNASSIGNED_SEQUENCE,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        session_id=session_id,
        agent_id=agent_id,
        rule_name=rule_name,
        rule_id=rule_id,
        severity=severity,
        category=category,
        status=status,
        description=description,
        evidence_sequence=evidence_sequence,
    )


class TestEvidenceRecordingTime:
    """When the store accepted a finding, which is what a reinstatement baseline uses.

    Detection rules stamp ``Finding.created_at`` deterministically (the three rules use
    a fixed epoch), so enforcement eligibility cannot be derived from it.
    """

    def test_recording_time_is_independent_of_the_finding_timestamp(self) -> None:
        service = FindingsService()
        epoch_finding = make_finding().model_copy(
            update={"created_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
        )

        before = datetime.now(timezone.utc)
        service.record_new_findings([epoch_finding])

        recorded_at = service.recorded_at("f-1")
        assert recorded_at is not None
        assert recorded_at >= before

    def test_recorded_after_excludes_evidence_accepted_at_or_before_the_baseline(
        self,
    ) -> None:
        service = FindingsService()
        service.record_new_findings([make_finding(finding_id="historical")])

        baseline = service.recorded_at("historical")

        # Strictly after: the finding that established the baseline is historical.
        assert service.list_findings(recorded_after=baseline) == []

    def test_recorded_after_includes_evidence_accepted_later(self) -> None:
        service = FindingsService()
        service.record_new_findings([make_finding(finding_id="historical")])
        baseline = datetime.now(timezone.utc)
        service.record_new_findings([make_finding(finding_id="fresh")])

        remaining = service.list_findings(recorded_after=baseline)

        assert [finding.finding_id for finding in remaining] == ["fresh"]

    def test_recorded_after_combines_with_other_filters(self) -> None:
        service = FindingsService()
        baseline = datetime.now(timezone.utc)
        service.record_new_findings(
            [
                make_finding(finding_id="mine", agent_id="agent-1"),
                make_finding(finding_id="theirs", agent_id="agent-2"),
            ]
        )

        mine = service.list_findings(agent_id="agent-1", recorded_after=baseline)

        assert [finding.finding_id for finding in mine] == ["mine"]

    def test_clear_forgets_recording_times(self) -> None:
        service = FindingsService()
        service.record_new_findings([make_finding()])

        service.clear()

        assert service.recorded_at("f-1") is None


class TestFindingsService:
    def test_record_finding(self) -> None:
        service = FindingsService()
        finding = make_finding()
        recorded = service.record_finding(finding)
        assert recorded.finding_id == finding.finding_id
        assert recorded.evidence_sequence == 1
        assert service.get_finding("f-1") == recorded

    def test_record_new_findings_skips_known_identifiers(self) -> None:
        service = FindingsService()
        original = make_finding(description="first crossing")
        repeat = make_finding(description="re-derived crossing")

        recorded = service.record_new_findings([original])
        assert len(recorded) == 1
        assert recorded[0].finding_id == original.finding_id
        assert recorded[0].evidence_sequence == 1
        # The repeat carries the same identity, so it is neither recorded nor reported.
        assert service.record_new_findings([repeat]) == []
        assert len(service.list_findings()) == 1
        assert service.get_finding("f-1").description == "first crossing"

    def test_record_new_findings_returns_only_new_entries(self) -> None:
        service = FindingsService()
        known = make_finding(finding_id="f-known")
        service.record_new_findings([known])

        fresh = make_finding(finding_id="f-fresh")
        recorded = service.record_new_findings([known, fresh])
        assert len(recorded) == 1
        assert recorded[0].finding_id == fresh.finding_id
        assert recorded[0].evidence_sequence == 2
        assert len(service.list_findings()) == 2

    def test_record_findings(self) -> None:
        service = FindingsService()
        f1 = make_finding("f-1")
        f2 = make_finding("f-2")
        service.record_findings([f1, f2])
        assert len(service.list_findings()) == 2

    def test_get_finding_returns_none_when_not_found(self) -> None:
        service = FindingsService()
        assert service.get_finding("nonexistent") is None

    def test_session_id_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", session_id="s-1"),
                make_finding("f-2", session_id="s-2"),
            ]
        )
        assert len(service.list_findings(session_id="s-1")) == 1
        assert service.list_findings(session_id="s-1")[0].finding_id == "f-1"

    def test_agent_id_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", agent_id="a-1"),
                make_finding("f-2", agent_id="a-2"),
            ]
        )
        assert len(service.list_findings(agent_id="a-1")) == 1

    def test_severity_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", severity=Severity.HIGH),
                make_finding("f-2", severity=Severity.LOW),
            ]
        )
        assert len(service.list_findings(severity=Severity.HIGH)) == 1

    def test_category_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", category=FindingCategory.PROMPT_INJECTION),
                make_finding("f-2", category=FindingCategory.DATA_EXFILTRATION),
            ]
        )
        assert len(service.list_findings(category=FindingCategory.PROMPT_INJECTION)) == 1

    def test_status_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", status=FindingStatus.OPEN),
                make_finding("f-2", status=FindingStatus.RESOLVED),
            ]
        )
        assert len(service.list_findings(status=FindingStatus.OPEN)) == 1

    def test_rule_id_filter(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", rule_id="RULE_1"),
                make_finding("f-2", rule_id="RULE_2"),
            ]
        )
        assert len(service.list_findings(rule_id="RULE_1")) == 1

    def test_multiple_filters(self) -> None:
        service = FindingsService()
        service.record_findings(
            [
                make_finding("f-1", session_id="s-1", severity=Severity.HIGH),
                make_finding("f-2", session_id="s-1", severity=Severity.LOW),
                make_finding("f-3", session_id="s-2", severity=Severity.HIGH),
            ]
        )
        results = service.list_findings(session_id="s-1", severity=Severity.HIGH)
        assert len(results) == 1
        assert results[0].finding_id == "f-1"

    def test_clear(self) -> None:
        service = FindingsService()
        service.record_finding(make_finding())
        assert len(service.list_findings()) == 1
        service.clear()
        assert len(service.list_findings()) == 0

    def test_concurrent_access(self) -> None:
        service = FindingsService()

        def record(i: int) -> None:
            service.record_finding(make_finding(finding_id=f"f-concurrent-{i}"))

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(record, range(100)))

        assert len(service.list_findings()) == 100


class TestFindingsAuthoritativeSequencing:
    """Validates monotonic sequence assignment, bootstrap, and baseline watermarking (B-10, B-12, B-14)."""

    def test_pre_m5_findings_receive_deterministic_sequences(self) -> None:
        """Pre-M5 findings with evidence_sequence == 0 are assigned monotonic sequences (B-14)."""
        f1 = make_finding(finding_id="f-1", agent_id="agent-1", evidence_sequence=0)
        f2 = make_finding(finding_id="f-2", agent_id="agent-1", evidence_sequence=0)
        f3 = make_finding(finding_id="f-3", agent_id="agent-2", evidence_sequence=0)

        service = FindingsService(initial_findings=[f1, f2, f3])

        stored_f1 = service.get_finding("f-1")
        stored_f2 = service.get_finding("f-2")
        stored_f3 = service.get_finding("f-3")

        assert stored_f1 is not None and stored_f1.evidence_sequence == 1
        assert stored_f2 is not None and stored_f2.evidence_sequence == 2
        assert stored_f3 is not None and stored_f3.evidence_sequence == 1

        # Next finding for agent-1 continues at 3
        f4 = service.record_finding(make_finding(finding_id="f-4", agent_id="agent-1"))
        assert f4.evidence_sequence == 3

        # Next finding for agent-2 continues at 2
        f5 = service.record_finding(make_finding(finding_id="f-5", agent_id="agent-2"))
        assert f5.evidence_sequence == 2

        # Bootstrap is idempotent when called again
        service.bootstrap_sequences()
        assert service.get_finding("f-1").evidence_sequence == 1
        assert service.get_finding("f-2").evidence_sequence == 2
        assert service.get_finding("f-4").evidence_sequence == 3

    def test_monotonic_sequence_assignment(self) -> None:
        """New findings receive monotonic 1-based sequences (B-12)."""
        service = FindingsService()
        f1 = service.record_finding(make_finding(finding_id="f-1", agent_id="agent-A"))
        f2 = service.record_finding(make_finding(finding_id="f-2", agent_id="agent-A"))
        f3 = service.record_finding(make_finding(finding_id="f-3", agent_id="agent-A"))

        assert f1.evidence_sequence == 1
        assert f2.evidence_sequence == 2
        assert f3.evidence_sequence == 3
        assert service.get_agent_sequence("agent-A") == 3

    def test_separate_agent_sequence_counters(self) -> None:
        """Sequence counters are isolated per agent."""
        service = FindingsService()
        f_a1 = service.record_finding(make_finding(finding_id="fa-1", agent_id="agent-A"))
        f_b1 = service.record_finding(make_finding(finding_id="fb-1", agent_id="agent-B"))
        f_a2 = service.record_finding(make_finding(finding_id="fa-2", agent_id="agent-A"))

        assert f_a1.evidence_sequence == 1
        assert f_b1.evidence_sequence == 1
        assert f_a2.evidence_sequence == 2
        assert service.get_agent_sequence("agent-A") == 2
        assert service.get_agent_sequence("agent-B") == 1

    def test_deduplication_does_not_burn_sequences(self) -> None:
        """Deduplicated findings via record_new_findings do not advance sequence counter (B-3)."""
        service = FindingsService()
        f1 = make_finding(finding_id="f-1", agent_id="agent-A")
        service.record_new_findings([f1])
        assert service.get_agent_sequence("agent-A") == 1

        # Attempt to record the same finding ID again
        repeat = make_finding(finding_id="f-1", agent_id="agent-A", description="duplicate")
        recorded = service.record_new_findings([repeat])
        assert recorded == []
        assert service.get_agent_sequence("agent-A") == 1

        # Next fresh finding gets sequence 2
        f2 = make_finding(finding_id="f-2", agent_id="agent-A")
        new_recorded = service.record_new_findings([f2])
        assert len(new_recorded) == 1
        assert new_recorded[0].evidence_sequence == 2
        assert service.get_agent_sequence("agent-A") == 2

    def test_capture_baseline_watermark(self) -> None:
        """capture_baseline creates an atomic BaselineWatermark covering evidence up to baseline_at (B-10)."""
        service = FindingsService()
        t1 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 20, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

        # Record findings with controlled recorded_at
        f1 = make_finding(finding_id="f-1", agent_id="agent-A")
        f2 = make_finding(finding_id="f-2", agent_id="agent-A")
        f3 = make_finding(finding_id="f-3", agent_id="agent-A")

        service.record_finding(f1)
        service._recorded_at["f-1"] = t1
        service.record_finding(f2)
        service._recorded_at["f-2"] = t2
        service.record_finding(f3)
        service._recorded_at["f-3"] = t3

        # Watermark at t2 should include f1 and f2 (sequence 2), excluding f3 (sequence 3)
        wm = service.capture_baseline("agent-A", baseline_at=t2)
        assert wm.agent_id == "agent-A"
        assert wm.baseline_at == t2
        assert wm.baseline_sequence == 2

        # Watermark before any findings should have sequence 0
        t0 = datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc)
        wm0 = service.capture_baseline("agent-A", baseline_at=t0)
        assert wm0.baseline_sequence == 0

    def test_b14_sequence_continuity_across_reconstruction(self) -> None:
        """Service initialized with partially sequenced findings continues from max sequence (B-14)."""
        f1 = make_finding(finding_id="f-1", agent_id="agent-A", evidence_sequence=5)
        f2 = make_finding(finding_id="f-2", agent_id="agent-A", evidence_sequence=0)

        service = FindingsService(initial_findings=[f1, f2])

        # f1 was 5, f2 (unassigned) receives 6
        assert service.get_finding("f-1").evidence_sequence == 5
        assert service.get_finding("f-2").evidence_sequence == 6
        assert service.get_agent_sequence("agent-A") == 6

        # Next finding is 7
        f3 = service.record_finding(make_finding(finding_id="f-3", agent_id="agent-A"))
        assert f3.evidence_sequence == 7
