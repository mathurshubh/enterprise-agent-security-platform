# AGENTS.md

## Project Overview

This repository contains an **Enterprise Agent Security Platform** focused on securing autonomous AI agents operating in enterprise environments.

The platform combines **runtime security controls** with selected **AI governance capabilities**.

### Primary Focus

- Agent Runtime Security
- Agent Identity and Traceability
- Authorization and Least Privilege
- Behavioral Detection
- Risk-Based Decisioning
- Automated Response

### Secondary Focus

- Model Registry
- AI Asset Inventory
- Governance Metadata
- Model Provenance
- Audit Evidence

Do **not** pivot this repository into a pure governance or compliance platform.

---

# Development Principles

- Prefer small, incremental changes.
- Preserve existing architecture unless explicitly instructed otherwise.
- Do not introduce new frameworks or dependencies without approval.
- Do not modify unrelated files.
- Ask clarifying questions if requirements are ambiguous.

---

# Security Principles

Assume all external inputs are untrusted.

Treat the following as potentially malicious:

- User prompts
- Retrieved content
- Tool outputs
- Agent memory
- External APIs
- Model responses

When implementing new functionality, consider:

- Prompt injection
- Tool abuse
- Authorization bypass
- Data leakage
- Excessive agency
- Denial-of-wallet scenarios
- Cross-agent trust issues

Security decisions should be deterministic.

Avoid introducing LLM-based decision-making into core security controls unless explicitly requested.

---

# Architecture Priorities

Current implementation priorities:

1. Detection Engine
2. Risk Engine
3. Approval Workflow
4. Response Actions

Future enhancements:

- Control Validation
- Attack Simulation
- Model Registry expansion
- AI Asset Inventory expansion

---

# Coding Standards

- Python 3.13+
- Use Pydantic models.
- Prefer typed fields.
- Use enums for constrained values.
- Use `default_factory` for timestamps.
- Follow existing project conventions.

Prefer consistency with the existing codebase over introducing new patterns.

---

# Service Conventions

Follow patterns established by:

- AgentService
- ToolService
- SessionService
- ModelService

Services should:

- Use domain-specific exceptions.
- Return domain objects.
- Remain focused and cohesive.
- Avoid unnecessary abstraction.

Use `RLock` for stateful in-memory services where appropriate.

---

# Testing Requirements

Every new feature must include pytest coverage.

Test:

- Success paths
- Failure paths
- Boundary conditions when relevant

Follow existing testing conventions:

- Factory helper functions
- Clear test naming
- Small, focused tests

Always execute tests using:

    .venv/bin/python -m pytest

Do not assume pytest is globally installed.

Do not use:

    python
    python3
    /usr/bin/python3

for test execution.

---

# Change Workflow

When implementing changes:

1. Review relevant files first.
2. Follow established conventions.
3. Implement incrementally.
4. Run tests.
5. Fix failures.
6. Summarize modifications.
7. Wait for approval before continuing with unrelated work.

Avoid large, multi-feature commits.

---

# Documentation Guidance

Keep documentation aligned with implementation status.

Do not mark features as completed unless they are implemented and tested.

README updates should accurately reflect:

- Current capabilities
- Completed milestones
- Planned milestones

Avoid overstating functionality.

---

# Repository Philosophy

This repository is intended to demonstrate:

- AI Security Engineering
- Agent Security Engineering
- Security Architecture Thinking
- Enterprise-Aware Design
- Production-Oriented Development Practices

Implementation depth is preferred over architectural breadth.

A few well-implemented security capabilities are more valuable than many partially implemented features.