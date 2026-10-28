---
name: update-changelog-for-release
description: Updates harold-mcp's CHANGELOG.md for the release process in DEVELOPER_GUIDE.md — confirms the codebase summary is current, derives the release version from pyproject.toml, reviews commits since the previous release tag, and writes concise deduplicated changelog entries. Use when preparing a release or when the user asks to update the changelog.
---

# Update Changelog for Release

## Overview

This SOP updates `CHANGELOG.md` for the release process described in
`DEVELOPER_GUIDE.md` ("Releasing a new version"): the changelog section for the
release version is used verbatim as the GitHub release notes, so before publishing
a release that section must cover every meaningful change committed since the
previous release.

The SOP asks the user to confirm that the codebase summary in `.agents/summary/`
is up to date, derives the release version from `pyproject.toml` by stripping the
`.dev0` suffix, enumerates the commits on `main` between the previous release tag
and HEAD, and makes sure each commit has a corresponding entry in the
`## [<version>]` section of the changelog. Duplicate entries for the same feature
are avoided, and trivial changes (typos, formatting, docs-only edits) are grouped
into a single generic "General fixes" entry. The SOP ends by asking the user to
increase the dev version in `pyproject.toml` for the next release.

## Parameters

- **changelog_path** (optional, default: "CHANGELOG.md"): Path to the changelog to update
- **pyproject_path** (optional, default: "pyproject.toml"): Path to `pyproject.toml`, the source of the current dev version
- **previous_version_tag** (optional): Tag of the previous release (e.g. `0.0.2`). When omitted, the SOP derives it as the most recent `*.*.*` tag reachable from HEAD
- **base_branch** (optional, default: "main"): Branch whose commits are considered for the release

**Constraints for parameter acquisition:**
- If all required parameters are already provided, You MUST proceed to the Steps
- If any required parameters are missing, You MUST ask for them before proceeding
- When asking for parameters, You MUST request all parameters in a single prompt
- When asking for parameters, You MUST use the exact parameter names as defined
- You MUST resolve relative paths against the repository root (the directory that contains `pyproject.toml`)
- You MUST confirm successful acquisition of all parameters before proceeding

## Steps

### 1. Confirm the Codebase Summary Is Up to Date

Ask the user to confirm that the codebase summary in `.agents/summary/` is up to
date. The changelog must be consistent with the documented state of the codebase.

**Constraints:**
- You MUST ask the user to confirm that the codebase summary in `.agents/summary/` is up to date
- You MUST NOT proceed until the user has answered, because the changelog must match the documented state of the codebase
- If the summary is not up to date, You MUST suggest re-running the codebase-summary skill and You MAY continue only with the user's consent
- You SHOULD NOT update `.agents/summary/` yourself in this SOP, since that is the codebase-summary skill's responsibility

### 2. Determine the Release Version

Read the current version from `pyproject.toml` and derive the release version by
removing the `.dev0` suffix.

**Constraints:**
- You MUST read the `version` field under the `[project]` table of {pyproject_path}
- You MUST strip a trailing `.dev0` suffix to obtain the release version (e.g. `0.0.3.dev0` becomes `0.0.3`)
- If the version has no `.dev0` suffix, You MUST use it as-is
- You MUST verify that the release version matches the `*.*.*` pattern; if it does not, You MUST ask the user for the correct release version
- You MUST NOT edit {pyproject_path} in this step, because the dev version must stay in place until the release is published

### 3. Identify the Commits Since the Previous Release

Determine the commit range to review: everything on {base_branch} after the
previous release tag, up to HEAD.

**Constraints:**
- If {previous_version_tag} was provided, You MUST use it
- Otherwise, You MUST use the most recent tag matching the `*.*.*` pattern that is reachable from HEAD on {base_branch}; for example with `git tag --merged HEAD --sort=-version:refname`
- If no previous tag exists (first release), You MUST treat the entire history reachable from HEAD as the range, and You MAY ask the user to confirm
- You MUST list the commits in the range with a command like `git --no-pager log --no-merges --oneline <previous_tag>..HEAD`
- You SHOULD skip merge commits, since they usually do not introduce changes by themselves
- You MUST NOT include commits that are already part of a released version, since older changelog sections already cover them

### 4. Map Each Commit to a Changelog Entry

Make sure the release subsection `## [<release_version>]` exists and covers every
commit from step 3, without duplicates.

**Constraints:**
- For each commit, You MUST classify it as a functional change, an architectural change, a bug fix, or a trivial change (typos, formatting, wording, or docs-only edits)
- You SHOULD inspect the diff of a commit (e.g. `git show --stat <sha>`) when its subject line does not make the change clear
- You MUST ensure the section `## [<release_version>]` exists at the top of the changelog (directly after the `# Changelog` title), using the existing `### Added`, `### Changed`, `### Fixed`, and `### Removed` grouping style
- For every functional change, architectural change, and bug fix, You MUST add a corresponding entry to that section if one does not exist yet, in the existing style (`- **Title** — description.`)
- You MUST NOT add entries for commits that are already covered by an existing entry, because duplicate entries for the same feature clutter the release notes
- You MAY merge several commits that implement the same feature into a single entry
- You MUST group trivial changes into a single generic entry (e.g. `- **General fixes** — assorted typos, formatting, and documentation polish.`) instead of one entry per trivial commit
- Change descriptions MUST be clear and concise, and MUST focus on the user-visible impact
- You MUST NOT modify the sections of already-released versions, since they are historical records

### 5. Verify Coverage and Report

Check that the release subsection accounts for every commit, and report the
result to the user.

**Constraints:**
- You MUST verify that every commit from step 3 is accounted for, either by a dedicated entry or by the generic "General fixes" entry
- You MUST present the user with a mapping of commits to changelog entries, and show the final diff of the changelog
- You MUST NOT commit or push the changes, since the release process is driven manually through GitHub releases

### 6. Ask About the Next Development Version

Finish by asking the user to increase the dev version on {pyproject_path}, so the
tip of `main` becomes the code of the next release (step 2 of the "New release"
process in `DEVELOPER_GUIDE.md`).

**Constraints:**
- You MUST ask the user to increase the dev version on {pyproject_path}, and You MUST suggest a concrete next version (e.g. from `0.0.3.dev0` to `0.0.4.dev0`)
- You MUST NOT modify {pyproject_path} without the user's explicit confirmation, because the next version number is the maintainer's decision
- If the user confirms, You MAY update the `version` field and add a new `## [<next_version>]` section to the changelog
- You MAY ask the user how large the bump should be (patch, minor, or major) when the next version is ambiguous

## Examples

### Example 1: Preparing the 0.0.3 Release

**Input:**
- `version = "0.0.3.dev0"` in `pyproject.toml`
- Most recent tag reachable from `main`: `0.0.2` at commit `e8a318f`

**Expected Behavior:**
- The release version is derived as `0.0.3`
- The commits in `e8a318f..HEAD` are listed, e.g. `Improve tool metadata`, `Disable IO from Maude`, `Simplify main with cyclopts`, `update docs`, `rephrase`
- The `## [0.0.3]` section is checked and completed: one entry per functional change (tool tags, tool annotations, disabled Maude IO, cyclopts CLI), no duplicates
- Commits like `update docs` and `rephrase` are folded into a single `- **General fixes** — assorted typos, formatting, and documentation polish.` entry
- Finally, the agent asks the user to bump `pyproject.toml` to `0.0.4.dev0`

### Example 2: First Release (No Previous Tag)

**Input:**
- `version = "0.1.0.dev0"` in `pyproject.toml`
- The repository has no `*.*.*` tags

**Expected Behavior:**
- Step 3 finds no previous tag, so the whole history up to HEAD is reviewed
- The agent asks the user to confirm the commit range before editing the changelog

## Troubleshooting

### No Previous Tag Found
If `git tag --merged HEAD` returns no `*.*.*` tag, treat the full history as the
range (first release), or ask the user to provide {previous_version_tag}.

### Version Without a `.dev0` Suffix
If the version in `pyproject.toml` has no `.dev0` suffix, use it as-is; the
version may already be a release version.

### Duplicate Entries
If the release subsection already contains an entry for a commit, do not add a
second one; extend the existing entry only if the description is incomplete.

### Missing or Shallow Git History
If commits appear to be missing, check for a shallow clone and, if needed, ask
the user to run `git fetch --unshallow` before re-running this SOP.

### Release Subsection Already Complete
If every commit is already covered, report that no changelog changes are needed
and skip straight to step 6.
