# Enterprise Agent Security Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688)
![Tests](https://img.shields.io/badge/Tests-128_Passing-success)
![Release](https://img.shields.io/badge/Release-v0.9.0-blue)
![Providers](https://img.shields.io/badge/Providers-Ollama_|_Gemini-orange)
![Security](https://img.shields.io/badge/Security-Zero_Trust-red)
![License](https://img.shields.io/badge/License-MIT-green)

Enterprise Agent Security Platform is a production-style Zero Trust governance platform for enterprise AI agents. Rather than building another AI agent framework, the project focuses on governing AI agents through deterministic security controls, authorization, policy enforcement, runtime monitoring, and auditability.
The platform treats Large Language Models (LLMs) as untrusted intent parsers.
Authorization, policy evaluation, detection, risk assessment, response, and audit logging remain deterministic.
Version 0.9 introduces a governed Rich Tool Ecosystem featuring Tool Registry, Rich Tool Metadata, Tool Discovery, and Tool Inventory.
Future releases will focus on observability, attack detection, and multi-agent governance.

---

## Why This Project?

Most AI agent frameworks focus on agent capabilities.
Enterprise Agent Security Platform focuses on governing those agents.
The platform demonstrates how organizations can apply Zero Trust principles to AI agents by separating natural language understanding from deterministic security enforcement.

---

## Security Architecture

The Enterprise Agent Security Platform treats Large Language Models (LLMs) as untrusted intent parsers rather than trusted decision makers.
Every request follows a deterministic security pipeline:

```
User Request
        ↓
Enterprise Agent
        ↓
ToolInvocation
        ↓
Authorization
        ↓
Policy Evaluation
        ↓
Detection
        ↓
Risk Assessment
        ↓
Response Selection
        ↓
Audit Logging
        ↓
Tool Registry
        ↓
Secure Tool Execution
```

The LLM never makes authorization, policy, or security decisions. All security controls remain deterministic and independently enforceable.

---

## Key Design Principles

- Zero Trust Architecture
- Deterministic Security Enforcement
- Provider-agnostic Architecture
- Least Privilege Authorization
- Full Auditability
- LLMs Treated as Untrusted Intent Parsers

---

## Runtime Architecture

```text
User Request
      │
      ▼
Enterprise Agent
      │
      ▼
Configured LLM Provider
      │
      ▼
ToolInvocation
      │
      ▼
Authorization
      │
      ▼
Policy Engine
      │
      ▼
Detection
      │
      ▼
Risk
      │
      ▼
Response
      │
      ▼
Tool Registry
      │
      ▼
Resolved BaseTool
      │
      ├── FileReadTool
      ├── DirectoryListTool
      └── Future Tools
      │
      ▼
Secure Tool Execution
```

---

## Architecture Highlights

- Provider-agnostic LLM architecture
- Zero Trust security model
- Deterministic authorization pipeline
- Resource-aware policy enforcement
- Pluggable provider abstraction
- Deterministic runtime security pipeline
- Rich Tool Metadata
- Centralized Tool Registry
- Tool Discovery and Inventory
- Governed Tool Execution

---

## What's New in v0.9

- Tool Registry
- Rich Tool Metadata
- BaseTool abstraction
- Runtime Tool Resolution
- Tool Discovery
- Tool Inventory Service
- Provider-agnostic LLM support
- 128 automated tests

---

## Enterprise Tool Governance

Every executable tool implements the `BaseTool` abstraction and registers immutable `ToolMetadata` describing its identity, capabilities, governance attributes, and operational characteristics.
The runtime resolves tools through the centralized Tool Registry rather than executing implementations directly. Discovery and inventory services expose only `ToolMetadata`, while executable tool instances remain behind deterministic authorization, policy evaluation, detection, risk assessment, and response controls.

---

## Engineering Metrics

- 128 automated tests
- Zero test warnings
- Provider-agnostic runtime architecture
- 2 LLM providers
- Zero Trust architecture
- Rich Tool Metadata model
- Tool Registry
- Tool Discovery
- Tool Inventory Service
- Provider-agnostic tool execution pipeline

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

## AI-Powered Tool Selection

The platform uses a provider-agnostic architecture to translate natural language requests into validated `ToolInvocation` objects.
Validated ToolInvocation objects are resolved through the Tool Registry before execution.
The Tool Registry resolves executable tools using immutable Tool Metadata while keeping execution behind deterministic security controls.
Current provider implementations include:
- Ollama
- Gemini
The selected provider is instantiated during application initialization through the ProviderFactory based on the configured provider.
Regardless of the selected provider, every `ToolInvocation` passes through deterministic authorization, policy evaluation, detection, risk assessment, response selection, and audit logging. Only after these controls succeed does the runtime resolve the requested tool through the Tool Registry and execute the appropriate `BaseTool` implementation.

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
│   └── v0.9.0.md
└── security/
    └── threat-model.md
```

### Key Documents

- **System Architecture:** `docs/architecture/system-architecture.md`
- **Threat Model:** `docs/security/threat-model.md`
- **OpenAPI Design:** `docs/api/openapi-design.md`
- **LLM Evaluation:** `docs/evaluations/tool-selection-evaluation-v1.md`
- **Release Notes:** `docs/releases/v0.9.0.md`

---

## Repository Structure

```text
enterprise-agent-security-platform/
│
├── app/
│   ├── agents/          # Enterprise agent implementations
│   ├── api/             # FastAPI REST API
│   ├── auth/            # Authentication & authorization
│   ├── config/          # Configuration
│   ├── models/          # Domain models
│   ├── policy/          # Deterministic policy engine
│   ├── providers/       # LLM provider abstraction
│   ├── registry/        # Tool Registry and discovery
│   ├── services/        # Runtime orchestration services
│   └── tools/           # Governed tool implementations
│
├── demo_workspace/      # Demo workspace
├── docs/                # Architecture, security and release docs
├── scripts/             # Development utilities
├── tests/               # Unit and scenario tests
├── requirements.txt
├── pytest.ini
├── LICENSE
├── SECURITY.md
└── README.md
```

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

#### Core Runtime
- Enterprise Agent Runtime
- Provider-agnostic LLM integration
- Runtime orchestration
- Governed tool execution through the Tool Registry

#### Security Platform
- JWT authentication
- Authorization service
- Policy engine
- Resource-aware authorization
- Detection service
- Risk service
- Response service
- Audit logging
- Session management

#### Tool Ecosystem
- Rich Tool Metadata
- BaseTool abstraction
- Tool Registry
- Tool Discovery
- Tool Inventory Service
- File Read Tool
- Directory List Tool

#### Testing & Validation
- 128 automated tests
- Runtime scenario validation
- Authorization validation
- Tool selection evaluation
- Zero test warnings

Current validation:

- 128 automated tests passing
- 0 test warnings
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

- v0.9.1 – Enterprise Management Console

### Upcoming Roadmap

Near-term priorities:
- Enterprise Management Console
- Human Approval Workflow
- Browser-Based Security Dashboard

- Indirect Prompt Injection Detection
- Prompt Injection Detection
- Automated LLM Evaluation Suite
- Agent Observability
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

### Planned Technologies

- OpenTelemetry
- Prometheus
- Grafana
- Jaeger

---

## Project Goals

- Demonstrate production-style Zero Trust governance for enterprise AI agents.
- Showcase deterministic security architecture and secure engineering patterns.
- Build a production-quality AI security portfolio project.
- Provide a reference architecture for governed enterprise AI agents.

---

## Future Vision: Agentic Security Analytics

The long-term vision is to evolve the platform from runtime governance into a comprehensive enterprise AI Security Operations capability.
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

The long-term objective is to evolve the platform into an evidence-driven AI Security Operations capability that assists human analysts while preserving deterministic governance, explainability, and human oversight.

This capability is not part of the current MVP and will only be considered after the runtime security platform, telemetry collection, and validation framework have matured.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.