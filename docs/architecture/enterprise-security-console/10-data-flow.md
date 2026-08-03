# 10 — Data Flow Architecture

## Purpose

This document specifies the **Data Flow Architecture**, API client integration, caching layers, and service wrappers for the Enterprise Security Console.

---

## Scope

Governs Axios API integration (`src/api/apiClient.ts`), service layer wrappers (`src/services/`), state hooks (`src/hooks/`), and the TanStack Query caching layer.

---

## End-to-End Client Data Architecture

```text
Backend REST APIs (/api/v1/* and /api/scenarios)
                    │
                    ▼
   Axios API Client (apiClient.ts)
                    │
                    ▼
   Domain Services (src/services/*.ts)
   • DTO Validation & Mapping                                  │
   • Enum Normalization & Fallbacks
                    │
                    ▼
   Query Cache Layer (TanStack Query)
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
- Configures Axios instance targeted to `/api` base URL.
- Uses `ApiRoutes` for `/v1` Management API routes and `/scenarios` Scenario API routes.
- Includes a JWT header injection stub; requests are sent unauthenticated by default.
- Normalizes HTTP and network errors into the frontend `ApiError` shape.

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

### 3. Query Cache Layer (TanStack Query)
- Replaces naive mount-time re-fetching with structured client-side query caching.
- Configures stale time intervals based on artifact lifecycle class:
  - **Registry Metadata (Agents, Tools, Rules, Scenarios):** Cached and refetched through TanStack Query.
  - **Operational Evidence (Audit Events, Sessions):** Queried from read-only Management API endpoints.
  - **Gated Capabilities (Findings, Approvals, Risk):** Query keys and types exist, but backend endpoints are not implemented.

### 4. Custom Hook Layer (`src/hooks/`)
- Exposes typed query and mutation state (`data`, `loading`, `error`, `refetch`, `mutate`) to presentation components.

---

## Scenario Execution Mutation Pattern

The frontend mutation path executes benchmark scenarios through the Scenario API:

```text
User Action (Click "Execute Scenario")
       │
       ▼
Scenario Page
       │
       ▼
Submit Mutation: POST /api/scenarios/:id/execute
       ▼
ScenarioRunnerService executes through RuntimeService and returns ScenarioExecutionResponse
       │
       ▼
Frontend renders observed decision, response, risk level, findings, and mismatches
```

> **Critical Rule:** The UI must render backend results as authoritative. It must not fabricate security decisions, findings, risk scores, or approval outcomes.

---

## Design Rationale

Defensive DTO mapping in the service layer prevents malformed backend responses from breaking UI rendering. TanStack Query eliminates redundant network requests while respecting backend ownership of platform state.

---

## Tradeoffs

- **Backend Dependency:** Gated pages remain placeholders until corresponding backend APIs exist. This avoids mock security data.

---

## Dependencies

- The frontend uses TanStack Query (`@tanstack/react-query`) through `QueryProvider`.

---

## Relationship to Other Architecture Documents

- Implements Principle 1 (Backend Is Truth), Principle 4 (Audited Operator Writes), and Principle 10 (Graceful Degradation) from [02-design-principles.md](02-design-principles.md).

---

## Future Evolution

Additional data flows should be documented only when corresponding backend endpoints exist.
