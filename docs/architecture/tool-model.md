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

The `ToolRegistry` ([`app/registry/tool_registry.py`](../../app/registry/tool_registry.py)) is the single source of truth for all registered tool descriptors and factories.

### Responsibilities
- **Registration**: Register `BaseTool` instances or lazy factories with strict metadata validation (`tool_id`, `name`, `version`).
- **Validation**: Enforce metadata non-emptiness and reject duplicate tool identifiers (`DuplicateToolRegistrationError`, `ToolMetadataValidationError`).
- **Resolution**: `resolve(tool_id, version)` returns a passive `ToolDescriptor`, separating lookup/resolution from execution handle instantiation.
- **Version Evolution Preparation**: Internal storage `_descriptors[tool_id][version]` and isolated `_match_version()` helper prepare the registry for future multi-version loading.
- **Discovery**: Expose defensive copies of tool metadata (`discover_tools()`) to the management plane.
- **Immutability**: All listing methods return immutable tuples (`tuple[ToolDescriptor, ...]`, `tuple[BaseTool, ...]`).
- **Thread Safety**: All state reads and mutations are guarded by `threading.RLock`.

---

## 2. Passive ToolDescriptor & ToolMetadata Architecture

`ToolDescriptor` ([`app/models/tool_descriptor.py`](../../app/models/tool_descriptor.py)) is a pure passive data container holding registration information:

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

---

## 3. Dedicated Tool Executor (`DefaultToolExecutor`)

`DefaultToolExecutor` ([`app/runtime/tool_executor.py`](../../app/runtime/tool_executor.py)) is responsible for tool instantiation, execution, and exception translation:

- Instantiates `BaseTool` handles from passive `ToolDescriptor` objects.
- Executes tools with validated parameters and `RuntimeContext`.
- Translates unhandled runtime execution errors into `ToolExecutionError`.
- Serves as the extensible insertion point for future PRs #71–#75 (telemetry, event storage, detection, risk, enforcement).

---

## 4. Runtime Execution Context (`RuntimeContext`)

Tool executions are accompanied by an immutable `RuntimeContext` ([`app/models/runtime_context.py`](../../app/models/runtime_context.py)) representing execution identity only:

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Unique session identifier |
| `request_id` | `str` | Unique request trace identifier |
| `user_id` | `str` | Initiating user identifier |
| `principal` | `str` | Authenticated principal |
| `authenticated_agent` | `str` | Authenticated agent identifier |
| `execution_metadata` | `dict[str, Any]` | Read-only execution metadata |

---

## 5. Runtime Lifecycle & Flow Architecture

```text
Tool Registration (ToolRegistry.register / register_factory -> ToolDescriptor)

↓

Authorization Check (AuthorizationService.authorize)

↓

Runtime Resolution (ToolRegistry.resolve(tool_id, version) -> ToolDescriptor)

↓

Execution (ToolExecutor.execute_descriptor(descriptor, parameters, context) -> BaseTool.execute)

↓

Audit Event Logged & Context Destroyed
```

---

## 6. Runtime Contracts (`app/runtime/contracts.py`)

Standardized protocol interfaces define clean decoupling points:

- `ToolRegistryProtocol`: Protocol governing tool registry operations.
- `ToolFactoryProtocol`: Protocol for creating/resolving tool instances.
- `ToolExecutorProtocol`: Protocol for executing tools with validated parameters and runtime context.