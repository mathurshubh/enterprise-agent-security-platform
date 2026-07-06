# AGENTS.md

This document defines the engineering workflow, architectural constraints, and implementation standards that all human and AI contributors must follow.

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
- Ask clarifying questions before implementation whenever requirements or architectural intent are ambiguous.
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

For service responsibilities, runtime orchestration, and trust boundaries, refer to the authoritative [docs/ai/ARCHITECTURE_PRINCIPLES.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/ai/ARCHITECTURE_PRINCIPLES.md).

Current architectural principles:

- Prefer dependency injection over constructing dependencies inside services.
- Prefer Protocol interfaces when appropriate.
- Keep services cohesive and focused on a single responsibility.
- Preserve trust boundaries between AI components and deterministic security components.

Future architectural enhancements should build upon these principles rather than replacing them.


---

# Repository Exploration

Before introducing new functionality:

- Inspect existing implementations.
- Review related unit tests.
- Search for similar patterns.
- Reuse existing abstractions where practical.
- Understand current integration points before proposing changes.

Avoid introducing duplicate implementations when an existing extension point already exists.

---

# Coding Standards

- Python 3.13+
- Use Pydantic models.
- Prefer typed fields.
- Use enums for constrained values.
- Use `default_factory` for timestamps.
- Follow existing project conventions.

Prefer consistency with the existing codebase over introducing new patterns.

Do not create temporary repository artifacts such as:

- implementation_plan.md
- task.md
- walkthrough.md
- notes.md

unless explicitly requested.

Planning, progress tracking, and summaries should normally be presented in chat rather than committed to the repository.

---

## Refactoring

Refactoring should:

- Improve readability.
- Preserve behavior.
- Preserve public interfaces.
- Preserve trust boundaries.
- Remain separate from new functionality whenever practical.

Avoid opportunistic refactoring unrelated to the requested task.

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

## Repository State

Before beginning any implementation:

1. Execute `git status`.
2. Summarize all modified and untracked files.
3. If the working tree is not clean, stop and ask whether to:
   - commit,
   - stash,
   - or discard the existing changes.
4. Do not begin implementation until the repository state has been confirmed.

Never mix unrelated work into the current task.

When implementing changes:

1. Review relevant files.
2. Search for similar implementations.
3. Review associated tests.
4. Identify every integration point.
5. Present an implementation plan in chat.
6. Wait for explicit approval before modifying repository files.
7. Implement incrementally.
8. Run tests.
9. Fix failures.
10. Summarize modifications.
11. Wait for approval before continuing with unrelated work.

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

# Pull Request Expectations

Before considering implementation complete, provide:

## Summary

- What changed
- Why it changed

## Files Modified

List every modified and newly created file.

## Architectural Impact

Explain:

- Responsibilities affected
- Trust boundary impact
- Security implications
- Backwards compatibility

## Validation

Report:

- Ruff status
- Pytest status
- Test count (if available)

Do not generate markdown reports unless explicitly requested.

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

Before completing a change, verify all checklist criteria in the authoritative [docs/ai/REVIEW_CHECKLIST.md](file:///Users/shubhankarmathur/projects/enterprise-agent-security-platform/docs/ai/REVIEW_CHECKLIST.md) are met.


## Additional AI Documentation

Repository-specific implementation guidance is located in:

- docs/ai/PROJECT_CONTEXT.md
- docs/ai/ARCHITECTURE_PRINCIPLES.md
- docs/ai/IMPLEMENTATION_WORKFLOW.md

Refer to docs/ai/README.md for the index and recommended reading order.