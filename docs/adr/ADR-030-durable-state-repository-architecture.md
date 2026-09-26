# ADR-030: Durable State Repository Architecture

**Status:** Proposed

**Date:** 2026-09-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Proposed for `v0.16.0` (Phase 1 Architecture Foundation)

---

# Context

The runtime security pipeline establishes deterministic enforcement, structured authorization evidence, and correlated audit attribution across single-turn and scenario executions ([ADR-004](ADR-004-deterministic-security-pipeline.md), [ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)).

However, existing service implementations (`AgentService`, `ToolService`, `AuditService`, `SessionService`) manage security state primarily via in-memory collections protected by `RLock`.

This model exposes critical operational and security weaknesses in enterprise production deployments:

1. **Enforcement State Volatility:** When an agent is placed into `SUSPEND_AGENT` enforcement posture ([ADR-024](ADR-024-agent-enforcement-state.md)), restarting the runtime process or cycling a container resets the agent’s posture back to `ACTIVE`. An adversary who triggers an automated suspension can deliberately clear it by forcing a service restart.
2. **Detection Horizon Evasion:** Behavioral accumulation rules (e.g. `EXCESSIVE_DENIALS`, [ADR-017](ADR-017-behavioral-detection-engine.md)) evaluate events across a temporal horizon. In-process event stores reset on restart, allowing slow or distributed evasion attacks to bypass detection thresholds by spanning process restarts.
3. **Audit Evidence Durability:** Correlated audit evidence ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)) held in memory lacks enterprise durability. Evidence correctness has been achieved, but evidence durability requires persistence decoupled from the process heap.
4. **Multi-Instance Split-Brain:** In horizontally scaled deployments (multiple runtime replicas behind a load balancer), independent in-memory stores cannot synchronize enforcement decisions, configuration updates, or detection horizons. Replicas operating on divergent state make conflicting security decisions.

These vulnerabilities cannot be addressed by treating all platform data as a single generic "database". As demonstrated in [ADR-027 (State Lifecycle Decomposition)](ADR-027-state-lifecycle-decomposition.md), different state categories have fundamentally different write semantics, lifecycles, and security invariants.

---

# Decision

The platform adopts a formal **Durable State Repository Architecture** that decouples security domain logic from persistence mechanisms via strict, typed repository protocols.

```text
                  Security Domain Services
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
AgentRepository         AuditEvidenceRepo      EnforcementStateRepo
ToolRepository                                 SessionHorizonRepo
PolicyRepository
     │                       │                       │
     └───────────────────────┼───────────────────────┘
                             ▼
                 Domain Repository Protocols
                             │
             ┌───────────────┴───────────────┐
             ▼                               ▼
   InMemoryAdapter (Tests)         SQLRepositoryAdapter
                                   ├── SQLite (Local Dev)
                                   └── PostgreSQL (Production)
```

## 1. Domain State Taxonomy

Platform state is decomposed into five distinct operational planes with explicit lifecycle boundaries:

| State Plane | Authoritative Entity | Write Semantics | Lifecycle / Retention | Security Role |
| :--- | :--- | :--- | :--- | :--- |
| **1. Configuration Plane** | `Agent`, `Tool`, `SecurityPolicy` | Low-frequency admin mutations | Permanent until explicitly retired | Authorizes identity, capability allowances, and static RBAC |
| **2. Audit Evidence Plane** | `AuditEvent` ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)) | Strict append-only | Permanent / Compliance tiering | Authoritative forensic evidence of all security decisions |
| **3. Enforcement State Plane** | `AgentEnforcementState`, `EnforcementEpoch` ([ADR-026](ADR-026-materialized-risk-projection-and-enforcement-epochs.md)) | Compare-and-set atomic update | Dynamic active state per agent | Authoritative dynamic security posture (`ACTIVE`, `SUSPENDED`) |
| **4. Detection Horizon Plane** | `SessionEvent` ([ADR-027](ADR-027-state-lifecycle-decomposition.md)) | Append + temporal prune | Bounded rolling horizon window | Sliding window for multi-turn accumulation rules (`EXCESSIVE_DENIALS`) |
| **5. Control-Plane Resumption** | `ExecutionGrant` ([ADR-031](ADR-031-execution-grant-approval-control-plane.md)) | Compare-and-set state transition (`PENDING -> APPROVED / REJECTED / EXPIRED -> CONSUMED`) | Bounded TTL (e.g. 15 minutes) | Bound authority token permitting one-shot execution after human review |

## 2. Repository Protocol Boundaries

Domain services interact exclusively with repository protocols defined in `app/repositories/interfaces/`. Database drivers and ORM models are forbidden from leaking into the domain layer.

### A. Configuration Repositories
Explicit domain repositories are established for each configuration entity:
- **`AgentRepository`**: Manages agent identity, lifecycle status, risk allowances, and registered capabilities.
- **`ToolRepository`**: Manages registered tool definitions, parameters, risk tiers, and availability flags.
- **`PolicyRepository`**: Manages resource policies and static authorization rules.

Domain-specific query methods (such as active filtering) are defined per domain interface rather than imposed as generic constraints across all entities.

### B. Audit Evidence Repository (`AuditEvidenceRepository`)
Owns the persistence of `AuditEvent` records per [ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md):
- `append(event: AuditEvent) -> None`
- `get_by_id(event_id: str) -> AuditEvent | None`
- `query(session_id: str | None, agent_id: str | None, limit: int, offset: int) -> list[AuditEvent]`
- **Invariants:**
  - **No `update()` or `delete()` methods exist on this interface.**
  - Every record includes `session_id`, `agent_id`, `decision`, and `timestamp` to ensure complete attribution independence from shorter-lived session event state.
  - Repository-level append-only semantics enforce application immutability, but do not by themselves establish cryptographic tamper-evidence against privileged database operators. Independent verifiability is required as an architectural invariant, with concrete cryptographic mechanisms (such as hash chaining or external signature authorities) evaluated separately.

### C. Enforcement State Repository (`EnforcementStateRepository`)
Owns dynamic agent posture and monotonic epoch progression per [ADR-024](ADR-024-agent-enforcement-state.md) and [ADR-026](ADR-026-materialized-risk-projection-and-enforcement-epochs.md):
- `get_state(agent_id: str) -> AgentEnforcementState | None`
- `record_transition(transition: EnforcementTransition, new_state: AgentEnforcementState, *, expected_epoch: int) -> bool`
- `list_transitions(agent_id: str | None = None) -> list[EnforcementTransition]`
- `get_epoch(agent_id: str, *, as_of: datetime) -> int`
- **Invariants:**
  - **Direct Epoch Authority:** `AgentEnforcementState.epoch` is persisted directly on the state entity; optimistic concurrency does not depend on derived history counts.
  - **Strict CAS Concurrency:** Updates succeed if and only if `expected_epoch == persisted_epoch` AND `new_state.epoch == expected_epoch + 1`.
  - **Single-Transaction Atomicity:** State update and transition ledger append are committed together atomically. If CAS or validation fails, neither record is persisted.
  - **Fail-Closed Availability:** Storage or infrastructure exceptions are normalized to `EnforcementStateUnavailableError` at the boundary. The authorization gate catches this and deterministically returns `Decision.DENY` without issuing execution grants.
  - **Pristine State Isolation:** An uninitialized agent (`get_state(...) is None`) indicates pristine status with no dynamic containment, proceeding normally to administrative status evaluation.

### D. Detection Horizon Repository (`SessionEventHorizonRepository`)
Maintains the authoritative behavioral evidence required for multi-turn behavioral detection per [ADR-027](ADR-027-state-lifecycle-decomposition.md), decoupled from session lifecycle state via role-specific protocols backed by a unified atomic adapter:
- `record_event(event: SessionEvent) -> SessionEvent`
- `list_eligible_events(query: HorizonQuery) -> list[SessionEvent]`
- `prune_events(before_timestamp: datetime) -> int`
- `update_event_final_decision(session_id: str, sequence_number: int, final_decision: Decision) -> None`
- **Invariants:**
  - **Dual Monotonic Positioning:** Every recorded event receives two immutable sequences assigned exclusively by the repository:
    - `sequence_number`: Session-local strictly monotonic sequence (`1..N`), used for session reconstruction and intra-session detection.
    - `agent_sequence`: Agent-scoped monotonic sequence (increasing, non-gapless across sessions), used for cross-session detection and enforcement baseline watermarks.
  - **Dual-Scoped Horizon Queries:** Supports both `AggregationScope.SESSION` (isolated to a session) and `AggregationScope.AGENT` (cross-session aggregation per agent).
  - **Snapshot Temporal Semantics:** Evaluates events bounded strictly by $[T_{\text{eval}} - W, T_{\text{eval}}]$, excluding future-dated events to prevent clock skew leakage.
  - **Watermark Isolation:** Evaluates only active events strictly newer than the agent's baseline watermark (`agent_sequence > query.baseline_agent_sequence`), preventing pre-recovery history from triggering false re-containment.
  - **Pruning Invariant:** Bounded retention pruning deletes events older than the retention threshold without resetting or modifying sequence counters.
  - **Fail-Closed Repository Boundary:** Repository exceptions normalize to `SessionRepositoryError` / `HorizonUnavailableError`, causing the runtime pipeline to fail closed (`HORIZON_UNAVAILABLE`) without granting execution authority.
  - **Stale Context Interlock:** Execution grant issuance validates `expected_epoch` under lock via `ExecutionAuthority.issue(...)` to prevent issuance on stale enforcement context.

### E. Approval Grant Repository (`ApprovalGrantRepository`)
Owns the lifecycle and atomic resumption of human-in-the-loop approval grants per [ADR-031](ADR-031-execution-grant-approval-control-plane.md):
- `create_grant(grant: ExecutionGrant) -> None`
- `get_grant(grant_id: str) -> ExecutionGrant | None`
- `transition_grant(grant_id: str, *, from_state: GrantState, to_state: GrantState, consumed_at: datetime | None = None, approved_by: str | None = None) -> bool`
- `list_grants(*, agent_id: str | None = None, state: GrantState | None = None) -> list[ExecutionGrant]`
- **Invariants:**
  - **Canonical State Machine:** Strict transitions only: `PENDING -> APPROVED | REJECTED | EXPIRED`, and `APPROVED -> CONSUMED`. Every other transition raises `InvalidGrantTransitionError`.
  - **Exactly-Once Execution Claim:** Transitioning from `APPROVED` to `CONSUMED` is an atomic compare-and-set operation executed under row-level locking (`SELECT ... FOR UPDATE`). Out of $N$ concurrent workers racing to claim an approved grant, exactly one succeeds; all others receive `False` and halt immediately.
  - **Zero Untrusted Re-Prompting:** Execution resumption uses the deeply frozen `grant.execution_parameters` directly; user prompts and intent parsing are never re-evaluated.
  - **Deep Immutability & Object Isolation:** Stored and returned grants are defensive deep copies isolated from ORM session lifecycles.

## 3. Multi-Adapter Strategy & Backend Roles

To preserve fast, deterministic local testing while supporting robust enterprise deployments, the architecture enforces a strict three-tier backend role separation:

1. **`InMemoryAdapter`:**
   - Pure Python collections protected by thread-safe synchronization (`RLock`).
   - Role: Process-local concurrency semantics, sub-second hermetic unit testing, and isolated sandbox benchmarks.
   - External dependencies: Zero.
2. **`SQLiteAdapter` (SQLAlchemy 2.0+):**
   - Relational persistence with foreign keys explicitly enforced (`PRAGMA foreign_keys=ON;`).
   - Role: Functional, single-node persistence, local developer workflows, and parameterized contract-suite validation.
   - Concurrency role: Validates single-worker transactional contracts; not an MVCC concurrency authority.
3. **`PostgreSQLAdapter` (SQLAlchemy 2.0+ & psycopg v3):**
   - Production connection-pooled relational persistence.
   - Role: The concurrency authority for the production SQL adapter and the authoritative environment for multi-worker MVCC row-locking verification.

## 4. Core Durable Architectural & Concurrency Invariants

The SQL repository layer implements the following explicit security invariants:

1. **Parent-Row Serialization Anchors:**
   When child or counter rows may not yet exist (such as pristine `agent_enforcement_state` or `agent_sequence_counters`), row-level locks on the child table cannot take effect. The repository serializes creation and concurrent mutations by locking the authoritative parent row (`agents` locked `FOR UPDATE`) before querying, inserting, or modifying child entities.
2. **Monotonic Enforcement Epoch Progression:**
   Enforcement state updates enforce strict compare-and-set progression (`expected_epoch == current_epoch` and `new_state.epoch == expected_epoch + 1`). State mutation and transition ledger append commit together in a single atomic transaction. Stale concurrent writers fail closed.
3. **Dual Sequence Allocation:**
   Every session event receives two immutable, monotonically increasing sequences:
   - `sequence_number`: Session-local, strictly monotonic sequence (`1..N`).
   - `agent_sequence`: Agent-scoped, monotonic, non-gapless sequence across all sessions of the agent.
   Allocations are strictly repository-owned; caller-supplied sequences are rejected.
4. **Detection Horizon Watermarking & Pruning:**
   Behavioral detection rules query sliding windows $[T_{\text{eval}} - W, T_{\text{eval}}]$ bounded strictly by `agent_sequence > baseline_agent_sequence`. Bounded retention pruning deletes events older than the threshold without resetting sequence counters.
5. **Exactly-Once Grant Consumption:**
   Grant consumption is an atomic CAS transition from `APPROVED` to `CONSUMED` under row-level locking (`FOR UPDATE`). Replay attacks across horizontal workers are physically serialized and rejected by the database.
6. **Authorization / Enforcement Interlock:**
   Grant issuance verifies `expected_epoch` under `agent_enforcement_state` row lock (`FOR UPDATE`). Concurrent agent containment transitions serialize cleanly against grant issuance; a request authorized against a pre-suspension epoch cannot obtain an execution grant.
7. **PostgreSQL as Concurrency Authority:**
   Multi-worker concurrency semantics (MVCC row locks, CAS ordering, interlock serialization) are verified through 7 live PostgreSQL 16 race tests (`tests/repositories/sql/test_sql_*concurrency_postgres.py`).
8. **Redis Excluded from Critical Path:**
   Redis is explicitly excluded from the v0.16 critical security state path to prevent memory eviction and split-brain containment bypass. Relational persistence provides ACID durability; Redis remains evaluated solely for optional, non-authoritative read caching post-v0.16.

## 5. Repository Contract Test Suite

To ensure that `InMemoryAdapter`, `SQLiteAdapter`, and `PostgreSQLAdapter` are semantically interchangeable, all adapters must execute and pass an identical parameterized **Repository Contract Test Suite** (`tests/repositories/test_contract.py`).

The contract suite validates:
- Optimistic concurrency and compare-and-set epoch progression.
- Strict append-only behavior and immutability guards in audit storage.
- Atomic state transitions and isolation across concurrent threads/connections.
- Correct temporal query filtering and pruning of detection horizon events.
- Deterministic recovery and state survival across repository re-instantiation (restart simulation).

---

# Rationale

1. **Separation of Concerns:** Security engines (authorization, detection, risk, response) must remain pure domain logic. Decoupling persistence into repository protocols ensures that storage mechanics (SQL dialect, connection pools, serialization) never leak into security-critical decision paths.
2. **Preventing Split-Brain Security Failures:** Multi-instance deployments cannot rely on in-memory locks. Atomic compare-and-set operations with strictly increasing epochs prevent conflicting enforcement decisions across replicas.
3. **Audit Integrity:** Isolating audit evidence into an append-only protocol guarantees that platform code cannot overwrite or prune forensic history during operational maintenance.
4. **Testability & Determinism:** The dual-adapter model ensures that unit tests run in milliseconds without spin-up overhead, while contract tests guarantee that the production database behaves identically.

---

# Alternatives Considered

## 1. Single Generic StateRepository
- **Approach:** Create a unified `StateRepository` handling key-value or document persistence for all entities.
- **Why Rejected:** Obscures critical lifecycle differences. Audit evidence requires strict append-only semantics; enforcement requires compare-and-set epochs; configuration requires read-heavy caching; detection requires time-bounded pruning. A generic store invites unsafe operations (such as deleting audit records via generic CRUD).

## 2. In-Memory State with Distributed Cache (Redis-First)
- **Approach:** Keep all security state in Redis for distributed sharing.
- **Why Rejected:** Redis eviction policies and memory volatility risk dropping audit records or losing suspension states during memory pressure. Relational persistence provides ACID guarantees and durable tables necessary for enterprise compliance. Redis may be evaluated post-`v0.16` solely as an optional read-through cache for epochs.

## 3. Direct ORM Integration in Domain Services
- **Approach:** Allow `AgentService` and `RuntimeService` to query database models directly.
- **Why Rejected:** Violates Clean Architecture and the LLM trust boundary. Binds core security algorithms to specific database engines and complicates testing.

---

# Consequences

## Positive
- Enforcement state (`SUSPEND_AGENT`) survives container restarts and pod redeployments.
- Multi-turn detection rules (`EXCESSIVE_DENIALS`) cannot be evaded by restarting the process.
- Forensic audit trail is durable and decoupled from ephemeral session lifecycles.
- Replicas in multi-instance deployments achieve atomic, consistent enforcement posture.
- Unit testing remains fast and dependency-free via `InMemoryAdapter`.

## Negative
- Introduces database schema migrations and connection management for production environments.
- Adds asynchronous/transactional overhead compared to pure in-memory dictionary access.

## Risks & Mitigations
- **Risk:** SQLite and PostgreSQL concurrency behaviors diverge (e.g. table-level locks vs row-level locks).
  - *Mitigation:* The parameterized Repository Contract Test Suite exercises concurrent writes and CAS semantics on both engines.
- **Risk:** Database latency impacts synchronous runtime evaluation.
  - *Mitigation:* Configuration and enforcement epochs are read-optimized and eligible for bounded in-memory caching validated against the epoch counter.

---

# Security Considerations

- **Fail-Closed on Persistence Errors:** If the repository cannot persist an audit event or verify an enforcement epoch due to database unavailability, the runtime pipeline must fail closed (halt tool execution and deny the request).
- **Least Privilege Database Accounts:** Production PostgreSQL roles for the runtime service must be granted `INSERT` and `SELECT` only on the audit evidence table, with `UPDATE` and `DELETE` privileges explicitly revoked.
- **Independent Verifiability:** Storage-level append-only guarantees must be augmented with independent verification mechanisms so that unauthorized modifications by privileged database users remain detectable.
