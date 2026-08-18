from concurrent.futures import ThreadPoolExecutor

from app.models.finding import Finding, FindingCategory, FindingStatus, Severity
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
    )


class TestFindingsService:
    def test_record_finding(self) -> None:
        service = FindingsService()
        finding = make_finding()
        recorded = service.record_finding(finding)
        assert recorded == finding
        assert service.get_finding("f-1") == finding

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
