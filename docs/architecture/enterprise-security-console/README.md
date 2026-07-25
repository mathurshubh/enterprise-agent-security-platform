# Enterprise Security Console Architecture

This directory contains the production-quality technical architecture specification for the **Enterprise Security Console** of the Enterprise Agent Security Platform.

This architecture governs the long-term evolution of the platform's frontend user interface from version `v0.12.0` through `v1.0.0`. It transforms the initial management console into a workflow-centric, evidence-first **Enterprise Security Operations Console** tailored for SOC analysts, security engineers, and governance officers.

---

## Purpose

To provide an authoritative architectural reference for the long-term design, component structure, navigation model, data flow, and backend alignment of the Enterprise Security Console frontend.

---

## Scope

Governs all user interface architecture, components (`src/components/`), layout wrappers (`src/layouts/`), route definitions (`src/App.tsx`), service layer wrappers (`src/services/`), type definitions (`src/types/`), and data flow hooks (`src/hooks/`) within `frontend/` across releases `v0.12.0` through `v1.0.0`.

---

## Document Index

| Index | Document | Description |
|---|---|---|
| **01** | [01-overview.md](01-overview.md) | Platform purpose, core users, operational questions, non-goals, and vision. |
| **02** | [02-design-principles.md](02-design-principles.md) | The 10 immutable architectural principles governing every frontend decision. |
| **03** | [03-information-architecture.md](03-information-architecture.md) | Two-axis IA model (Lifecycle Progression × Scope Granularity). |
| **04** | [04-navigation-architecture.md](04-navigation-architecture.md) | 3-mode primary navigation (MONITOR, INVESTIGATE, GOVERN) and migration path. |
| **05** | [05-operational-model.md](05-operational-model.md) | Work-oriented Command Center (Action Queue + Operational Awareness). |
| **06** | [06-investigation-graph.md](06-investigation-graph.md) | The Canonical Investigation Graph as a first-class architectural contract. |
| **07** | [07-session-investigation-workspace.md](07-session-investigation-workspace.md) | The central multi-panel forensic investigation environment. |
| **08** | [08-page-specifications.md](08-page-specifications.md) | Detailed specifications for all 9 canonical console pages. |
| **09** | [09-ui-component-architecture.md](09-ui-component-architecture.md) | Reusable architectural components and visual isolation of untrusted content. |
| **10** | [10-data-flow.md](10-data-flow.md) | Client data pipeline, TanStack Query caching, SSE streaming, and audited operator writes. |
| **11** | [11-implementation-roadmap.md](11-implementation-roadmap.md) | Four backend-gated implementation phases (v0.12.0 → v1.0.0). |

---

## Design Rationale

Structuring the architecture specification into eleven distinct, specialized documents ensures clean separation of concerns. Developers can consult the exact document relevant to their task—whether updating routing (`04-navigation-architecture.md`), adding a domain component (`09-ui-component-architecture.md`), or building query hooks (`10-data-flow.md`).

---

## Tradeoffs

- **Documentation Depth:** Maintenance requires ensuring that future frontend feature branches update the specific specification documents alongside code changes.

---

## Dependencies

- Serves as the primary specification container for [ADR-022: Enterprise Security Console Evolution](../../adr/ADR-022-enterprise-security-console-evolution.md).

---

## Relationship to Other Architecture Documents

- Implements requirements from [ADR-001](../../adr/ADR-001-zero-trust-security-model.md) through [ADR-021](../../adr/ADR-021-multi-agent-governance.md).
- Formally authorized by [ADR-022](../../adr/ADR-022-enterprise-security-console-evolution.md).

---

## Future Evolution

As platform milestones expand into `v1.0.0+` (such as advanced multi-agent Mesh visualizations), new specification chapters will be appended to this directory following the same architectural template.
