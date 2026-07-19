# OpenAPI Design Contract

## Overview
This document defines the authoritative API contract for the Enterprise Agent Security Platform. The design targets the **OpenAPI Specification 3.1**.

**Base Path:** `/api/v1`

---

## Architectural Intent
The platform exposes governance APIs rather than direct tool execution APIs. Clients interact with Enterprise Agents through deterministic runtime evaluation, preserving the Runtime Security Pipeline as the primary trust boundary. Direct or unauthenticated tool execution is prohibited.

---

## API Design Principles
The platform's APIs conform to the following engineering design principles:
*   **RESTful Resource-Oriented APIs:** Operations are modeled as stateless requests targeting identified resource collections.
*   **Stateless Execution:** Request processing does not depend on local server session state. All session attributes are passed in headers or payloads.
*   **JWT Bearer Authentication:** Secure token validation encapsulates caller identity and role attributes.
*   **Deterministic Security Policies:** All authorization and threat mitigation rules are evaluated deterministically prior to executing actions.
*   **Provider-Agnostic Design:** APIs remain decoupled from specific AI vendor data formats, using standardized tool request schemas.
*   **Consistent JSON Schemas:** Error formats, payload envelopes, and resource records follow consistent schemas.
*   **Auditability by Design:** Every request creates request tracking headers and triggers append-only audit event logging.

---

## API Security Model
API clients never execute enterprise tools directly. The Runtime Security Pipeline acts as the single trust boundary intercepting all client calls. Every incoming request flows through this security pipeline:

```text
Client Request → Authentication (JWT) → Authorization (RBAC) → Policy Evaluation → Threat Detection Engine → Risk Assessment → Response Override → SIEM Audit Log → Secure Tool Execution
```

---

## Request Lifecycle
The API request lifecycle transitions through the following logical path:

```text
  Client
    │
    ▼
[HTTP Request]
    │
    ▼
[Authentication]            (Token checked; identity resolved)
    │
    ▼
[Runtime Security Pipeline] (Deterministic access and threat checks)
    │
    ▼
[Tool Invocation]           (The validated request target payload)
    │
    ▼
[Secure Tool Execution]     (Tool executes inside secure zone)
    │
    ▼
[AgentRuntimeResult]        (Filtered result envelope constructed)
    │
    ▼
[HTTP Response]
```

---

## Standard Request Headers
All API calls targeting secure endpoints should supply the following standard request headers:
*   `Authorization` (String): Bearer token header (`Bearer <access_token>`).
*   `Content-Type` (String): Payload format representation (`application/json`).
*   `Accept` (String): Expected response payload format (`application/json`).
*   `X-Request-ID` (String, UUID): Client-supplied or server-generated request correlation identifier.
*   `X-Correlation-ID` (String, UUID): Client-supplied session identifier tracing multi-step agent actions.

---

## Request Tracing & Correlation
Every API request requires or generates `X-Request-ID` and `X-Correlation-ID` headers to support observability and audit correlation. These correlation identifiers are logged across the entire Runtime Security Pipeline and captured in SIEM audit records.

---

## Idempotency Guidance
To prevent duplicate execution or parameter configuration states, clients should observe the following idempotency rules:
*   `GET` requests are safe and idempotent.
*   `POST /api/v1/agents` is non-idempotent (creates a new agent governance record).
*   `POST /api/v1/tools/execute` is non-idempotent (may mutate files, directories, or cloud resources depending on tool arguments).

---

## Authentication
Authentication is enforced via JWT Bearer Tokens in the authorization header:

```http
Authorization: Bearer <access_token>
```

### Token Structure & Claims
JWTs used by the platform contain the following standard claims:
*   `sub` (Subject): The unique identifier of the calling Enterprise Agent or Administrator.
*   `iss` (Issuer): The authoritative auth issuer of the enterprise platform.
*   `aud` (Audience): The platform API audience identifier.
*   `exp` (Expiration): Unix timestamp after which the token is invalid (tokens default to 1-hour lifetimes).
*   `role` (Role claim): The assigned RBAC capability (`ADMIN`, `ANALYST`, `AGENT`).

*Note: Successful token authentication establishes identity and role classification, but does not grant permission to execute a tool. Authorization is evaluated separately on every tool invocation.*

---

## Authorization Model
Authorization decisions are deterministic and independent of the AI model's output. The pipeline calculates tool execution access permissions by combining:
1.  **Agent Identity:** The authenticated agent requesting the capability.
2.  **RBAC Role:** Verifying the token role satisfies tool permission requirements.
3.  **Tool Registry Metadata:** Retrieving the tool's required roles and risk levels.
4.  **Resource-Aware Policies:** Parsing resource parameters (e.g., specific file targets) against deny lists or restrictions.
5.  **Runtime Context:** Evaluating current session event history (e.g., block thresholds).

---

## Standard Success Envelope
Successful API resource responses return a standard envelope wrapper that exposes request tracking metadata alongside payload data:

```json
{
  "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
  "timestamp": "2026-07-19T22:23:00Z",
  "data": {}
}
```

---

## Approval Workflow Model
For critical or high-risk Tool Invocations, the platform implements a conditional three-way evaluation lifecycle:
*   **ALLOW:** The Tool Invocation satisfies all access requirements. Passes directly to Secure Tool Execution.
*   **DENY:** The request violates policies or triggers critical risk flags. The pipeline terminates the execution and returns an HTTP 403 error payload.
*   **HOLD:** The request is suspended and placed into an approval queue (`APPROVAL_REQUIRED`). The approval workflow must be explicitly approved or rejected by an analyst. If approved, it is released to Secure Tool Execution; if rejected, it returns a DENY state error response.

---

## Agent Registry API

### Register Agent
Creates a new governed agent profile in the platform inventory.

*   **Endpoint:** `POST /api/v1/agents`
*   **Idempotency:** Non-idempotent
*   **Request Payload:**
    ```json
    {
      "name": "SOC Agent",
      "owner": "Security Operations",
      "risk_tier": "HIGH",
      "approved_tools": [
        "file_read",
        "directory_list"
      ]
    }
    ```
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": {
        "agent_id": "soc-agent",
        "status": "REGISTERED"
      }
    }
    ```
*   **Status Codes:**
    *   `201 Created` — Agent record successfully stored.
    *   `400 Bad Request` — Validation failure on parameters or tool list.
    *   `409 Conflict` — Agent ID already registered.

### List Agents
Retrieves all registered agents.

*   **Endpoint:** `GET /api/v1/agents`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": [
        {
          "agent_id": "soc-agent",
          "name": "SOC Agent",
          "owner": "Security Operations",
          "status": "ACTIVE"
        }
      ]
    }
    ```

### Get Agent Details
Retrieves details for a specific agent.

*   **Endpoint:** `GET /api/v1/agents/{agent_id}`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": {
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
    }
    ```

---

## Token Generation API

Generates a JWT access token for an agent profile.

*   **Endpoint:** `POST /api/v1/auth/token`
*   **Request Payload:**
    ```json
    {
      "agent_id": "soc-agent"
    }
    ```
*   **Response Payload:**
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer"
    }
    ```

---

## Tool Governance API

### List Tools
Lists all registered tools with their governance metadata.

*   **Endpoint:** `GET /api/v1/tools`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": [
        {
          "tool_id": "file_read",
          "risk_level": "LOW"
        },
        {
          "tool_id": "directory_list",
          "risk_level": "LOW"
        }
      ]
    }
    ```

### Execute Tool
Evaluates a Tool Invocation and executes the target capability if allowed by the Runtime Security Pipeline.

*   **Endpoint:** `POST /api/v1/tools/execute`
*   **Idempotency:** Non-idempotent
*   **Request Payload (Tool Invocation):**
    ```json
    {
      "tool_id": "file_read",
      "parameters": {
        "path": "notes.txt"
      }
    }
    ```
*   **Response Payload (AgentRuntimeResult):**
    Returns the filtered execution result to preserve the trust boundary. Internal evaluation structures (`RuntimeResult`) remain hidden inside the platform.
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "decision": "ALLOW",
      "response_type": "MONITOR",
      "output": "sample notes content..."
    }
    ```

---

## Audit Events API

### List Audit Events
Retrieves SIEM-ready log records of all runtime decisions.

*   **Endpoint:** `GET /api/v1/events`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": [
        {
          "event_id": "9a8b7c6d-1234-5678-90ab-cdef12345678",
          "session_id": "session-123",
          "agent_id": "soc-agent",
          "tool_id": "file_read",
          "decision": "ALLOW",
          "timestamp": "2026-01-01T00:00:00Z"
        }
      ]
    }
    ```

### Get Audit Event
*   **Endpoint:** `GET /api/v1/events/{event_id}`
*   **Idempotency:** Idempotent
*   **Response Payload:**
    ```json
    {
      "request_id": "6c5432ab-1234-5678-abcd-ef1234567890",
      "timestamp": "2026-07-19T22:23:00Z",
      "data": {
        "event_id": "9a8b7c6d-1234-5678-90ab-cdef12345678",
        "session_id": "session-123",
        "agent_id": "soc-agent",
        "tool_id": "file_read",
        "decision": "ALLOW",
        "timestamp": "2026-01-01T00:00:00Z"
      }
    }
    ```

---

## Error Handling Model
All API errors return a standard JSON payload:

```json
{
  "error": {
    "code": "AUTHORIZATION_DENIED",
    "message": "Agent does not possess required roles to invoke the file_read tool.",
    "request_id": "6c5432ab-1234-5678-abcd-ef1234567890"
  }
}
```

### Standard Error Codes
*   `AUTHENTICATION_FAILED` (401): Missing, expired, or invalid JWT.
*   `AUTHORIZATION_DENIED` (403): The agent does not have permissions for the requested tool.
*   `POLICY_VIOLATION` (403): The request violated resource policies (e.g. sensitive file path).
*   `VALIDATION_FAILED` (400): Parameters violate datatype constraints or bounds.
*   `TOOL_NOT_FOUND` (404): The requested tool ID is not registered in the Tool Registry.
*   `APPROVAL_REQUIRED` (202): Request is held pending administrative review.
*   `INTERNAL_SERVER_ERROR` (500): Unexpected platform failure.

---

## Versioning Strategy
*   **URI-Based Versioning:** The platform uses explicit URI version prefixes (`/api/v1`).
*   **Backward Compatibility:** Field deletions, schema type modifications, and path updates will trigger a new version prefix increment (e.g. `/api/v2`). Field additions and optional parameters are considered backward compatible.
*   **Deprecation Policy:** Deprecated endpoints will return a standard HTTP header `Deprecation: true` for at least one minor release cycle prior to removal.

---

## Future API Conventions
List endpoints in future API updates are expected to support standard REST conventions:
*   **Pagination:** URL query parameters `limit` and `offset` (e.g. `/api/v1/events?limit=50&offset=100`).
*   **Filtering:** Filtering by active attributes (e.g. `/api/v1/events?decision=DENY`).
*   **Cursor-Based Navigation:** Page boundaries using opaque cursor keys (`starting_after`, `ending_before`) for high-frequency logs.

---

## Future Platform APIs

### Governance APIs
*   **Policy Management:** Manage deterministic policy configurations.
    *   `GET /api/v1/policies`
    *   `POST /api/v1/policies`
*   **Approvals Workflows:** Resolve held requests.
    *   `GET /api/v1/approvals`
    *   `POST /api/v1/approvals/{id}/approve`
    *   `POST /api/v1/approvals/{id}/reject`

### Security APIs
*   **Threat Findings:** Expose security flags raised during evaluation.
    *   `GET /api/v1/findings`
*   **Risk Metrics:** Expose agent and session threat scores.
    *   `GET /api/v1/risk`

### Observability APIs
*   **Console Dashboard Summary:** Metrics for the management console.
    *   `GET /api/v1/dashboard/summary`

### Multi-Agent APIs
*   **Agent Relationships:** Map cooperation paths between registered agents.
    *   `GET /api/v1/agents/{id}/relations`