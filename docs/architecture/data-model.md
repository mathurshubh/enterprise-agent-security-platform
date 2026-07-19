# Data Model

## Introduction

This document describes the primary domain models used throughout the Enterprise Agent Security Platform.

These models collectively define the deterministic contracts exchanged throughout the Runtime Security Pipeline. They represent the authoritative security state of the platform, enabling internal services to communicate using structured domain contracts rather than provider-specific objects.

The models support:

- Agent Governance
- Tool Governance
- Runtime Execution
- Authorization
- Detection
- Risk Assessment
- Auditability

The platform follows a Zero Trust model. User prompts, provider outputs, Tool Invocations, tool outputs, and external content are treated as untrusted input. Security decisions are represented through deterministic domain models and evaluated by platform services rather than by the AI model.

---

## Domain Model Principles

The platform's data layer conforms to the following domain design principles:

*   **Security-Relevant Information Mapping:** Models focus purely on representing state relevant to security enforcement, auditing, and threat detection.
*   **Deterministic Evaluation State:** Domain data states are parsed and checked deterministically, ensuring decisions are reproducible and explainable.
*   **Independence from AI Model Reasoning:** Domain structures cannot be altered by model prompts or provider reasoning outputs.
*   **Provider-Agnostic Schema:** Data schemas are unified and independent of the selected LLM provider API models.
*   **Service Contracts:** Domain models act as the strict contracts exchanged across service boundaries in the Runtime Security Pipeline.

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

Tool governance is a core pillar of the platform architecture. Executable enterprise capabilities are defined by a governance contract, while capability, identity, and operational attributes are represented as tool metadata.

The Tool Registry acts as the authoritative control plane for all executable capabilities. Discovery and inventory interfaces expose metadata only, never releasing executable tool references.

### ToolIdentity

`ToolIdentity` uniquely identifies an executable enterprise tool. It provides the stable `tool_id` used by Tool Invocations, authorization, policy evaluation, the Tool Registry, and runtime tool resolution.

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

These fields help future authorization, detection, and inventory workflows reason about tool behavior without exposing the executable tool implementation.

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

These capability attributes are descriptive metadata and do not grant permission to execute a tool. Capability metadata describes what a tool is capable of doing, not what it is authorized to do.

### ToolGovernance

`ToolGovernance` captures deterministic security metadata used by authorization and policy evaluation. It defines the tool risk level, required permissions, ownership metadata, and whether manual approval is required.

Authorization checks the Enterprise Agent, approved tool list, tool metadata, and resource-aware policy rules deterministically.

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

```json
{
  "enabled": true,
  "timeout_seconds": 30,
  "supports_streaming": false
}
```

Operational metadata does not participate in authorization decisions. It affects runtime execution behavior but is intentionally excluded from security evaluations.

### ToolMetadata

`ToolMetadata` is the primary governance model for an executable enterprise tool. Rather than simply aggregating metadata fields, it serves as the:
*   **Governance Contract:** The immutable security profile registered for the capability.
*   **Inventory Representation:** The authoritative catalog record.
*   **Authorization Input:** The schema parsed by policy engines to evaluate risk and permissions.
*   **Discovery Representation:** The safe, non-executable definition returned to developers and agents.

ToolMetadata is treated as an immutable contract registered with the Tool Registry. The registry exposes deep-copied metadata for discovery and inventory, while executable tool instances remain hidden behind the secure zone boundary.

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

`ToolInvocation` is the canonical representation of an agent's requested capability. It represents the structured request produced by the Enterprise Agent after the configured LLM provider adapter interprets the user prompt.

Every runtime security decision operates directly on the ToolInvocation rather than raw prompts or unstructured model outputs. It is treated as untrusted until it successfully passes through all stages of the Runtime Security Pipeline.

```json
{
  "tool_id": "file_read",
  "parameters": {
    "path": "notes.txt"
  }
}
```

### RuntimeResult

`RuntimeResult` represents the internal runtime evaluation object. It captures the detailed, security-specific output of the Runtime Security Pipeline—including raw detection findings, consolidated risk assessments, and response recommendation metadata—prior to executing the tool or returning results to the caller.

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

### AgentRuntimeResult

`AgentRuntimeResult` is the filtered external caller response returned after the security evaluations and (if allowed) secure tool executions are complete.

It preserves the trust boundary by exposing only the high-level decision, the response type, and the execution output payload, hiding internal findings, risk scores, and registry identifiers from untrusted clients.

```json
{
  "decision": "ALLOW",
  "response_type": "MONITOR",
  "output": "Project notes..."
}
```

---

## Security Models

The security models collectively represent the deterministic security state evaluated and mutated by the Runtime Security Pipeline.

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

`RiskAssessment` represents the assessed risk level generated from detection findings. The implementation aggregates findings by severity weight to compute a risk score, mapping it to a risk level.

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

`AuditEvent` records final, authoritative tool execution decisions. Every request processed by the pipeline produces a compliance-ready record mapping the agent, session, tool target, decision, and timestamp for SIEM ingestion.

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

`DetectionFinding` represents threat indicators flagged during execution. A finding maps a specific rule name, its severity, and description to a session context.

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
- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

### Authorization Decisions
- `ALLOW`
- `DENY`
- `APPROVAL_REQUIRED`

### Agent States
- `REGISTERED`
- `ACTIVE`
- `SUSPENDED`
- `DISABLED`

### Response Types
- `MONITOR`
- `ALERT`
- `REQUIRE_APPROVAL`
- `SUSPEND_AGENT`

### Detection Severities
- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

### JWT Roles
- `ADMIN`
- `ANALYST`
- `AGENT`

---

## Data Model Relationships

The conceptual data relationships flow as follows:

```text
EnterpriseAgent
       │
       ▼
Tool Invocation
       │
       ▼
Runtime Security Pipeline
       │
       ▼
RuntimeResult
       │
       ▼
Tool Registry
       │
       ▼
Secure Tool Execution
       │
       ▼
AgentRuntimeResult
       │
       ▼
AuditEvent
```

The Enterprise Agent interprets natural language queries and produces a Tool Invocation. The Runtime Security Pipeline parses the invocation, runs policy checks and threat rules, and outputs a RuntimeResult. 

If approved, the pipeline queries the Tool Registry to resolve ToolMetadata and initiate Secure Tool Execution. The outcomes are returned as an AgentRuntimeResult and permanently logged as an AuditEvent.

---

## Future Models

Future AI asset governance models will extend the current metadata-driven architecture to cover additional enterprise entities without changing the deterministic runtime security model.

### ModelMetadata

`ModelMetadata` is planned to describe AI model identity, provenance, provider, version, owner, risk tier, approval status, and governance attributes.

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

`ModelRegistry` is planned as a governed registry for approved models and providers, complementary to the Tool Registry.

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
- `APPROVED`
- `PENDING`
- `DEPRECATED`