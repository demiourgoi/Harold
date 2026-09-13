# Idea Honing — Port linter.py as part of the diagnostics tool

This document records the requirements-clarification Q&A for this project.

## Q1 — Autofix policy: apply fixes, or report suggestions?

**Context:** the source linter (`improve-rag/improvement/linter.py`) has a deterministic
`autofix()` that rewrites Unicode punctuation. Harold's existing tool is annotated
`readOnlyHint=True` / `destructiveHint=False`. Should the ported tool apply fixes to the
user's file, or report them?

**Decision (user, 2026-09-13):** **Report-only.** Add an **optional fix-suggestions field**
to the tool response; the tool must never modify the source file, keeping the read-only
annotation profile valid.

**Alternatives considered:**
- *Apply the autofix in place* — rejected: mutates user files, invalidates the read-only
  annotation.
- *Separate mutating tool with `readOnlyHint=False`* — not chosen: unnecessary once
  suggestions are exposed through the diagnostics result; can be revisited later.

## Q2 — What should a fix suggestion contain?

**Question:** Should a fix suggestion be:

- **(a) Applyable edits** — a precise span (line/column range) plus replacement text, so a
  client can apply it mechanically without re-deriving the change; or
- **(b) Human-readable advice only** — a text hint (e.g. "replace U+2019 with `'`") that the
  model/agent must locate and apply itself; or
- **(c) Both** — advice text plus applyable edits where the fix is deterministic.

**Answer:** _pending user response._

**Notes on implications (for the pending answer):**
- (a)/(c) require the linter to emit exact columns. The linter *can* (it processes raw text),
  but Maude never reports columns, so `MaudePosition.column` would change from "always
  `None`, reserved" to "populated for linter-produced fixes" — a documented semantic change.
- (b) keeps the model in charge and the payload tiny, but leaves mechanical work to it.
