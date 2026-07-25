# 10 — Data Flow Architecture

## Purpose

This document specifies the **Data Flow Architecture**, API client integration, caching layers, real-time streaming, and audited write operations for the Enterprise Security Console.

---

## Scope

Governs Axios API integration (`src/api/apiClient.ts`), service layer wrappers (`src/services/`), state hooks (`src/hooks/`), caching layer, and WebSocket/SSE streaming interfaces.

---

## End-to-End Client Data Architecture

```text
Backend REST Management API (/api/v1/*)          Backend SSE / Streaming Endpoint
                    │                                          │
                    ▼                                          ▼
   Axios API Client (apiClient.ts)              Server-Sent Events (SSE) Listener
                    │                                          │
                    ▼                                          │
   Domain Services (src/services/*.ts)                         │
   • DTO Validation & Mapping                                  │
   • Enum Normalization & Fallbacks                             │
                    │                                          │
                    ▼                                          ▼
   Query Cache Layer (TanStack Query)  ◄───────────── Cache Invalidation Events
   • Request Deduplication & Stale-While-Revalidate
   • Optimistic Updates Prohibited for Security Writes
                    │
                    ▼
   Custom React Hooks (src/hooks/use*.ts)
                    │
                    ▼
   Page & Component Presentation Layer
```

---

## Data Flow Layers

### 1. API Client Layer (`src/api/apiClient.ts`)
- Configures Axios instance targeted to `/api/v1` base URL.
- Attaches JWT authentication headers from secure session storage.
- Standardizes HTTP error interceptors (e.g., 401 Unauthorized redirect, 403 Forbidden alert, 503 Service Unavailable degraded mode).

### 2. Service Layer (`src/services/*.ts`)
- Encapsulates API endpoints and maps raw backend Data Transfer Objects (DTOs) to UI domain models.
- **Defensive DTO Mapping:** Performs array shape verification (`Array.isArray`), field null-coalescing, and enum fallback assignment to guarantee component safety.

```typescript
// Architectural Pattern: Defensive DTO Service Mapping
export async function getAgents(): Promise<Agent[]> {
  const response = await apiClient.get<AgentResponse[]>('/agents');
  const data = Array.isArray(response.data) ? response.data : [];
  return data.map((dto) => ({
    id: dto.agent_id,
    name: dto.name || 'Unnamed Agent',
    status: normalizeAgentStatus(dto.status),
    riskLevel: normalizeRiskTier(dto.risk_tier),
    owner: dto.owner || 'Unassigned',
    approvedTools: Array.isArray(dto.approved_tools) ? dto.approved_tools : [],
  }));
}
```

### 3. Query Cache Layer (TanStack Query — Introduced in Phase 2)
- Replaces naive mount-time re-fetching with structured client-side query caching.
- Configures stale time intervals based on artifact lifecycle class:
  - **Immutable Evidence (Audit Events, Findings):** Long stale time (`staleTime: 5 * 60 * 1000` / 5 mins); data is append-only and immutable.
  - **Current State (Active Sessions, Risk Posture):** Short stale time (`staleTime: 10 * 1000` / 10s); automatic background polling or SSE invalidation.
  - **Registry Metadata (Agents, Tools, Rules):** Moderate stale time (`staleTime: 60 * 1000` / 1 min).

### 4. Custom Hook Layer (`src/hooks/`)
- Exposes typed query and mutation state (`data`, `loading`, `error`, `refetch`, `mutate`) to presentation components.

---

## Audited Operator Write Operations Pattern

For administrative write operations (e.g., releasing a held session in `/approvals`), the data flow strictly follows an audited command pattern:

```text
User Action (Click "Approve Release")
       │
       ▼
Approval Action Panel (Requires Mandatory Justification Text)
       │
       ▼
Submit Mutation: POST /api/v1/approvals/:id/release { justification: "Analyst verified" }
       │ (Prohibited: Optimistic Local State Mutation)
       ▼
Backend API Validates JWT + RBAC + Session Hold State → Writes Immutable Audit Event → Returns 200 OK
       │
       ▼
Frontend Receives 200 OK → Invalidates Query Cache → Refetches Pending Approvals List
```

> **Critical Rule:** Optimistic UI state updates are **strictly prohibited** for security-critical governance writes. The UI MUST await authoritative backend HTTP 200 OK confirmation before updating visual state.

---

## Real-Time Streaming Architecture (Phase 4)

In Phase 4, real-time alert delivery utilizes Server-Sent Events (SSE) targeting `GET /api/v1/telemetry/stream`:
- Unidirectional event stream broadcasting new Behavioral Findings and Enforcement Hold triggers.
- Upon receiving an SSE payload, TanStack Query invalidates the `/approvals/pending` and `/findings` query cache keys, triggering an automatic UI refresh without full page reloads.

---

## Design Rationale

Defensive DTO mapping in the service layer prevents malformed backend responses from breaking UI rendering. Introducing TanStack Query eliminates redundant network requests while respecting the immutability of historical evidence. Prohibiting optimistic UI updates for governance write actions preserves Zero Trust integrity.

---

## Tradeoffs

- **Network Delay on Writes:** Disallowing optimistic updates means buttons show a loading spinner until the backend HTTP response completes (typically 50–150ms). This slight delay is an intentional design choice to guarantee security decision accuracy.

---

## Dependencies

- Phase 1 uses existing `src/hooks/useApiResource.ts`.
- Phase 2 introduces TanStack Query (`@tanstack/react-query`).
- Phase 4 introduces SSE streaming listener.

---

## Relationship to Other Architecture Documents

- Implements Principle 1 (Backend Is Truth), Principle 4 (Audited Operator Writes), and Principle 10 (Graceful Degradation) from [02-design-principles.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/architecture/enterprise-security-console/02-design-principles.md).

---

## Future Evolution

As WebSocket APIs are deployed in Phase 4 for live collaborative investigations, the SSE stream listener will upgrade to a bidirectional WebSocket transport wrapper.
