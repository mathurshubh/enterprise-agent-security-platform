# ADR-008: Enterprise Management API

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Enterprise Agent Security Platform
- **Supersedes:** None
- **Superseded by:** None

---

# Context

The Enterprise Agent Security Platform currently exposes runtime capabilities used to evaluate and govern AI agent execution through deterministic security controls.

As the platform evolves toward an Enterprise Security Console, additional consumers will require access to platform information including:

- Registered agents
- Registered tools
- Detection rules
- Runtime findings
- Audit events
- Risk assessments
- Security coverage
- Attack scenarios

These consumers do not require the ability to execute AI agents or invoke tools.

Without architectural separation, management clients could become coupled to the runtime execution pipeline or accidentally bypass deterministic security controls.

The platform therefore requires a dedicated management interface that exposes platform state while remaining completely outside the runtime security boundary.

## Scope

This ADR defines the observability interface of the Enterprise Management API.

It is intentionally limited to read-oriented platform visibility, including dashboards, audit history, findings, detection rules, and registry metadata.

Administrative write operations (such as agent lifecycle management, policy administration, or tool governance) are outside the scope of this ADR and will be addressed by future architectural decisions.

This separation preserves the deterministic runtime security boundary while allowing management clients to observe platform state without participating in runtime execution.

---

# Decision

The platform shall expose two independent API planes:

1. Runtime API
2. Enterprise Management API

These API planes serve different purposes and have different trust assumptions.

---

# Runtime API

The Runtime API exists solely for AI agent execution.

Responsibilities include:

- Accept execution requests
- Invoke RuntimeService
- Perform authorization
- Execute policy evaluation
- Execute detection rules
- Perform risk assessment
- Select response actions
- Record audit events
- Execute approved tools

The Runtime API represents the deterministic security boundary of the platform.

Example:

```text
POST /runtime/execute
```

Only RuntimeService may authorize tool execution.

---

# Enterprise Management API

The Enterprise Management API exists solely for platform observability and management visibility.

Administrative write operations are outside the scope of this ADR.

Responsibilities include:

- Expose registered agents
- Expose registered tools
- Expose detection rules
- Expose runtime findings
- Expose audit history
- Expose attack scenarios
- Expose dashboard metrics
- Expose platform metadata

The Management API never executes tools.

The Management API never invokes LLM providers.

The Management API never performs authorization decisions on behalf of runtime execution.

## Authentication

All Enterprise Management API endpoints require authenticated access.

The Management API will reuse the platform's JWT authentication mechanism while enforcing authorization scopes independent of Runtime API execution.

Authentication is enforced at the HTTP boundary before requests reach application services.

Management API authorization governs access to platform metadata and operational visibility only. It never authorizes runtime tool execution.

---

# Architectural Separation

```text
                     Enterprise Security Console
                                │
                                ▼
                    Enterprise Management API
                                │
        ┌──────────────┬──────────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
 Agent Service   Tool Registry  Detection Registry  Audit Service
        │              │              │              │
        ▼              ▼              ▼              ▼
    Read Only     Read Only      Read Only      Read Only

────────────────────────────────────────────────────────────────────

                     Runtime Execute API
                               │
                               ▼
                        RuntimeService
                               │
 Authorization → Detection → Risk → Response
                               │
                               ▼
                     Approved Tool Execution
                               │
                               ▼
                         Audit Service
```

---

# Service Composition

The Runtime API and Enterprise Management API share a common application service layer.

Services are composed during application startup and shared between both API planes through dependency injection.

This ensures a single authoritative application state while preserving logical separation between runtime execution and management observability.

The Management API must not instantiate independent in-memory service instances that could diverge from the Runtime API state.

This design ensures that both API planes observe a consistent platform state while preserving a clear separation between execution and observability.

---

# Trust Boundaries

## Boundary 1 – External Clients

External applications, dashboards, CLIs, automation systems, and web browsers are considered untrusted.

These clients interact only through authenticated APIs.

---

## Boundary 2 – Enterprise Management API

The Management API provides visibility into platform state.

It never performs runtime security decisions.

It never invokes tools.

It never bypasses RuntimeService.

---

## Boundary 3 – Runtime Security Boundary

RuntimeService remains the single authoritative security decision point.

Every execution request passes through:

- Authorization
- Policy evaluation
- Detection
- Risk assessment
- Response selection

before any tool execution occurs.

---

## Boundary 4 – Tool Execution

Tool execution is permitted only after RuntimeService authorizes execution.

No management endpoint may directly invoke registered tools.

---

# Security Principles

## Read-Only Management Plane

Management endpoints defined by this ADR expose platform state without participating in runtime execution.

Observability endpoints never invoke RuntimeService, execute tools, or bypass deterministic security controls.

Future administrative write operations may modify governance configuration (for example, agent registration or policy management), but they must never directly execute tools or bypass the runtime security pipeline.

---

## Single Runtime Authority

RuntimeService remains the only component capable of authorizing tool execution.

---

## Zero Trust User Interface

The Enterprise Security Console is treated as an untrusted client.

It visualizes security decisions but never participates in making them.

---

## Provider Independence

Management APIs expose platform abstractions rather than provider-specific implementations.

The UI should not depend on whether the underlying provider is Gemini, Ollama, OpenAI, Anthropic, or another supported model.

---

## UI Independence

The Enterprise Management API exposes stable platform domain objects rather than user interface representations.

The Enterprise Security Console is one consumer of the API alongside future CLI tooling, SDKs, automation systems, and SIEM integrations.

Presentation concerns remain outside the Management API to preserve long-term API stability.

---

## Stable Domain Model

The Enterprise Management API exposes stable platform domain objects rather than internal service implementations.

Consumers interact with concepts such as:

- Agent
- Tool
- Detection Rule
- Finding
- Audit Event
- Attack Scenario

This abstraction allows internal implementations to evolve without breaking external integrations.

---


# Initial Management Endpoints

The first version of the Enterprise Management API is expected to expose endpoints similar to:

```text
GET /api/v1/agents

GET /api/v1/tools

GET /api/v1/detection/rules

GET /api/v1/findings

GET /api/v1/audit/events

GET /api/v1/dashboard

GET /api/v1/scenarios
```

These endpoints are illustrative rather than normative.

The API specification will define the exact contracts.

---

# API Versioning

The Runtime API and Enterprise Management API are versioned independently.

Breaking changes to one API plane should not require version changes to the other.

This separation enables dashboards, SDKs, and enterprise integrations to evolve independently from runtime execution capabilities.

---

# Collection Endpoints

Management endpoints returning collections should support:

- Pagination
- Filtering
- Sorting

Collection endpoints should avoid returning unbounded result sets as the platform scales to larger enterprise deployments.

Current implementations inherit the limitations of the platform's in-memory storage model until persistent storage is introduced.

---

# Consequences

## Advantages

- Clear separation between execution and observability
- Smaller runtime trust boundary
- Supports Enterprise Security Console
- Supports CLI tooling
- Supports future SDKs
- Supports SIEM integrations
- Supports compliance reporting
- Simplifies API versioning

---

## Trade-offs

- Two independent API surfaces
- Additional authentication scopes
- Separate API documentation
- Separate testing strategy

These trade-offs are acceptable because they reinforce Zero Trust architecture and reduce coupling between runtime execution and management functionality.

---

# Deployment Assumptions

This ADR assumes the current single-node architecture using in-memory services.

Future distributed deployments will require shared persistence for services including:

- AgentService
- SessionService
- AuditService

A future persistence architecture decision will define the storage and synchronization model required for horizontally scaled deployments.

---

# Future Work

This ADR provides the architectural foundation for:

## User Interfaces

- ADR-009 – Enterprise Security Console
- Visibility Architecture
- Dashboard
- Detection Coverage View
- Audit Timeline
- Risk Dashboard

## Platform Integrations

- Management REST APIs
- Promptfoo Integration
- NVIDIA Garak Integration
- Microsoft PyRIT Integration
- SIEM Connectors
- Enterprise Reporting