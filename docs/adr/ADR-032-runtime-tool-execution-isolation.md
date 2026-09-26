# ADR-032: Runtime Tool Execution Isolation

**Status:** Approved

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

### 2. Environment & Secret Isolation
- **Clean-Room Baseline:** The tool process does **not** inherit `os.environ` from the platform server.
- **Scrubbing:** Platform secrets (`POSTGRES_URL`, `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, cloud credentials, API tokens) are unconditionally excluded from the environment.
- **Explicit Injection:** Only variables explicitly defined in `ExecutionCapabilities.environment_variables` are injected into the tool execution environment.

### 3. Network Boundary & Egress Policy
- **Default-Deny:** In the default `DISABLED` mode, outbound network socket creation is blocked.
- **Explicit Allowlist:** When `ALLOWLIST` is configured, connections are restricted strictly to declared `(host, port)` tuples.
- **No Socket Inheritance:** Open sockets and database connection handles belonging to the parent gateway process are closed before tool execution.

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

Every sandbox execution interaction is correlated with platform audit logs:

1. **Execution Evidence (`ExecutionEvidenceStore`):**
   - `record_started()`: Captures `receipt_id`, `grant_id`, `tool_id`, `binding_hash`, and start timestamps.
   - `record_completed()`: Captures `output_digest`, execution duration, and resource utilization metrics.
   - `record_failed()`: Captures normalized error codes, duration, and termination signal without leaking un-sanitized process stack traces.
2. **Audit Subsystem Correlation:** Audit events generated by `AuditService` include the `receipt_id`, `grant_id`, and `capability_profile_id`.

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
