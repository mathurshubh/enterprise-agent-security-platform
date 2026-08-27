# Enterprise Agent Security Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688)
![Tests](https://img.shields.io/badge/Tests-335_Passing-success)
![GitHub Release](https://img.shields.io/badge/GitHub_Release-v0.15-blue)
![Git Tag](https://img.shields.io/badge/Git_Tag-v0.15.0-blue)
![Development Cycle](https://img.shields.io/badge/Development-v0.16.0--dev-orange)
![Providers](https://img.shields.io/badge/Providers-Ollama_|_Gemini-orange)
![Security](https://img.shields.io/badge/Security-Zero_Trust-red)
![License](https://img.shields.io/badge/License-MIT-green)

**A production-quality reference implementation of Zero Trust security controls for enterprise AI agents.**

A Zero Trust security platform for governing autonomous AI agents in enterprise environments. Rather than building another AI agent framework, this platform provides runtime security orchestration, policy-driven authorization, real-time threat detection, dynamic risk assessment, and risk-based response controls.

> **The platform treats every LLM as an untrusted intent parser. All security decisions remain deterministic, auditable, and are enforced outside the AI model.**

---

## What This Platform Is

The Enterprise Agent Security Platform is a security and governance layer for enterprise AI agents.

It is **not** an AI agent framework or orchestration tool.

Instead, it provides deterministic security controls around AI agents, including:

- Authentication (JWT, RBAC)
- Resource-Aware Authorization
- Policy Enforcement
- Threat Detection & Behavioral Intelligence
- Authoritative Security Findings Persistence
- Dynamic Risk Assessment & Risk Level Calculation
- Automated Response Actions
- Immutable Audit Logging
- Management API & Enterprise Findings Console

---

## High-Level Architecture

```mermaid
flowchart TD
    A["User Request"] --> B["Enterprise Agent"]
    B --> C["Provider-Agnostic LLM (Intent Parser)"]
    C --> D["ToolInvocation"]
    D --> E["RuntimeService (Single Security Authority)"]
    E --> F["Authorization & Policy Engine"]
    F --> G["Session Event Recording"]
    G --> H["Threat Detection Engine"]
    H --> I["FindingsService (Authoritative Evidence)"]
    I --> J["RiskService (Derived Posture: session_id + agent_id)"]
    J --> K["ResponseService (Recommendation & Enforcement)"]
    K --> L{"Authoritative Decision"}
    L -->|ALLOW| M["Tool Execution"]
    L -->|DENY| N["Blocked"]
    L -->|APPROVAL_REQUIRED| O["Held for Review"]
    E --> P["Audit Event Logging"]
```

`RuntimeService` is the single authoritative source of security decisions. The LLM never makes authorization, policy, detection, risk, or enforcement decisions.

---

## Release & Platform Status

- **Latest Published GitHub Release:** `v0.15`
- **Latest Repository Tag:** `v0.15.0`
- **Current Development Cycle:** `v0.16.0` — Unreleased
- **Active Baseline PR:** PR #87 (Documentation, Architecture & Roadmap Synchronization)
- **Automated Test Coverage:** **335 passing backend pytest tests** (`.venv/bin/python -m pytest`)
- **Frontend Build Status:** Passing (`npm run build` & `npm run lint`)

---

## Project Metrics

| Metric | Value |
|----------|---------|
| Automated Tests | 335 Passing |
| Latest Published GitHub Release | v0.15 |
| Latest Repository Tag | v0.15.0 |
| Current Development Cycle | v0.16.0 (Unreleased) |
| Detection Rules | 4 (`PROMPT_INJECTION`, `SENSITIVE_FILE_ACCESS`, `DATA_EXFILTRATION`, `EXCESSIVE_DENIALS`) |
| Security Framework Mappings | 3 (OWASP LLM Top 10, MITRE ATLAS, MITRE ATT&CK) |
| Core Services | 10+ (`AgentService`, `ToolService`, `SessionService`, `FindingsService`, `RiskService`, `ResponseService`, `AuditService`, `RuntimeService`, `CapabilityService`, `ScenarioRunnerService`) |
| Python Version | 3.13+ |
| Security Model | Zero Trust (Deterministic Security Pipeline) |

---

## Core Design Principles

This platform is engineered around the following core security and software design principles:

*   **Zero Trust Architecture:** Every request is authenticated, authorized, evaluated, and audited; no internal transitions or agent actions are implicitly trusted.
*   **Deterministic Security Decisions:** All authorization, detection, risk assessment, and mitigation logic is implemented in deterministic code. The LLM never makes security decisions.
*   **Least Privilege Access:** Agents are restricted to explicitly approved tools and resources, guided by dynamic policies that evaluate agent and tool metadata.
*   **LLM as an Untrusted Intent Parser:** The AI model is treated as an untrusted client whose sole responsibility is converting natural language into structured request objects (`ToolInvocation`).
*   **Authoritative Evidence vs Derived Posture:** `Finding` objects stored in `FindingsService` represent authoritative security evidence. `RiskAssessment` objects in `RiskService` represent derived process-local posture indexed by composite `(session_id, agent_id)` keys.
*   **Cumulative Risk Posture:** Dynamic risk calculation aggregates all authoritative findings recorded for a session and agent scope. Subsequent benign tool executions maintain the session's cumulative risk level.
*   **Complete Auditability:** Every tool request, authorization decision, policy evaluation, finding, risk score, and mitigation action is logged as an immutable event.
*   **Provider-Agnostic Design:** Core security services are decoupled from underlying LLMs, permitting integration with alternative AI providers (Ollama, Gemini).

---

## Runtime Security Pipeline

The `RuntimeService` executes a deterministic security pipeline for every incoming `ToolInvocation`:

```text
1. Authorization     → Is the agent permitted to use this tool?
2. Policy Evaluation → Does the resource-aware policy allow this action?
3. Session Event     → Record the initial decision state
4. Detection         → Run detection rules against prompt, model output, tool output, and session events
5. Findings          → Record security findings in FindingsService (authoritative evidence)
6. Risk Assessment   → Calculate cumulative risk score and risk level for (session_id, agent_id) scope
7. Response          → Select response recommendation based on risk level
8. Decision Override → Apply Zero Trust enforcement (SUSPEND_AGENT → DENY, REQUIRE_APPROVAL → APPROVAL_REQUIRED)
9. Audit Event       → Record the final authoritative decision in AuditService
10. Execution        → Governed tool execution occurs ONLY if the final decision is ALLOW
```

---

## Implemented Platform Capabilities

### Core Runtime & Provider Layer
- Enterprise Agent Runtime
- Provider-agnostic LLM abstraction (Ollama, Gemini)
- Deterministic `RuntimeService` as single security authority
- Governed tool execution through Tool Registry
- Scenario Execution Engine & Framework
- Runtime Capability Discovery (`CapabilityService`, `PlatformCapabilities`)

### Security & Governance
- JWT authentication
- Role-Based Access Control (RBAC)
- Agent authorization service
- Resource-aware Policy Engine
- Session management (`SessionService`)
- Immutable audit event logging (`AuditService`)

### Behavioral Intelligence, Findings & Dynamic Risk
- Threat Detection Engine & Registry
- Prompt Injection Detection (`PROMPT_INJECTION`)
- Sensitive File Access Detection (`SENSITIVE_FILE_ACCESS`)
- Data Exfiltration Detection (`DATA_EXFILTRATION`)
- Excessive Denials Detection (`EXCESSIVE_DENIALS`)
- Security Standards Mapping (OWASP LLM Top 10, MITRE ATLAS, MITRE ATT&CK)
- **Findings & Alerts API (`GET /api/v1/findings`, `FindingsService`)**
- **Dynamic Risk Assessment Engine (`RiskService`, `GET /api/v1/risk-assessments`)**
- **Risk Assessment Scope Isolation:** Derived posture indexed by composite `(session_id, agent_id)` keys with `400 Bad Request` ambiguity protection.
- Response Actions & Zero Trust Overrides (`MONITOR`, `ALERT`, `REQUIRE_APPROVAL`, `SUSPEND_AGENT`)

### Management API & Enterprise Security Console
- Read-only Management API endpoints (`/v1/agents`, `/v1/tools`, `/v1/sessions`, `/v1/audit/events`, `/v1/findings`, `/v1/risk-assessments`)
- Enterprise Security Console UI (`/agents`, `/tools`, `/sessions`, `/rules`, `/findings`)

---

## Security Standards Mapping

Detection rules are mapped to industry security frameworks:

| Rule | Framework | Control ID | Title |
|------|-----------|------------|-------|
| `PromptInjectionRule` | OWASP LLM Top 10 | LLM01 | Prompt Injection |
| `PromptInjectionRule` | MITRE ATLAS | AML.T0043 | User Prompt Injection |
| `SensitiveFileAccessRule` | MITRE ATT&CK | T1083 | File and Directory Discovery |
| `DataExfiltrationRule` | MITRE ATT&CK | T1048 | Exfiltration Over Alternative Protocol |

---

## Tech Stack

- **Backend:** Python 3.13+, FastAPI, Pydantic
- **Frontend:** React, TypeScript, TanStack Query, Vite, Tailwind CSS
- **AI & LLM Integration:** Ollama (Llama 3.2), Google Gemini
- **Security & Authentication:** PyJWT
- **Testing & Quality:** Pytest, ESLint, Vite Build

---

## Quick Start

### 1. Ollama Setup

```bash
ollama pull llama3.2:3b
ollama serve
```

### 2. Backend Setup & Verification

```bash
git clone https://github.com/mathurshubh/enterprise-agent-security-platform.git
cd enterprise-agent-security-platform

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

.venv/bin/python -m pytest
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run build
npm run lint
```

---

## Testing

The platform maintains a comprehensive automated test suite executed with Pytest:

- **326 passing automated tests** covering authorization, policies, detection rules, findings service, risk service, runtime execution, management APIs, and scenario validation.
- **Ruff & ESLint** workflows enforce code quality.

```bash
.venv/bin/python -m pytest
```

---

## Documentation

- **DevSecOps & Quality Gates:** `docs/development/ci-cd-devsecops.md`
- **System Architecture:** `docs/architecture/system-architecture.md`
- **Data Model:** `docs/architecture/data-model.md`
- **Threat Model:** `docs/security/threat-model.md`
- **OpenAPI Design:** `docs/api/openapi-design.md`
- **Architecture Decision Records:** `docs/adr/` (ADR-000 through ADR-022)
- **PR #87 Documentation Audit & Plan:** `docs/research/pr-87-documentation-audit.md` & `docs/research/pr-87-documentation-plan.md`

---

## Future Roadmap

The roadmap defines the capability-based evolution of the platform. Sequencing preserves architectural flexibility as the system matures.

```text
Documentation & Baseline Synchronization (v0.16.0 Development Baseline)
      ↓
Phase 1: CI/CD & DevSecOps Quality Gates
      ↓
Phase 2: Observability & Distributed Tracing (OpenTelemetry, Prometheus, Grafana, Jaeger)
      ↓
Phase 3: Agent Abstraction Framework
      ↓
Phase 4: Rich Governed Tool Ecosystem (FileWriteTool, Network/HTTP, Governed Browser)
      ↓
Phase 5: Model Context Protocol (MCP) Integration Layer
      ↓
Phase 6: Multi-Agent & Agent-to-Agent (A2A) Security Governance
      ↓
Phase 7: Advanced Behavioral Intelligence & Anomaly Detection
      ↓
Phase 8: Automated Adversarial AI Security Evaluation (Promptfoo, Garak, PyRIT)
      ↓
Enterprise Multi-Agent Security Platform
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
