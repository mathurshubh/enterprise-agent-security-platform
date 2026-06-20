# ADR-004: Adopt a Deterministic Security Pipeline

**Status:** Accepted

**Date:** 2026-06-20

**Authors:**
- Shubhankar Mathur

---

# Context

Enterprise AI agents generate requests using probabilistic Large Language Models.

While LLMs are effective at interpreting user intent, they cannot provide deterministic security guarantees.

Executing tools directly from LLM output introduces significant risks, including:

- prompt injection
- indirect prompt injection
- tool abuse
- privilege escalation
- unauthorized resource access
- data exfiltration
- inconsistent authorization decisions

The platform requires a security architecture that guarantees every tool invocation is evaluated consistently before execution.

---

# Decision

The Enterprise Agent Security Platform adopts a deterministic security pipeline for every tool invocation.

Every `ToolInvocation` follows the same sequence of security controls before execution.

The current pipeline is:

```text
Authentication
        ↓
Authorization
        ↓
Policy Evaluation
        ↓
Session Validation
        ↓
Detection
        ↓
Risk Assessment
        ↓
Response Decision
        ↓
Tool Execution
```

No component may bypass or reorder the pipeline.

Each stage performs one deterministic security function.

Tool execution occurs only after all previous stages have successfully completed.

---

# Rationale

The deterministic security pipeline separates AI inference from security enforcement.

This provides several architectural advantages.

## Consistent Security Behavior

Every request is evaluated using the same sequence of security controls regardless of:

- LLM provider
- Enterprise Agent
- Tool
- User

---

## Defense in Depth

Security is implemented through multiple independent services.

Failure of one layer does not eliminate the protections provided by the remaining layers.

---

## Separation of Responsibilities

Each security component owns one deterministic responsibility.

This reduces coupling and simplifies testing.

---

## Extensibility

Additional security services can be inserted into the pipeline without modifying Enterprise Agents or tool implementations.

---

## Auditability

Each stage produces deterministic security decisions that can be independently audited and explained.

---

# Alternatives Considered

## Direct Tool Execution

Execute tools immediately after receiving an LLM response.

### Rejected

This bypasses deterministic security controls and significantly increases the attack surface.

---

## Agent-Level Security Enforcement

Allow Enterprise Agents to decide whether execution should continue.

### Rejected

This couples AI inference with security enforcement and violates the platform's Zero Trust principles.

---

## Tool-Level Security

Require every tool to implement its own authorization and security checks.

### Rejected

This duplicates security logic, complicates maintenance, and makes consistent enforcement difficult.

---

# Consequences

## Positive

- Predictable security behavior.
- Consistent enforcement across all tools.
- Easier reasoning about security.
- Simplified testing.
- Provider-independent governance.
- Supports future security services.

## Negative

- Additional request-processing latency.
- Increased architectural complexity.
- Multiple services participate in request execution.

## Risks

- Poorly defined service boundaries may increase coupling.
- Pipeline growth may impact performance if not monitored.

---

# Security Considerations

Every ToolInvocation is treated as untrusted until the complete pipeline has successfully executed.

Security decisions remain deterministic throughout the pipeline.

No component may execute tools independently.

The pipeline also provides multiple opportunities to detect:

- prompt injection
- policy violations
- excessive privilege requests
- anomalous behavior
- suspicious tool usage

before execution occurs.

---

# Architectural Principles Affected

- Principle 1 – Zero Trust by Default
- Principle 3 – Deterministic Security Decisions
- Principle 7 – Least Privilege
- Principle 8 – Defense in Depth
- Principle 10 – Security Before Tool Execution
- Principle 16 – Security Through Composition

---

# Related Documents

- Architecture Principles
- System Architecture
- Threat Model
- ADR-001: Adopt a Zero Trust Security Model
- ADR-002: Treat the LLM as an Untrusted Intent Parser
- ADR-003: Establish the Runtime Service as the Security Orchestrator

---

# Notes

The deterministic security pipeline is one of the fundamental architectural invariants of the Enterprise Agent Security Platform.

Future releases may introduce additional deterministic security stages, but the principle that every ToolInvocation passes through the complete pipeline before execution must remain unchanged.