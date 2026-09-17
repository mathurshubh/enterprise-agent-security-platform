<!--
Title: use Conventional Commits, for example
  feat(runtime): bind authorization decisions to executed operations
  fix(config): fail closed when the JWT signing key is not provisioned

Delete optional sections that do not apply. Keep every claim factual: do not
describe anything as implemented, fixed or secure unless it is tested.
-->

## Summary

<!--
What this PR changes and why, in one to three short paragraphs.
Name what it builds on or resolves, for example:
"Resolves H-5 from the post-v0.16 review", "Implements ADR-015",
"Hardens the Dynamic Risk Assessment introduced in PR #85".
-->

## Changes

<!--
Group changes under ### headings for the areas that apply, for example:
Backend, Runtime, Authentication, API, Frontend, Tests, CI/CD, Dependencies.
Name concrete classes, endpoints and behaviours rather than restating the title.
-->

## Files Changed

<!--
Required for implementation PRs (AGENTS.md); optional for small documentation PRs.
Group as Production / Tests / Docs and mark new files, for example:
- `app/runtime/execution_authority.py` (new)
-->

## Security / Architecture Impact

<!-- Required. State the effect explicitly, including when the answer is "no change". -->

- **Trust boundaries:** <!-- introduced, changed, or unchanged -->
- **LLM trust boundary:** <!-- confirm the LLM remains an untrusted intent parser and no security decision moved into a prompt or model output -->
- **Security decisions:** <!-- confirm authorization, policy, detection, risk and response remain deterministic and server-side -->
- **Responsibilities affected:** <!-- services or components whose responsibilities changed -->
- **Backwards compatibility:** <!-- API, contract or configuration changes and how existing callers are affected -->

## Documentation

<!-- List updated docs, ADRs and the threat model, or state "No documentation changes". -->

## Validation

<!-- Report commands actually run and their real results. Remove lines that do not apply. -->

- `.venv/bin/python -m pytest` — <!-- e.g. 506 passed, 16 xfailed -->
- `.venv/bin/python -m pytest tests/security -q -rxX` — <!-- note any invariant promoted from xfail -->
- `.venv/bin/ruff check` — <!-- clean -->
- `npm run lint --prefix frontend` — <!-- pass -->
- `npm run build --prefix frontend` — <!-- pass -->
- `npm run lint:md` — <!-- clean -->
- `git diff --check` — <!-- clean -->

## Scope

<!-- State what this PR is limited to, then list what it deliberately does not change. -->

This PR is limited to <!-- ... -->.

No changes to:

<!--
- authorization or policy evaluation
- detection, risk or response
- tool execution
-->

## Dependency

<!-- Optional. Builds on PR #... -->

## Follow-up

<!-- Optional. Known follow-up work, deferred findings or the next milestone. -->

## Checklist

- [ ] Tests cover success paths, failure paths and relevant boundary conditions
- [ ] Security decisions remain deterministic and outside the LLM
- [ ] No unrelated files modified
- [ ] Documentation reflects the implementation
- [ ] Any security corpus invariant that now passes has had its `xfail` removed
