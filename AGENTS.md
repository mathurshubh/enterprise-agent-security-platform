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
- Preserve backwards compatibility unless explicitly instructed otherwise.
- Prefer minimal, focused pull requests.
- Avoid large-scale formatting or repository-wide refactoring unless requested.
- Reuse existing abstractions before introducing new ones.
- Keep composition/bootstrap logic separate from domain logic where practical.

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

## LLM Trust Boundary

Treat every LLM as an **untrusted intent parser**.

The LLM is responsible only for converting natural language into structured
`ToolInvocation` objects.

The following security decisions must remain deterministic and outside the LLM:

- Authorization
- Policy Evaluation
- Detection
- Risk Assessment
- Approval Decisions
- Response Actions

Never move security-critical decisions into prompts unless explicitly requested.

---

# Architecture Principles

Prefer architecture consistency over introducing new abstractions.

Current architectural principles:

- RuntimeService is the single deterministic runtime security pipeline.
- AgentRuntimeService is responsible only for:
  - LLM invocation
  - ToolInvocation generation
  - Executing approved tools
- Avoid duplicating runtime orchestration.
- Prefer dependency injection over constructing dependencies inside services.
- Prefer Protocol interfaces when appropriate.
- Keep services cohesive and focused on a single responsibility.
- Preserve trust boundaries between AI components and deterministic security components.

Future architectural enhancements should build upon these principles rather than replacing them.

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

Before considering work complete:

- Verify trust boundaries remain intact.
- Verify security decisions remain deterministic.
- Update tests alongside implementation.
- Execute Ruff (if available).
- Execute:

    .venv/bin/python -m pytest

- Ensure documentation reflects implementation.
- Summarize architectural impact before proposing the change for merge.

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

---

# Architecture Review Checklist

Before completing a change, verify:

## Architecture

- Responsibilities remain well separated.
- No duplicated orchestration has been introduced.
- Existing architecture has not been unnecessarily redesigned.
- New abstractions provide measurable value.

## Security

- Authorization remains deterministic.
- Fail-closed behavior is preserved.
- No security decisions have moved into the LLM.
- Trust boundaries remain intact.

## Engineering

- Tests have been updated.
- Existing tests pass.
- Scope remains focused.
- Unrelated files have not been modified.

## Documentation

- Documentation matches implementation.
- Roadmap items are not marked complete until implemented and tested.

## Additional AI Documentation

Repository-specific implementation guidance is located in:

- docs/ai/README.md
- docs/ai/PROJECT_CONTEXT.md
- docs/ai/ARCHITECTURE_PRINCIPLES.md
- docs/ai/IMPLEMENTATION_WORKFLOW.md
- docs/ai/DEVELOPMENT_CHECKLIST.md
- docs/ai/PULL_REQUEST_GUIDELINES.md

Read these documents before making architectural or implementation changes.