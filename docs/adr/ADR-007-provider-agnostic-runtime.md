# ADR-007: Adopt a Provider-agnostic Runtime

**Status:** Accepted

**Date:** 2026-07-04

**Authors:**
- Shubhankar Mathur

---

# Context

The Enterprise Agent Security Platform uses LLM providers to translate natural language requests into structured `ToolInvocation` objects.

Provider APIs differ in configuration, request formats, response formats, error behavior, and model availability. If provider-specific logic were embedded directly in the runtime security pipeline, adding or changing providers would risk modifying authorization, policy evaluation, detection, risk assessment, response, auditability, or tool execution behavior.

The platform requires provider flexibility without weakening deterministic security controls.

---

# Decision

The platform adopts a Provider-agnostic Architecture.

Provider-specific integrations are isolated behind the `ProviderAdapter` interface. Provider construction is centralized in `ProviderFactory`, which selects the configured provider during application initialization.

The Enterprise Agent depends on the provider abstraction, not a specific provider implementation.

Security decisions remain outside provider implementations. Providers may help produce a syntactically valid `ToolInvocation`, but they never decide whether a request is authorized, safe, risky, or executable.

---

# Rationale

This decision separates AI inference infrastructure from runtime security enforcement.

The provider abstraction allows the platform to:

- support multiple providers
- change providers through configuration
- keep deterministic security behavior consistent
- test provider integrations independently
- prevent provider-specific code from bypassing the security pipeline

`ProviderFactory` exists to keep provider selection in the application composition layer rather than scattering provider construction across runtime services.

---

# Alternatives Considered

## Provider-specific Runtime

Embed provider-specific clients directly inside runtime services.

### Rejected

This would couple provider behavior to security enforcement and make each provider change a potential security-sensitive runtime change.

## Agent-owned Provider Construction

Allow each Enterprise Agent to construct its own provider client.

### Rejected

This would duplicate configuration logic and make provider selection harder to audit.

## Provider-managed Security Decisions

Allow providers to evaluate authorization or safety before returning tool calls.

### Rejected

LLM providers are not trusted security boundaries. Security decisions must remain deterministic and platform-owned.

---

# Consequences

## Positive

- Provider-agnostic runtime behavior.
- Multiple providers can be supported without changing security controls.
- Clear separation between inference and governance.
- Provider selection is configuration-driven.
- Deterministic authorization, policy evaluation, detection, risk assessment, response, and auditability remain platform-owned.

## Negative

- Provider adapters must normalize provider-specific behavior.
- Structured output validation remains required.
- ProviderFactory becomes part of application composition that must be tested.

## Risks

- Poor adapter implementation could produce malformed `ToolInvocation` objects.
- Provider-specific capabilities may be unavailable through the common abstraction.
- Configuration errors may select the wrong provider.

---

# Security Considerations

Provider responses are treated as untrusted input.

Security invariants:

- Providers never make authorization decisions.
- Providers never execute tools.
- Providers never receive executable `BaseTool` instances.
- Provider output becomes a `ToolInvocation` that must pass deterministic validation and runtime security controls.
- The Tool Registry remains the only boundary for executable tool resolution.

This preserves Zero Trust behavior regardless of the selected provider.

---

# Architectural Principles Affected

- Principle 1 - Zero Trust by Default
- Principle 2 - The LLM is an Untrusted Intent Parser
- Principle 3 - Deterministic Security Decisions
- Principle 5 - Separation of Governance and Inference
- Principle 11 - Separation of Responsibilities

---

# Related Documents

- Architecture Principles
- System Architecture
- Threat Model
- ADR-001: Adopt a Zero Trust Security Model
- ADR-002: Treat the LLM as an Untrusted Intent Parser
- ADR-004: Adopt a Deterministic Security Pipeline
- ADR-005: Adopt a Centralized Tool Registry

---

# Notes

The current implementation includes multiple provider implementations behind `ProviderAdapter` and selects the configured provider through `ProviderFactory`.

Future providers should be added by implementing the provider abstraction, not by modifying deterministic security services.
