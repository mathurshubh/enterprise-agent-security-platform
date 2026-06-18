# Enterprise Agent Security Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688)
![Tests](https://img.shields.io/badge/Tests-90_Passing-success)
![Release](https://img.shields.io/badge/Release-v0.7.0-purple)
![LLM](https://img.shields.io/badge/LLM-Ollama-orange)
![Security](https://img.shields.io/badge/Security-Zero_Trust-red)

Enterprise Agent Security Platform is a production-style reference implementation demonstrating how AI agents can be governed using Zero Trust security principles.

The platform intentionally separates intent understanding (LLM) from security enforcement (authorization, policy, detection, and risk assessment), ensuring that no security decision is delegated to the language model.

Unlike traditional AI agent projects that rely on the LLM for orchestration and security decisions, this platform treats the LLM as an untrusted intent parser while enforcing authorization, policy, detection, and risk management through deterministic services.

Enterprise-focused security platform for governing, authorizing, monitoring, and auditing AI agent interactions with enterprise resources. AI agents are treated as untrusted execution environments, with all actions evaluated through centralized authorization, auditing, policy enforcement, and risk management before interacting with enterprise resources.

## Problem Statement

Organizations are increasingly deploying AI agents with access to enterprise systems, repositories, APIs, and sensitive data.

This project explores how organizations can safely enable AI agents while maintaining:

- Visibility
- Governance
- Authorization
- Risk Management
- Auditability
- Detection Engineering

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

## Core Capabilities

### Agent Runtime

- LLM-Based Tool Selection (Ollama)
- Natural Language Query Routing
- Structured Tool Invocation Generation
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

- JWT Authentication
- RBAC
- Tool Authorization
- Policy Enforcement
- Resource-Aware Authorization
- Session Context
- Adaptive Security Controls

### Security Monitoring

- Audit Logging
- Detection Engineering
- Risk Management
- Security Telemetry
- Control Effectiveness Monitoring

### Future Enterprise Capabilities

- Human Approval Workflows
- Shadow AI Discovery
- Model Provenance Tracking
- Supply Chain Visibility

## Architecture

```text
User Query
  ↓
OllamaAgent
  ↓
Tool Invocation
  ↓
Agent Runtime Service
  ↓
Runtime Service
  ↓
Authorization Service
  ↓
Policy Engine
  ↓
Policy Decision
  ↓
Session Service
  ↓
Session Events
  ↓
Detection Service
  ↓
Findings
  ↓
Risk Service
  ↓
Risk Assessments
  ↓
Response Service
  ↓
Response Actions
  ↓
Secure Tool Execution
  ↓
File Read Tool / Directory List Tool
  ↓
Agent Runtime Result
```

## Documentation

The project documentation is organized as follows:

```text
docs/
├── api/
│   └── openapi-design.md              # REST API design
├── architecture/
│   ├── system-architecture.md         # Overall system architecture
│   └── data-model.md                  # Domain model and relationships
├── evaluations/
│   └── tool-selection-evaluation-v1.md # LLM tool selection evaluation
└── security/
    └── threat-model.md                # Threat model and security assumptions
```

### Key Documents

- **System Architecture:** `docs/architecture/system-architecture.md`
- **Threat Model:** `docs/security/threat-model.md`
- **OpenAPI Design:** `docs/api/openapi-design.md`
- **LLM Evaluation:** `docs/evaluations/tool-selection-evaluation-v1.md`
 
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

## Current Status

### Completed

Architecture

- System Architecture
- Threat Model
- OpenAPI Design
- Data Model

Security

- JWT Authentication
- Authorization
- Policy Engine
- Resource Authorization

Runtime

- Runtime Service
- Agent Runtime
- Ollama Integration
- LLM Tool Selection

Validation

- Scenario Framework
- Evaluation Framework
- 90 Automated Unit & Integration Tests

### Planned

- Human Approval Workflow
- Indirect Prompt Injection Detection
- Agent Abstraction
- Multi-Provider LLM Support (Gemini / OpenAI / Claude)
- Browser-Based Security Dashboard

## AI-Powered Tool Selection

The platform uses a locally hosted Ollama model to translate natural language requests into structured `ToolInvocation` objects.

Security decisions are never delegated to the LLM.

Every tool invocation is evaluated through deterministic authorization, resource-aware policies, behavioral detection, risk assessment, and response enforcement before interacting with enterprise resources.

The initial implementation was evaluated using a representative prompt suite covering supported requests, unsupported requests, and prompt injection scenarios. Results are documented in `docs/evaluations/tool-selection-evaluation-v1.md`.

## Tech Stack

Backend

- FastAPI
- Pydantic

AI

- Ollama
- Llama 3.2 3B (Local Inference)

Testing

- Pytest

Security

- PyJWT

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

Authorization

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

Authorization

```text
DENY
```

↓

Output

```text
None
```

## Project Structure

```text
enterprise-agent-security-platform/
├── app/
│   ├── api/             # FastAPI endpoints
│   ├── auth/            # Authentication & authorization
│   ├── models/          # Domain models
│   ├── policy/          # Policy evaluation engine
│   ├── services/        # Runtime orchestration & business logic
│   └── tools/           # Secure tool implementations
├── demo_workspace/      # Sample workspace for tool execution
├── docs/
│   ├── api/
│   ├── architecture/
│   ├── evaluations/
│   └── security/
├── tests/               # Unit and integration tests
├── requirements.txt
└── README.md
```

### Planned Technologies

- Redis
- OpenTelemetry
- Prometheus
- Grafana
- Jaeger

## Project Goals

- Demonstrate production-style Enterprise AI Security architecture and governance patterns.
- Showcase Agent Governance Controls
- Implement Security-Focused Design Patterns
- Build a Production-Style Portfolio Project

---

## Current Implementation Status

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

#### Services

- Agent Inventory Service
- Tool Registry Service
- Audit Logging Service
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
- Simple Agent (baseline implementation)
- Ollama Service
- Ollama Agent
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

- 90 automated tests passing
- Resource-aware authorization validated
- Governed agent execution validated
- LLM tool selection evaluated (14/15)
- Manual validation completed for governed agent execution
- Manual validation completed for resource-aware authorization

Manual tool selection evaluation:

- Model: llama3.2:3b
- 14/15 evaluation scenarios passed (93.3%)
- See docs/evaluations/tool-selection-evaluation-v1.md

### Immediate Next Milestone

- Agent Abstraction

### Upcoming Roadmap

- Agent Abstraction
- Multi-Provider LLM Support
- Automated LLM Evaluation Suite
- Prompt Injection Detection
- Human Approval Workflow
- Browser-Based Security Dashboard
- Agent Observability
- Agent Skill Supply Chain Security

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


## Planned AI Security Enhancements

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

## Future Enhancements

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