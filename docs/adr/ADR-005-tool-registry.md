# ADR-005: Adopt a Centralized Tool Registry

**Status:** Accepted

**Date:** 2026-06-20

**Authors:**
- Shubhankar Mathur

---

# Context

Enterprise Agents interact with enterprise systems by requesting tool execution.

Because `ToolInvocation` objects originate from LLM output, they may reference unknown tools, hallucinated tool names, manipulated parameters, or functionality that should not exist within the governed runtime.

Without a centralized mechanism for registering and resolving executable tools, the platform would risk:

- direct tool execution from untrusted LLM output
- inconsistent tool metadata
- authorization bypass
- provider-specific tool definitions
- fragmented auditability
- unclear ownership of executable capabilities

The v0.9 implementation introduces a governed tool ecosystem with `BaseTool`, immutable `ToolMetadata`, Tool Discovery, Tool Inventory, and centralized runtime resolution.

---

# Decision

The Enterprise Agent Security Platform uses a centralized Tool Registry as the authoritative runtime registry for executable tools.

Every executable tool must:

- implement the `BaseTool` abstraction
- expose immutable `ToolMetadata`
- be explicitly registered before execution
- be resolved through the Tool Registry at runtime

The Tool Registry owns executable `BaseTool` instances. Discovery and inventory surfaces expose only deep-copied `ToolMetadata`, not executable tool objects.

The runtime layer resolves a requested tool through the Tool Registry only after deterministic authorization, policy evaluation, detection, risk assessment, and response selection allow the action.

The Tool Registry does not make authorization decisions. It controls which executable tools exist and provides the boundary between governed metadata and executable capability.

---

# Rationale

A centralized Tool Registry separates AI-generated intent from executable platform capability.

This decision provides:

- a single source of truth for registered executable tools
- stable tool identity for authorization, audit, detection, and inventory
- provider-agnostic tool resolution
- consistent `ToolMetadata` for governance decisions
- prevention of direct execution of hallucinated or unregistered tools
- a clear boundary between metadata discovery and `BaseTool` execution

By keeping executable tool instances behind the Tool Registry, the runtime can expose governance and inventory data without exposing execution capability.

---

# Alternatives Considered

## Direct Tool Invocation

Allow Enterprise Agents or providers to cause direct tool execution by name outside the Tool Registry.

### Rejected

This would couple LLM output to executable capability and weaken Zero Trust enforcement.

## Provider-specific Tool Definitions

Allow each provider to define and own available tools.

### Rejected

Tool governance must be platform-owned. Provider-specific tool definitions would undermine Provider-agnostic Architecture and make security behavior inconsistent across providers.

## Tool Metadata Without Registry-controlled Resolution

Maintain tool metadata but allow runtime components to instantiate or execute tools independently.

### Rejected

Metadata alone does not prevent registry bypass. Executable tools must be resolved through one controlled runtime boundary.

---

# Consequences

## Positive

- Centralized governance of executable capabilities.
- Consistent Tool Metadata.
- Clear separation between discovery, inventory, and execution.
- Better auditability and traceability.
- Provider-agnostic tool execution.
- Reduced risk of executing hallucinated tools.

## Negative

- Every new tool requires explicit registration.
- Registry availability is required for execution.
- Tool lifecycle governance becomes an operational responsibility.

## Risks

- Stale or incorrect Tool Metadata can weaken downstream governance.
- Registry compromise could affect executable capability resolution.
- Larger tool ecosystems will require stronger lifecycle controls.

---

# Security Considerations

The Tool Registry is a critical Zero Trust boundary.

Security invariants:

- LLMs never receive executable `BaseTool` instances.
- Enterprise Agents never execute tools directly.
- `ToolInvocation` values are treated as untrusted until validated.
- Tool Metadata is trusted only when obtained from the Tool Registry.
- Executable `BaseTool` instances are resolved only through the Tool Registry.
- Authorization remains deterministic and separate from registry lookup.

This reduces the risk of prompt injection, hallucinated tool execution, registry bypass, metadata spoofing, and unauthorized capability use.

---

# Architectural Principles Affected

- Principle 1 - Zero Trust by Default
- Principle 3 - Deterministic Security Decisions
- Principle 5 - Separation of Governance and Inference
- Principle 7 - Least Privilege
- Principle 10 - Security Before Tool Execution
- Principle 11 - Separation of Responsibilities

---

# Related Documents

- Architecture Principles
- System Architecture
- Data Model
- Threat Model
- ADR-002: Treat the LLM as an Untrusted Intent Parser
- ADR-003: Establish the Runtime Layer as the Security Orchestrator
- ADR-004: Adopt a Deterministic Security Pipeline

---

# Notes

This ADR documents the v0.9 implementation decision to make the Tool Registry the runtime boundary for executable tools.

Future AI asset governance capabilities should extend this pattern without weakening the separation between metadata, discovery, inventory, authorization, and execution.
