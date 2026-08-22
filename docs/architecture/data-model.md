# Data Model

## Introduction

This document describes the primary domain models used throughout the Enterprise Agent Security Platform.

These models collectively define the deterministic contracts exchanged throughout the Runtime Security Pipeline. They represent the authoritative security state of the platform, enabling internal services to communicate using structured domain contracts rather than provider-specific objects.

The models support:

- Agent Governance
- Tool Governance
- Runtime Execution
- Authorization
- Threat Detection
- Authoritative Findings Persistence
- Dynamic Risk Assessment
- Auditability

The platform follows a Zero Trust model. User prompts, provider outputs, Tool Invocations, tool outputs, and external content are treated as untrusted input. Security decisions are represented through deterministic domain models and evaluated by platform services rather than by the AI model.

---

## Domain Model Principles

The platform's data layer conforms to the following domain design principles:

*   **Security-Relevant Information Mapping:** Models focus purely on representing state relevant to security enforcement, auditing, and threat detection.
*   **Authoritative Evidence vs Derived Posture:** `Finding` objects represent authoritative security evidence. `RiskAssessment` objects represent derived process-local posture.
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
  "approved_tools": [
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

### ToolGovernance

`ToolGovernance` captures deterministic security metadata used by authorization and policy evaluation. It defines the tool risk level, required permissions, ownership metadata, and whether manual approval is required.

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

### ToolMetadata

`ToolMetadata` is the primary governance model for an executable enterprise tool. Rather than simply aggregating metadata fields, it serves as the:
*   **Governance Contract:** The immutable security profile registered for the capability.
*   **Inventory Representation:** The authoritative catalog record.
*   **Authorization Input:** The schema parsed by policy engines to evaluate risk and permissions.
*   **Discovery Representation:** The safe, non-executable definition returned to developers and agents.

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

`AgentRuntimeResult` is the filtered external caller response returned after security evaluations and secure tool executions are complete. It preserves the trust boundary by exposing only the high-level decision, response type, and output payload.

```json
{
  "decision": "ALLOW",
  "response_type": "MONITOR",
  "output": "Project notes..."
}
```

---

## Security & Behavioral Intelligence Models

### Finding (Authoritative Evidence)

`Finding` represents a security threat indicator flagged by the Threat Detection Engine. Findings are recorded in `FindingsService`, which serves as the authoritative, thread-safe security evidence repository.

```json
{
  "finding_id": "find-101",
  "session_id": "session-123",
  "agent_id": "agent-1",
  "rule_name": "PROMPT_INJECTION",
  "category": "PROMPT",
  "severity": "HIGH",
  "description": "System prompt override attempt detected",
  "rule_id": "rule-pi-01",
  "status": "OPEN",
  "mitre_techniques": ["AML.T0043"],
  "created_at": "2026-08-21T18:00:00Z"
}
```

### RiskAssessment (Derived Posture)

`RiskAssessment` represents derived process-local security posture. It is calculated by `RiskService` summing fixed severity weights (`LOW=10`, `MEDIUM=25`, `HIGH=50`, `CRITICAL=100`) over all accumulated authoritative findings for a specific `(session_id, agent_id)` scope.

`RiskAssessment` is indexed internally by composite tuple key `(session_id, agent_id)` to isolate risk posture across agents.

```json
{
  "session_id": "session-123",
  "agent_id": "agent-1",
  "risk_score": 50,
  "risk_level": "HIGH",
  "finding_count": 1,
  "assessed_at": "2026-08-21T18:00:05Z"
}
```

### AuditEvent

`AuditEvent` records final, authoritative tool execution decisions for compliance and SIEM ingestion.

```json
{
  "event_id": "audit-123",
  "agent_id": "agent-1",
  "tool_id": "file_read",
  "decision": "ALLOW",
  "timestamp": "2026-07-04T00:00:00Z"
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

### Finding Categories
- `PROMPT`
- `DATA`
- `TOOL`
- `IDENTITY`
- `BEHAVIORAL`
- `POLICY`

### Finding Statuses
- `OPEN`
- `IN_PROGRESS`
- `RESOLVED`
- `DISMISSED`
