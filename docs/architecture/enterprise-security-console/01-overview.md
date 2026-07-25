# 01 — Enterprise Security Console Overview

## Purpose

The **Enterprise Security Console** is the operational control surface for the Enterprise Agent Security Platform. It enables enterprise security teams to observe, investigate, govern, and audit autonomous AI agents operating under Zero Trust security controls.

The console is **not** an AI agent. It is a deterministic, read-only (with targeted, audited operator write commands) visualization and operations layer that sits entirely outside the Runtime Security Boundary defined in [ADR-003](../../adr/ADR-003-runtime-security-orchestrator.md) and [ADR-008](../../adr/ADR-008-enterprise-management-api.md).

---

## Scope

This specification governs the architectural evolution of the platform's user interface from version `v0.12.0` through `v1.0.0`. It covers:
- User personas and operational workflows.
- Information architecture and primary navigation.
- The Canonical Investigation Graph and Session Investigation Workspace.
- Data flow, caching, streaming, and audited operator write actions.
- Four backend-gated implementation phases.

Out of scope:
- Client-side policy evaluation or risk scoring (strictly backend-enforced per [ADR-002](../../adr/ADR-002-llm-untrusted-intent-parser.md)).
- Direct tool execution or LLM provider orchestration.
- Replacement of enterprise SIEM, SOAR, or IAM platforms.

---

## Core Operational Questions

The console is engineered to answer three primary operational questions:

1. **"What needs my attention?"** *(Monitoring & Work Triage)* — Handled via the Action Required Queue in the Command Center.
2. **"What happened and why?"** *(Forensic Investigation)* — Handled via the Session Investigation Workspace, Findings, and Audit Trail.
3. **"Is the security posture correct?"** *(Governance & Configuration)* — Handled via Agent, Tool, Detection Rule, and Scenario registries.

---

## Target User Personas

| Persona | Primary Focus | Key Responsibilities | Primary Console Views |
|---|---|---|---|
| **SOC Analyst** | Triage & Investigation | Monitors active alerts, triages behavioral findings, reviews held sessions, issues manual approval releases, investigates suspicious sessions. | Command Center (Action Queue), Approval Queue, Session Investigation Workspace, Findings. |
| **Security Engineer** | Policy & Detection | Authors detection rules, tunes behavioral risk thresholds, analyzes policy hit rates, runs attack scenario test suites. | Detection Rules, Scenarios, Session Workspace (Policy Trace / Tool Activity). |
| **Governance Officer** | Audit & Compliance | Audits enforcement decision chains, verifies evidence integrity, exports compliance records, reviews inter-agent trust topologies. | Audit Trail, Agent Registry, Tool Registry, Scenarios. |

---

## Design Rationale

Early console iterations (v0.9.0–v0.11.0) functioned as inventory database viewers—displaying static tables of agents, tools, detection rules, and audit events. While adequate for basic visibility, an inventory view fails to support active security operations.

Security operations require answering operational questions in priority order. By organizing the console around three operational modes (**MONITOR**, **INVESTIGATE**, **GOVERN**), the user experience transitions from passive inspection to active, evidence-based security response.

---

## Non-Goals

- **No client-side security decisions:** The console never computes risk scores, evaluates policy rules, or blocks tool execution. All security decisions remain 100% backend-enforced.
- **No synthetic data:** The console never fabricates metric counters or placeholder states when backend APIs return empty payloads.
- **No single-page rewrite:** The console evolves incrementally without breaking existing paths or user bookmarks.

---

## Tradeoffs

- **Strict backend dependency:** Advanced operational views (e.g., Approval Queue, Behavioral Findings) cannot render until corresponding backend APIs exist.
- **Cognitive shift:** Experienced administrators moving from flat database tables to workflow-centric queues require minor adjustment to operational habits.

---

## Dependencies

- **Backend Management API** ([ADR-008](../../adr/ADR-008-enterprise-management-api.md)): Source of truth for platform state.
- **Behavioral Intelligence Suite** ([ADR-014](../../adr/ADR-014-behavioral-intelligence-and-autonomous-agent-governance.md) – [ADR-021](../../adr/ADR-021-multi-agent-governance.md)): Source of telemetry, findings, risk assessments, and enforcement decisions.

---

## Relationship to Other Architecture Documents

- Implements the UI capabilities outlined in [ADR-009](../../adr/ADR-009-enterprise-security-console.md) and [ADR-020](../../adr/ADR-020-agent-security-operations.md).
- Formally authorized by [ADR-022](../../adr/ADR-022-enterprise-security-console-evolution.md).
- Detailed design principles defined in [02-design-principles.md](02-design-principles.md).

---

## Future Evolution

As backend multi-agent governance ([ADR-021](../../adr/ADR-021-multi-agent-governance.md)) matures, the console will incorporate agent topology graph views and inter-agent trust relationship inspection under the **GOVERN** operational mode without altering the foundational overview architecture.
