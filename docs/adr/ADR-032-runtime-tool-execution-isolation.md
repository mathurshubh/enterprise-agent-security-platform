# ADR-032: Runtime Tool Execution Isolation

**Status:** Accepted / Implemented

**Date:** 2026-09-27

**Authors:**
- Shubhankar Mathur

---

## 1. Context

The Enterprise Agent Security Platform governs the execution of autonomous AI agents operating in enterprise environments. Through ADR-001 through ADR-031, the platform has established a deterministic, zero-trust security control plane:

1. **LLM as Untrusted Intent Parser (ADR-002):** The model translates natural language prompts into structured `ToolInvocation` payloads but never makes security, authorization, or policy decisions.
2. **Deterministic Security Pipeline (ADR-003, ADR-004):** `RuntimeService` executes a 10-step zero-trust pipeline (Authentication, Authorization, Resource-Aware Policy, Session Positioning, Detection Scanning, Authoritative Evidence, Cumulative Risk, Response Overrides, Immutable Auditing, Execution Granting).
3. **Durable State & Concurrency Control Plane (Plane 3, ADR-030, ADR-031):** All security state (session sequence numbers, behavioral detection horizons, monotonic enforcement epochs, and single-use execution grants) is persisted in relational storage (PostgreSQL 16 MVCC authority / SQLite) with parent-row serialization anchors and compare-and-set (CAS) state progression.

While Plane 3 deterministically answers **"May this execution happen?"**, it hands off an approved `ExecutionGrant` to `DefaultToolExecutor`.

Under the current implementation, `DefaultToolExecutor` consumes the grant via `verify_and_consume()` and then executes:
```python
result = tool.execute(dict(parameters))
```
This tool invocation occurs **in-process within the host Python interpreter process of the security gateway server**.

---

## 2. Problem

In-process execution of authorized tools creates an unconstrained physical execution boundary. Once an `ExecutionGrant` is consumed, the executing tool inherits the entire operating context of the platform server:

1. **Ambient Credential & Secret Exposure:** The executing tool can read `os.environ`, exposing database connection strings (`POSTGRES_URL`), platform signing keys (`JWT_SECRET_KEY`), and host credentials.
2. **Host Filesystem Access:** Although `PolicyEngine` validates requested resource parameters logically, an in-process tool can bypass logical checks via uninspected file descriptors, internal imports, or relative navigation outside the application boundary.
3. **Unrestricted Network Egress:** Tools can initiate arbitrary outbound TCP/UDP sockets, enabling data exfiltration, Server-Side Request Forgery (SSRF), or command-and-control communication.
4. **Shared Address Space & Process Tampering:** A tool running in the same memory space can monkey-patch runtime services, manipulate internal singletons, or access thread locks.
5. **Denial-of-Service / Resource Exhaustion:** An uncontained tool can enter infinite CPU loops, allocate unbounded memory, spawn orphaned child processes, or block worker threads indefinitely.

**The core architectural problem:**  
Plane 3 protects the **decision** to execute. The platform currently has no architectural boundary to protect against the physical **consequences** of execution.

---

## 3. Architectural Invariant

This ADR establishes the following foundational invariant:

> **Core Invariant:**  
> An authorized tool execution must not inherit capabilities from the security platform process that are not explicitly granted by the execution context.
>
> **Non-Fallback Invariant:**  
> There must be no security-sensitive fallback path from the isolated execution boundary to in-process `tool.execute()`. If isolation is unavailable or fails, execution must fail closed.

---

## 4. Decision

The platform introduces an explicit **Runtime Execution Isolation** layer between authorization grant consumption and physical tool execution.

1. **Decouple Admission from Containment:** `ToolExecutor` remains the admission authority that verifies and consumes single-use `ExecutionGrant` tokens. Physical execution is delegated to an isolated `ToolExecutionSandbox`.
2. **Capability-Governed Execution:** Tool execution occurs inside a constrained environment configured strictly from frozen `ExecutionCapabilities`.
3. **Defense-in-Depth Isolation:** The sandbox enforces isolation across four independent dimensions:
   - Filesystem confinement (physical directory containment).
   - Environment scrubbing (explicit clean-room environment).
   - Network boundary (default-deny egress).
   - Process & resource caps (CPU, memory, timeout, process-group termination).
4. **No Secondary Authorization:** The sandbox does not evaluate policy or make security authorization decisions; it enforces the physical boundary for already-authorized executions.
5. **Fail-Closed Semantics:** Sandbox unavailability, resource exhaustion, or lifecycle faults result in execution failure and immutable audit recording. In-process fallback is strictly prohibited.

---

## 5. Trust Boundary

```text
[ UNTRUSTED ZONE ]
User Prompt ──► LLM (Untrusted Intent Parser) ──► ToolInvocation
                                                         │
                                                         ▼
[ DETERMINISTIC CONTROL PLANE - TRUSTED PLATFORM PROCESS ]
RuntimeService (Auth ──► Policy ──► Detection ──► Risk ──► Epoch CAS)
  │
  ├─► ExecutionAuthority.issue(grant) ──► Database (execution_grants table)
  │
  ▼
ToolExecutor.execute(grant, context)
  │
  ├─► verify_and_consume() [Row lock CAS: APPROVED ──► CONSUMED]
  │
  ▼
═══════════════════════════════════════════════════════════════════════════
 TRUST BOUNDARY: ToolExecutionSandbox Protocol Interface
═══════════════════════════════════════════════════════════════════════════
  │
  ▼
[ ISOLATED EXECUTION BOUNDARY - UNTRUSTED EXECUTION DOMAIN ]
ToolExecutionSandbox (Local Process / Container / MicroVM)
  ├── 1. Filesystem Jail (Read-Only / Bound Workspace)
  ├── 2. Clean-Room Environment (Stripped Secrets, Explicit Env Only)
  ├── 3. Default-Deny Network Egress
  ├── 4. Resource Ceilings (Memory, CPU, Output Truncation)
  └── 5. Lifecycle Guard (Hard Wall-Clock Timeout & Process-Group SIGKILL)
        │
        ▼
   Tool Runtime Process ──► Tool Implementation
```

---

## 6. Execution Flow

The end-to-end execution sequence preserves the existing security pipeline while isolating tool execution:

```text
1. Request Ingress        → ToolInvocation received by RuntimeService.
2. Authorization & Policy → Authenticates agent, checks tool permissions, validates arguments.
3. Capability Resolution  → Context resolves effective ExecutionCapabilities for (tool, agent, session).
4. Risk & Enforcement CAS → Evaluates detection horizon and records transition if needed.
5. Grant Issuance         → ExecutionAuthority issues ExecutionGrant bound to ExecutionCapabilities reference.
6. Dispatch to Executor   → ToolExecutor receives grant, tool descriptor, parameters, and runtime context.
7. Atomic Grant Claim     → ToolExecutor calls ExecutionAuthority.verify_and_consume() (CAS APPROVED → CONSUMED).
8. Evidence Recorded      → STARTED execution receipt recorded before sandbox invocation.
9. Sandbox Admission      → ToolExecutor passes tool, parameters, and ExecutionCapabilities to ToolExecutionSandbox.
10. Isolated Execution    → Sandbox constructs clean-room environment and dispatches execution.
11. Lifecycle Enforcement → Sandbox monitors execution duration, memory ceiling, and process hierarchy.
12. Result Capture        → Sandbox captures stdout, sanitized output digest, and exit status.
13. Complete & Audit      → Executor records COMPLETED / FAILED receipt and emits immutable audit event.
```

---

## 7. ExecutionCapabilities

To keep `ExecutionGrant` focused as a security evidence and continuation token, the detailed sandbox configuration is encapsulated in an immutable `ExecutionCapabilities` domain model.

```python
class FilesystemCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    read_only: bool = True
    workspace_root: str
    allowed_subpaths: tuple[str, ...] = ()
    allow_temp_writes: bool = False


class NetworkEgressMode(str, Enum):
    DISABLED = "disabled"
    ALLOWLIST = "allowlist"


class NetworkCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: NetworkEgressMode = NetworkEgressMode.DISABLED
    allowed_destinations: tuple[str, ...] = ()  # "host:port"


class ResourceLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_memory_bytes: int = 256 * 1024 * 1024  # 256 MB
    max_cpu_seconds: float = 5.0
    max_output_bytes: int = 1024 * 1024        # 1 MB
    wall_clock_timeout_seconds: float = 10.0


class ExecutionCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability_profile_id: str
    filesystem: FilesystemCapability
    environment_variables: Mapping[str, str] = {}
    network: NetworkCapability = NetworkCapability()
    resources: ResourceLimits = ResourceLimits()
```

---

## 8. ToolExecutionSandbox Protocol

The sandbox abstraction is defined as a runtime protocol decoupled from specific isolation technologies:

```python
class SandboxExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    output: Any | None = None
    output_digest: str | None = None
    exit_code: int = 0
    duration_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None
    resource_usage: Mapping[str, Any] = {}


class ToolExecutionSandbox(Protocol):
    """Protocol governing physical tool execution isolation."""

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        capabilities: ExecutionCapabilities,
        context: RuntimeContext,
    ) -> SandboxExecutionResult:
        """Execute an authorized tool within the isolated sandbox environment.

        Raises:
            SandboxUnavailableError: If sandbox backend is unconfigured or failed.
            SandboxResourceExhaustedError: If memory, CPU, or output limits breached.
            SandboxTimeoutError: If execution exceeds wall-clock deadline.
            SandboxIsolationError: If filesystem, environment, or egress policy violated.
        """
        ...
```

---

## 9. Isolation Dimensions

The sandbox enforces four independent isolation dimensions:

### 1. Filesystem Confinement
- **Logical vs. Physical:** Logical path validation in `PolicyEngine` verifies *whether* a file access is authorized. The sandbox enforces *physical access restrictions*.
- **Enforcement:** The tool process executes with its root or working directory restricted strictly to `workspace_root`. System paths (`/etc`, `/proc`, `/sys`, `/app`, `/home`) are physically unreachable.
- **Immutability:** Default filesystem access is read-only. Temporary writes (if permitted) are directed to an isolated ephemeral scratch directory discarded upon execution completion.
- **Trusted Bootstrap:** The working directory is pinned to `workspace_root`, so the child is launched with `-P` to keep that directory off `sys.path`. Without it, `python -m` prepends the working directory ahead of `PYTHONPATH`, and a workspace containing `app/runtime/sandbox/runner.py` would be imported *as* the runner — workspace-controlled code executing as the sandbox bootstrap, before the filesystem and network guards exist. The runner must resolve from the platform root alone; no check inside the runner can substitute, because the shadowing import happens first.

### 2. Environment & Secret Isolation
- **Clean-Room Baseline:** The tool process does **not** inherit `os.environ` from the platform server.
- **Scrubbing:** Platform secrets (`POSTGRES_URL`, `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, cloud credentials, API tokens) are unconditionally excluded from the environment.
- **Explicit Injection:** Only variables explicitly defined in `ExecutionCapabilities.environment_variables` are injected into the tool execution environment.

### 3. Network Boundary & Egress Policy
- **Three-Level Security Hierarchy:** Level 1 (Policy Authorization via `PolicyEngine`), Level 2 (Process-Level Enforcement via `NetworkSandboxGuard`), and Level 3 (Strong OS/Kernel Isolation via Container/MicroVM).
- **Default-Deny:** In the default `DISABLED` mode, outbound network socket creation and datagram transmissions (`connect`, `sendto`) are blocked.
- **Authoritative Enforcement Point:** Destination authorization is enforced at `socket.connect()` and `socket.sendto()` time using the actual resolved sockaddr. `getaddrinfo()` provides resolution observation but does not grant authorization.
- **Internal & Metadata Protection:** Loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), and cloud metadata (`169.254.169.254`) are unconditionally denied by the process backend.
- **AF_UNIX Separation:** Unix-domain sockets are governed independently from filesystem capabilities and denied by default.
- **Listener / Exposure Restriction:** `socket.bind()` is treated as listener creation and denied by default.
- **Proxy Scrubbing & No Socket Inheritance:** Proxy environment variables (`HTTP_PROXY`, `HTTPS_PROXY`, etc.) are stripped by default, and `close_fds=True` guarantees no parent sockets leak into the child process.
- **Explicit Allowlist:** In `ALLOWLIST` mode, connections are restricted strictly to declared `(host, port)` tuples using connection-time canonicalized IP checks, eliminating DNS rebinding and HTTP redirect SSRF bypasses.
- **Process-Level Boundary:** Enforces the declared network capability at supported Python networking boundaries (`urllib`, `requests`, `httpx`, `socket`, `asyncio`), reducing SSRF and unauthorized socket egress paths for standard Python tools without claiming kernel-level packet isolation.
- **DNS/Egress Abuse:** Standard Python socket-based DNS and network egress paths are subject to the process-level network guard. Native resolver behavior, native extensions, or raw syscalls remain outside the Level 2 security boundary and require Level 3 isolation.

### 4. Process & Resource Limits
- **CPU Limits:** Hard limits on total CPU execution time.
- **Memory Ceiling:** Memory allocation capped to prevent host memory exhaustion.
- **Hard Timeout:** Monotonic wall-clock deadline enforced via external timer.
- **Output Buffering:** `stdout` and `stderr` streams capped to `max_output_bytes` to prevent memory flooding.
- **Process Cleanup:** Tool execution spawns in a dedicated OS process group (`setpgrp` / `setsid`). Upon completion, timeout, or failure, the entire process hierarchy is terminated (`SIGTERM` followed by `SIGKILL`) to eliminate orphaned background processes.

---

## 10. Grant / Sandbox Capability Binding

To prevent grant bloat while guaranteeing immutability:

1. **Grant Binding:** `ExecutionGrant` references the immutable capability set via `execution_capability_ref` (or SHA-256 `capability_digest`).
2. **Snapshot Immutability:** The effective `ExecutionCapabilities` are evaluated and frozen during the pipeline's authorization phase.
3. **No Re-Evaluation:** The sandbox accepts the pre-evaluated capability snapshot. It does not look up dynamic, mutable policies at execution time.
4. **Tamper Detection:** If the capability reference or digest presented to `ToolExecutor` does not match the authority record, execution fails closed with `ExecutionBindingError`.

---

## 11. Failure Semantics

The isolation boundary adheres to strict fail-closed principles:

```text
                              Execution Request
                                     │
                                     ▼
                        [ Sandbox Available? ]
                                     │
                   ┌─────────────────┴─────────────────┐
                  YES                                 NO
                   │                                   │
                   ▼                                   ▼
        [ Execute in Sandbox ]              [ FAIL CLOSED ]
                   │                        Execution Refused
         ┌─────────┴─────────┐              Reason: SANDBOX_UNAVAILABLE
      SUCCESS              FAILURE          (No in-process fallback!)
         │                   │
         ▼                   ▼
    Record STARTED      Record FAILED
    + COMPLETED         Reason: TIMEOUT / OOM / VIOLATION
    Evidence            Evidence
```

1. **No In-Process Fallback:** Under no circumstance does the platform fall back to in-process `tool.execute()` if the sandbox is unavailable, uninstalled, or failing.
2. **Sandbox Error Translation:** Sandbox errors are translated into deterministic `ToolExecutionError` categories:
   - `SandboxTimeoutError` $\to$ Execution timeout.
   - `SandboxResourceExhaustedError` $\to$ OOM or CPU quota breach.
   - `SandboxUnavailableError` $\to$ Infrastructure or admission refusal.
   - `SandboxIsolationError` $\to$ Filesystem escape or egress violation.
3. **Governance Independence:** Execution failure does not retroactively alter the pipeline's prior `ALLOW` authorization decision; it records an authoritative execution failure receipt.

---

## 12. Audit & Evidence

Execution evidence records what the execution boundary **observed**. It is not an
authorization mechanism: the grant decides whether an execution may cross the boundary,
and the receipt records what happened when it did. Reconciliation resolves evidence
whose outcome was never observed; it never authorizes, denies or reinterprets an
execution.

```text
SECURITY EXECUTION BOUNDARY          EVIDENCE / RECOVERY BOUNDARY
  AuthorizationResult                  ExecutionReceipt
        ↓  decision                          ↑  observation
  ExecutionGrant                       ExecutionEvidenceService
        ↓  authority                         ↑
  DefaultToolExecutor  ──────────────────────┘
        ↓
  ProcessToolExecutionSandbox           ExecutionReconciler
                                        resolves unobserved outcomes
```

### 12.1 Two-axis outcome and integrity model

Execution outcome and evidence persistence are **independent axes** and are never
collapsed. *Execution outcome* is what happened in the sandbox; *evidence integrity* is
whether the platform recorded it.

| Execution | Terminal evidence | Result |
|---|---|---|
| succeeded | recorded | `SUCCEEDED` |
| succeeded | **failed** | **integrity failure**, never a successful completed execution |
| failed | recorded | the execution failure |
| failed | **failed** | the execution failure remains **primary**; the integrity failure is retained as secondary information on it |

- **STARTED persistence failure prevents execution.** If STARTED evidence cannot be
  recorded the sandbox is not invoked, so no side effect exists. A pre-execution
  fail-closed condition, distinct in type from a post-execution integrity failure —
  the difference between an execution that was prevented and one that happened and was
  not recorded.
- **Terminal persistence failure cannot be rolled back.** The execution occurred, so it
  is never reported as success; where the execution itself also failed, an evidence
  fault must not erase the outcome it was trying to record.
- Evidence errors are **not** sandbox errors. An isolation failure and a failure to
  record are different things; collapsing them would categorise an evidence fault as an
  `ISOLATION_FAILURE` in the very receipt that could not be written.

### 12.2 Receipt correlation and provenance

| Field | Role |
|---|---|
| `receipt_id` | evidence identity |
| `grant_id` | **authoritative execution-authority identity** — the bridge between authorization and execution |
| `agent_id`, `session_id` | security identity, read from the verified grant |
| `request_id` | correlation only; never authority, and deliberately distinct from `grant_id` |
| `binding_hash` | the operation the decision covered |
| `capability_profile_id`, `capability_digest` | the capability set that governed the execution |
| `declared_timeout_seconds` | the wall-clock limit that applied to this execution |
| `output_digest` | SHA-256 of normalized output, linking the recorded result to the receipt |

Provenance derives **exclusively from the verified grant**, whose signature covers the
identity fields. A caller-supplied `RuntimeContext` is unsigned and contributes
`request_id` only; a context contradicting the grant is refused as `IDENTITY_MISMATCH`
before the grant is consumed (ADR-023). A receipt must identify the capability profile
and digest that governed its execution, so those fields are required: a receipt that
cannot say what an execution was permitted to do is not evidence of it.

### 12.3 Per-receipt reconciliation deadline

Reconciliation evaluates each receipt against the limit that governed **that**
execution. There is no global or default execution SLA.

```text
execution_deadline      = started_monotonic + receipt.declared_timeout_seconds
reconciliation_deadline = execution_deadline + recovery_grace
```

Two clocks, never summed into one: the execution timeout answers *how long may this
execution legitimately run*, the recovery grace answers *how long after that limit
before the outcome is unrecoverable*. A deadline shorter than a capability's declared
timeout would let the platform assert a timeout that had not occurred, and then refuse
the genuine terminal transition under N3-4 — manufacturing an execution outcome.

### 12.4 Reconciliation concurrency

Reconciliation operates on a snapshot of open receipts, so:

- A receipt that reached a terminal state **between snapshot and transition** is an
  expected race and the better outcome — the execution reported its own result. It is
  skipped: never forced to `UNKNOWN`, and never counted as a reconciliation.
- An **unexpected** per-receipt failure is isolated and observed; the batch continues.
  One bad record must not become a batch-wide availability failure.
- **Timing-contract violations stay visible.** A store that cannot report a receipt's
  monotonic start is a contract violation and fails loudly; it is not silently treated
  as "this execution is unrecoverable". `None` from a conforming store means the timing
  is genuinely missing, which is itself reconcilable.

### 12.5 Bounded retention

Bounded terminal retention is **mandatory** for the production evidence writer; capacity
is a deployment decision and carries no domain default.

- Terminal receipts are retained up to the configured capacity, **oldest first by
  `started_at`** once exceeded.
- `UNKNOWN` is terminal and therefore evictable.
- **`STARTED` receipts are never normal retention candidates.** They are the reconciler's
  only input, so evicting one would convert a reconcilable unknown into a silently lost
  execution. Their accumulation is an operational signal about evidence health, not
  something retention should absorb.
- Eviction prunes every structure keyed by the receipt, so the bound applies to the
  whole in-memory evidence state rather than to one index.

### 12.6 Startup recovery boundary

```text
process startup → live evidence reconciliation → reconciliation succeeds
    → application ready → execution permitted
```

Recovery runs in the application lifespan, synchronously with respect to readiness: the
application serves no request until it returns, so no live execution enters the
execution boundary while stale `STARTED` receipts are unresolved. It is not run at
import time, which would make lifecycle ordering an accidental consequence of module
import order. **A reconciliation failure prevents startup** — coming up anyway would
serve requests against an unrecovered evidence plane.

The reconciler is constructed in the composition root against the one live store, so
startup cannot build a second evidence plane that would report a clean recovery while
the executor's store still held unresolved receipts.

### 12.7 Scenario isolation (ADR-013 M2a)

Scenario execution evidence is real execution evidence but **not live production
security state**. Each scenario run receives its own evidence store, constructed with
the sandbox it belongs to.

```text
live runtime      → live evidence store
scenario sandbox  → its own per-run evidence store

no shared store · no promotion · no fallback
```

There is no path — no discovery, no global, no "use the live store if none was
supplied" — by which scenario execution reads or writes live evidence, and nothing
promotes, copies or synchronises receipts between the planes. Omitting a store leaves an
executor without one rather than resolving to the live plane. This extends M2a to the
evidence plane; the M2a telemetry boundary is unchanged.

### 12.8 Execution evidence invariants

| ID | Invariant |
|---|---|
| N3-1 | **Provenance.** Identity and binding derive exclusively from the verified grant. |
| N3-2 | **Grant/Execution Separation.** Consuming a grant does not imply execution started or succeeded. |
| N3-3 | **Trusted Boundary.** STARTED evidence is established before the sandbox is invoked; a store failure fails closed and the sandbox is not executed. |
| N3-4 | **Terminal Monotonicity.** Terminal execution states are immutable and cannot be transitioned again. |
| N3-5 | **Reconciliation Authority.** Only the reconciliation layer may transition an unresolved execution to `UNKNOWN`. |
| N3-6 | **Evidence/Telemetry Separation.** The evidence store is authoritative; telemetry is an operational projection that fails silent — except the evidence-integrity signal, which is never routed through the fail-silent path, because discarding it would drop the one signal saying the platform cannot account for an execution that happened. A telemetry fault is recorded rather than raised, so it never becomes an execution or evidence failure. |
| N3-7 | **Diagnostic Safety.** Raw exception messages are excluded from evidence and from operational logs; only controlled `error_type` and `error_code` are recorded. |
| N3-8 | **Governance Independence.** Execution failure does not mutate the prior ALLOW decision. |
| N3-9 | **Grant Receipt Uniqueness.** One receipt per `grant_id`, over *retained* evidence state. This is a provenance property of the evidence index, not the mechanism preventing re-execution: single-use grant consumption in `ExecutionAuthority` is that, and it holds whether or not the receipt is still retained. |
| N3-10 | **UTC Evidence Time.** Evidence timestamps are timezone-aware UTC. |
| N3-11 | **Per-Receipt Elapsed Time.** Monotonic start is tracked per receipt and reconciliation derives its deadline from the timeout declared for that execution (§12.3). |

### 12.9 Lifecycle observability

| Counter | Kind | Meaning |
|---|---|---|
| `open_receipt_count` | derived | receipts currently in `STARTED` |
| `terminal_receipt_count` | derived | retained terminal receipts, including `UNKNOWN` |
| `evidence_failure_count` | counted | evidence **persistence** failures, never execution failures |
| `reconciled_unknown_count` | counted | executions reconciliation actually resolved to `UNKNOWN` |

The first two are derived from authoritative state so no lifecycle or eviction path can
leave them disagreeing with the receipts. The other two are events rather than
populations: an evidence failure leaves no receipt, and a reconciled `UNKNOWN` remains a
fact about what reconciliation did after its receipt is evicted. The expected
self-resolution race (§12.4) is deliberately not counted as an evidence failure.

### 12.10 Persistence scope

The evidence plane is **production-wired, not durably persisted**. Its persistence
characteristics are those of the configured store implementation; the current
implementation is in-memory, so a process restart begins with an empty plane and startup
reconciliation finds nothing to resolve. Relational persistence of execution evidence is
**not** part of this plane and is not covered by
[ADR-030](ADR-030-durable-state-repository-architecture.md), which governs the durable
security state plane. Production-wired does not mean durable across restart.

---

## 13. Security Threats & Threat-Model Updates

This ADR adds the following explicit threat scenarios to the platform Threat Model:

| Threat ID | Threat Description | Architectural Mitigation |
|---|---|---|
| **THREAT-SEC-01** | **Host Secret Extraction:** Malicious tool reads `os.environ` to exfiltrate `POSTGRES_URL` or `JWT_SECRET_KEY`. | Clean-room environment scrubbing; zero secret inheritance. |
| **THREAT-SEC-02** | **Host Filesystem Escape:** Tool attempts path traversal or direct `/etc` inspection. | Sandbox filesystem confinement; workspace jail. |
| **THREAT-SEC-03** | **Data Exfiltration via Egress:** Tool establishes outbound TCP connection to external server. | Default-deny network egress policy. |
| **THREAT-SEC-04** | **Denial-of-Service / Infinite Loop:** Tool monopolizes CPU or memory indefinitely. | OS process resource limits and hard wall-clock timeout. |
| **THREAT-SEC-05** | **Orphaned Process Persistence:** Tool forks background daemon that survives session termination. | Process-group termination (`SIGTERM`/`SIGKILL` across process tree). |
| **THREAT-SEC-06** | **Sandbox Bypass Fallback:** Attacker disables sandbox to force in-process execution fallback. | Non-fallback invariant: platform fails closed on sandbox unavailability. |

---

## 14. v0.17 Scope (MVP)

The initial `v0.17` milestone delivers a production-grade, hermetic local process boundary:

1. **Domain Abstractions:** `ExecutionCapabilities`, `FilesystemCapability`, `NetworkCapability`, `ResourceLimits`, `SandboxExecutionResult`.
2. **Sandbox Protocol:** `ToolExecutionSandbox(Protocol)` integrated with `DefaultToolExecutor`.
3. **Local Process Sandbox (`ProcessToolExecutionSandbox`):**
   - Independent subprocess execution via clean Python worker runner.
   - Environment scrubbing (removes all host secrets; allowlist only).
   - Enforced workspace directory confinement.
   - Dedicated process group with guaranteed cleanup on exit/timeout.
   - Hard wall-clock execution deadline.
   - Output buffer truncation and exit code normalization.
4. **Fail-Closed Wiring:** `DefaultToolExecutor` requires a configured sandbox; missing sandbox fails closed.
5. **Contract Test Suite:** Test suite verifying environment scrubbing, directory confinement, timeout enforcement, process group cleanup, and failure closed on error.

### Architectural Reality: ProcessToolExecutionSandbox ≠ Strong Hostile-Code Sandbox

The `v0.17` implementation establishes process-level execution isolation and capability restriction. It explicitly does not claim protection against a malicious native process, kernel exploit, or a sufficiently privileged sandbox escape.

The initial implementation bounds the blast radius of standard agent tools and prevents ambient credential/filesystem inheritance. It preserves the clean `ToolExecutionSandbox` protocol interface so that hardened container (`ContainerToolExecutionSandbox`) or microVM (`MicroVMToolExecutionSandbox`) backends can be introduced in subsequent milestones without altering platform governance.

### Process Sandbox Security Boundary

The v0.17 process sandbox provides process-level capability enforcement for standard Python execution. It is not a kernel-level hostile-code sandbox. Native extensions, raw syscalls, privileged operations, and kernel-level escape techniques are outside this boundary. Strong isolation of hostile or arbitrary native code requires a future container or microVM backend.

---

## 15. Explicit Non-Goals for v0.17

To prevent premature infrastructure bloat, the following are explicitly out of scope for v0.17:

- **No Container Daemon Dependency:** The test suite and core platform must not require a running Docker, Podman, or Kubernetes daemon.
- **No MicroVM / Hardware Virtualization:** Firecracker, gVisor, and Kata Containers are deferred to future sandbox backends.
- **No In-Kernel eBPF Filtering:** Kernel-level syscall interception is deferred.
- **No Distributed Workload Scheduler:** Subprocess execution is managed locally by the gateway node.
- **No Dynamic DLP:** Deep packet inspection of allowed network traffic is deferred.

---

## 16. Future Sandbox Backends

The `ToolExecutionSandbox` protocol enables seamless adoption of alternative isolation backends without altering platform governance:

```text
                    ToolExecutionSandbox (Protocol)
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
ProcessToolExecutionSandbox  ContainerSandbox          MicroVMSandbox
    (v0.17 Local MVP)     (Docker / Podman / Kube)   (Firecracker / gVisor)
```

---

## 17. Alternatives Considered

### Alternative A: In-Process Thread Isolation & Mocking
- **Description:** Run tools in Python threads with mocked `os.environ` and monkey-patched `builtins.open`.
- **Rejected:** Python threads share global interpreter state, memory space, and file descriptors. Threads cannot be forcefully terminated on timeout (`thread.stop()` does not exist in Python). Any native C extension can bypass Python-level monkey-patching.

### Alternative B: Mandatory Docker / Kubernetes Container per Tool
- **Description:** Require every tool invocation to spin up an ephemeral Docker container or Kubernetes pod.
- **Rejected:** Introduces multi-second cold-start latency (1–3 seconds per tool call), breaks hermetic developer setup, requires root/docker-socket privileges on the host, and complicates local testing.

### Alternative C: WASM Runtime (e.g. Wasmtime)
- **Description:** Compile and execute tools as WebAssembly binaries.
- **Rejected:** Severe ecosystem friction. Standard Python tools (e.g., Pandas, Requests, OS integrations) cannot be easily compiled to WASI without custom toolchains.

---

## 18. Consequences

### Positive
- **Drastic Reduction in Blast Radius:** A compromised tool or model prompt cannot read gateway credentials or compromise the server process.
- **Safe Tool Ecosystem Expansion:** The platform can safely introduce shell, code execution, file write, and network tools in subsequent releases.
- **Clean Architecture:** Decouples authorization logic from physical execution containment.
- **Testable Security:** Environment scrubbing, timeouts, and filesystem restrictions can be deterministically tested.

### Negative
- **Subprocess Overhead:** Spawning an isolated subprocess introduces a modest execution latency (10–30 ms) compared to raw method calls.
- **Parameter Serialization:** Tool parameters and outputs must be serializable (e.g. JSON/IPC) across process boundaries.

---

## 19. Implementation Constraints

1. **Python 3.13+ Compatibility:** Implementation must use modern Python standard library constructs (`subprocess`, `os.set_inheritable`, `signal`, `resource`).
2. **Zero In-Process Fallback:** Code reviews must enforce that no path catches a sandbox exception and calls `tool.execute()` in-process.
3. **Deterministic Testing:** Tests must use hermetic temporary workspaces and mock executors to guarantee sub-second execution without flaky timing races.

---

## 20. Test & Acceptance Requirements

The `v0.17` implementation must satisfy the following acceptance tests:

1. **Environment Scrubbing Test:** An executed tool attempting to read `os.environ["POSTGRES_URL"]` or `os.environ["JWT_SECRET_KEY"]` receives `KeyError` or empty string.
2. **Filesystem Confinement Test:** An executed tool attempting to read files outside the designated workspace (e.g. `/etc/passwd` or parent directories) is physically blocked.
3. **Hard Timeout Test:** A tool executing an infinite loop is killed cleanly within the configured deadline, and the executor records a `TIMEOUT` failure receipt.
4. **Process Cleanup Test:** A tool spawning child background processes has all descendants terminated when execution finishes.
5. **Sandbox Unavailable Fail-Closed Test:** Invoking `ToolExecutor` without a valid sandbox fails closed with `ExecutionRefusalReason.SANDBOX_UNAVAILABLE`.
6. **No-Fallback Invariant Test:** Static analysis or unit tests verify that no exception path in `ToolExecutor` falls back to `tool.execute()`.
