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
| **5. Control-Plane Resumption** | `ExecutionGrant` ([ADR-031](ADR-031-execution-grant-approval-control-plane.md)) | Compare-and-set state transition | Bounded TTL (e.g. 15 minutes) | Bound authority token permitting one-shot execution after human review |

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
Maintains the temporal window of session events required for multi-turn behavioral detection per [ADR-027](ADR-027-state-lifecycle-decomposition.md):
- `record_event(event: SessionEvent) -> None`
- `get_horizon_events(session_id: str, since_timestamp: datetime) -> list[SessionEvent]`
- `prune_expired_horizon(retention_threshold: datetime) -> int`
- **Invariants:**
  - Durability is bounded by the active detection horizon: `retention >= max(rule_temporal_window) + safety_margin`.
  - Events older than the retention threshold are pruned. This store does not provide permanent audit retention (audit retention belongs exclusively to `AuditEvidenceRepository`).
  - Cycling a runtime process does not reset the accumulated event history within the active horizon.

## 3. Multi-Adapter Strategy

To preserve fast, deterministic local testing while supporting robust enterprise deployments, the architecture enforces a dual-adapter pattern:

1. **`InMemoryAdapter`:**
   - Pure Python collections protected by thread-safe synchronization (`RLock`).
   - Used for unit tests, local test fixtures, and isolated sandbox benchmarks.
   - Eliminates external dependencies for basic developer workflows.
2. **`SQLRepositoryAdapter`:**
   - Implemented using relational database mapping (SQLAlchemy Core).
   - **SQLite Adapter:** Zero-configuration, file-based persistence for single-node development and small-scale deployments.
   - **PostgreSQL Adapter:** Robust connection-pooled persistence for production multi-replica enterprise deployments.

## 4. Repository Contract Test Suite

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
