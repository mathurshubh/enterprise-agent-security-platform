# 09 — UI Component Architecture

## Purpose

This document specifies the **UI Component Architecture**, server-state management, reusable component inventory, visual design tokens, and untrusted content rendering rules for the Enterprise Security Console.

---

## Scope

Governs:
- Server-state management (`src/api/`, `src/providers/`, `src/hooks/`)
- Presentational components (`src/components/`)
- Design system primitives (`src/components/ui/`)
- Shared domain widgets (`src/components/common/`)
- Tailwind CSS tokens (`src/styles/index.css`)
- Feature flag configuration (`src/config/featureFlags.ts`)

---

## Server-State Architecture (PR #70)

The Enterprise Security Console uses **TanStack Query v5** as the standard mechanism for all server state. Client-side UI state (search filters, selected rows, modal visibility) uses React `useState`.

### Data Flow

```
Backend Management API
        ↓
   Axios API Client (src/api/apiClient.ts)
        ↓
   Service Functions (src/services/*.ts)
        ↓
   TanStack Query (useQuery / useMutation)
        ↓
   Domain Hooks (src/hooks/use*.ts)
        ↓
   Page Components (src/pages/)
```

### QueryClient Configuration (`src/api/queryClient.ts`)

| Option | Value | Rationale |
|---|---|---|
| `staleTime` | `30_000` ms | Management API data changes infrequently. Avoids redundant requests while navigating between pages. |
| `gcTime` | `300_000` ms | Keeps cache alive for 5 minutes after all observers unmount, enabling instant back-navigation. |
| `retry` | `1` | Retries once on transient failure before surfacing an error. Handles backend restarts without hiding persistent failures. |
| `refetchOnWindowFocus` | `false` | Prevents surprising re-renders when an analyst switches browser tabs during an investigation. |
| `refetchOnReconnect` | `true` | Refreshes stale data when connectivity is restored after a brief network interruption. |

### Query Key Registry (`src/api/queryKeys.ts`)

All TanStack Query keys are defined in a single centralized registry. This eliminates scattered string literals and enables reliable cache invalidation across all hooks.

```typescript
import { queryKeys } from '../api/queryKeys'

// Collection queries
useQuery({ queryKey: queryKeys.agents.all, ... })
useQuery({ queryKey: queryKeys.findings.all, ... })
useQuery({ queryKey: queryKeys.approvals.pending, ... })

// Parameterized queries
useQuery({ queryKey: queryKeys.sessions.byId(sessionId), ... })
useQuery({ queryKey: queryKeys.findings.bySession(sessionId), ... })

// Cache invalidation after a mutation
queryClient.invalidateQueries({ queryKey: queryKeys.approvals.pending })
```

**Registry coverage** (current + planned):

| Domain | Keys |
|---|---|
| `agents` | `all`, `byId` |
| `tools` | `all`, `byId` |
| `sessions` | `all`, `byId`, `events` (PR #72) |
| `auditEvents` | `all` |
| `detectionRules` | `all`, `byId` |
| `scenarios` | `all`, `byId` |
| `findings` | `all`, `byId`, `bySession`, `byAgent` (PR #69) |
| `risk` | `bySession`, `byAgent` (PR #70 vertical slice) |
| `approvals` | `pending`, `byId` (PR #71) |
| `dashboard` | `summary` (Phase 2+) |

### API Client (`src/api/apiClient.ts`)

The shared Axios instance provides:

- **Base URL**: `/api/v1` (Management API only; never targets Runtime API endpoints)
- **Request interceptor**: JWT `Authorization` header injection stub (Phase 3 — ADR-009)
- **Response interceptor**: Normalizes all HTTP and network errors into `ApiError` shape before reaching hooks

```typescript
// ApiError shape (src/types/api.ts)
interface ApiError {
  status: number    // HTTP status code; 0 for network-level failures
  message: string   // Human-readable summary for ErrorState display
  detail?: string   // Optional backend error detail
}
```

---

## Error Isolation Architecture (PR #70)

### React Error Boundary (`src/components/common/ErrorBoundary.tsx`)

A React class component wraps the layout `<Outlet />` in `AppLayout.tsx`. This provides page-level crash isolation:

```
AppLayout
  ├── <Sidebar />          (always rendered)
  ├── <Header />           (always rendered)
  └── <main>
        └── <ErrorBoundary>   ← crash isolation boundary
              └── <Outlet />  ← page content (may throw)
```

If a page component throws a render error:
- The `ErrorBoundary` catches it and renders a structured fallback UI with a **Retry** button
- The sidebar and header remain fully functional
- The analyst can navigate to another page without a full page reload

Error Boundary does **not** catch: async errors, event handlers, or server errors (those are handled by TanStack Query's `error` state).

---

## Feature Flag Framework (`src/config/featureFlags.ts`)

Static boolean constants gate Phase 2+ capabilities on backend API availability.

| Flag | Default | Activates In |
|---|---|---|
| `BEHAVIORAL_TELEMETRY_ENABLED` | `false` | PR #68 |
| `FINDINGS_ENABLED` | `false` | PR #69 |
| `RISK_ENGINE_ENABLED` | `false` | PR #70 vertical slice |
| `ENFORCEMENT_ENGINE_ENABLED` | `false` | PR #71 |
| `SESSION_TIMELINE_ENABLED` | `false` | PR #72 |

**Security invariant**: Feature flags control UI presentation only. They are **not** authorization controls. The backend enforces authorization for every request independently of these flags.

---

## Permission Guard Stub (`src/components/common/PermissionGuard.tsx`)

A structural placeholder wrapping UI elements that will require authorization in Phase 3.

```tsx
<PermissionGuard permission="approvals:write">
  <ReleaseButton ... />
</PermissionGuard>
```

**Current behavior (PR #70)**: Renders children unconditionally. No authorization logic is applied.

**Phase 3 behavior (ADR-009)**: Will evaluate JWT claims against the required permission and render children or a fallback accordingly.

**Security invariant**: The guard controls UI presentation only. Backend endpoints enforce authorization for every API call independently.

---

## Route Lazy Loading (`src/App.tsx`)

All page components use `React.lazy()` with a single `<Suspense>` boundary for route-level code splitting.

```
Initial bundle: Layout shell + TanStack Query + Router (~267 kB)
Route chunks (loaded on demand):
  DashboardPage       ~2.8 kB
  AgentsPage          ~7.3 kB
  ToolsPage           ~7.5 kB
  DetectionRulesPage  ~6.5 kB
  ScenariosPage       ~6.7 kB
  SessionsPage        ~3.7 kB
  AuditTimelinePage   ~5.0 kB
  ApprovalQueuePage   ~0.5 kB (placeholder)
  FindingsPage        ~0.5 kB (placeholder)
```

Layout components (`AppLayout`, `Sidebar`, `Header`) are **eagerly loaded** because they are needed immediately on every route and represent a negligible fraction of the bundle.

---

## Reusable Component Directory

### Tier 1: Design System Primitives (`src/components/ui/`)
- `<Badge>`: Standardized status pills with color tokens for Agent Status, Risk Level, Audit Decisions, and Threat Categories.
- `<PageHeader>`: Consistent page title and description header.
- `<NavIcon>`: Sidebar navigation icon component.

### Tier 2: Shared Domain Widgets (`src/components/common/`)
- `<ErrorBoundary>`: Page-level crash isolation (PR #70).
- `<PermissionGuard>`: Authorization enforcement stub for Phase 3 (PR #70).
- `<LoadingState>`: Centered spinner with optional fullscreen mode for Suspense fallback.
- `<ErrorState>`: Structured API error display with connection troubleshooting context.
- `<EmptyState>`: Empty collection state with optional title, description, and CTA action.
- `<MetricCard>`: Metric card with label, value, and loading skeleton.
- `<GatedPlaceholderPage>`: Reusable Phase 2-gated placeholder for routes awaiting backend APIs.

### Tier 3: Domain Components (`src/components/domain/`) — Phase 2+
- `<FindingCard>`: Compact card rendering a Behavioral Finding with severity badge, rule name, and timestamp.
- `<RiskIndicator>`: Visual risk score gauge (0–100) and risk tier badge.
- `<EnforcementBadge>`: Color-coded badge for canonical enforcement actions.
- `<ApprovalActionPanel>`: Audited form panel for approval queue release/rejection.

### Tier 4: Presentational Tables (`src/pages/*/components/`)
- Domain-specific table components (`AgentTable`, `ToolTable`, `DetectionRuleTable`, `AuditTable`, `SessionTable`, `ScenarioTable`) rendering structured tabular data with skeleton loading states and empty state fallbacks.

---

## Untrusted Content Isolation Architecture

Per Principle 9 ([02-design-principles.md](02-design-principles.md)), raw content generated by user prompts, LLMs, or tool execution outputs MUST be visually isolated from platform-determined security metadata:

```html
<!-- Example Untrusted Content Box Pattern -->
<div className="border border-border-secondary bg-bg-secondary p-3 rounded font-mono text-xs text-text-secondary">
  <div className="flex items-center justify-between pb-2 mb-2 border-b border-border-secondary text-text-muted">
    <span className="flex items-center gap-1">
      <ShieldAlertIcon className="w-3.5 h-3.5 text-status-warning" />
      Untrusted Payload (Model Output / Raw Parameters)
    </span>
    <span className="uppercase text-[10px] tracking-wider">Escaped Render</span>
  </div>
  <pre className="whitespace-pre-wrap break-all">{sanitizedPayload}</pre>
</div>
```

---

## Shared Type Inventory (`src/types/`)

| File | Domain | Status |
|---|---|---|
| `agent.ts` | Agent identity, status, risk tier | Implemented |
| `tool.ts` | Tool registration, capabilities | Implemented |
| `session.ts` | Execution session state | Implemented |
| `auditEvent.ts` | Audit event trail records | Implemented |
| `detectionRule.ts` | Detection rule catalog | Implemented |
| `scenario.ts` | Attack simulation scenarios | Implemented |
| `finding.ts` | Detection findings | Typed (PR #69 implements) |
| `approval.ts` | Pending approval tickets | Typed (PR #71 implements) |
| `dashboard.ts` | Command Center summary metrics | Typed (Phase 2+ implements) |
| `api.ts` | `ApiError`, `PaginatedResponse<T>` | Implemented (PR #70) |

---

## Design System Tokens & Color Maps

The UI utilizes OKLCH color tokens configured in `src/styles/index.css` via Tailwind CSS v4 `@theme`:

| Status Category | Semantic Token | OKLCH Color Value | Used For |
|---|---|---|---|
| **Canvas Background** | `--color-bg-primary` | `oklch(0.145 0.012 265)` | Dark app canvas |
| **Surface Secondary** | `--color-bg-secondary` | `oklch(0.185 0.012 265)` | Sidebar, header, card headers |
| **Surface Card** | `--color-bg-surface` | `oklch(0.215 0.014 265)` | Metric cards, table rows, drawers |
| **Primary Accent** | `--color-accent-primary` | `oklch(0.62 0.18 260)` | Active navigation, primary buttons |
| **Status: Active / Low** | `--color-status-active` | `oklch(0.65 0.18 155)` | `ACTIVE`, `LOW` risk, `ALLOW` |
| **Status: Warning / Med** | `--color-status-warning` | `oklch(0.75 0.15 75)` | `SUSPENDED`, `MEDIUM` risk, `REQUIRE_APPROVAL` |
| **Status: Error / High** | `--color-status-error` | `oklch(0.60 0.20 25)` | `DISABLED`, `HIGH`/`CRITICAL` risk, `DENY` |

---

## Dependencies

- Serves as the implementation basis for all page components in Page Specifications ([08-page-specifications.md](08-page-specifications.md)).

---

## Relationship to Other Architecture Documents

- Implements Principle 9 (Untrusted Content Isolation) from [02-design-principles.md](02-design-principles.md).
- TanStack Query integration established by PR #70 (Frontend Foundation).
- ADR-009 (JWT enforcement) integration point documented in `PermissionGuard` and API client.

---

## Future Evolution

As the Phase 2 vertical slices ship (PR #68–PR #72), the following will be added:

- `<FindingCard>` and `<RiskIndicator>` domain components (PR #69–PR #70 vertical slice)
- `<ApprovalActionPanel>` with audited release/reject mutations (PR #71)
- `<SessionTimeline>` replay control components (PR #72)
- `<ReplayControlBar>` (Play, Pause, Step, Speed) when Phase 4 forensic replay ships

Frontend unit testing (Vitest) will begin in PR #71, the first feature-bearing PR with meaningful business behavior to validate.
