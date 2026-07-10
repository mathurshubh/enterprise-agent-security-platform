# Enterprise Security Console

The frontend for the Enterprise Agent Security Platform — a read-only visualization layer over the Enterprise Management API.

This console is **not** an AI agent.  It lies entirely outside the Runtime Security Boundary and does not participate in policy enforcement, risk decisions, or tool execution.

---

## Architecture Reference

This project implements [ADR-009: Enterprise Security Console](../docs/adr/ADR-009-enterprise-security-console.md).

The console consumes the [Enterprise Management API](../docs/adr/ADR-008-enterprise-management-api.md) (read-only) and never interacts with the Runtime API.

---

## Technology Stack

| Technology   | Purpose                                      |
|-------------|----------------------------------------------|
| React        | Component-based UI rendering                 |
| TypeScript   | Compile-time type safety                     |
| Vite         | Build tooling and development server         |
| Tailwind CSS | Utility-first styling (v4 with Vite plugin)  |
| React Router | Client-side routing                          |
| Axios        | HTTP client for Management API consumption   |

---

## Directory Structure

```
src/
├── api/                    # Axios client and future API utilities
│   └── apiClient.ts        # Pre-configured Axios instance (baseURL: /api/v1)
│
├── assets/                 # Static assets (images, fonts)
│
├── components/             # Reusable UI components
│   ├── common/             # Shared components (buttons, badges, cards)
│   └── layout/             # Application shell components
│       ├── Sidebar.tsx      # Navigation sidebar
│       └── Header.tsx       # Top header bar
│
├── hooks/                  # Custom React hooks
│
├── icons/                  # Icon components
│
├── layouts/                # Page layout wrappers
│   └── AppLayout.tsx       # Sidebar + Header + Outlet shell
│
├── pages/                  # Page components (one per route)
│   ├── Dashboard/
│   ├── Agents/
│   ├── Tools/
│   ├── Detection/
│   └── Audit/
│
├── routes/                 # Route configuration (future extraction)
│
├── services/               # API service wrappers (future)
│
├── styles/                 # Global styles and theme tokens
│   └── index.css           # Tailwind imports + CSS custom properties
│
├── types/                  # TypeScript type definitions for API models
│
├── utils/                  # Utility functions
│
├── App.tsx                 # Root component with route definitions
└── main.tsx                # Application entry point
```

---

## Development

### Prerequisites

- Node.js >= 20
- npm >= 10

### Install Dependencies

```bash
npm install
```

### Start Development Server

```bash
npm run dev
```

The dev server starts at `http://localhost:3000`.

### Build for Production

```bash
npm run build
```

Produces optimized static files in `dist/`.

### Lint

```bash
npm run lint
```

---

## Routes

| Path          | Page                | ADR-009 Reference     |
|--------------|---------------------|-----------------------|
| `/`          | Dashboard           | Dashboard             |
| `/agents`    | Agents              | Agents View           |
| `/tools`     | Tools               | Tools View            |
| `/detection` | Detection Rules     | Detection Rules View  |
| `/audit`     | Audit Timeline      | Audit Timeline        |

---

## ADR-009 Compliance

The console is a **thin client** that:

- Contains zero security enforcement logic
- Makes no write operations or mutations
- Never invokes RuntimeService or executes tools
- Never calls LLM providers
- Never evaluates authorization, policies, or detection rules
- Relies on framework-provided output escaping for untrusted content

---

## Roadmap

Upcoming pages (pending backend API support):

- **Coverage View** — requires `GET /api/v1/coverage`
- **Findings View** — requires `GET /api/v1/findings` and persistent findings storage

Upcoming capabilities:

- Dashboard widget implementation (PR #49)
- Agent table with API integration
- Tool inventory with API integration
- Detection rule grid with security framework mappings
- Audit event timeline with API integration
- Live Runtime Monitor (requires backend event streaming)
- Session Explorer (requires session ownership validation)
