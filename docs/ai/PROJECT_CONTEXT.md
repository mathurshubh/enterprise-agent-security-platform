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

- Latest Published GitHub Release: `v0.15`
- Latest Repository Tag: `v0.15.0`
- Current Development Cycle: `v0.16.0` — Unreleased
- Version Authority Model: Git tags (`v*`) are the release authority; root `VERSION` file is the sole machine-readable authority (`0.15.0`). Neither backend nor frontend inspects `.git` at runtime. Public `GET /version` exposes release metadata distinct from `GET /health`.
- Architecture Baseline: Jan–Aug 2026 AI Security Architecture Review (`4abf2b6`)
- Automated Test Coverage: **851 passed, 7 xfailed** (`.venv/bin/python -m pytest`)
- Architecture Reference Range: ADR-000 through ADR-028

Implemented Capabilities:

- Agent Registry & Tool Registry
- JWT Authentication & Plane Authorization (role-gated API surfaces, execution identity bound to agent)
- Policy Engine with Resource-Aware Authorization
- Deterministic `RuntimeService` Single Security Authority
- Detection Engine (`PROMPT_INJECTION`, `SENSITIVE_FILE_ACCESS`, `DATA_EXFILTRATION`, `EXCESSIVE_DENIALS`)
- Attack Scenario Framework & Security Standards Mapping (OWASP LLM, MITRE ATLAS, MITRE ATT&CK)
- Provider Abstraction (Ollama, Gemini)
- Runtime Capability Discovery (`CapabilityService`, `PlatformCapabilities`)
- **Findings & Alerts API (`GET /api/v1/findings`, `FindingsService` authoritative evidence)**
- **Enterprise Findings Console UI (`/findings`)**
- **Dynamic Risk Engine & Management API (`RiskService`, `GET /api/v1/risk-assessments`)**
- **Materialized Risk Projections & Enforcement Epochs (`RiskAggregator`, ADR-026)**
- **Agent Enforcement State & Atomic Baselines (ADR-024, ADR-026)**
- **Execution Grants & Single-Use Tokens (`DefaultToolExecutor`, ADR-023)**
- **DevSecOps Quality Pipeline:** GitHub Actions (`ci.yml`), Gitleaks secret scanning, Dependabot (`dependabot.yml`), and multi-job quality gates

---

## Non-Goals

This repository is not intended to:

- Build a general-purpose AI agent framework.
- Replace enterprise IAM or SIEM platforms.
- Delegate security decisions to LLMs.
- Demonstrate prompt engineering techniques.
- Serve as a chatbot application.

Its purpose is to provide a deterministic Zero Trust security layer governing enterprise AI agents.
