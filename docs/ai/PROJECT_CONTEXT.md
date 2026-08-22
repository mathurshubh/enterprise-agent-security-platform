# Enterprise Agent Security Platform

Enterprise Agent Security Platform is a Zero Trust governance platform for enterprise AI agents.

The platform is NOT an AI agent.

The platform governs AI agents.

Its purpose is to provide deterministic security controls for enterprise agent execution.

Core principles:

- Zero Trust
- Least Privilege
- Deterministic Authorization
- Full Auditability
- Provider Agnostic
- LLM as Untrusted Intent Parser
- Authoritative Evidence vs Derived Posture Separation

Release Status:

- Latest Published GitHub Release: `v0.13.1`
- Latest Repository Tag: `v0.15.0`
- Current Development Cycle: `v0.16.0` — Unreleased
- Baseline PR: PR #87 (Documentation, Architecture & Roadmap Synchronization)

Implemented Capabilities:

- Agent Registry & Tool Registry
- JWT Authentication & RBAC
- Policy Engine with Resource-Aware Authorization
- Deterministic `RuntimeService` Single Security Authority
- Detection Engine (`PROMPT_INJECTION`, `SENSITIVE_FILE_ACCESS`, `DATA_EXFILTRATION`, `EXCESSIVE_DENIALS`)
- Attack Scenario Framework & Security Standards Mapping (OWASP LLM, MITRE ATLAS, MITRE ATT&CK)
- Provider Abstraction (Ollama, Gemini)
- Runtime Capability Discovery (`CapabilityService`, `PlatformCapabilities`)
- **Findings & Alerts API (`GET /api/v1/findings`, `FindingsService`)**
- **Enterprise Findings Console UI (`/findings`)**
- **Dynamic Risk Engine & Management API (`RiskService`, `GET /api/v1/risk-assessments`)**
- **Risk Assessment Integrity & Isolation:** Composite `(session_id, agent_id)` identity with HTTP 400 Bad Request ambiguity protection
- **326 passing backend pytest tests**

---

## Non-Goals

This repository is not intended to:

- Build a general-purpose AI agent framework.
- Replace enterprise IAM or SIEM platforms.
- Delegate security decisions to LLMs.
- Demonstrate prompt engineering techniques.
- Serve as a chatbot application.

Its purpose is to provide a deterministic Zero Trust security layer governing enterprise AI agents.
