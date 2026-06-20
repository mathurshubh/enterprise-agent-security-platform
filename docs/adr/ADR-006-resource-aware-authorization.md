# ADR-006: Adopt Resource-aware Authorization

**Status:** Accepted

**Date:** 2026-06-20

**Authors:**
- Shubhankar Mathur

---

# Context

Traditional Role-Based Access Control (RBAC) determines whether an identity may perform a particular action.

While this is sufficient for many enterprise applications, AI agents frequently operate on specific enterprise resources such as:

- files
- directories
- repositories
- databases
- cloud resources
- APIs

Authorizing a tool alone is insufficient.

For example:

A user may be authorized to invoke `FileReadTool` but should not necessarily be permitted to read every file on the system.

The platform therefore requires authorization decisions that consider both the requested tool and the target resource.

---

# Decision

The Enterprise Agent Security Platform adopts resource-aware authorization.

Authorization decisions evaluate both:

- the requested operation
- the target resource

Tool authorization alone is never considered sufficient.

Every ToolInvocation is evaluated against resource-specific authorization policies before execution.

The Authorization Service remains deterministic and independent of LLM reasoning.

---

# Rationale

Resource-aware authorization provides finer-grained security controls than traditional RBAC.

## Principle of Least Privilege

Permissions are granted for specific resources rather than broad tool access.

This reduces unnecessary privileges.

---

## Improved Enterprise Security

Enterprise resources frequently have different sensitivity levels.

Authorization decisions should account for the specific resource being accessed rather than assuming identical protection requirements.

---

## Reduced Blast Radius

If an Enterprise Agent is compromised, resource-aware authorization limits the scope of accessible resources.

---

## Future Policy Support

Resource-aware authorization enables future policy models including:

- path-based authorization
- repository-specific authorization
- tenant isolation
- cloud resource authorization
- data classification policies

without changing the Runtime architecture.

---

# Alternatives Considered

## Tool-level Authorization Only

Authorize only the requested tool.

### Rejected

Tool authorization alone cannot determine whether access to a particular resource should be permitted.

This grants excessive privileges.

---

## Role-Based Access Control Only

Use RBAC as the sole authorization mechanism.

### Rejected

RBAC identifies who may perform an action but does not evaluate the target resource.

Enterprise AI agents require finer-grained authorization.

---

## Delegate Resource Decisions to Tools

Allow individual tools to determine whether a resource may be accessed.

### Rejected

This duplicates authorization logic and weakens centralized governance.

Authorization remains the responsibility of the Authorization Service.

---

# Consequences

## Positive

- Supports least privilege.
- Reduces over-privileged tool execution.
- Enables fine-grained authorization.
- Simplifies future policy evolution.
- Improves enterprise governance.

## Negative

- Authorization decisions become more complex.
- Policies require additional resource metadata.
- Larger policy datasets may be required.

## Risks

- Incorrect resource metadata may produce inaccurate authorization decisions.
- Policy complexity may increase as additional resource types are introduced.

---

# Security Considerations

Authorization evaluates both the requested operation and the target resource.

Enterprise Agents never determine whether access should be granted.

LLMs never participate in authorization decisions.

Resource-aware authorization also improves protection against:

- prompt injection
- privilege escalation
- data exfiltration
- unauthorized resource access

by ensuring every requested resource is evaluated independently.

---

# Architectural Principles Affected

- Principle 1 – Zero Trust by Default
- Principle 3 – Deterministic Security Decisions
- Principle 7 – Least Privilege
- Principle 10 – Security Before Tool Execution
- Principle 11 – Separation of Responsibilities

---

# Related Documents

- Architecture Principles
- System Architecture
- Threat Model
- ADR-003: Establish the Runtime Service as the Security Orchestrator
- ADR-004: Adopt a Deterministic Security Pipeline
- ADR-005: Adopt a Tool Registry for Controlled Tool Execution

---

# Notes

Resource-aware authorization extends traditional RBAC rather than replacing it.

RBAC determines whether an identity may invoke a capability.

Resource-aware authorization determines whether that capability may operate on a specific resource.

Both authorization layers are required to satisfy the platform's Zero Trust security model.