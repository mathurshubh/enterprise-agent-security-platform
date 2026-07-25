# 05 — Operational Model

## Purpose

This document specifies the **Operational Model** of the Enterprise Security Console, defining how operators interact with the platform landing surface (**Command Center**) and work-triage queues.

---

## Scope

Governs the Command Center landing page (`/`), the Action Required Work Queue, and operational triage workflows.

---

## Command Center Architecture

The Command Center is structured into two distinct operational zones:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: ACTION REQUIRED QUEUE (Primary Work-Oriented Landing — Dominant Top Zone)│
│                                                                                 │
│  [!] HELD SESSION      Agent: Financial-Assistant-01   Risk: HIGH (78/100)      │
│      Action Required: Require Human Approval on 'file_read /secrets/keys.pem'   │
│      [ Review & Release ]  [ Reject Session ]                     (2 mins ago)  │
│ ─────────────────────────────────────────────────────────────────────────────── │
│  [!] CRITICAL FINDING  Agent: Data-Exfil-Agent       Type: Sensitive Access   │
│      Triggered Rule: SensitiveFileAccessRule                       (5 mins ago)  │
│      [ Investigate Session ]                                                    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ ZONE 2: OPERATIONAL AWARENESS (Secondary Posture Metrics — Supporting Lower Zone)│
│                                                                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────────────────┐ │
│  │ Active       │ │ Risk         │ │ Enforcement  │ │ Platform Health         │ │
│  │ Sessions     │ │ Distribution │ │ Summary      │ │ Backend Status: OK      │ │
│  │ 12 Active    │ │ 2 High, 10 Low│ │ 1 Held, 0 Susp│ │ 243 Tests Verified      │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Zone 1: Action Required Work Queue (Primary)

The **Action Required Queue** is a prioritized, severity-sorted operational work list rendering items requiring explicit analyst intervention:

1. **Held Agent Sessions:** Sessions placed in `REQUIRE_APPROVAL` or `HOLD_SESSION` states by the Behavioral Enforcement Engine ([ADR-019](../../adr/ADR-019-behavioral-enforcement-engine.md)).
2. **Critical/High Behavioral Findings:** Unacknowledged threat detection findings emitted by the Behavioral Detection Engine ([ADR-017](../../adr/ADR-017-behavioral-detection-engine.md)).
3. **Suspended Agent Review:** Enterprise Agents whose identities have been suspended (`SUSPEND_AGENT`).

### Card Anatomy:
- **Severity Indicator:** Color-coded border and badge (`CRITICAL` / `HIGH` / `MEDIUM`).
- **Target Entity:** Agent ID, Session ID, and requested tool action.
- **Trigger Rationale:** Triggering rule name, risk score, or policy threshold.
- **Direct Action Affordance:** One-click transition to Session Investigation Workspace or Approval Release drawer.

---

## Zone 2: Operational Awareness (Secondary)

Positioned directly below Zone 1, **Zone 2** provides high-level security posture awareness through concise summary indicators:
- **Active Sessions Counter:** Real-time count of currently executing agent sessions.
- **Risk Distribution Gauge:** Breakdown of sessions across risk tiers (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Enforcement Posture Summary:** Tally of active containment actions across all agents.
- **Platform Health Status:** Read-only system summary derived from `GET /api/v1/info`.

---

## Design Rationale

Traditional dashboards display static charts and metric counters. When a SOC analyst starts their shift, a dashboard forces them to visually scan multiple widgets to deduce whether an incident is occurring.

Replacing static dashboards with a **Work-Oriented Landing** shifts the console from passive observation to active operational response. When items require attention, Zone 1 dominates the screen; when no items require attention, Zone 1 displays a clear "System Normal" verification state while Zone 2 surfaces posture context.

---

## Tradeoffs

- **Empty State Behavior:** When no security alerts or held sessions exist, Zone 1 renders a prominent green verification banner ("All Agent Sessions Operating Within Normal Security Bounds"). Developers must ensure empty states feel reassuring rather than broken.

---

## Dependencies

- Zone 2 utilizes existing `GET /api/v1/info`, `/agents`, `/sessions`, `/audit/events`.
- Zone 1 is gated by Phase 2 backend APIs (`GET /approvals/pending`, `GET /findings`).

---

## Relationship to Other Architecture Documents

- Implements Navigation Architecture ([04-navigation-architecture.md](04-navigation-architecture.md)).
- Operational actions defined in Page Specifications ([08-page-specifications.md](08-page-specifications.md)).

---

## Future Evolution

In Phase 4 (AgentSecOps), Zone 1 will integrate open SOC incident cases (`/cases`) assigned to the logged-in analyst.
