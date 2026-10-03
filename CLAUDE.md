# CLAUDE.md

## Project

Enterprise Agent Security Platform.

This repository implements a production-style Zero Trust security and governance
platform for enterprise AI agents.

The platform is NOT itself an AI agent.

## Source of Truth

Before making architectural or security-sensitive changes, inspect:

- `AGENTS.md`
- `README.md`
- `docs/architecture/`
- `docs/security/`
- relevant ADRs
- relevant tests

Do not infer repository behavior from memory when it can be established from
the source.

When documentation conflicts with implementation, investigate and report the
discrepancy rather than silently choosing one.

## Core Security Rule

The LLM is an untrusted intent parser.

LLM output may produce structured intent such as `ToolInvocation`.

The LLM must never make:

- authorization decisions
- policy decisions
- risk decisions
- detection decisions
- response decisions
- execution decisions

All security decisions remain deterministic.

## Architecture

Preserve:

- Zero Trust
- least privilege
- deterministic authorization
- explicit trust boundaries
- fail-closed behavior
- immutable/frozen authority
- auditability
- evidence integrity
- monotonic execution identity

Once `(tool_id, tool_version)` has been resolved and authorized,
downstream code must not re-resolve, substitute, downgrade, or upgrade it.

## Approval Authority

Keep these concepts separate:

### ApprovalContinuation

Durable, persisted, human-approved authority.

Not directly executable.

### RuntimeExecutionGrant

Ephemeral, cryptographically signed execution authority.

The continuation must be claimed before a runtime grant is minted.

Never reverse this ordering.

## Database Discipline

Never edit an already-applied Alembic migration to represent a new schema.

Add a new migration.

Never use drop/recreate for a potentially populated table merely because an
earlier migration used that pattern for an empty table.

Security-sensitive historical data must never be fabricated through inference
or defaulting.

## Change Discipline

Before implementing a significant change:

1. Inspect current behavior.
2. Identify affected trust boundaries.
3. Identify security invariants.
4. Stress-test the proposal.
5. Review relevant ADRs.
6. Implement the smallest coherent change.
7. Add regression tests.
8. Run the full validation suite.
9. Update documentation.
10. Review the final diff for unintended semantic changes.

Do not mix unrelated refactors into security-sensitive changes.

If an unrelated defect is discovered, record it separately.

## Testing

Security tests are architectural contracts.

Do not weaken, delete, or bypass security tests merely to make an implementation
pass.

For security-sensitive changes consider:

- replay
- race conditions
- stale authority
- privilege escalation
- identity substitution
- capability mismatch
- persistence round-trip
- restart behavior
- fail-closed behavior
- migration upgrade/downgrade
- schema drift

## Architecture Review

For significant changes evaluate:

1. Does this invalidate a current architectural decision?
2. Does this introduce a threat requiring a threat-model update?
3. Is this current implementation or future backlog?
4. Does this justify a new enterprise platform capability?

Stress-test proposals before accepting them.

## Commands

Before changing command conventions, inspect the repository and CI configuration.

Use the project's existing:

- test commands
- Ruff configuration
- markdownlint configuration
- Alembic migration workflow
- frontend validation
- CI checks

Do not invent replacement commands when repository-defined commands exist.

## Git

Keep changes incremental.

Do not rewrite history or modify existing migrations.

Before declaring a change complete:

- inspect `git diff`
- inspect `git status`
- run relevant tests
- run the full suite for security-sensitive changes
- verify documentation
- verify no unrelated files changed

Do not commit or push unless explicitly requested.