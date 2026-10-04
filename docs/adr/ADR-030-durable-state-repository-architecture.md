# ADR-030: Durable State Repository Architecture

**Status:** Proposed

**Date:** 2026-09-24

**Authors:**
- Shubhankar Mathur

**Implementation Status:**
- Proposed for `v0.16.0` (Phase 1 Architecture Foundation)

*Amended 2026-10-03 — Lifecycle Persistence Alignment (L.1–L.12). This ADR remains Proposed.*

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

Platform state is decomposed into ~~five~~ distinct operational planes with explicit lifecycle boundaries:

> **Amended (L.2).** This table is superseded by the six-plane taxonomy in L.2 and is retained as the original decision record. Row 2's authority over "all security decisions" and row 3's `ACTIVE` enforcement state no longer apply.

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
- **`AgentRepository`**: Manages agent identity, ~~lifecycle status,~~ risk allowances, and registered capabilities. *Amended (L.3): authoritative lifecycle state belongs to the Administrative Lifecycle Plane; `Agent.status` is a non-authoritative projection (ADR-024 A.2).*
- **`ToolRepository`**: Manages registered tool definitions, parameters, risk tiers, and availability flags.
- **`PolicyRepository`**: Manages resource policies and static authorization rules.

Domain-specific query methods (such as active filtering) are defined per domain interface rather than imposed as generic constraints across all entities.

### B. Audit Evidence Repository (`AuditEvidenceRepository`)
Owns the persistence of `AuditEvent` records per [ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md):
- `append(event: AuditEvent) -> None`
- `get(event_id: str) -> AuditEvent | None` *(editorial: previously written `get_by_id`; no decision content)*
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
  - **Pristine State Isolation:** An uninitialized agent (`get_state(...) is None`) indicates pristine status with no dynamic containment, proceeding normally to administrative status evaluation. *Amended (L.4): the pristine enforcement state is `NOT_SUSPENDED` at epoch 0; the administrative plane is evaluated independently (ADR-024 A.4).*

### D. Detection Horizon Repository (`SessionEventHorizonRepository`)
Maintains the authoritative behavioral evidence required for multi-turn behavioral detection per [ADR-027](ADR-027-state-lifecycle-decomposition.md), decoupled from session lifecycle state via role-specific protocols backed by a unified atomic adapter:
- `record_event(event: SessionEvent) -> SessionEvent`
- `list_eligible_events(query: HorizonQuery) -> list[SessionEvent]`
- `prune_events(*, cutoff: datetime) -> int` *(editorial: previously written `prune_events(before_timestamp: datetime)`; no decision content)*
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
  - ~~**Stale Context Interlock:** Execution grant issuance validates `expected_epoch` under lock via `ExecutionAuthority.issue(...)` to prevent issuance on stale enforcement context.~~ *Corrected (L.11).*

### E. Approval Continuation Repository (`ApprovalContinuationRepository`)

*Editorial: identifiers below updated to the names introduced by migration `0006` (`ExecutionGrant` → `ApprovalContinuation`, `ApprovalGrantRepository` → `ApprovalContinuationRepository`, `GrantState` → `ContinuationState`, `*_grant` → `*_continuation`, `InvalidGrantTransitionError` → `InvalidContinuationTransitionError`). No decision content.*

Owns the lifecycle and atomic resumption of human-in-the-loop approval grants per [ADR-031](ADR-031-execution-grant-approval-control-plane.md):
- `create_continuation(grant: ApprovalContinuation) -> None`
- `get_continuation(grant_id: str) -> ApprovalContinuation | None`
- `transition_continuation(grant_id: str, *, from_state: ContinuationState, to_state: ContinuationState, consumed_at: datetime | None = None, approved_by: str | None = None) -> bool`
- `list_continuations(*, agent_id: str | None = None, state: ContinuationState | None = None) -> list[ApprovalContinuation]`
- **Invariants:**
  - **Canonical State Machine:** Strict transitions only: `PENDING -> APPROVED | REJECTED | EXPIRED`, and `APPROVED -> CONSUMED`. Every other transition raises `InvalidContinuationTransitionError`.
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
   ~~Grant issuance verifies `expected_epoch` under `agent_enforcement_state` row lock (`FOR UPDATE`). Concurrent agent containment transitions serialize cleanly against grant issuance; a request authorized against a pre-suspension epoch cannot obtain an execution grant.~~
   *Corrected (L.11): not implemented as described. Durable issuance validation is an ADR-024 A.9 precondition, deferred to Gate 3 (L.12).*
7. **PostgreSQL as Concurrency Authority:**
   Multi-worker concurrency semantics (MVCC row locks, CAS ordering, interlock serialization) are verified through 7 live PostgreSQL 16 race tests (`tests/repositories/sql/test_sql_*concurrency_postgres.py`). *Amended (L.11): the issuance/containment race test simulates issuance with a stand-in transaction and does not exercise `ExecutionAuthority`.*
8. **Redis Excluded from Critical Path:**
   Redis is explicitly excluded from the v0.16 critical security state path to prevent memory eviction and split-brain containment bypass. Relational persistence provides ACID durability; Redis remains evaluated solely for optional, non-authoritative read caching post-v0.16.

## 5. Repository Contract Test Suite

To ensure that `InMemoryAdapter`, `SQLiteAdapter`, and `PostgreSQLAdapter` are semantically interchangeable, all adapters must execute and pass an identical parameterized **Repository Contract Test Suite** (`tests/repositories/contracts/`; *editorial: previously written `tests/repositories/test_contract.py`, which does not exist; no decision content*).

The contract suite validates:
- Optimistic concurrency and compare-and-set epoch progression.
- Strict append-only behavior and immutability guards in audit storage.
- Atomic state transitions and isolation across concurrent threads/connections.
- Correct temporal query filtering and pruning of detection horizon events.
- Deterministic recovery and state survival across repository re-instantiation (restart simulation).

## 6. Composition Contract — No Silent Persistence Downgrade

*Added 2026-10-03 (adversarial review Finding 3). This ADR remains Proposed.*

Selecting a backend is a statement about durability, so the composition boundary must not quietly make it false. `create_repositories()` (`app/repositories/factory.py`) enforces:

> With `backend="sql"`, no repository is implicitly replaced by an in-memory implementation. Existing SQL adapters are used by default; missing required adapters cause composition failure unless an adapter is explicitly supplied by the caller.

- **SQL defaults:** session, enforcement, approval-continuation, tool and audit-evidence repositories default to their SQL adapters.
- **Missing adapter:** there is no SQL `AgentRepository`. Under `backend="sql"`, `agent_repository` must be supplied, and its absence raises `RepositoryCompositionError` before any service is constructed. The factory previously substituted an in-memory agent registry; because the SQL session, enforcement and continuation tables reference `agents` and no application path writes that table, session binding for an agent absent from the SQL `agents` table then failed on its foreign key at request time.
- **Explicit injection:** an adapter supplied by the caller is used as given. That is a visible composition choice, not a fallback. An explicitly supplied in-memory adapter under `backend="sql"` is **not** a durable topology; production composition must enforce its own durability contract.
- **Scope of the guarantee:** this governs the factory only. The application composition root (`app/api/dependencies.py`) constructs in-memory repositories directly and does not call the factory, so the running API is not SQL-backed. Production durable composition — backend configuration, startup lifecycle, a SQL `AgentRepository` — is separate, outstanding work.

---

# Amendment — Lifecycle Persistence Alignment

*Status of this amendment: Proposed. Dated 2026-10-03. This ADR remains Proposed. Origin: the ADR-030
design review and the Gate 1 decision record (DR-1, DR-2, DR-3, DR-6(a), DR-6(b), DR-7, DR-8, DR-9),
aligning this ADR with the F-09 amendments to [ADR-024](ADR-024-agent-enforcement-state.md),
[ADR-025](ADR-025-management-plane-authorization.md),
[ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md) and
[ADR-034](ADR-034-audit-identity-contract.md).*

## L.1 Context and sources

The F-09 amendments define two independently authoritative agent lifecycle planes, administrative
and enforcement (ADR-024 A.2). This ADR modelled lifecycle as configuration and used an enforcement
vocabulary that predates F-09, and a design review found statements here that the implementation
does not match. This amendment records the persistence architecture F-09 requires and corrects those
statements. It changes no F-09 decision.

Sources are labelled by kind:

- **[Reviewer]** — what an adversarial reviewer found:
  - `docs/security/reviews/2026-10-03-antigravity-opus-4.6-adversarial-review.md`: FINDING-4
    (continuation epoch/expiry), FINDING-5 (factory fallback), FINDING-6 (in-memory production
    runtime).
  - `docs/security/reviews/2026-10-03-antigravity-gemini-flash-adversarial-review.md`: FINDING-3
    (factory fallback), FINDING-5 (continuation epoch/expiry), FINDING-10 (crash reconciliation
    inoperative with an in-memory evidence store).
- **[Adjudication]** — the adjudicated disposition, in
  `docs/security/reviews/2026-10-03-adversarial-review-adjudication.md`: Finding 3 (closed; production
  durable composition remains separate work), Finding 4 (deferred to F-09), Finding 5 (already
  covered; D-G1).
- **[Analysis]** — conclusions of the ADR-030 design review, not reviewer findings: the issuance
  interlock is not implemented as documented (L.11); two quantities share the name "epoch" (L.5);
  `UNIQUE(agent_id, epoch)` is described in the architecture principles but absent from the schema
  (L.9); partial durability suppresses detection (L.6).
- **[Code]** and **[ADR]** — direct repository evidence, cited where used.

## L.2 State taxonomy (amends §1)

| # | Plane | Authority | Write semantics | Security role |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Configuration** | `Agent` identity and descriptive configuration, `Tool`, `SecurityPolicy` | Low-frequency admin mutations | Identity, capability allowances, static RBAC. Not lifecycle authority. |
| 2 | **Audit Evidence** | `AuditEvent` ([ADR-028](ADR-028-audit-evidence-ownership-and-lifecycle.md)) | Strict append-only | Authoritative evidence of runtime tool-request decisions |
| 3 | **Administrative Lifecycle** | Administrative state record (L.3) | Compare-and-set on `administrative_version` with atomic ledger append | Authoritative `REGISTERED` / `ACTIVE` / `DISABLED` |
| 4 | **Enforcement State** | `AgentEnforcementState` | Compare-and-set on `epoch` with atomic ledger append | Authoritative `NOT_SUSPENDED` / `SUSPENDED` |
| 5 | **Detection Horizon** | `SessionEvent` ([ADR-027](ADR-027-state-lifecycle-decomposition.md)) | Append + temporal prune | Sliding window for multi-turn accumulation rules |
| 6 | **Control-Plane Resumption** | `ApprovalContinuation` ([ADR-031](ADR-031-execution-grant-approval-control-plane.md)) | Compare-and-set state transition | Durable, human-approved authority; not directly executable |

Evidence ownership:

- Runtime tool-request evidence → `AuditEvent`.
- Administrative lifecycle evidence → administrative ledger; refused administrative attempts →
  `AdministrativeAuditEvent` (ADR-028 §6, ADR-034 §8).
- Enforcement lifecycle evidence → enforcement ledger.

Lifecycle evidence never enters `AuditEvent` or `SessionEvent` (ADR-024 A.8).

`Agent.status` sits outside this authority model: it is a materialized projection of the effective
state of the two lifecycle planes and is never an authorization input (ADR-024 A.2).

## L.3 Administrative Lifecycle Plane

**Persistence:**

- `agent_administrative_state` — `agent_id` (foreign key to `agents`), `state`,
  `administrative_version`, with `CHECK (state IN ('REGISTERED', 'ACTIVE', 'DISABLED'))`.
- `agent_administrative_transitions` — the administrative ledger, with the fields required by
  ADR-024 A.8 and `UNIQUE(agent_id, administrative_version_after)`.
- `administrative_audit_events` — refused administrative attempts; append-only; no control-plane
  foreign keys (ADR-028 §6).

**Concurrency and atomicity** (ADR-024 A.6), mirroring §2.C:

- *Lock order:* the `agents` row first, then the administrative state row. `agents` remains the
  identity record and parent-lock anchor for both lifecycle planes.
- *Compare-and-set:* a transition succeeds only if `expected_version` equals the persisted version
  and the new version equals `expected_version + 1`.
- *Atomicity:* the state change and its ledger entry commit in one transaction; on compare-and-set
  or validation failure neither is persisted.
- Process-local locks are never the correctness mechanism.
- Storage failures are normalized to a plane-specific unavailability error at the repository
  boundary (L.10).

**Repositories:** `AdministrativeStateRepository` owns the state and the ledger.
`AdministrativeAuditRepository` owns refusal evidence and exposes append and read operations only.
Registration is the first administrative transition and yields `REGISTERED` (ADR-024 A.3, A.10).

**Missing record:** an agent with no administrative state record has no establishable
administrative state. It is reported as `ADMINISTRATIVE_STATE_UNAVAILABLE` (L.10) and is never
interpreted as `REGISTERED` or as `AGENT_NOT_ACTIVE`.

**Projection:** `Agent.status` is written after the owning plane commits. Security decisions read
effective state from the authoritative planes. A briefly lagging projection is acceptable because it
is never authoritative. No transaction spans both lifecycle planes (ADR-024 A.2).

## L.4 Enforcement plane vocabulary (amends §1 row 3 and §2.C)

- Enforcement states are `NOT_SUSPENDED` and `SUSPENDED`. `ACTIVE` is exclusively an administrative
  state (ADR-024 A.5, A.10).
- Pristine enforcement state is `NOT_SUSPENDED` at epoch 0. The administrative plane is evaluated
  independently.
- The §2.C invariants — direct epoch authority, strict compare-and-set, single-transaction
  atomicity, fail-closed availability — are unchanged.

## L.5 Namespaces

| Namespace | Allocator | Meaning |
| :--- | :--- | :--- |
| `administrative_version` | Administrative state repository; compare-and-set, +1 per committed administrative transition | Administrative lifecycle generation |
| `AgentEnforcementState.epoch` | Enforcement state repository; compare-and-set, +1 per committed enforcement transition | Enforcement generation and grant freshness |
| `recovery_generation` | Derived from the enforcement ledger: the count of `REINSTATE` transitions with `occurred_at` at or before the evaluated event's timestamp | Which recovery lifecycle a detection crossing belongs to |

The three are never compared with or substituted for one another. `administrative_version` is not a
grant-freshness input (ADR-024 A.2, A.7).

`recovery_generation` is the namespace defined by this decision. It is a detection and evidence
namespace, not a lifecycle plane. The existing `get_epoch(as_of=...)` repository method and
`Finding.enforcement_epoch` field represent this namespace and are renamed to
`get_recovery_generation(as_of=...)` and `Finding.recovery_generation`, respectively, during the F-09
implementation. Existing values, historical evaluation semantics, and finding-identity derivation
remain unchanged. Being derived from the enforcement ledger, its durability is the ledger's (L.6).
Explicit allocation in place of derivation is deferred (L.12).

*Correction of record [Analysis]:* findings consume `recovery_generation`, not
`AgentEnforcementState.epoch` ([Code] `app/services/runtime_service.py`,
`app/services/detection_service.py`).

## L.6 Durable Watermark Integrity

> **Durable Watermark Integrity:** A durable watermark may reference only a namespace whose
> allocator is durable, whose position is never reset or rewound below any watermark that
> references it, and whose state is restored together with the watermark.

Current references [Code]:

| Durable value | References | Allocator today |
| :--- | :--- | :--- |
| `agent_enforcement_state.baseline_evidence_sequence` | `Finding.evidence_sequence` | `FindingsService`, in process memory; no repository |
| `agent_enforcement_state.baseline_agent_sequence` | `SessionEvent.agent_sequence` | `agent_sequence_counters` |
| `approval_continuations.enforcement_epoch` | `AgentEnforcementState.epoch` | Enforcement state repository |

Consumers ignore records at or below these watermarks ([Code]
`app/services/agent_risk_aggregate.py`; §2.D *Watermark Isolation*). A volatile or rewound allocator
would cause new records to be treated as already covered, suppressing detection [Analysis].

Required:

1. **Composition validation.** A composition must not make a store durable while it holds a
   watermark into a volatile namespace. Durable enforcement with in-memory findings is not a valid
   durable-security topology.
2. **No rewind.** An allocator position below a watermark that references it is an integrity
   violation.
3. **Coordinated restoration.** Referencing and referenced namespaces are restored together.
   Whole-database point-in-time restoration is acceptable. Restoring related stores to different
   points is unsupported, and partial restoration must not silently resume service.
4. **Startup.** If any allocator position is below a watermark that references it, the service
   refuses to become operational. This is a persistence-integrity condition, not an agent-specific
   posture.

## L.7 Lifecycle caching (supersedes the caching mitigation in *Risks & Mitigations*)

Authoritative administrative and enforcement state is not cached in process memory on the
authorization or issuance path.

- Permitted: descriptive configuration, and non-authoritative presentation or read caches whose
  contents cannot influence authorization, lifecycle, issuance, revocation, or enforcement decisions.
- Not permitted: a cached lifecycle value used for any security decision, whether validated by a
  time-to-live, by `epoch`, or by `administrative_version`; and validation of administrative state
  against `epoch`, which is namespace substitution.

## L.8 Composition boundary (extends §6)

- **F-09 boundary.** The F-09 implementation does not change the production composition root
  (`app/api/dependencies.py`), which remains in-memory. It may deliver the lifecycle domain changes,
  both adapters for both planes, the ledgers, administrative audit, migrations, issuance gating,
  bootstrap activation, and SQLite and PostgreSQL contract tests.
- **Durable production composition** remains a separate ADR-030 workstream and is subject to L.6.
- **Multi-instance composition** is unsupported until the ADR-024 A.9 preconditions are met (L.12).
- The factory composition contract (§6) applies unchanged.

## L.9 Historical enforcement-ledger migration

`agent_enforcement_transitions` (migration `0001`) may be populated and lacks the fields ADR-024 A.8
requires. Its migration:

- **Is additive.** A new migration; existing migrations are not edited and the table is not dropped
  or recreated.
- **Marks format explicitly.** `ledger_format` is `1` for existing rows and `2` for F-09-format rows.
  The value `1` asserts only that a row predates F-09, which is true by construction.
- **Adds the F-09 fields.** Nullable `actor_type`, `actor_id`, `correlation_id`, and
  `enforcement_epoch_before`, with a `CHECK` constraint requiring them, and the F-09 vocabulary, on
  every format-2 row. The existing `epoch` column keeps its meaning: the epoch after the transition.
- **Preserves format-1 rows exactly as recorded**, including the original `actor` string and the
  original `ACTIVE` / `SUSPENDED` values.
- **Fabricates nothing.** No actor type, actor identity, correlation id, or
  `enforcement_epoch_before` is written into historical rows. `epoch_before = epoch - 1` is not
  asserted as historical fact; no historical evidence records it.
- **Adds `UNIQUE(agent_id, epoch)`** in a migration that fails if duplicates exist. It does not
  repair, renumber, merge, or rewrite any row.

ADR-024 A.8's structured format — structured actor, mandatory correlation id, namespaced versions,
plane vocabulary — applies to F-09-format lifecycle records. Format-1 rows are pre-F-09 history,
preserved as recorded.

*Current state only:* `agent_enforcement_state.current_status` is mapped from `ACTIVE` to
`NOT_SUSPENDED`. This is an exact representation change of current state, not reconstruction of
history: the repository derives the value solely from `suspended_at` ([Code]
`SqlEnforcementStateRepository.record_transition`).

## L.10 Lifecycle unavailability and refusal evidence

**At decision time.** When a plane's authoritative state cannot be established, including when an
agent has no administrative state record (L.3), the decision is `DENY` with that plane's code:

- `ADMINISTRATIVE_STATE_UNAVAILABLE`
- `ENFORCEMENT_STATE_UNAVAILABLE`

These express the fail-closed condition ADR-024 A.2 and A.4 already require. They are not lifecycle
states. `AGENT_NOT_ACTIVE`, `AGENT_DISABLED`, and `AGENT_SUSPENDED` remain reserved for known states
(ADR-024 A.4), and an unavailable repository is never reported as one of them.

Both planes are evaluated independently. When several conditions fail, the primary surfaced code
follows this precedence:

1. `ADMINISTRATIVE_STATE_UNAVAILABLE`
2. `ENFORCEMENT_STATE_UNAVAILABLE`
3. `AGENT_DISABLED`
4. `AGENT_NOT_ACTIVE`
5. `AGENT_SUSPENDED`

**Administrative operations.**

- If an operation is refused and its `AdministrativeAuditEvent` cannot be persisted, the caller
  receives `503`. The response never implies the refusal was recorded, nothing is committed, and the
  infrastructure failure may be emitted as non-authoritative telemetry.
- If administrative state is unavailable, no state mutation occurs. A refusal with code
  `ADMINISTRATIVE_STATE_UNAVAILABLE` is recorded if the audit store is reachable; otherwise the
  `503` rule applies.

## L.11 Issuance and epoch interlock — correction of record (amends §2.D, §4.6, §4.7)

[Analysis], against [Code] `app/runtime/execution_authority.py` and `app/api/dependencies.py`:

- `ExecutionAuthority.issue()` validates `expected_epoch` only when an enforcement state repository
  was injected. If that repository exposes a `_lock` attribute, as the in-memory adapter does, the
  check runs under that process-local lock. Otherwise, as with the SQL adapter, it is an unlocked
  `get_state()` read; no `FOR UPDATE` row lock is taken.
- The production composition constructs `ExecutionAuthority()` without an enforcement state
  repository, so no epoch check is performed at issuance in the running API.
- In the single-process composition, issuance closure is process-local: `suspend_issuance` closes
  issuance and revokes the agent's outstanding grants within one hold of the authority's lock.
- The §4.7 issuance/containment race test simulates issuance with a stand-in transaction that
  inserts an `ApprovalContinuation` row. It does not exercise `ExecutionAuthority`.
- Durable validation of the enforcement epoch at issuance, and durable or shared issuance closure
  and revocation, are ADR-024 A.9 preconditions for multi-instance composition. This amendment does
  not decide their mechanism (L.12). *Mechanism recommended in amendment AG (Proposed).*

## L.12 Deferred to Gate 3 (not decided)

- **DR-4 — deployment boundary:** whether durable single-instance deployment precedes multi-instance
  support, and how single-instance operation would be enforced. *Addressed by amendment DB
  (Proposed).*
- **DR-5 — multi-instance revocation.** Candidates:
  - (a) durable epoch check at claim time — does not cover disablement; requires an ADR-023
    amendment;
  - (b) a declared authority-revocation namespace — requires an ADR-023 amendment and a new
    namespace;
  - (c) time-to-live as the revocation bound — **flagged: conflicts with ADR-024 A.9.2; not
    selectable without F-09 adjudication.**

  *Addressed by amendment AG (Proposed). DR-5(c) remains rejected.*
- The issuance interlock mechanism satisfying ADR-024 A.9.1 (L.11). *Addressed by amendment AG
  (Proposed).*
- Explicit allocation of `recovery_generation` in place of timestamp-based derivation.
- Durable repositories for findings and execution evidence, required by L.6 before durable
  enforcement composition.

---

# Amendment — Execution-Authority Revocation (DR-5)

*Status of this amendment: Proposed. Dated 2026-10-03. This ADR remains Proposed. Origin: Gate 3
DR-5 design review and lock validation. Mechanism for the
[ADR-023](ADR-023-execution-authorization-grants.md) revocation contract (RC.1–RC.7). It does not
close Gate 3 (AG.8).*

## AG.1 `authority_generation`

`authority_generation` is execution-authority invalidation state, derived from transitions that
remove execution authority. It is not a lifecycle plane, not a third lifecycle state, and not an
authorization source. It is never compared with or substituted for `administrative_version`,
`AgentEnforcementState.epoch`, or `recovery_generation`.

```text
Administrative plane ─┐
                      ├─ authority removal ─▶ authority_generation ─▶ grant invalidation
Enforcement plane ────┘
```

**Persistence:** one record per agent in `agent_authority_generation` — `agent_id` (primary key,
foreign key to `agents`) and `authority_generation`. The record is created at 0 in the same
transaction as registration. A missing record means no generation can be established: it fails
closed at issuance and at claim, and is never defaulted.

## AG.2 Advancing the generation

The generation is advanced by +1 **inside the plane's own transition transaction**, after `agents`
is locked, so that it commits atomically with the state change and its ledger entry:

- `ACTIVE → DISABLED` (administrative transaction);
- entering `SUSPENDED` (enforcement transaction).

No transaction writes both lifecycle planes (ADR-024 A.2): each plane's transaction writes its own
state and this invalidation record. Reinstatement, activation, `REGISTERED → DISABLED`, and other
transitions that remove no execution authority do not advance it.

## AG.3 S-IV: serialized issuance

Grant issuance — direct (`ALLOW → issue()`) and minting after a D-G1 continuation claim — runs as
one transaction:

1. **Lock:** `agents` `FOR SHARE`. Every lifecycle transition takes `agents FOR UPDATE` first, so
   issuance and authority-removing transitions are serialized on the same row.
2. **Read:** administrative state, enforcement state and its epoch, and `authority_generation`.
3. **Check:** `ACTIVE ∧ NOT_SUSPENDED ∧ epoch == expected_epoch`. The epoch check satisfies
   ADR-024 A.9.1.
4. **Mint:** the grant, bound to the generation read.
5. **Commit.**

The **issuance linearization point** is the acquisition of the shared `agents` row lock together
with the reads made under it. Because every lifecycle transition holds `agents FOR UPDATE` until it
commits, an issuance's linearization point falls either entirely before such a transition takes its
lock or entirely after it commits.

Guarantee: **once an authority-removing transition commits, no issuance whose linearization point
falls after that commit may successfully mint an execution grant for that agent.** This is
issuance linearization, not an additional authorization check. Grants whose issuance linearized
before the commit are handled by AG.4.

Constraints from the lock validation:

- **Process-wide lock:** the authority's process-wide lock must not be held while waiting for the
  `agents` row lock. Otherwise per-agent database contention becomes process-wide contention for
  issuance, claims, suspension, and reinstatement.
- **Minting and commit:** minting and registering the grant are inside the issuance transaction's
  correctness boundary. If the transaction does not commit after the grant is created, the grant is
  invalidated or withdrawn before issuance reports failure, and is never returned as executable
  authority. The mechanism for clearing in-process state is an implementation concern; this
  amendment does not assume that grant creation can roll itself back.
- **Lock scope:** issuance locks only `agents`. An issuance transaction that also locked a session
  row would have to follow the session-row-then-`agents` order used by event recording.

**Throughput:** every request's event recording takes `agents FOR UPDATE`
(`SqlSessionRepository.record_event`). In a durable composition, issuance therefore contends per
agent with event recording on every replica. This is a throughput consideration, not a correctness
one.

## AG.4 R-b: claim-time check

Claim-time generation validation is a revocation check, not lifecycle re-authorization (ADR-023
RC.3).

- **Linearization point:** the authoritative generation read is the claim's revocation-validation
  linearization point.
- **Final validation:** the authoritative generation equality check must be the final revocation
  validation performed before the grant is consumed. No operation that can materially delay
  consumption or introduce another revocation-validation window may occur between generation
  validation and consumption.
- **Already in flight:** a claim that has established a matching generation before an
  authority-removing transition commits is treated as already in flight and is not retroactively
  invalidated. This is the residual risk ADR-023 already accepts: revocation cannot stop execution
  already under way.
- **After the commit:** a claim whose generation validation occurs after the transition commits
  must observe the new generation and refuse the stale grant (`REVOKED`).
- **Authoritative read:** the read must observe the authoritative store's committed state — no
  cache (L.7), and no lagging read replica or other source that could return a value from before
  the commit.
- **Unavailable:** if the value cannot be established, the claim fails closed
  (`REVOCATION_STATE_UNAVAILABLE`).
- **No row lock:** the claim takes no row lock; it is linearized by its read.
- **Process-wide lock:** the authority's process-wide lock must not be held while waiting for the
  read (the same rule as AG.3).

## AG.5 Mechanism per composition

| Composition | Issuance closure | Revocation after issuance |
|---|---|---|
| In-memory, single-process (current production; L.8) | Per-plane gates under the authority's lock | Process-local revocation on every authority-removing transition |
| Durable, single active instance (not yet supported) | Per-plane gates under the authority's lock | Process-local revocation on every authority-removing transition |
| Durable, multi-instance (not yet supported) | AG.3 (S-IV) | AG.4 (R-b) |

In the in-memory and the durable single-active-instance compositions, process-local issuance
closure and revocation are sufficient, because exactly one active process issues and claims
grants; that single-active-process condition is a deployment-boundary requirement. Lifecycle
transitions remain serialized by durable compare-and-set in every durable composition (ADR-024
A.6).

AG.3 and AG.4 apply to the multi-instance durable composition. There, the in-process fast path
remains but is never the sole correctness mechanism (ADR-024 A.9).

## AG.6 Restart and restore

- **Restart:** grants never survive a restart, because the signing key is per-process.
  `authority_generation` is not referenced by any durable watermark, so the L.6 startup check does
  not apply to it.
- **Restore:** restoring the database requires **every replica to restart before execution
  resumes**. An online restore could move the generation backwards and make old grants claimable
  again. This extends the coordinated-restoration requirement of L.6.

## AG.7 Resumption path

The D-G1 continuation claim ([ADR-031](ADR-031-execution-grant-approval-control-plane.md) §9) is
unchanged. Minting after a claim goes through AG.3. A claimed continuation of an agent that has
since been disabled is refused at minting and remains consumed and unspent (ADR-031 §9.4). This is
documented behaviour, not a new decision.

## AG.8 Gate 3 items still open (not decided here)

- **DR-4 — deployment boundary:** which composition is supported until the AG.3 and AG.4
  preconditions are implemented. *Addressed by amendment DB (Proposed).*
- **DR-8(c) — `recovery_generation` allocation:** the allocation mechanism remains undecided,
  including the concern about clocks on different replicas.
- **Durable evidence boundary:** which namespaces must be durable before a durable composition
  satisfies L.6.

---

# Amendment — Deployment Boundary (DR-4)

*Status of this amendment: Proposed. Dated 2026-10-04. This ADR remains Proposed. Origin: Gate 3
DR-4 review and wording stress-test. It establishes the supported deployment topologies and their
staging. It authorizes no implementation of stage B, B2, or C. It changes no text in ADR-024,
ADR-026, or ADR-032; DB.4 records an interpretation of their wording.*

## DB.1 Context

The single-process boundary assumed by ADR-024 A.9, L.8, and AG.5 existed only in documentation
([Code]):

- No deployment artifact exists. The only runner (`scripts/dev-start.sh`) starts one `uvicorn`
  process.
- The composition root (`app/api/dependencies.py`) builds every repository and `ExecutionAuthority`
  in memory, at import time, in each process.
- Nothing detects or refuses a second worker or instance.

Because `JWT_SECRET_KEY` is shared configuration, every process accepts the same tokens. Several
workers or instances would therefore form independent security authorities: containment recorded
in one is invisible to another, detection horizons and finding sequences fragment (ADR-026), session
ownership is enforced per process, and audit evidence is split. Grants stay process-local and are
not the failure.

## DB.2 Staged deployment boundary

| Stage | Topology | Issuance and revocation | Supported when |
|---|---|---|---|
| **A** (current) | Exactly one application process; in-memory state | Process-local (AG.5) | Now |
| **B** | Exactly one active process; durable state | Process-local (AG.5) | F-09 implemented; production durable composition; durable evidence boundary decided and implemented (L.6); DB.5 and DB.6 implemented |
| **B2** | One active process and non-serving standbys; durable state | Process-local (AG.5) | As B |
| **C** | Multiple active processes; shared durable state | AG.3 (S-IV) and AG.4 (R-b) | All of B, plus DB.7 |
| **D** | Stateless API workers in front of one authority process | — | **Not recommended**: it adds a worker-to-authority trust boundary with no current requirement for it |

Each stage is supported only when its preconditions exist. AG.3, AG.4, a distributed sequence
authority, and execution-receipt ownership are stage-C preconditions only; stages B and B2 need a
durable sequence allocator (L.6), not a distributed one.

## DB.3 Stage A deployment invariant

Stage A is a **deployment invariant**, not a recommended topology: exactly one application process
per deployment.

- **Local guard:** the application refuses to start an additional process on the same host. This
  is fail-closed startup enforcement, not a distributed security control. Under a multi-worker
  launcher, the additional workers fail startup and may be restarted repeatedly by their
  supervisor. The guard is not implemented today.
- **Across hosts:** the operator or orchestrator ensures that only one application instance
  exists. The local guard cannot detect instances on other hosts.
- **Unsupported:** multiple active execution-serving instances.

## DB.4 Active instances (interpretation of ADR-024 A.9 and ADR-026)

For the ADR-024 A.9 multi-instance execution precondition, the relevant topology is concurrently
active execution-serving instances. For the ADR-026 sequence-authority residual, it is concurrently
active sequence-allocating processes. A standby process that holds no active-instance authority,
serves no security-relevant requests and allocates no sequences is neither.

The unsafe condition is therefore concurrency in the security-relevant role, not process count.

## DB.5 Startup ordering (stages B and B2)

```text
acquire active-instance authority → L.6 integrity check → evidence reconciliation → ready
```

- Reconciliation mutates evidence, so the L.6 integrity check precedes it.
- A process that cannot acquire active-instance authority does not run the integrity check against
  shared state, does not reconcile, and serves nothing; otherwise a standby could mutate evidence
  belonging to the active instance.
- Failure at any step prevents serving.
- This refines the startup recovery boundary of
  [ADR-032](ADR-032-runtime-tool-execution-isolation.md) §12.6 for stages B and B2. The
  corresponding ADR-032 amendment is recorded when stage B2 is designed; it is not written here.

## DB.6 Active-authority fencing (stages B and B2)

- A process may serve security-relevant requests only while it can establish possession of
  active-instance authority within a bounded verification interval. Failure to establish it causes
  the process to stop serving (fail closed).
- A process taking over must not become active until the previous holder is known to be unable to
  continue serving, or equivalent fencing has been established.
- A process that has stopped serving resumes only through the full DB.5 ordering.

A database session lock alone is insufficient: it is released when its connection drops, while the
process that held it may still be running and serving from in-memory state. The mechanism — for
example a lease with bounded renewal, a fencing token, per-request verification, or process
termination on lost connection — is a stage-B design decision.

Fencing never replaces the restart of every process required on restore (AG.6).

## DB.7 Stage C preconditions

- AG.3 (S-IV) and AG.4 (R-b) implemented.
- A distributed sequence authority (ADR-026).
- **Execution-receipt ownership:** receipts must identify their owning execution authority or
  instance sufficiently for startup reconciliation to distinguish orphaned executions from
  executions still owned by another live instance. Today `reconcile_on_startup` resolves every open
  receipt and receipts carry no owner ([Code] `app/services/execution_reconciler.py`). The
  mechanism belongs to the durable evidence boundary and ADR-032.
- DR-8(c) decided.

## DB.8 Not decided here

- The stage-B active-instance mechanism, its verification bound, and takeover timing (DB.6).
- The ADR-032 §12.6 amendment text (DB.5).
- **Durable evidence boundary** (Gate 3, open): which namespaces must be durable before a durable
  composition satisfies L.6. It spans this ADR (findings and watermarks) and ADR-032 (execution
  receipts; ADR-032 §12.10).
- **DR-8(c)** (Gate 3, open): `recovery_generation` allocation.

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
- Replicas in multi-instance deployments achieve atomic, consistent enforcement posture. *Amended (L.8, L.12): a target, not current behaviour; multi-instance composition is unsupported until the ADR-024 A.9 preconditions are met.*
- Unit testing remains fast and dependency-free via `InMemoryAdapter`.

## Negative
- Introduces database schema migrations and connection management for production environments.
- Adds asynchronous/transactional overhead compared to pure in-memory dictionary access.

## Risks & Mitigations
- **Risk:** SQLite and PostgreSQL concurrency behaviors diverge (e.g. table-level locks vs row-level locks).
  - *Mitigation:* The parameterized Repository Contract Test Suite exercises concurrent writes and CAS semantics on both engines.
- **Risk:** Database latency impacts synchronous runtime evaluation.
  - ~~*Mitigation:* Configuration and enforcement epochs are read-optimized and eligible for bounded in-memory caching validated against the epoch counter.~~ *Superseded (L.7).*

---

# Security Considerations

- **Fail-Closed on Persistence Errors:** If the repository cannot persist an audit event or verify an enforcement epoch due to database unavailability, the runtime pipeline must fail closed (halt tool execution and deny the request).
- **Least Privilege Database Accounts:** Production PostgreSQL roles for the runtime service must be granted `INSERT` and `SELECT` only on the audit evidence table, with `UPDATE` and `DELETE` privileges explicitly revoked. *Amended (L.3): this also applies to the administrative and enforcement ledgers and to `administrative_audit_events` (ADR-024 A.8).*
- **Independent Verifiability:** Storage-level append-only guarantees must be augmented with independent verification mechanisms so that unauthorized modifications by privileged database users remain detectable.
