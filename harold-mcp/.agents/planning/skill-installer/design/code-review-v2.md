# Code review — round 2 (ponytail-review SOP)

Reviewed: the three implementation commits (`2984061` packaging, `30cc13f`
`setup` command, `986f90f` README) against `design/detailed-design.md` and the
step sections of `implementation/plan.md`. Read the changed files, the callers
(`main.py` console script, Makefile, release workflow) and the tests.
Assumed load: one user running `uvx harold-mcp setup`, occasionally
re-running after `uvx --refresh`. Verified live: `make skills && uv build`
(27 skill files in wheel and sdist), `make check`, `make test-unit` (397
tests), a `setup` install/re-install smoke run, `make docs-test`, and the
integration `test_lifespan.py`.

What this change does: it ships the `maude-manual` skill inside the
`harold-mcp` build artifacts (a git-ignored copy re-included through
hatchling `artifacts`, produced by `make skills`, which both `make build` and
the release workflow run first), and adds a `setup` CLI command that installs
or refreshes the skill in an agent skills directory; the README now documents
that flow and links the Zed/opencode MCP docs.

## Must fix

None.

## Should fix

1. **The release changelog does not mention the new feature**
   (`CHANGELOG.md`, `## [0.0.6]` section)
   - **What this is:** the repo convention is one changelog section per
     release; the guide's release process fills it before publishing.
   - **Problem:** `## [0.0.6]` is empty; a reviewer of the release — or a
     user reading the history — cannot see that this version adds `setup`
     and ships the skill.
   - **Fix:** add an `### Added` entry under `[0.0.6]` describing the
     `setup` command and the bundled skill.
   - **If we skip it:** the release notes step would have to rediscover it;
     the feature would ship undocumented in the history.

## Nice to have

2. `main.py`'s `setup` ignores `--directory` when `-g` is passed (documented
   in the option help and the README). An explicit conflict error would be
   stricter, but silently honoring the conventional global location matches
   the design; no change requested.

Verdict: fix 1 first.

Lean: 0 lines possible.
Not checked: nothing.
