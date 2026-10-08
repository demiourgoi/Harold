# Research: the quirk's full inventory (what exactly leaks across `maude.load` calls)

Scratch scripts: `scratch_quirks.py`, `scratch_deps.py` (this directory).
Environment: `maude==1.6.0` (Maude 3.5.1) on Python 3.14.2, Linux, one process per
scenario (no cross-scenario state).

## Findings

### 1. `quit .` behaves like `q .`

Loading a file with a top-level `quit .` leaves the same residue: the next
`maude.load` in the process captures
`Warning: "quit_main.maude", line 2: syntax error`. The trigger class is "REPL quit
commands", not just `q .`.

### 2. Content after `q .` is consumed by the *next* load — as real commands

File `after.maude`:

```maude
red in NAT : 1 + 2 .
q .  foo bar
fmod NEVER is pr NAT . endfm
```

- Loading `after.maude` itself: `ok=True`, stderr empty; the `red` runs (stdout).
- The **next** `maude.load` capture contains:
  - `Warning: "after.maude", line 2: syntax error`
  - `Warning: "after.maude", line 2: skipped unexpected token: foo`
  - `Warning: "after.maude", line 2: skipped unexpected token: bar`
- And `maude.getModule("NEVER")` is defined **after** that next load: the pending
  remainder of `after.maude` (line 3) was *parsed and executed* during the next load.

So the residue is not only a stray warning — it is **unparsed commands from the
previous file, executed in the next call's context**. This kills option B (flush) as a
complete fix: a flush would *execute* those pending commands (defining modules, running
reductions) and only discard their warnings. Only process isolation (option A) makes
the residue disappear entirely.

### 3. The quirk travels through `load` (dependency files)

`qmain.maude` = `load qdep.maude .` + `fmod QMAIN ...`, where `qdep.maude` contains
`red ...` + `q .`:

- Loading `qmain.maude`: `ok=True`, stderr empty (the `red` in the dep runs).
- The **next** load's capture contains three warnings:
  - `Warning: "clean.maude", line 1 (fmod CLEAN): undeclared sort Nat.` (the next
    file's own genuine warning),
  - `Warning: "qdep.maude", line 2: syntax error` (the dep's deferred `q .`),
  - `Warning: "qmain.maude", line 2 (fmod QMAIN): undeclared sort Nat.` (the
    *interrupted main file's* pending remainder, parsed during the next load).

A `q .` in a dependency contaminates the next call with warnings attributed to three
different files. The tool's parser strips file names and attributes everything to the
file being diagnosed.

### 4. Relative paths passed to `maude.load` are order-dependent

Maude's internal "current directory" starts at the prelude's directory, not the process
cwd:

- **Fresh process** (right after `init`): `maude.load("rel.maude")` fails with
  `Warning: <standard input>, line 1: unable to locate file: rel.maude` and `ok=False`
  even when the file exists in the process cwd.
- **After any successful absolute load** of a file in directory D, a bare relative
  name resolves against D (verified with decoys: cwd ignored, D wins).
- **After a q-file** the pending command pins resolution to the q-file's directory
  (the README's `relative_after_q` failure: the relative path resolved against the
  fixtures dir and failed).

Consequence for the tool: with `max_tasks_per_child=1` every call starts fresh, so a
**relative** `path` argument will *consistently* fail at the worker
(`ok=False` → synthesized whole-file error), whereas today it fails only on the first
call and "works" when a previous load happened to be in the same directory. The fix is
to absolutize the path before it crosses the worker boundary (see design) — which also
makes the tool's documented "absolute path" contract self-enforcing.

### 5. `maude.input` is not a fix (re-confirmed)

Still a dead end: misbehaves in normal state and segfaults after a pending-state load
(see the README and `scratch_flush.py`). Not considered further.

### 6. Command-set evaluation (Maude manual, Appendix A)

Source: *Maude manual*, Appendix A "Complete List of Maude Commands"
(`maude-manualap1.html`, section `x131-316000A`; text extract in
`manual-commands-appendix.txt`). Scratch script: `scratch_commands.py` (one fresh
process per candidate; each candidate file is `red ...` + the command + a trailing
`fmod NEVERX` whose definition proves whether the remainder was parsed).

The system-level commands (A.16) are documented as **not followed by a period**: `cd`,
`eof`, `in`, `load`, `ll`, `ls`, `popd`, `pushd`, `pwd`, `quit`, `sload`. The classic
period-terminated `q .` does **not appear in the command list at all** — it is an
undocumented shorthand (the lexer tokenizes `q` like `quit`, and the period-terminated
form takes the ordinary command path).

Measured behavior of quit-like commands inside a file:

| Command in file | First load | Next load's stderr | Remainder parsed? |
| --- | --- | --- | --- |
| `q .` / `quit .` | ok, silent | deferred `syntax error` at that line | yes — **during the next load** |
| `quit` (no period) | ok, silent | clean | yes — during the first load (no interrupt) |
| `q` (no period) | ok, silent | clean | yes — during the first load |
| `eof` / `eof .` | ok, silent | clean | **no** — cleanly discarded, no residue |
| `break .`, `abort .`, `resume .`, `step .`, `where .` | ok, silent | clean | yes — during the first load |

Conclusions:

- **The residue trigger class is exactly the period-terminated quit forms** `q .` and
  `quit .`. The documented `quit` (no period) does not even stop file parsing, and the
  documented `eof` stops it **cleanly** (discards the remainder, leaves no residue) —
  `eof` is the sanctioned way to end a file early, and it is what the maude-bindings
  bug report should point at as the expected behavior for the `q .` path.
- No other command in the appendix interrupts the parse loop: rewriting/searching/
  matching/tracing/debugger commands all parse normally inside files (debugger
  commands without an active debugging session are harmless).
- File-system commands (`cd`, `ls`, `pushd`, `popd`, `pwd`, `sload`) are additionally
  neutralized in the worker by `setAllowDir/File/Processes(False)`; they are not part
  of the residue class.
- `in`/`load`/`sload` inside files are documented (nested includes supported); the
  documented bare-name resolution is current directory → `MAUDE_LIB` → executable
  directory, which matches the empirical rule once Maude's internal current directory
  is understood to follow the file being read (see `dependencies.md`).

Net: the quirk inventory needed exactly one extension — the trigger class is the
period-terminated quit pair `q .`/`quit .` (undocumented), with `eof` as the clean
reference behavior. Everything else in the appendix is irrelevant to the residue bug.
