# Research: Maude file dependencies (`load`/`in` inside a file)

Scratch scripts: `scratch_deps.py`, `scratch_resolve.py`, `scratch_nested.py` (this
directory). One fresh process per scenario; decoy files with distinguishable module
contents in every candidate directory.

## Resolution rule (empirical)

`load X .` and `in X .` inside a file resolve `X` against the directory **of the file
containing the command**, not the process cwd and not the top-level file:

- decoy in the process cwd is **ignored** when a dep exists next to the file;
- dep exists **only** in the process cwd → `unable to locate file` (not found);
- nested: `main.maude` (dir A) → `load sub/nested.maude .` → nested's `load dep.maude .`
  resolves against `A/sub/` (decoys in `A/` and cwd both ignored);
- absolute paths in `load` work as expected.

This is good news for diagnostics: a file that `load`s a sibling dependency loads
correctly regardless of the server's cwd, in every worker (also with
`max_tasks_per_child=1`, since resolution is cwd-independent).

## What the tool reports for dependency scenarios

- **Clean main + clean dep**: `ok=True`, no warnings, `success=true`. Modules from the
  dep are defined in that call's interpreter (which dies with the worker afterwards —
  with isolation, cross-file module reuse disappears; see design).
- **Missing dep** (`load missing.maude .` + `including NOPE`): `ok=True` (Maude
  recovers) with three `warning`s attributed to the **main file** at the `load` line:
  `unable to locate file`, `module NOPE does not exist`, and the module-errors trailer.
  Good, actionable diagnostics pointing at the diagnosed file.
- **Dep with a syntax problem**: warnings are attributed to the **dep's own filename**
  (`"baddep.maude", line 4 ...`) with the dep's line numbers. The tool's
  `_parse_warnings` drops the filename and attributes them to the diagnosed file at the
  dep's line number — a **misattribution** (the option-C latent bug, exposed by
  dependencies). Known limitation; not part of this fix.
- **Dep containing `q .`**: the quirk travels through `load` (see
  `quirk-inventory.md` §3) — isolation fixes this; a "depends on a file with a REPL
  quit command" regression test is in scope.

## Open design question answered

The user asked whether several files are needed as input (a dependency list, IDE-style
multi-file diagnostics). Research shows Maude itself resolves sibling `load`s from the
file's directory, so **one file at a time already works** for the common case: the
diagnosed file's own `load` statements pull in its dependencies automatically. A
multi-file tool input is therefore **not needed** for correct diagnostics of
file-dependency projects. The one limitation is warning *attribution* for dependency
files (above), which is a separate hardening item.
