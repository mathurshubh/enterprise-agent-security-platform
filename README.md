# Enterprise Agent Security Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688)
![Tests](https://img.shields.io/badge/Tests-97_Passing-success)
![Release](https://img.shields.io/badge/Release-v0.8.0-blue)
![Providers](https://img.shields.io/badge/Providers-Ollama_|_Gemini-orange)
![Security](https://img.shields.io/badge/Security-Zero_Trust-red)
![License](https://img.shields.io/badge/License-MIT-green)

Enterprise Agent Security Platform is a production-style reference implementation for governing enterprise AI agents using Zero Trust security principles.

The platform treats Large Language Models (LLMs) as untrusted intent parsers while enforcing deterministic authorization, policy evaluation, risk assessment, detection, response, and audit logging before any interaction with enterprise resources.

The current implementation builds on the v0.8 provider-agnostic architecture while extending the platform toward the v0.9 Rich Tool Ecosystem roadmap.

Current status: v0.8 establishes the provider-agnostic runtime and deterministic security pipeline. v0.9 focuses on expanding the governed tool ecosystem before introducing advanced AI security detections in v1.0.

Current implementation focuses on deterministic runtime governance for AI agents. Advanced behavioral detection, observability, and multi-agent capabilities are planned for future releases.

---

## Architecture Highlights

- Provider-agnostic LLM architecture
- Zero Trust security model
- Deterministic authorization pipeline
- Resource-aware policy enforcement
- Pluggable provider abstraction
- Runtime security telemetry

---

## Key Design Principles

- Zero Trust Architecture
- Deterministic Security Enforcement
- Provider Independence
- Least Privilege Authorization
- Full Auditability
- LLMs Treated as Untrusted Intent Parsers

---

## Problem Statement

Organizations are increasingly deploying AI agents with access to enterprise systems, repositories, APIs, and sensitive data.

This project explores how organizations can safely enable AI agents while maintaining:

- Visibility
- Governance
- Authorization
- Risk Management
- Auditability
- Detection Engineering

---

## What's New in v0.8

- Provider-agnostic architecture
- EnterpriseAgent abstraction
- Gemini provider support
- ProviderFactory
- Externalized provider configuration
- 97 automated tests

---

## Enterprise AI Security Focus

This project is designed around enterprise AI security requirements including:

- Agent identity and traceability
- AI asset inventory
- Model governance
- Policy-based authorization
- Auditable controls
- Continuous monitoring
- Risk classification
- Adaptive security controls

---

## Core Capabilities

### Agent Runtime

- Provider-Agnostic Tool Selection
- EnterpriseAgent Abstraction
- Multi-Provider LLM Support
- Structured Tool Invocation Generation
- Natural Language Query Routing
- Tool Invocation Modeling
- Agent Runtime Orchestration
- Secure Local Tool Execution Foundations

### AI Governance

- Agent Inventory
- AI Asset Inventory
- Model Governance
- Risk Classification
- Identity & Traceability

### Security Controls

- Identity Foundation
- RBAC
- Tool Authorization
- Policy Enforcement
- Resource-Aware Authorization
- Session Context
- Adaptive Security Controls

### Security Monitoring

- Security Event Recording
- Detection Engineering
- Risk Management
- Security Telemetry
- Control Effectiveness Monitoring

### Future Enterprise Capabilities

- Human Approval Workflows
- Shadow AI Discovery
- Model Provenance Tracking
- Supply Chain Visibility

---

## Architecture

```text
User Request
      │
      ▼
Enterprise Agent
      │
      ▼
Configured LLM Provider
(Ollama / Gemini)
      │
      ▼
ToolInvocation
      │
      ▼
Deterministic Security Pipeline
      │
      ▼
Secure Tool Execution
```

---

## Documentation

The project documentation is organized as follows:

```text
docs/
├── api/
│   └── openapi-design.md
├── architecture/
│   ├── system-architecture.md
│   └── data-model.md
├── evaluations/
│   └── tool-selection-evaluation-v1.md
├── releases/
│   └── v0.8.0.md
└── security/
    └── threat-model.md
```

### Key Documents

- **System Architecture:** `docs/architecture/system-architecture.md`
- **Threat Model:** `docs/security/threat-model.md`
- **OpenAPI Design:** `docs/api/openapi-design.md`
- **LLM Evaluation:** `docs/evaluations/tool-selection-evaluation-v1.md`
- **Release Notes:** `docs/releases/v0.8.0.md`

---

### Near-Term Roadmap

- Indirect Prompt Injection Detection
- Human Approval Workflow
- Browser-Based Security Dashboard

---

## AI-Powered Tool Selection

The platform uses a provider-agnostic architecture to translate natural language requests into validated `ToolInvocation` objects.

Current provider implementations include:

- Ollama
- Gemini

The selected provider is instantiated during application initialization through the ProviderFactory based on the configured provider.

Regardless of the selected provider, every ToolInvocation passes through deterministic authorization, policy evaluation, detection, risk assessment, response enforcement, and audit logging before interacting with enterprise resources.

---

## Tech Stack

Backend

- FastAPI
- Pydantic

AI & LLM

- Ollama
- Google Gemini
- Llama 3.2 via Ollama

Security

- PyJWT

Testing

- Pytest

Observability (Planned)

- OpenTelemetry
- Prometheus
- Grafana
- Jaeger

---

## Quick Start

### Ollama Setup

```bash
ollama pull llama3.2:3b
ollama serve
```

### Project Setup

```bash
git clone https://github.com/mathurshubh/enterprise-agent-security-platform.git

cd enterprise-agent-security-platform

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

python -m pytest
```

---

## Running the Demo

Start the Python REPL:

```bash
python
```

Then run:

```python
from app.services.agent_runtime_service import AgentRuntimeService

service = AgentRuntimeService()

print(service.execute("read notes.txt"))
print(service.execute("read secrets.txt"))
```

---

## Example

Query

```text
please read notes.txt
```

↓

Tool Selected

```text
file_read
```

↓

Policy Decision

```text
ALLOW
```

↓

Output

```text
notes.txt contents
```

---

Query

```text
please read secrets.txt
```

↓

Tool Selected

```text
file_read
```

↓

Policy Decision

```text
DENY
```

↓

Output

```text
None
```

---

## Repository Structure

```text
enterprise-agent-security-platform/
│
├── app/
│   │
│   ├── __init__.py
│   ├── agents/                  # Enterprise agent abstractions
│   │   └── enterprise_agent.py
│   │
│   ├── api/                     # FastAPI endpoints
│   │
│   ├── auth/                    # Authentication and authorization
│   │
│   ├── config/                  # Application configuration
│   │
│   ├── models/                  # Domain models
│   │
│   ├── policy/                  # Policy evaluation engine
│   │
│   ├── providers/               # LLM provider abstraction layer
│   │   ├── provider_adapter.py
│   │   ├── provider_factory.py
│   │   ├── ollama_provider.py
│   │   └── gemini_provider.py
│   │
│   ├── services/                # Business logic and orchestration
│   │
│   └── tools/                   # Secure tool implementations
│
├── demo_workspace/              # Sample workspace for runtime demonstrations
│
├── docs/
│   ├── api/                     # API design documentation
│   ├── architecture/            # Architecture and design documents
│   ├── evaluations/             # LLM evaluation reports
│   ├── releases/                # Release notes
│   └── security/                # Threat model and security documentation
│
├── scripts/                     # Development and validation utilities
│
├── tests/
│   ├── api/
│   ├── auth/
│   ├── models/
│   ├── policy/
│   ├── providers/
│   ├── scenarios/
│   ├── services/
│   └── tools/
│
├── requirements.txt             # Python dependencies
├── pytest.ini                   # Pytest configuration
└── README.md                    # Project overview
```

---

### Planned Technologies

- OpenTelemetry
- Prometheus
- Grafana
- Jaeger

---

## Project Goals

- Demonstrate production-style Enterprise AI Security architecture and governance patterns.
- Showcase Agent Governance Controls
- Implement Security-Focused Design Patterns
- Build a Production-Style Portfolio Project

---

## Current Implementation Status

### Security Validation Flow

```text
Attack Scenarios
  ↓
Scenario Runner
  ↓
Runtime Service
  ↓
Authorization Service
  ↓
Detection Service
  ↓
Risk Service
  ↓
Scenario Results
  ↓
Automated Security Validation
```

### Implemented

#### Domain Models

- Agent
- Tool
- Audit Event
- JWT Claims
- Tool Execution Request
- Session
- Session Event
- Finding
- Risk Assessment
- Response Action
- Tool Invocation
- Runtime Result
- Agent Runtime Result
- Tool Metadata

#### Agents

- EnterpriseAgent

#### Provider Layer

- ProviderFactory
- ProviderAdapter
- OllamaProvider
- GeminiProvider

#### Services

- Agent Inventory Service
- Tool Registry Service
- Audit Service
- JWT Authentication Service
- Authorization Service
- Policy Engine
- Resource-Aware Authorization Policies
- Session Service
- Model Registry Service
- Detection Service
- Risk Service
- Response Service
- Runtime Service
- Scenario Runner Service
- Ollama Service
- Agent Runtime Service
- Security-Mediated Execution Pipeline
- Secure File Read Tool
- Secure Directory List Tool
- Runtime Authorization Pipeline

#### Testing

- Pytest-based unit tests
- Agent Service tests
- Tool Service tests
- Audit Service tests
- JWT Service tests
- Authorization Service tests
- Session Service tests

Current test status:

```bash
python -m pytest
```

Current validation:

- 97 automated tests passing
- Resource-aware authorization validated
- Governed agent execution validated
- LLM tool selection evaluation completed (14/15 scenarios passed)
- Manual validation completed for governed agent execution
- Manual validation completed for resource-aware authorization

Manual tool selection evaluation:

- Model: llama3.2:3b
- 14/15 evaluation scenarios passed (93.3%)
- See docs/evaluations/tool-selection-evaluation-v1.md

### Immediate Next Milestone

- v0.9 – Rich Tool Ecosystem

### Upcoming Roadmap

- Prompt Injection Detection
- Indirect Prompt Injection Detection
- Automated LLM Evaluation Suite
- Human Approval Workflow
- Browser-Based Dashboard
- Agent Observability

---

## Future Vision: Agentic Security Analytics

The long-term vision for this platform extends beyond runtime protection into evidence-driven AI Security Operations.

The objective is to help security teams investigate, understand, and govern autonomous agents using natural language while preserving auditability, explainability, and human oversight.

Potential capabilities include:

- Prompt injection trend analysis
- Agent risk investigations
- Executive AI security posture reporting
- Root cause analysis assistance
- Evidence-backed recommendation generation
- Security analyst investigation workflows

Any future analytics capability will adhere to the following principles:

- Evidence Grounding: Every conclusion must reference supporting telemetry.
- Authorization Awareness: Access to analytics will remain role-based and policy-aware.
- Prompt Injection Resistance: Retrieved evidence will be treated as untrusted input.
- Auditability: Investigations, evidence retrieval, reports, and approvals will be logged.
- Human Oversight: Recommendations will support analysts rather than automatically triggering security actions.

This capability is not part of the current MVP and will only be considered after the runtime security platform, telemetry collection, and validation framework have matured.

The goal is not to build another chatbot, but rather an AI Security Analytics capability that helps humans understand, investigate, and govern autonomous agents.

---

## Roadmap Beyond v1.0

- Indirect Prompt Injection Detection
- Session-Based Behavioral Analysis
- Advanced Resource-Aware Authorization Policies
- Risk-Based Authorization
- MITRE ATLAS Technique Mapping
- OWASP LLM Top 10 Coverage Mapping
- AI Asset Inventory
- Model Governance and Provenance
- Control Effectiveness Metrics
- Agent Traceability and Investigation Workflows
- Agent Attack Simulations
- Adversarial Evaluation Harness
- Prompt Injection Validation Scenarios
- Tool Abuse Simulation Framework
- Adaptive Security Controls
- Multi-Agent Governance
- Security Posture Scoring
- Agent Risk Analytics
- Shadow AI Discovery
- Unauthorized Model Detection
- Unregistered Agent Detection

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.