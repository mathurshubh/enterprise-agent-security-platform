# Adversarial Review Adjudication — 2026-10-03

**Review date:** 2026-10-03
**Scope:** Adjudication of the independent Opus 4.6 and Gemini Flash reports. The
September 2026 AI-security architecture review is a separate review cycle.

**Repository-grounded status notes:** ADR-030 is Proposed. In ADR-031, the
Phase A `ApprovalContinuation` terminology/model rename is implemented; Phase B
(D-G1 durable continuation claim and orchestration) is not implemented.
`transition_continuation` is not the specified `claim_continuation` contract.
Execution evidence is production-wired, not durably persisted.

### Finding 1 — Resource / Path Canonicalization

**Conclusion**
Resource and path identity are evaluated without canonicalization or path normalization across the request parsing, execution binding, and policy evaluation boundaries. Because `PolicyEngine` evaluates protected resource restrictions using exact string equality against raw input values while the underlying tool resolves paths against the workspace root, path syntaxes such as `"./secrets.txt"` or `"sub/../secrets.txt"` bypass logical policy checks.

**Evidence**
- **Relevant Code / File:**
  - [`app/policy/policy_engine.py`](../../../app/policy/policy_engine.py#L44-L121): Lines 44–46 declare `PROTECTED_RESOURCES = {"secrets.txt"}`. Lines 118–121 check `tool.tool_id == "file_read" and resource in self.PROTECTED_RESOURCES`.
  - [`app/models/execution_binding.py`](../../../app/models/execution_binding.py#L39-L137): `canonicalize_parameters` only sorts parameter names and validates string types; it performs zero normalization on `resource` or `parameters["path"]`. Line 126 performs a raw string equality check (`resource != declared`).
  - [`app/tools/file_read_tool.py`](../../../app/tools/file_read_tool.py#L48-L57): Lines 48–50 resolve `target_path = (self._workspace / relative_path).resolve()`, which collapses `./secrets.txt` into `<workspace>/secrets.txt` and successfully reads the target.
- **Relevant ADR:**
  - `ADR-006` (§4.1, §5.2): Mandates resource-aware authorization where authorization evaluates both the operation and target resource.
  - `ADR-023` (§3.2): Assumes `ExecutionBinding` represents canonical operation identity.
  - `ADR-032` (§4.1): Distinguishes logical authorization in `PolicyEngine` from physical containment in the sandbox.
- **Relevant Test:**
  - [`tests/policy/test_policy_engine.py`](../../../tests/policy/test_policy_engine.py#L127-L185): Only tests exact literal `"secrets.txt"`.
  - Grep across `tests/` reveals zero test cases asserting non-canonical relative paths (`./secrets.txt`, `foo/../secrets.txt`).
- **Concrete Behavior:**
  An HTTP request to `/agents/{agent_id}/execute` specifying `tool_id="file_read"`, `parameters={"path": "./secrets.txt"}` yields `resource="./secrets.txt"`. In `PolicyEngine`, `"./secrets.txt" in {"secrets.txt"}` evaluates to `False`, returning `Decision.ALLOW`.

**Is it exploitable now?**
CONDITIONAL.
1. At the API decision layer (`/agents/{agent_id}/execute`), the policy check is bypassed and the platform returns `decision: ALLOW`.
2. In end-to-end sandboxed execution, `FilesystemSandboxGuard.check_access` applies a keyword check (`"secret" in name_lower`), which blocks `secrets.txt` specifically. However, for any protected resource not matching that hardcoded substring filter, or when the platform operates in decision-only governance mode, the bypass succeeds entirely.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No. It violates the intent of `ADR-006` and `ADR-023`, which assumed canonical binding representation.
2. *Does it require a threat-model addition?* Yes. Update Threat 9 ("Authorization/Execution Divergence") in `docs/security/threat-model.md` to explicitly address resource path aliasing and canonicalization.
3. *Current implementation or future backlog?* Current implementation defect.
4. *Does it justify a new enterprise capability?* No. It requires strict input normalization within the existing binding domain model.

**Disposition**
ACCEPT

**Required Action**
Define a strict semantic canonicalization rule for filesystem resources in `ExecutionBinding.from_operation` (e.g., resolving pure relative POSIX paths against a normalized root, stripping leading `./` and redundant separators, and rejecting parent-directory escapes before policy evaluation).

**Implementation Note**
The accepted design canonicalizes filesystem resource identity in `RuntimeService` (via
`FilesystemResourceIdentityResolver`) before authorization and binding, rather than inside
`ExecutionBinding.from_operation`. This preserves `ExecutionBinding` as a generic
authorization-binding structure while ensuring the canonical resource is the value supplied
to both policy evaluation and binding.

**Implementation Status — CLOSED**
The Finding 1 remediation is implemented and security-reviewed. `RuntimeService` resolves
filesystem requests against the configured workspace before authorization, and the same
workspace-relative POSIX identity is used for the policy resource, signed
`ExecutionBinding`, and authorized `path` parameter passed to tool execution. The
`FileReadTool` and `DirectoryListTool` recheck identity and containment at execution.
ADR-023 and Threat 9 document the contract and its remaining TOCTOU limitation. Focused
Finding 1 regression tests passed (107 tests), and `git diff --check` passed.

**Validation Caveat — Separate Test-Environment Issue**
The repository-wide suite is not fully green: 1,634 passed, 11 skipped, 5 xfailed,
and 3 failed. Two failures passed on individual rerun. Its remaining unresolved failure is
`tests/scripts/test_dev_credentials.py::TestOutputDoesNotLeak::test_dry_run_prints_no_secret_or_token`,
which exits because development port 8931 is already in use. This is recorded as a
separate test-environment issue; it is not attributed to Finding 1, and no Finding 1
code change was made to work around it. The network-bind and process-cleanup failures
from the same suite passed when rerun individually.

---

### Finding 2 — SessionEvent Foreign Keys

**Conclusion**
Foreign key constraints on `SessionEventModel` contradict the platform's audit and evidence principles. While the session-binding refusal path (`_refuse_session_binding`) avoids failure by never persisting `SessionEventModel`, the main runtime pipeline (`execute()`) attempts to insert a `SessionEventModel` for unrecognized or unregistered tool IDs before authorization concludes. In SQL storage mode, this triggers an unhandled `IntegrityError` that crashes the service instead of returning a clean denial.

**Evidence**
- **Relevant Code / File:**
  - [`app/repositories/sql/models/session_event.py`](../../../app/repositories/sql/models/session_event.py#L41-L65): Line 65 defines `ForeignKey("tool_families.tool_id", ondelete="RESTRICT")`.
  - [`app/services/runtime_service.py`](../../../app/services/runtime_service.py#L403-L430): `_refuse_session_binding` persists only an `AuditEvent` (which has no FKs) and creates an in-memory `SessionEvent` for `RuntimeResult`, avoiding database insert.
  - [`app/services/runtime_service.py`](../../../app/services/runtime_service.py#L927-L935): In `execute()`, when an unknown `tool_id` is supplied, `_tool_registry.resolve(tool_id)` fails and authorization evaluates to `DENY`. Line 935 immediately calls `self._session_service.record_event(event)` passing the unregistered `tool_id`.
  - [`app/repositories/sql/session_repository.py`](../../../app/repositories/sql/session_repository.py#L316-L338): Commits `SessionEventModel`, triggering a database constraint violation.
- **Relevant ADR:**
  - `ADR-034` (§2.3): Explicitly established that trust-boundary refusal evidence must not depend on relational existence of the requested entity.
- **Relevant Test:**
  - [`tests/repositories/sql/test_sql_session_repository.py`](../../../tests/repositories/sql/test_sql_session_repository.py#L189-L199): Asserts that `record_event` with an unknown `tool_id` raises `IntegrityError`. The test passes because it expects the crash, but `RuntimeService.execute()` leaves this exception unhandled.
- **Concrete Behavior:**
  When `SqlSessionRepository` is configured, an agent requesting an unapproved or nonexistent tool causes `runtime_service.execute()` to raise an unhandled SQLAlchemy `IntegrityError` at line 935, resulting in an HTTP 500 error instead of a clean `DENY` decision.

**Is it exploitable now?**
CONDITIONAL.
In the default runtime wiring (`app/api/dependencies.py`), `InMemorySessionRepository` is used, masking the issue. When running with the SQL backend, any caller can trigger a denial-of-service crash on the request thread by submitting an unregistered `tool_id`.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No. It directly aligns with the precedent set in `ADR-034` for `AuditEventModel`.
2. *Does it require a threat-model addition?* No. It falls under robustness and denial-of-service prevention.
3. *Current implementation or future backlog?* Current implementation defect.
4. *Does it justify a new enterprise capability?* No.

**Disposition**
ACCEPT

**Required Action**
Remove the relational foreign key constraint `ForeignKey("tool_families.tool_id")` from `SessionEventModel` (or decouple requested tool identifier from resolved tool entity), ensuring behavioral denials for unknown tools are durably persistable in SQL.

**Implementation Note**
Repository investigation established that the family foreign key was a recorded decision, not
an oversight: migration `0004` and a `security_invariant` test required every session event to
name a registered family, on the premise that a refused event always does. The runtime records
the family the request named, before and regardless of its existence, so that premise is false.
The remediation therefore reverses a recorded decision and is documented as an amendment to
`ADR-034` (§7) rather than as schema cleanup. Both tool-registry references were removed, not
only the family one: the composite `(tool_id, tool_version)` reference carried the same denial
path for a version removed between resolution and the write, and the same inverted `ON DELETE
RESTRICT` dependency. The requested-versus-resolved identity split was deliberately left out of
scope and remains separately tracked.

**Implementation Status — CLOSED (implementation validated; PR review and merge remain the final integration gate)**
Migration `0007` removes the `session_events` references to `tool_families` and `tools`, copying
every row unchanged; session and agent ownership, sequence uniqueness, positive-sequence checks
and indexes are retained. Its downgrade refuses, before any schema change, if a stored event
names an unregistered family or version, and never deletes evidence. A SQL-mode runtime
regression shows a request for an unregistered tool is denied cleanly and its event recorded
(the same test fails with `IntegrityError` against the previous schema), and three such denials
produce an excessive-denial finding. `ADR-034` §7 and Threat 10 document the contract; the
change grants no execution authority. Validated with Ruff, `git diff --check`, the full suite
(the single failure, `test_process_group_cleanup_invariant_kills_child_and_grandchild`, also
fails on `main`), and migration upgrade and downgrade on populated SQLite. The full PostgreSQL
migration chain cannot currently reach `0007` because migration `0002` fails on PostgreSQL on
`main`; `0007` was therefore validated on PostgreSQL 16 against `session_events` built by
`0004`'s own DDL, whose foreign keys carry PostgreSQL-generated names that `0007` drops by
reflection. That `0002` failure, and a separately failing PostgreSQL continuation test, are
pre-existing and are not modified by this change.

---

### Finding 3 — SQL Factory Silent Fallback

**Conclusion**
`create_repositories(backend="sql", ...)` silently instantiates in-memory repositories for `agent_repository`, `tool_repository`, and `audit_repository` when caller arguments are omitted, despite the existence of `SqlToolRepository` and `SqlAuditEvidenceRepository` and the complete absence of a `SqlAgentRepository`.

**Evidence**
- **Relevant Code / File:**
  - [`app/repositories/factory.py`](../../../app/repositories/factory.py#L97-L104):
    ```python
    return RepositoryContainer(
        agent_repository=agent_repository or InMemoryAgentRepository(),
        tool_repository=tool_repository or InMemoryToolRepository(),
        session_repository=SqlSessionRepository(sf),
        enforcement_repository=SqlEnforcementStateRepository(sf),
        approval_grant_repository=SqlApprovalContinuationRepository(sf),
        audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),
    )
    ```
  - [`app/api/dependencies.py`](../../../app/api/dependencies.py#L52-L61): Production composition root directly instantiates `InMemory*Repository` and does not invoke `create_repositories`.
- **Relevant ADR:**
  - `ADR-030` — *Durable State Repository Architecture* (**Proposed**, §§2.A, 4.1): Defines the target durable repository architecture across Configuration, Enforcement, and Session planes.
- **Relevant Test:**
  - [`tests/repositories/sql/test_sql_pipeline_e2e.py`](../../../tests/repositories/sql/test_sql_pipeline_e2e.py#L85-L122): Manually inserts SQL rows for agents while separately registering them into `InMemoryAgentRepository` to make the test pass.
- **Concrete Behavior:**
  An operator or deployment invoking `create_repositories(backend="sql", engine=engine)` receives a split-brain container where session, enforcement, and approval data persist to SQL, while agent definitions, tools, and audit logs silently remain volatile in-memory.

**Is it exploitable now?**
NO.
No production HTTP route or bootstrap script currently invokes `create_repositories(backend="sql")`. The platform composition root strictly uses in-memory repositories.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No. It is an incomplete implementation of `ADR-030`.
2. *Does it require a threat-model addition?* No.
3. *Current implementation or future backlog?* Current implementation defect in the factory.
4. *Does it justify a new enterprise capability?* No.

**Disposition**
ACCEPT

**Required Action**
Refactor `create_repositories` in `app/repositories/factory.py` to fail fast: wire `SqlToolRepository` and `SqlAuditEvidenceRepository` when `session_factory` is provided, and raise `NotImplementedError` if `agent_repository` is omitted under `backend="sql"`, preventing silent fallbacks to volatile memory.

---

### Finding 4 — Agent REGISTERED Lifecycle Semantics

**Conclusion**
`AgentStatus.REGISTERED` is treated as functionally active by `PolicyEngine`, which only denies `SUSPENDED` and `DISABLED` agents. While this creates a semantic asymmetry (an agent begins as `REGISTERED`, is reported as "active" in evaluation reasons, and becomes `ACTIVE` upon reinstatement after suspension), it is not an authorization bypass. Registration is the initial valid state for newly enrolled agents.

**Evidence**
- **Relevant Code / File:**
  - [`app/models/agent.py`](../../../app/models/agent.py#L6-L26): Line 26 sets `status: AgentStatus = AgentStatus.REGISTERED`.
  - [`app/policy/policy_engine.py`](../../../app/policy/policy_engine.py#L54-L75): Denies only if `agent.status in {AgentStatus.SUSPENDED, AgentStatus.DISABLED}`. Line 73 logs reason `"Agent '{agent.agent_id}' is active"`.
  - [`app/services/agent_service.py`](../../../app/services/agent_service.py#L153-L191): Reinstatement sets `AgentStatus.ACTIVE`. No separate `activate_agent` method exists.
- **Relevant ADR:**
  - `ADR-024` (§3, §5): Distinguishes administrative lifecycle (`ACTIVE`, `DISABLED`) from dynamic runtime posture (`ACTIVE`, `SUSPENDED`).
  - `ADR-030` (§2.A): Outlines agent registration and lifecycle management.
- **Relevant Test:**
  - [`tests/services/test_agent_enforcement.py`](../../../tests/services/test_agent_enforcement.py#L7-L143): Explicitly documents and tests the transition `REGISTERED/ACTIVE ──suspend──▶ SUSPENDED ──reinstate──▶ ACTIVE`.
- **Concrete Behavior:**
  A newly provisioned agent with `AgentStatus.REGISTERED` undergoes standard policy evaluation, tool approval validation, and risk tier evaluation without being blocked for lacking an explicit activation step.

**Is it exploitable now?**
NO.
All security controls (RBAC, tool approvals, risk tier thresholds, parameter validation) execute identically for `REGISTERED` agents. An unregistered agent is rejected immediately with `AgentNotFoundError`.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No.
2. *Does it require a threat-model addition?* No.
3. *Current implementation or future backlog?* Future backlog.
4. *Does it justify a new enterprise capability?* No.

**Disposition**
DEFER

**Required Action**
Document that `REGISTERED` is an executable initial state in the administrative lifecycle, or introduce an explicit administrative activation lifecycle step (`activate_agent`) if enterprise onboarding requires staged pre-activation provisioning.

---

### Finding 5 — ApprovalContinuation Claim: Epoch + Expiration

**Conclusion**
The repository method `transition_continuation` only performs compare-and-swap on `state == from_state`. It does not evaluate `enforcement_epoch` or `expires_at`, and returns a boolean rather than the claimed frozen authority. It is not equivalent to the specified `claim_continuation` contract. This is not an unexpected vulnerability in v0.18.0, but an explicitly phased roadmap deliverable: ADR-031 §10.5 defined Phase A (terminology/model rename) as completed and Phase B (D-G1 implementation of the durable atomic claim and orchestration) as pending.

**Evidence**
- **Relevant Code / File:**
  - [`app/repositories/sql/approval_continuation_repository.py`](../../../app/repositories/sql/approval_continuation_repository.py#L117-L137): CAS checks only `row.state != from_state.value`.
  - [`app/repositories/interfaces/approval_continuation_repository.py`](../../../app/repositories/interfaces/approval_continuation_repository.py#L33-L51): Does not accept `expected_epoch` or `now`.
- **Relevant ADR:**
  - `ADR-031` — *Execution Grant and Approval Control Plane* (Accepted): §8 (D-G1A) specifies durable continuation authority; §9 (D-G1B) specifies the claim contract (`state == APPROVED AND enforcement_epoch == current agent epoch AND now < expires_at`) and the transition to a newly minted `RuntimeExecutionGrant`; §10 specifies continuation naming, while §10.5 specifies the Phase A terminology rename and Phase B implementation sequence. The ADR title retains its historical "Execution Grant" terminology.
- **Relevant Test:**
  - [`tests/repositories/contracts/base_approval_continuation_contract.py`](../../../tests/repositories/contracts/base_approval_continuation_contract.py#L65-L104): Tests state transitions and metadata validation; contains no tests for atomic claim with epoch or expiry.
- **Concrete Behavior:**
  `ApprovalContinuation` is currently a frozen approval record and is not yet invoked as live execution authority by the runtime executor. Ephemeral execution authority is governed independently by `ExecutionAuthority.issue()` (which validates epochs and 30s TTL).

**Is it exploitable now?**
NO.
The approval continuation claim mechanism is not exposed on any executable runtime path in v0.18.0.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No. It is explicitly mandated by `ADR-031`.
2. *Does it require a threat-model addition?* No.
3. *Current implementation or future backlog?* Milestone D-G1 implementation scope.
4. *Does it justify a new enterprise capability?* No.

**Disposition**
ALREADY COVERED

**Required Action**
Implement `claim_continuation` in `ApprovalContinuationRepository` during milestone D-G1 exactly as specified in ADR-031 §9, evaluating `state`, `enforcement_epoch`, and `expires_at` atomically under lock and returning the frozen authority instance before minting a `RuntimeExecutionGrant`.

---

### Finding 6 — Sandbox Subprocess Boundary

**Conclusion**
`ProcessSandbox` executes child worker processes with stripped environments, process group isolation, and resource limits. Inside the runner, CPython audit hooks intercept filesystem and socket operations, but do not register hooks for `subprocess.Popen` or OS process execution (`os.system`, `os.posix_spawn`). This is an inherent property of in-process CPython audit hooks rather than a defect in the current tool suite.

**Evidence**
- **Relevant Code / File:**
  - [`app/runtime/sandbox/runner.py`](../../../app/runtime/sandbox/runner.py#L100-L107): Installs only `FilesystemSandboxGuard` and `NetworkSandboxGuard`.
  - [`app/runtime/sandbox/filesystem.py`](../../../app/runtime/sandbox/filesystem.py#L234-L285): Audit hook covers `open`, `listdir`, `scandir`, `mkdir`, `rmdir`, `unlink`, `chmod`, `rename`, `symlink`.
  - [`app/runtime/sandbox/network.py`](../../../app/runtime/sandbox/network.py#L268-L300): Audit hook covers `socket.connect`, `socket.sendto`, `socket.sendmsg`, `socket.bind`.
  - [`app/runtime/sandbox/registry.py`](../../../app/runtime/sandbox/registry.py#L74-L87): The only registered tools in the platform are `file_read_v1` and `directory_list_v1`.
- **Relevant ADR:**
  - `ADR-032` (§3.1, §4.2): Explicitly defines `ProcessSandbox` as process-level isolation utilizing Python audit hooks for capability enforcement within the runner.
- **Relevant Test:**
  - [`tests/runtime/test_process_sandbox.py`](../../../tests/runtime/test_process_sandbox.py): Verifies process group termination, timeout enforcement, clean-room environments, and `-P` flags.
- **Concrete Behavior:**
  The registered production tools (`FileReadTool` and `DirectoryListTool`) are pure Python implementations that do not spawn subprocesses. The LLM is an untrusted intent parser that generates structured `ToolInvocation` parameters, not arbitrary executable code.

**Is it exploitable now?**
NO.
Arbitrary code execution is not supported by any registered tool. Registered tools only accept discrete file path arguments.

**Architecture Impact**
1. *Does it invalidate a locked architectural decision?* No.
2. *Does it require a threat-model addition?* Yes. Explicitly state the trust assumption regarding tool implementation code: tool implementations themselves are trusted not to maliciously spawn un-hooked subprocesses, until container or microVM isolation is introduced.
3. *Current implementation or future backlog?* Future backlog / Defense-in-depth enhancement.
4. *Does it justify a new enterprise capability?* Yes, when the platform expands to support arbitrary code execution tools (e.g., Python code interpreters, Bash execution tools).

**Disposition**
DEFER

**Required Action**
As an immediate defense-in-depth measure, add an audit hook in `runner.py` intercepting `subprocess.Popen` and `os.system`/`os.posix_spawn` to fail-closed on unauthorized process creation. Track full OS-level isolation (containers/microVMs) in the containerization roadmap for arbitrary code execution workloads.

---

# Final Adjudication

## Closed Before D-G1
1. **Resource / Path Canonicalization (Finding 1):** CLOSED. The canonical resource identity contract is implemented across authorization, signed binding, and tool execution, with execution-time containment rechecks. The repository-wide test-environment issue is tracked separately above.
2. **SessionEvent SQL Foreign Key Constraint (Finding 2):** CLOSED — implementation validated; PR review and merge remain the final integration gate. `session_events` no longer references the tool registry (migration `0007`, `ADR-034` §7); denials for unknown tools are recorded in SQL mode, and session/agent ownership and sequence integrity are retained.

## Must Fix Before D-G1
1. **Repository Factory Fail-Fast (Finding 3):** Remove silent in-memory fallback in `create_repositories(backend="sql")`, wire existing SQL repositories, and raise `NotImplementedError` if SQL adapters are missing.

## Must Fix During D-G1
1. **Atomic Continuation Claim (Finding 5):** Implement `ApprovalContinuationRepository.claim_continuation` validating `state == APPROVED`, `enforcement_epoch == current_epoch`, and `now < expires_at` in a single concurrency-controlled transaction returning the frozen authority domain model (ADR-031 Phase B).

## Follow-up Backlog
1. **Subprocess Audit Hook (Finding 6):** Register a CPython audit hook inside `runner.py` to block unauthorized subprocess spawning.
2. **Agent Lifecycle Formalization (Finding 4):** Standardize the semantic distinction between `REGISTERED` and `ACTIVE` across management plane endpoints and documentation.
3. **Raw-Path Authorization Record Without Filesystem Profile (Finding 1 post-merge review):** Filesystem canonicalization in `RuntimeService` runs only when the tool version resolves or a filesystem capability profile exists. For an unresolved filesystem tool with no profile, policy evaluates the raw path, so the recorded authorization decision and telemetry can show `ALLOW` for a non-canonical alias. No execution occurs (no version, no profile, no grant). Evidence-quality concern, not an authorization bypass. Finding 1 remains CLOSED.
4. **Parameter Hash Computed From Raw Parameters (Finding 1 post-merge review):** `RuntimeService` computes telemetry `parameter_hash` from the caller-supplied parameters rather than the canonical bound parameters, weakening correlation between telemetry and the `ExecutionBinding`. Evidence-quality concern, not an authorization bypass. Finding 1 remains CLOSED.

## Rejected / False Positives
- **Assertion that `_refuse_session_binding` fails on SQL foreign keys:** Rejected. Code inspection confirms `_refuse_session_binding` persists only an `AuditEvent` (which has no foreign keys) and does not persist a `SessionEvent`.
- **Assertion that `REGISTERED` status constitutes an active security breach:** Rejected. Registration is the valid initial enrollment state; policy evaluation, tool approvals, and risk limits are fully enforced for registered agents.

## Recommended Engineering Order
1. **Finding 1:** Closed as documented above.
2. **Finding 2:** Closed as documented above.
3. **Factory Hardening (Finding 3):** Eliminate silent in-memory fallbacks in SQL composition and fail startup when required durable adapters are unavailable.
4. **D-G1 Atomic Claim Implementation:** Deliver ADR-031 Phase B continuation claim contract.
5. **Runner Audit Hook Hardening:** Add subprocess interception hook to sandbox child runner.
