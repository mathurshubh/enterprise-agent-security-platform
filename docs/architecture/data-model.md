# Data Model

## Introduction

This document describes the primary domain models used throughout the Enterprise Agent Security Platform.

The models support:

- Agent Governance
- Tool Governance
- Runtime Execution
- Authorization
- Detection
- Risk Assessment
- Auditability

The platform follows a Zero Trust model. User prompts, provider output, `ToolInvocation` objects, tool outputs, and external content are treated as untrusted input. Security decisions are represented through deterministic domain models and evaluated by platform services rather than by the LLM.

---

## Identity Models

### Agent

The `Agent` model represents an approved Enterprise Agent operating under platform governance. It identifies the agent, records ownership, assigns a risk tier, defines the tools the agent is allowed to request, and tracks the current lifecycle status.

The agent model is used by authorization and policy evaluation to determine whether a requested tool action is allowed.

```json
{
  "agent_id": "agent-1",
  "name": "Local Agent",
  "owner": "security-team",
  "risk_tier": "HIGH",
  "allowed_tool_ids": [
    "file_read",
    "directory_list"
  ],
  "status": "ACTIVE"
}
```

---

## Tool Governance Models

Tool governance is the core of the current v0.9 architecture. Executable tools implement the `BaseTool` abstraction, while governance, capability, identity, and operational attributes are represented as `Tool Metadata`.

The `Tool Registry` owns executable `BaseTool` instances. Discovery and inventory surfaces expose metadata only, not executable tool objects.

### ToolIdentity

`ToolIdentity` uniquely identifies an executable enterprise tool. It provides the stable `tool_id` used by `ToolInvocation`, authorization, policy evaluation, the `Tool Registry`, and runtime tool resolution.

```json
{
  "tool_id": "file_read",
  "name": "File Read",
  "version": "1.0.0",
  "description": "Read files from the workspace"
}
```

### ToolCapability

`ToolCapability` describes what a tool is capable of doing from a security perspective. The current implementation models capability through a category and explicit access flags rather than free-form supported operation lists.

These fields help future authorization, detection, and inventory workflows reason about tool behavior without exposing the executable `BaseTool`.

```json
{
  "category": "filesystem",
  "reads_files": true,
  "writes_files": false,
  "network_access": false,
  "internet_access": false,
  "database_access": false,
  "shell_access": false
}
```

These capability attributes are descriptive metadata and do not grant permission to execute a tool.

Capability metadata describes what a tool is capable of doing, not what it is authorized to do.

### ToolGovernance

`ToolGovernance` captures deterministic security metadata used by authorization and policy evaluation. It defines the tool risk level, required permissions, ownership metadata, and whether manual approval is required.

In the current implementation, authorization checks the Enterprise Agent, approved tool list, tool metadata, and resource-aware policy rules deterministically. Environment allow lists are not yet implemented.

```json
{
  "risk_level": "LOW",
  "required_permissions": [
    "files:read"
  ],
  "owner": "security-team",
  "approval_required": false
}
```

### ToolOperational

`ToolOperational` contains operational metadata for a registered tool. It describes whether the tool is enabled, how long execution may run, and whether the tool supports streaming behavior.

Retry policy metadata is not currently implemented.

```json
{
  "enabled": true,
  "timeout_seconds": 30,
  "supports_streaming": false
}
```

Operational metadata does not participate in authorization decisions.

Operational metadata affects runtime behavior but is intentionally excluded from authorization decisions.

### ToolMetadata

`ToolMetadata` is the aggregate governance model for an executable enterprise tool. It combines identity, governance, capability, and operational metadata into one object that can be registered with the platform.

Executable `BaseTool` implementations expose `ToolMetadata` through their metadata property. `ToolMetadata` is treated as an immutable governance contract registered with the `Tool Registry`. The `Tool Registry` registers executable tools and exposes deep-copied metadata for discovery and inventory. Runtime components performing discovery or inventory should rely on `ToolMetadata`. Executable `BaseTool` instances remain internal to the runtime and are never exposed through discovery or inventory APIs.

```json
{
  "identity": {
    "tool_id": "file_read",
    "name": "File Read",
    "version": "1.0.0",
    "description": "Read files from the workspace"
  },
  "capability": {
    "category": "filesystem",
    "reads_files": true,
    "writes_files": false,
    "network_access": false,
    "internet_access": false,
    "database_access": false,
    "shell_access": false
  },
  "governance": {
    "risk_level": "LOW",
    "required_permissions": [
      "files:read"
    ],
    "owner": "security-team",
    "approval_required": false
  },
  "operational": {
    "enabled": true,
    "timeout_seconds": 30,
    "supports_streaming": false
  }
}
```

---

## Runtime Models

### ToolInvocation

`ToolInvocation` represents structured output produced by the Enterprise Agent after the configured provider interprets a user request.

The `ToolInvocation` is treated as untrusted until it passes deterministic validation, authorization, policy evaluation, detection, risk assessment, and response selection. The LLM may propose a tool call, but it does not decide whether the call is allowed or execute the tool.

```json
{
  "tool_id": "file_read",
  "parameters": {
    "path": "notes.txt"
  }
}
```

### RuntimeResult

`RuntimeResult` represents the outcome of deterministic runtime evaluation, including detection findings, risk assessment, response selection, and execution context before results are returned to the caller.

```json
{
  "event": {
    "session_id": "session-123",
    "agent_id": "agent-1",
    "tool_id": "file_read",
    "decision": "ALLOW",
    "timestamp": "2026-07-04T00:00:00Z"
  },
  "findings": [],
  "risk_assessment": {
    "session_id": "session-123",
    "agent_id": "agent-1",
    "risk_score": 0,
    "risk_level": "LOW",
    "finding_count": 0,
    "assessed_at": "2026-07-04T00:00:00Z"
  },
  "response_action": {
    "session_id": "session-123",
    "agent_id": "agent-1",
    "risk_level": "LOW",
    "response_type": "MONITOR",
    "reason": "Low risk execution",
    "created_at": "2026-07-04T00:00:00Z"
  }
}
```

RuntimeResult captures the outcome of deterministic runtime evaluation before secure tool execution results are returned to the caller.

### AgentRuntimeResult

`AgentRuntimeResult` is the high-level result returned to the caller after the runtime security pipeline and, when allowed, secure tool execution have completed.

It intentionally exposes a concise decision, response type, and output rather than internal executable tool objects.

```json
{
  "decision": "ALLOW",
  "response_type": "MONITOR",
  "output": "Project notes..."
}
```

---

## Security Models

### Policy

Policies are evaluated deterministically at runtime rather than stored as configurable policy objects. The policy layer evaluates agent status, agent risk tier, tool risk level, protected resources, and approval requirements.

Current policy behavior includes:

- Deny suspended or disabled agents.
- Deny low-risk-tier agents from using high-risk or critical tools.
- Deny protected resource access such as `secrets.txt`.
- Require approval for critical-risk tools.

Illustrative policy representation:

```json
{
  "policy_id": "resource-protection",
  "effect": "DENY",
  "resource": "secrets.txt",
  "reason": "Protected resource access is not allowed"
}
```

### RiskAssessment

`RiskAssessment` represents the deterministic risk assessment generated from detection findings. The implementation scores findings by severity and maps the resulting score to a risk level.

```json
{
  "session_id": "session-123",
  "agent_id": "agent-1",
  "risk_score": 25,
  "risk_level": "MEDIUM",
  "finding_count": 1,
  "assessed_at": "2026-07-04T00:00:00Z"
}
```

### AuditEvent

`AuditEvent` records governed tool execution decisions. Every governed execution produces audit-relevant events so the platform can answer which agent requested which tool, what decision was made, and when it occurred.

```json
{
  "event_id": "audit-123",
  "session_id": "session-123",
  "agent_id": "agent-1",
  "tool_id": "file_read",
  "decision": "ALLOW",
  "timestamp": "2026-07-04T00:00:00Z"
}
```

### DetectionFinding

Detection findings are represented by the implemented `Finding` model. A finding records a detection rule result associated with a session and agent.

The current detection service produces findings for excessive denials. Additional detection rules are planned as the runtime monitoring layer expands.

```json
{
  "finding_id": "finding-123",
  "session_id": "session-123",
  "agent_id": "agent-1",
  "rule_name": "EXCESSIVE_DENIALS",
  "severity": "MEDIUM",
  "description": "Session contains 3 denied actions",
  "created_at": "2026-07-04T00:00:00Z"
}
```

### ApprovalRecord

`ApprovalRecord` is a planned capability and is not implemented in the current release.

The current platform can return `APPROVAL_REQUIRED` and map high-risk outcomes to response actions, but a complete approval workflow, approval persistence model, approver assignment, expiry, and approval decision lifecycle remain future work.

Planned model shape:

```json
{
  "approval_id": "approval-123",
  "session_id": "session-123",
  "agent_id": "agent-1",
  "tool_id": "critical_tool",
  "status": "PENDING",
  "approver": null,
  "created_at": "2026-07-04T00:00:00Z",
  "expires_at": "2026-07-04T01:00:00Z"
}
```

---

## Enumerations

### Risk Levels

Risk levels are used by `RiskAssessment`, response selection, tool governance, model governance, and agent risk tiers.

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

### Authorization Decisions

Authorization decisions are represented by the `Decision` enum.

- `ALLOW`
- `DENY`
- `APPROVAL_REQUIRED`

### Agent States

Agent lifecycle state is represented by `AgentStatus`.

- `REGISTERED`
- `ACTIVE`
- `SUSPENDED`
- `DISABLED`

### Response Types

Response actions are selected deterministically from the assessed risk level.

- `MONITOR`
- `ALERT`
- `REQUIRE_APPROVAL`
- `SUSPEND_AGENT`

### Detection Severities

Detection findings use severity values aligned with risk levels.

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

### JWT Roles

JWT claims support role-based identity for API security.

- `ADMIN`
- `ANALYST`
- `AGENT`

---

## Data Model Relationships

The current runtime flow connects the primary models as follows:

```text
EnterpriseAgent
        │
        ▼
ToolInvocation
        │
        ▼
Tool Registry
        │
        ▼
Resolve ToolMetadata
        │
        ▼
Resolve BaseTool
        │
        ▼
RuntimeResult
        │
        ▼
AuditEvent
```

The Enterprise Agent delegates natural language interpretation to the configured provider, which returns a structured `ToolInvocation`. The runtime treats that invocation as untrusted and evaluates it through deterministic authorization, policy evaluation, detection, risk assessment, and response selection.

The requested `tool_id` is matched against governed `Tool Metadata` and resolved through the `Tool Registry`. Only after the security pipeline allows execution does the runtime retrieve the executable `BaseTool` and perform secure tool execution. The resulting decision and execution context are captured through runtime results and audit events.

---

## Future Models

Future AI asset governance will intentionally mirror the architecture established by the Tool Registry, extending deterministic governance to foundation models while preserving the platform's Zero Trust design principles.

The following models are planned capabilities and are not implemented in the current runtime architecture.

### ModelMetadata

`ModelMetadata` is planned to describe AI model identity, provenance, provider, version, owner, risk tier, approval status, and governance attributes.

This will extend the current provider-agnostic architecture into deterministic enterprise model governance.

Planned model shape:

```json
{
  "model_id": "llama3.2-3b",
  "provider": "ollama",
  "version": "3b",
  "owner": "security-team",
  "status": "APPROVED",
  "risk_tier": "MEDIUM",
  "provenance": {
    "source": "internal-approved-provider",
    "approved_at": "2026-07-04T00:00:00Z"
  }
}
```

### ModelRegistry

`ModelRegistry` is planned as a governed registry for approved models and providers. It will complement the `Tool Registry` by tracking model provenance, approval state, lifecycle status, and enterprise ownership.

Planned model shape:

```json
{
  "registry_id": "enterprise-model-registry",
  "approved_models": [
    "llama3.2-3b",
    "gemini-enterprise"
  ],
  "default_provider": "ollama",
  "last_reviewed_at": "2026-07-04T00:00:00Z"
}
```

### AIAssetInventory

`AIAssetInventory` is planned as a broader inventory of AI assets, including agents, tools, models, prompts, datasets, and related governance metadata.

This future capability should extend the current Tool Governance architecture without pivoting the platform away from its primary focus on Agent Runtime Security, deterministic authorization, risk assessment, detection, response, and auditability.

Planned model shape:

```json
{
  "inventory_id": "ai-assets-prod",
  "agents": [
    "agent-1"
  ],
  "tools": [
    "file_read",
    "directory_list"
  ],
  "models": [
    "llama3.2-3b"
  ],
  "last_updated_at": "2026-07-04T00:00:00Z"
}
```

### Planned Model Status Values

The repository includes a basic model governance model. This is secondary to runtime security and is not yet a full model registry.

- `APPROVED`
- `PENDING`
- `DEPRECATED`