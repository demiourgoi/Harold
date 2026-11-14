# Design review — round 1 (ponytail-review SOP)

Reviewed: `detailed-design.md` against `rough-idea.md`, the requirements in
`idea-honing.md`, and `research/release-packaging.md`. Assumed load: a single
user running `uvx harold-mcp setup` on a laptop, occasionally re-running it
after an upgrade.

What this change does: it ships the `maude-manual` skill inside the
`harold-mcp` wheel by copying it into the package tree at build time, and adds
a `setup` CLI command that copies the packaged skill into an agent skills
directory, overwriting any previous copy so re-running it updates the skill.

## Must fix

1. **`install_skill` breaks when the destination exists as a file**
   (`detailed-design.md`, `install_skill` section)
   - **What this is:** `setup` copies the skill to `<base>/maude-manual` after
     removing an existing destination.
   - **Problem:** the design only says "remove it first (`shutil.rmtree`)".
     If a user (or a broken earlier tool) left a regular *file* named
     `maude-manual` in the base directory, `rmtree` raises
     `NotADirectoryError` and `setup` always fails until the user deletes the
     file by hand, with no hint.
   - **Fix:** remove the destination whether it is a directory or a file
     (`rmtree` if `is_dir()`, `unlink` otherwise), and say so in the design.
   - **If we skip it:** a one-line manual fix for the user, but the failure
     message gives no clue; the update promise ("run setup again") breaks.

## Should fix

2. **No automated check that the artifact actually contains the skill**
   (`detailed-design.md`, Tests section)
   - **What this is:** the design verifies the wheel contents only by hand.
   - **Problem:** the one thing this feature must guarantee — the skill is in
     the published artifact — has no automated check anywhere; a future change
     to the Makefile or workflow fails silently at release time, when PyPI
     versions are immutable.
   - **Fix:** add a cheap unit test that, when `src/harold_mcp/skills/
     maude-manual` exists in the checkout (i.e. after `make skills`), asserts
     `skill_source()` points at a directory containing `SKILL.md`
     (skipif the copy is absent, so a plain dev checkout still passes).
   - **If we skip it:** a silent bad release is plausible and expensive.

3. **`make release` does not exercise the new packaging path**
   (`detailed-design.md`, Packaging section)
   - **What this is:** `make release` is the pre-release gate the developer
     guide tells the maintainer to run before publishing.
   - **Problem:** nothing in the documented release checklist runs
     `make skills` or a build, so the maintainer never validates the artifact
     locally before the immutable PyPI upload.
   - **Fix:** mention in the design that the release workflow now builds via
     `make skills && uv build`, and note `make build` as the local equivalent
     to verify the artifact (already implied by `build: skills`); keep it
     out of `make release` itself to avoid slowing the test gate.
   - **If we skip it:** the workflow change alone still covers the real
     release; this is defense in depth.

## Nice to have

4. The design's `skill_source()` coerces `importlib.resources.files(...)` to
   `Path` directly. That is correct for pip/uv installs (wheels are unzipped),
   and zip-imported installs cannot exist for this package (it is not
   zip-safe and `maude` ships native wheels). No change needed; noted so the
   assumption is on record.

Verdict: fix 1–3 in the design before implementation.

Lean: 0 lines possible.
Not checked: actual wheel contents (implementation Step 1 verifies them).
