# OpenAPI Design

## Overview

This document defines the initial API contract for the Enterprise Agent Security Platform.

Version:

```text
v1
```

Base Path:

```text
/api/v1
```

Primary Objectives:

- Agent registration
- Authentication
- Tool execution
- Audit visibility

Future versions will introduce:

- Risk scoring
- Policy management
- Approval workflows
- Detection findings
- Security dashboards

---

# Authentication

Authentication uses JWT Bearer Tokens.

Authorization header:

```http
Authorization: Bearer <token>
```

---

# Agent Registry

## Register Agent

### Endpoint

```http
POST /api/v1/agents
```

### Request

```json
{
  "name": "SOC Agent",
  "owner": "Security Operations",
  "risk_tier": "HIGH",
  "approved_tools": [
    "file_read",
    "web_fetch"
  ]
}
```

### Response

```json
{
  "agent_id": "soc-agent",
  "status": "REGISTERED"
}
```

### Status Codes

| Code | Meaning |
|--------|--------|
| 201 | Agent Created |
| 400 | Invalid Request |
| 409 | Agent Exists |

---

## List Agents

### Endpoint

```http
GET /api/v1/agents
```

### Response

```json
[
  {
    "agent_id": "soc-agent",
    "owner": "Security Operations",
    "status": "ACTIVE"
  }
]
```

---

## Get Agent

### Endpoint

```http
GET /api/v1/agents/{agent_id}
```

### Response

```json
{
  "agent_id": "soc-agent",
  "name": "SOC Agent",
  "owner": "Security Operations",
  "risk_tier": "HIGH",
  "approved_tools": [
    "file_read",
    "web_fetch"
  ],
  "status": "ACTIVE"
}
```

---

# Authentication API

## Generate Token

### Endpoint

```http
POST /api/v1/auth/token
```

### Request

```json
{
  "agent_id": "soc-agent"
}
```

### Response

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

### JWT Claims

```json
{
  "sub": "soc-agent",
  "agent_id": "soc-agent",
  "role": "analyst"
}
```

---

# Tool Registry

## List Tools

### Endpoint

```http
GET /api/v1/tools
```

### Response

```json
[
  {
    "tool_id": "file_read",
    "risk_level": "MEDIUM"
  },
  {
    "tool_id": "web_fetch",
    "risk_level": "HIGH"
  }
]
```

---

## Execute Tool

### Endpoint

```http
POST /api/v1/tools/execute
```

### Request

```json
{
  "tool": "file_read",
  "arguments": {
    "path": "/docs/security_policy.md"
  }
}
```

### Response

```json
{
  "request_id": "uuid",
  "decision": "ALLOW",
  "result": {
    "content": "sample content"
  }
}
```

### Decision Values

```text
ALLOW
DENY
APPROVAL_REQUIRED
```

### Status Codes

| Code | Meaning |
|--------|--------|
| 200 | Success |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Tool Not Found |

---

# Audit Events

## List Events

### Endpoint

```http
GET /api/v1/events
```

### Response

```json
[
  {
    "event_id": "uuid",
    "agent_id": "soc-agent",
    "tool": "file_read",
    "decision": "ALLOW",
    "timestamp": "2026-01-01T00:00:00Z"
  }
]
```

---

## Get Event

### Endpoint

```http
GET /api/v1/events/{event_id}
```

### Response

```json
{
  "event_id": "uuid",
  "agent_id": "soc-agent",
  "tool": "file_read",
  "decision": "ALLOW",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

---

# Future APIs

The following APIs are intentionally deferred.

## Risk Engine

```http
GET /api/v1/risk
```

---

## Policy Engine

```http
GET /api/v1/policies
POST /api/v1/policies
```

---

## Approval Workflow

```http
GET /api/v1/approvals

POST /api/v1/approvals/{id}/approve

POST /api/v1/approvals/{id}/reject
```

---

## Detection Findings

```http
GET /api/v1/findings
```

---

## Dashboard APIs

```http
GET /api/v1/dashboard/summary
```

---

# Sprint 1 Scope

The following APIs must be implemented first:

```text
POST /api/v1/agents

GET /api/v1/agents

GET /api/v1/agents/{id}

POST /api/v1/auth/token

GET /api/v1/tools

POST /api/v1/tools/execute

GET /api/v1/events

GET /api/v1/events/{id}
```

All additional APIs are future enhancements.