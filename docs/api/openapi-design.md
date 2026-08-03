# OpenAPI Design Contract

## Overview
This document defines the API design contract for the Enterprise Agent Security Platform. The design targets the **OpenAPI Specification 3.1**.

### Implemented API Roots

- Runtime API: `/agents/{agent_id}/execute`
- Scenario API: `/api/scenarios`
- Management API: `/api/v1`

---

## Architectural Intent
The platform exposes a deterministic Runtime API for tool invocation evaluation, a Scenario API for security benchmark execution, and a read-only Enterprise Management API for platform observability. Clients do not execute enterprise tools directly; execution is allowed only after the Runtime Security Pipeline returns an `ALLOW` decision.

---

## API Design Principles
The platform's APIs conform to the following engineering design principles:
*   **RESTful Resource-Oriented APIs:** Operations are modeled as stateless requests targeting identified resource collections.
*   **Stateless Execution:** Request processing does not depend on local server session state. All session attributes are passed in headers or payloads.
*   **Deterministic Runtime Evaluation:** Runtime execution requests are evaluated by `RuntimeService`, not by LLM prompts or client-side logic.
*   **Deterministic Security Policies:** All authorization and threat mitigation rules are evaluated deterministically prior to executing actions.
*   **Provider-Agnostic Design:** APIs remain decoupled from specific AI vendor data formats, using standardized tool request schemas.
*   **Consistent JSON Schemas:** Implemented endpoints return direct JSON domain DTOs.
*   **Auditability by Design:** Runtime execution records append-only audit events after the final security decision.

---

## API Security Model
API clients never execute enterprise tools directly. Runtime execution requests flow through this security pipeline:

```text
Client Request → RuntimeService → Authorization → Policy Evaluation → Detection → Risk Assessment → Response Override → Audit Event → Secure Tool Execution if ALLOW
```

---

## Request Lifecycle
The API request lifecycle transitions through the following architectural path:

```text
Client
  │
  ▼
[HTTP Request]
  │
  ▼
[Runtime Security Pipeline]
  │
  ▼
[Runtime Result]
  │
  ▼
[HTTP Response]
```

---

## Standard Request Headers
API calls should supply the following standard request headers:
*   `Content-Type` (String): Payload format representation (`application/json`).
*   `Accept` (String): Expected response payload format (`application/json`).

---

## Request Tracing & Correlation

### Architecture

Requests propagate a unique tracking context (such as a session or request identifier) to correlate actions throughout execution evaluation, session history, and auditing.

### Implementation Notes

The Runtime API accepts a `session_id` in the request body to correlate related interactions. Explicit correlation headers are not enforced at the FastAPI routing boundary.

---

## Idempotency Guidance
To prevent duplicate execution or parameter configuration states, clients should observe the following idempotency rules:
*   `GET` requests are safe and idempotent.
*   `POST /agents/{agent_id}/execute` is non-idempotent because it records session and audit events.
*   `POST /api/scenarios/{scenario_id}/execute` is non-idempotent because it executes a benchmark scenario and records runtime events.

---

## Authentication

### Authentication Architecture

The platform expects a JSON Web Token (JWT) supplied in the standard HTTP header:
```http
Authorization: Bearer <access_token>
```

### Implementation Notes

The backend includes `JwtService` to handle token creation and verification logic.

### Known Limitations

FastAPI routers do not enforce JWT verification at the HTTP boundary for this release.

### Token Structure & Claims

JWTs used by the platform contain the following standard claims:
*   `sub` (Subject): The unique identifier of the calling Enterprise Agent or Administrator.
*   `iss` (Issuer): The authoritative auth issuer of the enterprise platform.
*   `aud` (Audience): The platform API audience identifier.
*   `exp` (Expiration): Unix timestamp after which the token is invalid (tokens default to 1-hour lifetimes).
*   `role` (Role claim): The assigned RBAC capability (`ADMIN`, `ANALYST`, `AGENT`).

*Note: Token authentication, where used by callers, does not grant permission to execute a tool. Authorization is evaluated separately on every runtime tool invocation.*

---

## Authorization Model

### Architecture

Authorization decisions are deterministic and independent of the AI model's output. The pipeline evaluates tool execution access permissions by combining:
1.  **Agent Identity:** The authenticated identity of the agent requesting tool execution.
2.  **Approved Tool List:** Verification that the requested tool is explicitly allowed for the agent.
3.  **Tool Governance Metadata:** Rules associated with the tool, such as required permissions or risk thresholds.
4.  **Resource-Aware Policies:** Parameter validation constraints (e.g., path restrictions) defined outside the agent runtime.
5.  **Session Context:** Behavioral analysis inputs, such as session history and consecutive execution failure counts.

### Implementation Notes

Tool metadata is resolved via `ToolRegistry` and permissions checked by `AuthorizationService`. Resource constraints are validated against `PolicyEngine`, and session behavioral checks (like `EXCESSIVE_DENIALS`) query active session events recorded in `SessionService`.

---

## Response Shape

### Architecture

API endpoints return direct JSON payload representations of the requested resources or execution outcomes.

### Representative Example (Tool Registry Response)

```json
[
  {
    "tool_id": "file_read",
    "name": "File Read",
    "description": "Read files from the workspace",
    "version": "1.0.0"
  }
]
```

---

## Approval Workflow Model

### Architecture

For high-risk tool invocations, the security pipeline evaluates the request against a three-way decision model:
*   **ALLOW:** The invocation meets all policy requirements and proceeds to secure execution.
*   **DENY:** The invocation violates access policies or triggers security rules (resulting in a blocked action).
*   **APPROVAL_REQUIRED:** The invocation triggers a requirement for administrative review, moving the transaction to a pending hold state.

### Known Limitations

A persistent approval queue or interactive release action is not implemented in this release. An `APPROVAL_REQUIRED` result acts as a terminal hold state, blocking execution and returning a response indicating that manual approval is required.

---

## Implemented Runtime API

### Execute Agent Request

Evaluates a requested tool through the Runtime Security Pipeline.

*   **Endpoint:** `POST /agents/{agent_id}/execute`
*   **Idempotency:** Non-idempotent
*   **Request Payload:**
    ```json
    {
      "session_id": "session-123",
      "tool_id": "file_read",
      "user_prompt": "read notes.txt",
      "model_output": "",
      "tool_output": ""
    }
    ```
*   **Response Payload:**
    ```json
    {
      "session_id": "session-123",
      "agent_id": "agent-1",
      "tool_id": "file_read",
      "decision": "ALLOW",
      "findings": [],
      "risk_score": 0,
      "risk_level": "LOW",
      "response_type": "MONITOR",
      "response_reason": "Low risk execution"
    }
    ```

---

## Implemented Management API
The Enterprise Management API is a read-only endpoint suite providing operational visibility into platform configuration.

### Implementation Notes

Endpoints retrieve state from shared service instances injected via FastAPI dependencies.

### List Agents

Retrieves all registered agents.

*   **Endpoint:** `GET /api/v1/agents`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    [
      {
        "agent_id": "soc-agent",
        "name": "SOC Agent",
        "owner": "Security Operations",
        "risk_tier": "HIGH",
        "approved_tools": [
          "file_read",
          "directory_list"
        ],
        "status": "ACTIVE"
      }
    ]
    ```

---

### List Tools

Lists metadata for all tools registered in the shared Tool Registry.

*   **Endpoint:** `GET /api/v1/tools`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    [
      {
        "tool_id": "file_read",
        "name": "File Read",
        "description": "Read files from the workspace",
        "version": "1.0.0"
      }
    ]
    ```

### List Detection Rules

Lists active Content Detection Rules from the shared `DetectionRegistry`.

*   **Endpoint:** `GET /api/v1/detection/rules`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    [
      {
        "name": "PROMPT_INJECTION",
        "category": "PROMPT_SECURITY",
        "description": "Detects prompt injection attempts",
        "controls": []
      }
    ]
    ```

### List Audit Events

Retrieves append-only audit records of final runtime decisions.

*   **Endpoint:** `GET /api/v1/audit/events`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    [
      {
        "event_id": "evt-123",
        "agent_id": "agent-1",
        "tool_id": "file_read",
        "decision": "ALLOW",
        "timestamp": "2026-01-01T00:00:00Z"
      }
    ]
    ```

### List Sessions

Retrieves active session records.

*   **Endpoint:** `GET /api/v1/sessions`
*   **Idempotency:** Idempotent

### Platform Info

Returns lightweight platform metadata and resource counts.

*   **Endpoint:** `GET /api/v1/info`
*   **Idempotency:** Idempotent

---

## Implemented Scenario API

The Scenario API exposes the loaded attack scenario registry and executes scenarios through `ScenarioRunnerService`.

### List Scenarios

*   **Endpoint:** `GET /api/scenarios`
*   **Query Parameters:** `category`, `severity`, `tag`, `enabled`
*   **Idempotency:** Idempotent

### Get Scenario

*   **Endpoint:** `GET /api/scenarios/{scenario_id}`
*   **Idempotency:** Idempotent

### Execute Scenario

*   **Endpoint:** `POST /api/scenarios/{scenario_id}/execute`
*   **Idempotency:** Non-idempotent
*   **Response Payload:**
    ```json
    {
      "execution_id": "exec-123",
      "scenario_id": "BEN-001",
      "session_id": "scenario-run-BEN-001",
      "execution_mode": "TOOL_SEQUENCE",
      "status": "COMPLETED",
      "passed": true,
      "observed_decision": "ALLOW",
      "observed_response": "MONITOR",
      "observed_risk_level": "LOW",
      "observed_findings": [],
      "mismatches": [],
      "error_message": null,
      "started_at": "2026-01-01T00:00:00Z",
      "finished_at": "2026-01-01T00:00:01Z"
    }
    ```

---

## Error Handling Model
FastAPI returns standard validation and HTTP exception payloads. Scenario lookup failures return `404` with a detail message:

```json
{
  "detail": "Scenario 'UNKNOWN' not found"
}
```

### Standard Error Codes

*   `VALIDATION_FAILED` (422): FastAPI request validation failed.
*   `SCENARIO_NOT_FOUND` (404): The requested scenario ID is not registered.
*   `INTERNAL_SERVER_ERROR` (500): Unexpected platform failure.

---

## Versioning Strategy
*   **URI-Based Versioning:** The platform uses explicit URI version prefixes (`/api/v1`).
*   **Backward Compatibility:** Field deletions, schema type modifications, and path updates will trigger a new version prefix increment (e.g. `/api/v2`). Field additions and optional parameters are considered backward compatible.
*   **Deprecation Policy:** Deprecated endpoints will return a standard HTTP header `Deprecation: true` for at least one minor release cycle prior to removal.

---

## Collection Endpoint Limits

### Architecture

Endpoints retrieving lists of resources are bounded to prevent denial-of-service and optimize resource usage, supporting standard pagination conventions.

### Implementation Notes

The list endpoints in this release return complete in-memory collections. Pagination parameters (such as `limit` and `offset`) are not enforced by the backend services.
