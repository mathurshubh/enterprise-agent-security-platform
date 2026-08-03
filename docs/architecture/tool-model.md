# Tool Model & Consolidated Tool Registry Specification

## Objective

Define the single authoritative ToolRegistry, passive ToolDescriptor, and DefaultToolExecutor governing enterprise tools in the platform runtime.

---

## Motivation

Tools represent one of the primary attack surfaces within agentic AI systems.

To support authorization, risk assessment, threat detection, auditing, and human-in-the-loop approval workflows, each tool must expose structured metadata and be managed through a clean separation of concerns:

- `ToolRegistry` = Lookup & metadata discovery
- `ToolDescriptor` = Passive metadata & registration state container
- `DefaultToolExecutor` = Tool handle instantiation & execution
- `RuntimeService` = Operational orchestration

---

## 1. Consolidated Tool Registry (`ToolRegistry`)

The `ToolRegistry` is the single source of truth for all registered tool descriptors and factories.

### Responsibilities
- **Registration**: Register `BaseTool` instances or lazy factories with strict metadata validation (`tool_id`, `name`, `version`).
- **Validation**: Enforce metadata non-emptiness and reject duplicate tool identifiers (`DuplicateToolRegistrationError`, `ToolMetadataValidationError`).
- **Resolution**: `resolve(tool_id, version)` returns a passive `ToolDescriptor`, separating lookup/resolution from execution handle instantiation.
- **Version Evolution Preparation**: Internal storage `_descriptors[tool_id][version]` and isolated `_match_version()` helper prepare the registry for future multi-version loading.
- **Discovery**: Expose defensive copies of tool metadata (`discover_tools()`) to the management plane.
- **Immutability**: All listing methods return immutable tuples (`tuple[ToolDescriptor, ...]`, `tuple[BaseTool, ...]`).

### Implementation Notes
*   **Source File:** Located at [`app/registry/tool_registry.py`](../../app/registry/tool_registry.py).
*   **Concurrency Control:** All state reads and mutations are guarded by a reentrant lock (`threading.RLock`) to ensure thread safety.

---

## 2. Passive ToolDescriptor & ToolMetadata Architecture

`ToolDescriptor` is a pure passive data container holding registration information:

```text
ToolDescriptor (Passive Runtime Registration Object)
├── metadata: ToolMetadata (Descriptive Identity & Governance)
│   ├── ToolIdentity (tool_id, name, version, description)
│   ├── ToolGovernance (risk_level, required_permissions, owner, approval_required)
│   ├── ToolCapability (category, reads_files, writes_files, network_access, internet_access, database_access, shell_access)
│   └── ToolOperational (enabled, timeout_seconds, supports_streaming)
├── instance: BaseTool | None (Pre-instantiated Tool Handle)
├── factory: Callable | None (Lazy Instantiation Factory)
├── tool_class: type[BaseTool] | None (Implementation Class Reference)
├── enabled: bool
└── registration_state: "REGISTERED" | "UNREGISTERED" | "DEPRECATED"
```

### Implementation Notes
*   **Source File:** Located at [`app/models/tool_descriptor.py`](../../app/models/tool_descriptor.py).

---

## 3. Dedicated Tool Executor (`DefaultToolExecutor`)

`DefaultToolExecutor` is responsible for tool instantiation, execution, and exception translation:

- Instantiates `BaseTool` handles from passive `ToolDescriptor` objects.
- Executes tools with validated parameter mappings.
- Translates unhandled runtime execution errors into `ToolExecutionError`.
- Keeps tool lookup/resolution separate from executable tool invocation.

### Implementation Notes
*   **Source File:** Located at [`app/runtime/tool_executor.py`](../../app/runtime/tool_executor.py).

---

## 4. Runtime Execution Context (`RuntimeContext`)

Tool executions are accompanied by an immutable context representing execution identity only:

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Unique session identifier |
| `request_id` | `str` | Unique request trace identifier |
| `user_id` | `str` | Initiating user identifier |
| `principal` | `str` | Authenticated principal |
| `authenticated_agent` | `str` | Authenticated agent identifier |
| `execution_metadata` | `dict[str, Any]` | Read-only execution metadata |

### Implementation Notes
*   **Source File:** Located at [`app/models/runtime_context.py`](../../app/models/runtime_context.py).

---

## 5. Runtime Lifecycle & Flow Architecture

```text
Bootstrap Registration (runtime_bootstrap.py -> ToolRegistry.register / register_factory -> ToolDescriptor)

↓

Runtime Security Pipeline (RuntimeService.execute)

↓

Authorization → Policy Evaluation → Detection → Risk Assessment → Response → Audit

↓

If ALLOW: AgentRuntimeService resolves ToolRegistry descriptor

↓

Execution (DefaultToolExecutor.execute_descriptor(descriptor, parameters) -> BaseTool.execute)
```

---

## 6. Runtime Contracts

Standardized protocol interfaces define clean decoupling points:

- `ToolRegistryProtocol`: Protocol governing tool registry operations.
- `ToolFactoryProtocol`: Protocol for creating/resolving tool instances.
- `ToolExecutorProtocol`: Protocol for executing tools with validated parameters and runtime context.

### Implementation Notes
*   **Source File:** Located at [`app/runtime/contracts.py`](../../app/runtime/contracts.py).
