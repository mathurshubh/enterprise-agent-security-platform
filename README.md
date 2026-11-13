# Enterprise Agent Security Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688)
![React](https://img.shields.io/badge/React-19-61DAFB)
![Tests](https://img.shields.io/badge/Tests-1%2C788_passing-success)
![Release](https://img.shields.io/badge/Release-v0.18.0-blue)
![Security](https://img.shields.io/badge/Security-Zero_Trust-red)
![License](https://img.shields.io/badge/License-MIT-green)

**A Zero Trust security and governance platform for enterprise AI agents.**

The platform governs AI agents through deterministic identity verification, authentication,
authorization, policy enforcement, runtime containment, detection, risk assessment, response
and auditability. It is **not** an AI agent framework and is not itself an AI agent: it is the
control layer that sits between agents and the tools they want to use.

> **Every LLM is treated as an untrusted intent parser. The LLM may propose a structured
> `ToolInvocation`; it never makes an authorization, policy, risk, detection, response or
> execution decision. Those decisions are deterministic code, enforced outside the model.**

![Command Center of the Enterprise Security Console](docs/assets/screenshots/01-command-center.png)

*The Enterprise Security Console running locally. A complete runtime decision timeline is shown
under [Enterprise Security Console](#enterprise-security-console).*

---

## Contents

- [Why this platform exists](#why-this-platform-exists)
- [Core design principles](#core-design-principles)
- [Architecture overview](#architecture-overview)
- [Security enforcement lifecycle](#security-enforcement-lifecycle)
- [Implemented capabilities](#implemented-capabilities)
- [Enterprise Security Console](#enterprise-security-console)
- [API surface](#api-surface)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Installation and local development](#installation-and-local-development)
- [Running tests and quality checks](#running-tests-and-quality-checks)
- [Security architecture and threat model](#security-architecture-and-threat-model)
- [Architecture Decision Records](#architecture-decision-records)
- [Current implementation status](#current-implementation-status)
- [Known gaps and limitations](#known-gaps-and-limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why this platform exists

Enterprise AI agents turn natural language into actions against files, systems and data. The
model that interprets the request can be manipulated — by a user prompt, by retrieved content,
or by a tool's own output — so it cannot also be the component that decides whether an action
is allowed.

This platform separates the two responsibilities:

| LLM responsibility | Security platform responsibility |
|---|---|
| Interpret natural language | Authenticate callers and agents (JWT) |
| Produce a structured `ToolInvocation` | Authorize the agent for the tool (approved tools, lifecycle state) |
| | Evaluate resource-aware policy (risk tier, protected resources) |
| | Detect threats in prompts, model output, tool output and session behaviour |
| | Assess cumulative risk and select a response |
| | Issue single-use execution authority and run the tool in a process sandbox |
| | Record audit evidence for every decision |

---

## Core design principles

- **Zero Trust.** Every request is authenticated, authorized, evaluated and audited. No agent
  action or internal transition is implicitly trusted.
- **Least privilege.** Agents may use only explicitly approved tools, within the resource and
  risk-tier constraints policy allows. Each API plane admits only the roles it declares.
- **Deterministic security decisions.** Authorization, policy, detection, risk and response are
  implemented in deterministic code ([ADR-002](docs/adr/ADR-002-llm-untrusted-intent-parser.md),
  [ADR-004](docs/adr/ADR-004-deterministic-security-pipeline.md)).
- **Resource-aware authorization.** Policy evaluates what would actually be executed — the
  resource and parameters — not just the tool name
  ([ADR-006](docs/adr/ADR-006-resource-aware-authorization.md)).
- **Fail closed.** Missing configuration, an invalid persistence topology, an unrecordable
  detection result, a missing sandbox or missing lifecycle state all refuse rather than degrade.
- **Immutable, monotonic authority.** Once `(tool_id, tool_version)` is resolved and authorized,
  nothing downstream re-resolves, substitutes, downgrades or upgrades it. Execution identity is
  carried on the signed grant, never inferred from caller context.
- **Auditability and evidence integrity.** Audit records requested and resolved identity as
  separate facts, and denial evidence is recorded even when a request names a tool that does not
  exist ([ADR-034](docs/adr/ADR-034-audit-identity-contract.md)).
- **Provider-agnostic.** Security services are decoupled from the LLM provider (Ollama and
  Google Gemini adapters are implemented).

---

## Architecture overview

```mermaid
flowchart TD
    U["User request"] --> LLM["LLM provider (Ollama / Gemini)<br/>untrusted intent parser"]
    LLM --> TI["Structured ToolInvocation"]
    TI --> RS["RuntimeService<br/>single security authority"]

    subgraph PIPE["Deterministic security pipeline"]
        RS --> AZ["Authorization + PolicyEngine<br/>agent, tool, lifecycle, risk tier, resource"]
        AZ --> SE["Session event recording"]
        SE --> DET["Detection<br/>content rules + EXCESSIVE_DENIALS"]
        DET --> FS["FindingsService<br/>authoritative evidence"]
        FS --> RK["RiskService / RiskAggregator<br/>derived posture"]
        RK --> RP["ResponseService<br/>MONITOR / ALERT / REQUIRE_APPROVAL / SUSPEND_AGENT"]
        RP --> DEC{"Final decision"}
    end

    DEC -->|ALLOW| EA["ExecutionAuthority<br/>signed single-use RuntimeExecutionGrant"]
    EA --> SB["ProcessToolExecutionSandbox<br/>isolated child process"]
    DEC -->|DENY| BL["Blocked"]
    DEC -->|APPROVAL_REQUIRED| HR["Held for human approval"]
    RS --> AU["AuditService"]
    RS -.-> TD["TelemetryDispatcher<br/>non-blocking BehavioralEvent"]
```

`RuntimeService` is the single authoritative source of runtime security decisions. The
Enterprise Security Console and the management API are read-mostly observability and control
clients; they hold no security authority.

### Canonical security chain

```text
Identity → Authority → Policy → Capability → Runtime → Resource → Telemetry → Response
```

1. **Identity** — authenticate the caller and bind execution to the authenticated agent.
2. **Authority** — the agent's administrative and enforcement lifecycle planes must both permit
   execution, and the tool must be approved for the agent.
3. **Policy** — resource-aware rules over the requested resource and parameters.
4. **Capability** — resolve one concrete, enabled tool version from the governed catalog.
5. **Runtime** — a signed, single-use grant bound to exactly the evaluated operation.
6. **Resource** — process-level filesystem and network guards inside the sandbox.
7. **Telemetry** — audit events and non-blocking behavioural telemetry.
8. **Response** — monitoring, alerting, approval escalation or agent suspension.

---

## Security enforcement lifecycle

For every runtime request, the pipeline produces the stages shown in the console's
*Authoritative Execution Timeline* (screenshot above):

```text
1. Request         Agent identity, session and requested tool/resource
2. Intent          The ToolInvocation (from the LLM, or a deterministic tool sequence)
3. Authorization   Six canonical policy checks, short-circuiting on the first failure:
                     agent_check · tool_check · approved_tool_check ·
                     status_check · risk_tier_check · resource_check
4. Detection       Content rules over prompt / model output / tool output,
                   plus the stateful EXCESSIVE_DENIALS rule over the session horizon
5. Risk            Cumulative risk level and score for the (session_id, agent_id) scope
6. Response        MONITOR, ALERT, REQUIRE_APPROVAL or SUSPEND_AGENT
7. Audit           An audit event correlated to the session
8. Final decision  ALLOW, DENY or APPROVAL_REQUIRED (response overrides apply:
                   SUSPEND_AGENT → DENY, REQUIRE_APPROVAL → APPROVAL_REQUIRED)
```

Only an `ALLOW` causes `ExecutionAuthority` to mint a signed `RuntimeExecutionGrant`, and only a
verified grant lets the tool run in the process sandbox. The public runtime endpoint is
**decision-only**: it never executes a tool and never returns a grant
([ADR-023](docs/adr/ADR-023-execution-authorization-grants.md)).

### Approval authority

Two concepts are deliberately kept separate
([ADR-031](docs/adr/ADR-031-execution-grant-approval-control-plane.md)):

- **`ApprovalContinuation`** — an approval-lifecycle artifact representing human-approved
  authority, with the states `PENDING → APPROVED / REJECTED / EXPIRED → CONSUMED`. It is a frozen
  artifact and is **not** directly executable. Its repository interface has in-memory and SQL
  adapters, but durable operation is not available in the runnable configuration today (see
  [Known gaps](#known-gaps-and-limitations)).
- **`RuntimeExecutionGrant`** — ephemeral, cryptographically signed execution authority.

A continuation must be claimed (exactly once) before a runtime grant is minted; the ordering is
never reversed.

---

## Implemented capabilities

### Identity, authentication and plane authorization

- JWT authentication (FastAPI `HTTPBearer`, PyJWT). The platform refuses to start without an
  explicit `JWT_SECRET_KEY` of sufficient length; there is no development fallback and `.env`
  files are not loaded.
- Plane authorization ([ADR-025](docs/adr/ADR-025-management-plane-authorization.md)): each
  router is mounted with the roles its plane admits — runtime `AGENT`; scenarios and management
  `ANALYST`/`ADMIN`; reinstatement `ADMIN` only. A route may narrow its plane, never widen it.
- Execution identity is bound to the authenticated agent: an agent can execute only as itself,
  and authority to manage an agent is never authority to act as one.

### Agent identity and lifecycle (F-09)

- Agent registry with owner, risk tier and approved tools.
- **Two lifecycle planes**, evaluated independently:
  - *Administrative plane* — `REGISTERED → ACTIVE → DISABLED`, with attributed, versioned
    compare-and-set transitions and an administrative audit trail.
  - *Enforcement plane* — runtime `SUSPEND` and administrative `REINSTATE`, with monotonic
    enforcement epochs ([ADR-024](docs/adr/ADR-024-agent-enforcement-state.md),
    [ADR-026](docs/adr/ADR-026-materialized-risk-projection-and-enforcement-epochs.md)).
- Execution authority is issued only when **both** planes permit it; missing administrative
  state fails closed. The runtime may contain an agent but never returns one to service —
  recovery runs only through the `EnforcementCoordinator` reinstatement path.
- Suspension revokes the agent's outstanding execution grants immediately.

### Tool registry and authorization

- Versioned tool identity: tool families plus concrete `(tool_id, version)` rows, with
  version-scoped enablement and family-scoped authorization kept distinct
  ([ADR-005](docs/adr/ADR-005-tool-registry.md), [ADR-033](docs/adr/ADR-033-tool-catalog-contract.md)).
- Default tools: `file_read` and `directory_list`, operating on a confined workspace.
- An authorization decision binds to one concrete operation — tool, version, resource and
  parameters — and an explicit resource that contradicts its path parameter is denied.

### Policy enforcement

- `PolicyEngine` with lifecycle, risk-tier/tool-risk alignment and protected-resource checks;
  `CRITICAL`-risk tools require human approval.
- Canonical filesystem resource identity, so a protected resource cannot be reached through an
  alternative spelling of its path.

### Detection and findings

| Rule | Type | Framework mapping |
|---|---|---|
| `PROMPT_INJECTION` | Content (registry) | OWASP LLM01, MITRE ATLAS AML.T0043 |
| `SENSITIVE_FILE_ACCESS` | Content (registry) | MITRE ATT&CK T1083 |
| `DATA_EXFILTRATION` | Content (registry) | MITRE ATT&CK T1048 |
| `EXCESSIVE_DENIALS` | Stateful, over a 30-minute session detection horizon | — |

- The three content rules are registered at a single authoritative site and are what the
  console's Detection Rules page lists; `EXCESSIVE_DENIALS` is evaluated by `DetectionService`.
- `FindingsService` records findings as authoritative evidence, with identity derived from the
  occurrence ([ADR-029](docs/adr/ADR-029-finding-occurrence-identity.md)). If detection evidence
  cannot be recorded, the request is refused.

### Risk assessment and response

- Cumulative risk per `(session_id, agent_id)` scope, plus a materialized agent-level risk
  projection (`RiskAggregator`).
- `ResponseService` maps risk to `MONITOR`, `ALERT`, `REQUIRE_APPROVAL` or `SUSPEND_AGENT`, and
  the runtime applies Zero Trust overrides to the final decision.

### Runtime tool execution isolation

- `ProcessToolExecutionSandbox`: tools run in a dedicated child process across a JSON-only IPC
  boundary. There is no in-process fallback — a missing sandbox or a sandbox failure fails
  closed ([ADR-032](docs/adr/ADR-032-runtime-tool-execution-isolation.md)).
- Grants carry an HMAC-signed `capability_profile_id` and a SHA-256 `capability_digest`,
  verified before consumption.
- `FilesystemSandboxGuard` (workspace confinement, symlink-escape detection, scratch
  directories) and `NetworkSandboxGuard` (egress limited to declared CIDRs/ports; loopback,
  link-local, cloud-metadata and Unix sockets denied by default).
- Process-group cleanup (`SIGTERM`, then `SIGKILL`) and differentiated receipts (`TIMEOUT`,
  `RESOURCE_EXHAUSTED`, `ISOLATION_FAILURE`, `TOOL_EXECUTION_ERROR`).
- Execution evidence with grant-derived correlation, bounded terminal retention, and startup
  reconciliation that resolves interrupted executions to `UNKNOWN` before the application
  serves requests.

> **Sandbox boundary.** The process sandbox enforces capabilities for standard Python
> execution. It is not a kernel-level sandbox for hostile code: native extensions, raw syscalls,
> privileged operations and kernel escapes are outside its boundary. Strong isolation of
> arbitrary native code needs a future container or microVM backend.

### Durable state (Plane 3)

- Repository protocol interfaces with in-memory and SQL (SQLAlchemy 2.0, psycopg 3) adapters
  held to one shared contract suite ([ADR-030](docs/adr/ADR-030-durable-state-repository-architecture.md)).
- Alembic migrations `0001`–`0010` covering agents, administrative lifecycle, enforcement state
  and ledger, sessions and events, tool families/versions, audit evidence and approval
  continuations.
- Compare-and-set state progression, dual monotonic sequences (session-local and agent-scoped),
  detection-horizon watermarks, and parent-row serialization anchors, validated against
  PostgreSQL concurrency tests.
- **Configurable backend with startup validation:** `REPOSITORY_BACKEND` defaults to `memory`.
  Setting it to `sql` is currently **refused at startup** by the ADR-030 L.6 topology check,
  because findings are not yet durable and a durable enforcement watermark over a volatile
  findings allocator would silently suppress detection after a restart. See
  [Known gaps](#known-gaps-and-limitations).

### LLM integration and scenario execution

- Provider-agnostic adapter layer with Ollama (default model `llama3.2:3b`) and Google Gemini
  providers ([ADR-007](docs/adr/ADR-007-provider-agnostic-runtime.md)). Malformed model output
  fails closed.
- Scenario framework ([ADR-010](docs/adr/ADR-010-scenario-execution-architecture.md)–
  [ADR-013](docs/adr/ADR-013-scenario-runner-service-boundaries.md)): 19 YAML-defined
  scenarios across prompt injection, data exfiltration, authorization, sensitive data, tool
  abuse, provider failure, session behaviour, workflow security and benign baselines.
- Two execution modes: `TOOL_SEQUENCE` (deterministic, no LLM) and `PROMPT` (the LLM parses
  intent; requires a running provider).
- Scenario runs execute in an isolated sandbox pipeline with their own evidence store, so
  scenario activity never enters live security state (ADR-013 M2a).

### Audit and observability

- `AuditService` with an append-only audit trail; events record requested and resolved tool
  identity separately and correlate to their originating session.
- Non-blocking `TelemetryDispatcher` emitting canonical `BehavioralEvent`s
  ([ADR-015](docs/adr/ADR-015-behavioral-telemetry-architecture.md)).
- Runtime capability discovery (`CapabilityService`, `GET /api/v1/info`).

---

## Enterprise Security Console

The console is a React + TypeScript single-page application in [`frontend/`](frontend/) that
reads the management and scenario APIs. It is an observability and control-plane client and
holds no security authority: it implements no client-side authorization, and the browser holds
no credentials (see [Local development](docs/development/local-development.md)). Its nine routes
are grouped as defined in [ADR-022](docs/adr/ADR-022-enterprise-security-console-evolution.md):

| Section | Route | Page | State |
|---|---|---|---|
| Monitor | `/` | Command Center | Live data |
| Monitor | `/approvals` | Approval Queue | Placeholder — no approval API exists yet |
| Investigate | `/sessions` | Sessions | Live data |
| Investigate | `/findings` | Findings & Alerts | Live data |
| Investigate | `/audit` | Audit Trail | Live data |
| Govern | `/agents` | Agent Registry | Live data |
| Govern | `/tools` | Tool Registry | Live data |
| Govern | `/detection` | Detection Rules | Live data |
| Govern | `/scenarios` | Scenario Library and execution | Live data |

### Screenshots

These are screenshots of the running application at commit `8bc5c74`, taken at a 1440×900
viewport in headless Chrome. The data was produced by the platform itself: six decision requests
sent to the real runtime endpoint as the bootstrap agent `agent-1` (three benign workspace requests, a prompt
injection, an unregistered tool and a protected-resource read with exfiltration intent), plus
scenario runs from the console. Nothing was edited after capture. The only presentation change
was hiding the development-only TanStack Query devtools button. The Findings screenshot was
recaptured at commit `2445a92`, after the `detected_at` fix in #273, from the same six requests.

#### Runtime decision — the platform's core function

![Scenario execution timeline showing a DENY decision](docs/assets/screenshots/09-runtime-decision-deny.png)

Scenario `TOOL-002` (deterministic tool sequence) run from the console. The timeline shows each
pipeline stage for the final request in the sequence: the deterministic intent, the six canonical
policy checks (the tool check fails because `unauthorized_tool` is not registered, so later checks
are `NOT EVALUATED`), an `EXCESSIVE_DENIALS` finding, `MEDIUM` risk, an `ALERT` response, the
correlated audit event, and the final `DENY`. The evaluation `PASSED` because observed outcomes
matched the scenario's expectations.

#### Monitor

![Command Center](docs/assets/screenshots/01-command-center.png)

**Command Center** — platform inventory (agents, tools, detection rules, sessions, audit
events) and activity (healthy and high-risk agents, allowed and denied decisions). The
Action Required queue is still a placeholder.

#### Investigate

![Findings and alerts](docs/assets/screenshots/05-findings.png)

**Findings & Alerts** — findings from the runtime requests, with severity, rule, framework
control (`AML.T0043`, `T1048`), agent and session, plus session risk posture. "Detected At" is
the time the platform recorded each finding as evidence.

![Audit trail](docs/assets/screenshots/07-audit-trail.png)

**Audit Trail** — every runtime decision (`ALLOW`, `APPROVAL_REQUIRED`, `DENY`) with agent, tool
and resolved tool version. The unregistered `shell_exec` request appears as `unresolved`: its
denial is recorded even though the tool does not exist.

![Sessions](docs/assets/screenshots/06-sessions.png)

**Sessions** — agent execution sessions in the live runtime.

#### Govern

![Agent registry](docs/assets/screenshots/02-agent-registry.png)

**Agent Registry** — `agent-1` is `SUSPENDED`. The runtime contained the agent after the
high-risk requests in the demo sequence. Only an `ADMIN` reinstatement can return it to service.

![Tool registry](docs/assets/screenshots/03-tool-registry.png)

**Tool Registry** — the registered tools and their concrete versions.

![Detection rules](docs/assets/screenshots/04-detection-rules.png)

**Detection Rules** — the registered content rules and their OWASP LLM Top 10, MITRE ATLAS and
MITRE ATT&CK mappings.

![Scenario library](docs/assets/screenshots/08-scenario-library.png)

**Scenario Library** — the 19 security scenarios, filterable by category, with expected
detection and response.

---

## API surface

| Plane | Roles | Routes |
|---|---|---|
| Public | — | `GET /health`, `GET /version` |
| Runtime | `AGENT` (bound to own identity) | `POST /agents/{agent_id}/execute` (decision-only) |
| Scenarios | `ANALYST`, `ADMIN` | `GET /api/scenarios`, `GET /api/scenarios/{scenario_id}`, `POST /api/scenarios/{scenario_id}/execute` |
| Management | `ANALYST`, `ADMIN` | `GET /api/v1/agents`, `GET /api/v1/agents/{agent_id}/enforcement`, `GET /api/v1/tools`, `GET /api/v1/detection/rules`, `GET /api/v1/audit/events`, `GET /api/v1/sessions`, `GET /api/v1/findings`, `GET /api/v1/findings/{finding_id}`, `GET /api/v1/risk-assessments`, `GET /api/v1/risk-assessments/{session_id}`, `GET /api/v1/info` |
| Management (admin) | `ADMIN` | `POST /api/v1/agents/{agent_id}/reinstate` |

Interactive OpenAPI documentation is served by FastAPI at `/docs` while the backend runs. The
design notes are in [`docs/api/openapi-design.md`](docs/api/openapi-design.md).

---

## Technology stack

- **Backend:** Python 3.13, FastAPI, Pydantic, Uvicorn, PyJWT
- **Persistence:** SQLAlchemy 2.0, Alembic, PostgreSQL via psycopg 3 (adapters and migrations)
- **LLM providers:** Ollama, Google Gemini (`google-genai`)
- **Frontend:** React 19, TypeScript, React Router, TanStack Query, Axios, Vite, Tailwind CSS
- **Quality:** pytest, Ruff, ESLint, markdownlint, pip-audit, npm audit (GitHub Actions)

---

## Repository structure

```text
app/
  api/            FastAPI routers (runtime, scenarios, management, health, version) and auth
  auth/           JWT and authorization services
  policy/         PolicyEngine and lifecycle authorization
  detection/      Detection rules, registry and engine
  services/       RuntimeService, risk, response, findings, audit, sessions, scenarios, ...
  runtime/        ExecutionAuthority, tool executor, capability registry, process sandbox
  repositories/   Repository interfaces, in-memory and SQL adapters, composition validation
  registry/       Tool and scenario registries
  providers/      LLM provider adapters (Ollama, Gemini)
  scenarios/      YAML scenario definitions
  telemetry/      Behavioural telemetry dispatcher
  models/         Domain and API models
alembic/          Database migrations (0001–0010)
frontend/         Enterprise Security Console (React + TypeScript + Vite)
tests/            pytest suites, including security invariant and regression suites
scripts/          dev-start.sh, dev_credentials.py, compile-requirements.sh
demo_workspace/   Confined workspace the default file tools operate on
docs/             ADRs, architecture, security, API, development and release documentation
```

---

## Installation and local development

Requirements: Python 3.13, Node.js 20+ and npm. Ollama is optional; it is needed only for
`PROMPT`-mode scenarios and the LLM-driven agent runtime.

```bash
git clone https://github.com/mathurshubh/enterprise-agent-security-platform.git
cd enterprise-agent-security-platform

python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # generated lock; see local-development.md

(cd frontend && npm install)
```

### Start the backend and console

```bash
scripts/dev-start.sh
```

The script runs preflight checks, generates an ephemeral JWT signing secret and a matching
least-privilege `ANALYST` token, starts the backend at `http://127.0.0.1:8000` (OpenAPI docs at
`/docs`) and the console at `http://localhost:3000`, and verifies the credential pair. The
token stays inside the Vite development proxy and never reaches the browser. `Ctrl+C` stops both
processes, and the credentials stop existing. `scripts/dev-start.sh --dry-run` runs the checks
only.

On a fresh start the platform contains only the bootstrap agent `agent-1` and two tools. Live
sessions, findings and audit events appear once requests reach the runtime endpoint, which
requires an `AGENT` token. Scenario runs from the console are sandboxed and do not populate live
state.

### Optional: local LLM

```bash
ollama pull llama3.2:3b
ollama serve
```

The provider is chosen with `DEFAULT_PROVIDER` (`ollama` or `gemini`). See
[docs/development/local-development.md](docs/development/local-development.md) for every
option, the manual two-terminal alternative and dependency-lock management.

---

## Running tests and quality checks

```bash
.venv/bin/python -m pytest                                   # full backend suite
.venv/bin/python -m pytest -m "security_invariant or security_regression"
.venv/bin/ruff check
(cd frontend && npm run lint && npm run build && npm run test:dev-proxy)
npm install && npm run lint:md                               # markdownlint, from the repo root
```

Results at commit `8bc5c74` (2026-11-14):

| Check | Result |
|---|---|
| Backend tests | **1,788 passed**, 11 skipped, 5 xfailed |
| Security-marked tests | 361 passed (`security_invariant`, `security_regression`) |
| Ruff | Clean |
| Frontend | `npm run lint`, `npm run build` passing; dev-proxy tests 26/26 |
| Markdownlint | Clean |

The test suite provisions its own signing key (`tests/conftest.py`). CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the lock check, Ruff, pytest,
frontend lint/build/tests, markdownlint, pip-audit and npm audit.

---

## Security architecture and threat model

- [Threat model](docs/security/threat-model.md)
- [System architecture](docs/architecture/system-architecture.md) and
  [data model](docs/architecture/data-model.md)
- [Tool model](docs/architecture/tool-model.md)
- [Architecture principles](docs/ai/ARCHITECTURE_PRINCIPLES.md)
- [AI security architecture review, Jan–Aug 2026](docs/security/ai-security-architecture-review-jan-aug-2026.md)
  and [September 2026](docs/security/ai-security-architecture-review-september-2026.md)
- [Scenario capability matrix](docs/security/scenario-capability-matrix.md)
- [Enterprise Security Console architecture](docs/architecture/enterprise-security-console/README.md)
- [CI/CD and DevSecOps](docs/development/ci-cd-devsecops.md)
- [Security policy](SECURITY.md)

The threat model covers 14 threat domains identified in the Jan–Aug 2026 review: indirect prompt
injection, tool abuse, MCP compromise and tool poisoning, agent identity and impersonation,
delegated authorization abuse, credential theft, AI supply-chain compromise, runtime escape,
memory/context poisoning, workflow manipulation, agent persistence, agent-to-agent abuse,
autonomous exploitation, and evaluation/sandbox escape. Not all of these have implemented
controls; the [roadmap](#roadmap) separates them.

### Core architectural invariants

- **Policy decides. Authorization limits. Runtime enforces.**
- **Telemetry records. Human approval escalates. Containment limits the blast radius.**
- The LLM proposes; it never decides.

---

## Architecture Decision Records

Decisions are recorded in [`docs/adr/`](docs/adr/), **ADR-000 through ADR-035**. Key records:

| ADR | Decision |
|---|---|
| [001](docs/adr/ADR-001-zero-trust-security-model.md) / [002](docs/adr/ADR-002-llm-untrusted-intent-parser.md) | Zero Trust model; LLM as untrusted intent parser |
| [004](docs/adr/ADR-004-deterministic-security-pipeline.md) / [006](docs/adr/ADR-006-resource-aware-authorization.md) | Deterministic pipeline; resource-aware authorization |
| [022](docs/adr/ADR-022-enterprise-security-console-evolution.md) | Enterprise Security Console information architecture |
| [023](docs/adr/ADR-023-execution-authorization-grants.md) / [031](docs/adr/ADR-031-execution-grant-approval-control-plane.md) | Execution grants; approval control plane |
| [024](docs/adr/ADR-024-agent-enforcement-state.md) / [025](docs/adr/ADR-025-management-plane-authorization.md) | Agent enforcement state; plane authorization |
| [030](docs/adr/ADR-030-durable-state-repository-architecture.md) | Durable state and repository architecture (status: Proposed, with amendments) |
| [032](docs/adr/ADR-032-runtime-tool-execution-isolation.md) | Runtime tool execution isolation |
| [033](docs/adr/ADR-033-tool-catalog-contract.md) / [034](docs/adr/ADR-034-audit-identity-contract.md) / [035](docs/adr/ADR-035-execution-evidence-and-capability-durability.md) | Tool catalog, audit identity, evidence durability contracts |

---

## Current implementation status

- **Latest published release:** [`v0.18.0`](docs/releases/v0.18.0.md) (tag commit `cab46d7`,
  October 2026). Git tags are the release authority. `v0.16` and `v0.17.x` were
  development-cycle labels, never releases.
- **`main` after v0.18.0 (unreleased):** the F-09 agent lifecycle work — the two-plane
  administrative/enforcement lifecycle, durable administrative state (migration `0010`), and the
  configurable repository backend with L.6 startup validation.
- **Architecture freeze:** the platform is deliberately frozen at this milestone. The remaining
  durability gap is enforced at startup rather than hidden.

---

## Known gaps and limitations

Stated plainly so the platform is not read as claiming more than it delivers:

- **Production persistence is in-memory.** The SQL adapters and migrations are complete and
  contract-tested, but a durable deployment is refused at startup until findings (and their
  `evidence_sequence` allocator) are durable. Security state therefore does not survive a
  restart in a runnable configuration today.
- **No approval API or UI.** `ApprovalContinuation` and its repositories exist, but no route
  lists or decides pending approvals, and the console's Approval Queue is a placeholder.
- **Console authentication** relies on the local development proxy. Production console
  authentication (an identity provider) is not implemented.
- **Not yet implemented:** the ADR-033 tool catalog API projection, ADR-034 §2.5 audit
  reconciliation detection, and persistence for execution receipts and capability profiles.
- **Process sandbox, not a kernel sandbox** (see the sandbox boundary note above).
- **Observed while capturing screenshots** (recorded, not yet fixed):
  - The console's 10-second API timeout can expire before a local `PROMPT`-mode scenario
    finishes with `llama3.2:3b`, and the run is reported as a timeout.
  - Some console placeholder text still refers to `v0.13.0` as the target release.
  - Several scenarios do not currently match their declared expectations (for example
    `AUTH-001` and `AUTH-003` expect `REQUIRE_APPROVAL` and observe `MONITOR`). `PROMPT`-mode
    results also vary with the local model's output.

---

## Roadmap

These items are **not implemented**. They follow the Jan–Aug 2026 baseline review and the
September 2026 review.

**Next architectural phase**

- Durable findings and `evidence_sequence`, which unblocks a valid fully durable topology.
- Approval queue API and operator workflow over `ApprovalContinuation`.
- Cryptographic agent workload credentials and delegated authorization chains
  (`Human → Delegation → Agent → Tool`).
- Tool / skill / MCP registry security: provenance, publisher identity, version integrity.
- Agent security observability (distributed tracing across reasoning and tool boundaries).
- Context-aware indirect prompt injection detection.
- Automated adversarial evaluation (red-teaming pipelines).

**Future / research**

- Memory and context security; workflow integrity verification across multi-step sequences.
- Multi-agent (A2A) governance and cascading-compromise prevention.
- AI supply-chain attestation; container/microVM or confidential-computing isolation.
- Multi-instance authority (`authority_generation`, ADR-030 AG.1) and advanced incident
  response.

The console's planned evolution is described in
[`docs/architecture/enterprise-security-console/11-implementation-roadmap.md`](docs/architecture/enterprise-security-console/11-implementation-roadmap.md).

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
