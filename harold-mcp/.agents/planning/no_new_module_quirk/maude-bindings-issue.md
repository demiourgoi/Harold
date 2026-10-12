# GitHub issue proposal — maude-bindings

Status: **draft, ready to send** (no code changes required in Harold to file it).
Target repository: <https://github.com/fadoss/maude-bindings>.
The minimal reproduction lives next to this file: [`repro_minimal.py`](./repro_minimal.py)
(run it with the bindings installed; no other dependency).

---

## Title

`maude.load()` leaves the parser half-parsed after a top-level `q .`/`quit .` and the
pending input contaminates the next `load()`

---

## Body

### Environment

- `maude` Python bindings **1.6.0** (PyPI wheels), Maude **3.5.1**
- Python 3.14.2, Linux x86-64

### Summary

`maude.load()` returns `True` with empty stderr for a file whose last executed command is
a period-terminated quit (`q .` or `quit .`), but it leaves the parser **half-parsed**:
the interrupted command — and any statements after it in the file — stay pending and are
consumed by the **next** `maude.load()` call in the same process. That next call's fd-2
capture then contains the previous file's warning (`Warning: "q.maude", line 2: syntax
error`), attributed to a different file than the one being loaded.

The documented `eof` command (Maude manual, Appendix A.16) stops a file cleanly, with no
residue, so the `load` parse loop appears to return early for the `q .` case without
discarding the pending input.

### Minimal reproduction

Four Maude files (the real inputs; also `repro/` in the repository this report comes
from) plus a script that loads them in one process, capturing fd 2 per `maude.load`:

`q.maude`:

```maude
red in NAT : 1 + 2 .
q .
```

`quit.maude`:

```maude
red in NAT : 1 + 2 .
quit .
```

`eof.maude`:

```maude
red in NAT : 1 + 2 .
eof
```

`clean.maude`:

```maude
fmod CLEAN is
    pr NAT .
    op m : -> Nat .
endfm
```

```python
"""Loads q.maude, then clean.maude twice, capturing fd 2 per maude.load call."""
import os
import re
import tempfile
from pathlib import Path

import maude

_HERE = Path(__file__).resolve().parent  # the .maude files live next to this script
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def load_capturing_stderr(name: str) -> tuple[bool, str]:
    with tempfile.TemporaryFile(mode="w+b") as capture, open(os.devnull, "wb") as sink:
        saved_err, saved_out = os.dup(2), os.dup(1)
        try:
            os.dup2(capture.fileno(), 2)
            os.dup2(sink.fileno(), 1)  # silence the `red` output for a clean report
            ok = bool(maude.load(str(_HERE / name)))
        finally:
            os.dup2(saved_err, 2)
            os.dup2(saved_out, 1)
            os.close(saved_err)
            os.close(saved_out)
        _ = capture.seek(0)
        return ok, _ANSI.sub("", capture.read().decode("utf-8", errors="replace"))


assert maude.init(loadPrelude=True, advise=False)
for name in ("q.maude", "clean.maude", "clean.maude"):
    print(name, load_capturing_stderr(name))
```

Observed:

```text
q.maude (True, '')
clean.maude (True, 'Warning: "q.maude", line 2: syntax error\n')   # <- belongs to the previous load
clean.maude (True, '')                                             # residue consumed once
```

`repro_minimal.py` (attached / in the repository this report comes from) is the same
script extended with the `quit .` scenario and the `eof` contrast (all four files are in
its `repro/` directory):

```text
1. load q.maude        -> ok=True, stderr=''
2. load clean.maude    -> ok=True, stderr='Warning: "q.maude", line 2: syntax error\n'
3. load clean.maude 2  -> ok=True, stderr=''
4. load quit.maude     -> ok=True, stderr=''
5. load clean.maude    -> ok=True, stderr='Warning: "quit.maude", line 2: syntax error\n'
6. load clean.maude 2  -> ok=True, stderr=''
7. load eof.maude      -> ok=True, stderr=''
8. load clean.maude    -> ok=True, stderr=''   # documented `eof`: no residue
```

### Expected

`maude.load` should either fully consume the file or discard what remains after the quit
command (the behavior `eof` exhibits today), so a later `load()` only ever captures its
own file's diagnostics and the process state does not depend on call order.

### Actual

The residue survives in the parser and leaks into the next `load()`. Note `q .` is
widely used to end Maude scripts and is accepted by the REPL (`q .  foo bar` quits
immediately, trailing text ignored), even though Appendix A documents only the
period-less `quit` — so files containing it are common in the wild, not an edge case.

### Additional observations (all reproduced; happy to share scripts)

1. **Pending statements execute during the next load.** With a file
   `red in NAT : 1 + 2 .` / `q .` / `fmod LATE is … endfm`, `maude.getModule("LATE")` is
   defined only after the *next* `maude.load()` in the process — the remainder is parsed
   then, not discarded.
2. **Relative paths get pinned to the previous file's directory.** After loading a
   q-file from directory `D`, `maude.load("sub/file.maude")` resolves against `D` and
   fails (`unable to locate file`); after a normal load it resolves as usual.
3. **`maude.input()` is not usable as a workaround.** It already misbehaves in normal
   state (`input("red in NAT : 1 .")` returns `False`, `unexpected end-of-input.`), and
   when called while the parser is pending it **segfaults** (exit code 139) — for both
   `input("")` and `input(" ")`.
4. **The deferred warning keeps the old file/line**, so callers that parse only
   `line: message` silently misattribute it to their current file.

### Mechanism pointer

`load()` in `src/maude_wrappers.cc`:

```cpp
UserLevelRewritingContext::ParseResult parseResult = UserLevelRewritingContext::NORMAL;
while (parseResult == UserLevelRewritingContext::NORMAL) {
    if (yyparse(&parseResult))
        return false;
}
return true;
```

When `q .` makes the parser return a non-`NORMAL` result, the loop exits and `true` is
returned without consuming the remainder of the input. (For comparison, `eof` in a file
stops parsing *and* leaves no residue, so whatever the `eof` path does — or does not —
with the remaining input is the reference behavior.)

### Suggested fix / API

- Preferred: after the parse loop, discard any pending input when the file was stopped
  by something other than natural EOF — i.e. make the `q .` path behave like `eof`.
- Alternatively (or additionally): expose a parser-reset function
  (`resetInput()`/`clearPendingInput()`) callers can invoke between loads, and document
  the `q .` caveat on `load()`.

### Workaround we use (for context)

Our tool (an MCP server that loads user files for diagnostics) now runs each
`maude.load` in a **fresh process** (`ProcessPoolExecutor(max_tasks_per_child=1)`), which
sidesteps the residue entirely — at ~1 s of spawn + prelude init per load. A binding-level
fix would let long-lived processes load files safely again.

### References

- Maude manual, Appendix A — Complete List of Maude Commands (`eof`, `quit`, system
  commands are not period-terminated): <https://maude.lcc.uma.es/maude-manual/maude-manualap1.html#x131-316000A>
- Reproduction script: `repro_minimal.py` (this directory / attached)
