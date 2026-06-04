# Data Model

## Agent

Represents an approved enterprise agent.

```json
{
  "agent_id": "soc-agent",
  "name": "SOC Agent",
  "owner": "Security Operations",
  "environment": "production",
  "risk_tier": "HIGH",
  "approved_tools": [
    "jira_read",
    "threat_intel"
  ],
  "status": "ACTIVE"
}
```

---

## Tool

Represents a controlled enterprise tool.

```json
{
  "tool_id": "file_read",
  "risk_level": "MEDIUM",
  "required_permissions": [
    "file.read"
  ],
  "approval_required": false
}
```

---

## Policy

Represents a security control.

```json
{
  "policy_id": "POL-001",
  "name": "No Bulk Export",
  "effect": "DENY",
  "condition": "bulk_export == true"
}
```

---

## Tool Execution Request

```json
{
  "request_id": "uuid",
  "agent_id": "soc-agent",
  "tool": "file_read",
  "arguments": {},
  "timestamp": "2026-01-01T00:00:00Z"
}
```

---

## Risk Evaluation

```json
{
  "request_id": "uuid",
  "risk_score": 82,
  "risk_level": "HIGH",
  "reasons": [
    "Sensitive data access",
    "External destination"
  ]
}
```

---

## Approval Record

```json
{
  "approval_id": "uuid",
  "request_id": "uuid",
  "status": "PENDING",
  "approver": null,
  "created_at": "2026-01-01T00:00:00Z"
}
```

### Approval States

- PENDING
- APPROVED
- REJECTED
- EXPIRED

---

## Audit Event

```json
{
  "event_id": "uuid",
  "agent_id": "soc-agent",
  "tool": "file_read",
  "decision": "ALLOW",
  "risk_score": 42,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

---

## Detection Finding

```json
{
  "finding_id": "uuid",
  "rule_name": "excessive_tool_usage",
  "severity": "HIGH",
  "agent_id": "soc-agent",
  "description": "Agent exceeded tool threshold",
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

# Risk Levels

| Level | Score Range |
|---------|---------|
| LOW | 0-30 |
| MEDIUM | 31-60 |
| HIGH | 61-80 |
| CRITICAL | 81-100 |

---

# Agent States

- REGISTERED
- ACTIVE
- SUSPENDED
- DISABLED

---

# Authorization Decisions

- ALLOW
- DENY
- APPROVAL_REQUIRED