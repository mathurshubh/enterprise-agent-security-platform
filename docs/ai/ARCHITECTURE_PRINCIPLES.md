# Runtime

RuntimeService is the single deterministic security pipeline.

AgentRuntimeService is only responsible for:

- LLM invocation
- ToolInvocation generation
- Executing approved tools

Never duplicate runtime orchestration.

---

# Monotonic Security-State Namespace Integrity

Monotonic security-state values are namespace-specific and governed by a single
authoritative allocator. A value may only be compared with, persisted as a watermark for,
or used for idempotency or freshness **within the semantic namespace governed by that
allocator**.

The platform currently distinguishes seven:

| Namespace | Allocator | Meaning | Consumers |
|---|---|---|---|
| `SessionEvent.sequence_number` | session event repository | session-local event ordering | session queries, event finalization |
| `SessionEvent.agent_sequence` | agent sequence counter | agent-wide event ordering | detection horizon, enforcement baseline |
| `Finding.evidence_sequence` | `FindingsService` | finding ordering and projection cursor | risk aggregate, enforcement baseline |
| `AgentEnforcementState.epoch` | enforcement state repository (CAS, +1 per committed transition) | enforcement generation and freshness | grant issuance, enforcement ledger |
| `administrative_version` | administrative state repository (CAS, +1 per committed administrative transition) | administrative lifecycle generation | administrative transitions, administrative ledger, administrative audit evidence |
| `recovery_generation` | derived from the enforcement ledger (count of `REINSTATE` transitions at or before the evaluated event's timestamp) | recovery lifecycle of a detection crossing | finding identity |
| `authority_generation` | execution-authority state (+1 per transition that removes execution authority, inside that plane's transaction) | execution-authority invalidation generation | grant issuance (binding), grant claim (revocation check) |

These are **not interchangeable merely because they are monotonically increasing
integers**. Event ordering, finding ordering, and enforcement generation are different
security semantics, and each must retain explicit namespace identity at the domain,
persistence and consumer boundaries.

Generation counters are not event-ordering sequences. `epoch` answers *which enforcement
generation is this* and does not order records; comparing it against a sequence, or a
sequence against it, is a category error even though both are per-agent and both increase.
`UNIQUE(agent_id, epoch)` is the persistence-level expression of the generation
namespace's identity: no two committed enforcement generations for one agent may occupy
the same epoch. The constraint is not yet present in the schema; it is added by the
enforcement-ledger migration specified in ADR-030 amendment L.9.

`administrative_version` and `epoch` are both per-agent generation counters and are still
**different namespaces**: one answers *which administrative lifecycle generation is this*
(registration, activation, disablement), the other *which enforcement generation is this*
(suspension, reinstatement). An administrative transition never advances `epoch`, an
enforcement transition never advances `administrative_version`, and neither value is ever
compared with or substituted for the other (ADR-024 amendment A.2).

`administrative_version` is **not** a grant-freshness input. Grant issuance validates
`epoch`; loss of administrative execution authority is enforced by issuance closure and
revocation, not by a version check (ADR-024 amendment A.7). Introducing an administrative
freshness check later would be a new decision, not an implication of this namespace.
`UNIQUE(agent_id, administrative_version_after)` in the administrative ledger is the
persistence-level expression of this namespace's identity, as `UNIQUE(agent_id, epoch)` is
for enforcement (ADR-030 amendment L.3).

`recovery_generation` is a detection and evidence namespace, not a lifecycle plane and not
a generation counter with its own allocator. It is derived from the enforcement ledger and
answers *which recovery lifecycle does this detection crossing belong to*: reinstatement
starts a new one, suspension does not. It is part of finding identity. It is currently
exposed as `get_epoch(as_of=...)` and stored as `Finding.enforcement_epoch`; those
identifiers are renamed to `get_recovery_generation(as_of=...)` and
`Finding.recovery_generation` during the F-09 implementation, with values and semantics
unchanged (ADR-030 amendment L.5). It is never compared with or substituted for `epoch`,
although its current identifiers suggest otherwise.

`authority_generation` is an execution-authority invalidation namespace, not a lifecycle
plane, not lifecycle state, and not an authorization source. Both lifecycle planes advance
it when they remove execution authority, each inside its own transaction; neither plane's
state is written by the other. It is never compared with or substituted for
`administrative_version`, `epoch`, or `recovery_generation`, and is not a grant-freshness
input in place of `epoch` at issuance (ADR-030 amendment AG.1; ADR-023 amendment RC.3).

Name fields for the namespace they belong to. A generic name such as `baseline_sequence`
makes two orderings look interchangeable and is how they come to be conflated.

Cross-repository capture of independent namespaces need not be globally atomic unless a
domain invariant requires a common snapshot boundary. Each watermark or generation value
must, however, be obtained from its authoritative allocator and consumed only within its
own namespace.

---

# Trust Boundary

User

↓

LLM (untrusted)

↓

ToolInvocation

↓

RuntimeService

↓

Authorization

↓

Detection

↓

Risk

↓

Response

↓

Tool Execution