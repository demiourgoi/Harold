"""Probe: what Maude writes to fd 1 / fd 2 during each term operation.

Answers the questions behind ``../worker-behavior.md`` §Streams:

- does ``parseTerm`` write its error message to stderr (as ``maude.load`` does)?
- do successful ``reduce``/``rewrite``/``match``/``search`` write anything?
- are any outputs ANSI-colorized when stderr is not a TTY?

The capture mechanism mirrors the worker's ``load_diagnostics`` (temp files, not
pipes), so buffering behavior is comparable.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_streams.py
"""

import os
import tempfile
from collections.abc import Callable
from typing import Any

import maude

maude.init(loadPrelude=True, advise=False)
nat = maude.getModule("NAT")
maude.input("""
mod COUNTER is
  pr NAT .
  op c : Nat -> Nat [ctor] .
  var N : Nat .
  rl [inc] : c(N) => c(N + 1) .
endm
""")
counter = maude.getModule("COUNTER")


def capture(label: str, fn: Callable[[], Any]) -> None:
    """Run ``fn`` with fd 1/2 redirected to temp files and print what was written."""
    with tempfile.TemporaryFile(mode="w+b") as out, tempfile.TemporaryFile(mode="w+b") as err:
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        try:
            os.dup2(out.fileno(), 1)
            os.dup2(err.fileno(), 2)
            result = fn()
        finally:
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
            os.close(saved_out)
            os.close(saved_err)
        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", errors="replace")
        stderr = err.read().decode("utf-8", errors="replace")
    print(f"--- {label}")
    print(f"    result = {result!r}")
    print(f"    stdout = {stdout!r}")
    print(f"    stderr = {stderr!r}")


capture("parseTerm ok", lambda: str(nat.parseTerm("2 * 3")))
capture("parseTerm syntax error", lambda: nat.parseTerm("2 +"))
capture("parseTerm undeclared operator", lambda: nat.parseTerm("nope(3)"))
capture("parseTerm wrong sort context (var undeclared)", lambda: counter.parseTerm("c(M)"))

t = nat.parseTerm("2 * 3")
capture("reduce ok", lambda: t.reduce())
capture("reduce already normal", lambda: nat.parseTerm("6").reduce())

capture("rewrite(1)", lambda: counter.parseTerm("c(0)").rewrite(1))
capture("rewrite(0)", lambda: counter.parseTerm("c(0)").rewrite(0))
capture("frewrite(2)", lambda: counter.parseTerm("c(0)").frewrite(2))
capture("erewrite(2)", lambda: str(counter.parseTerm("c(0)").erewrite(2)))

capture(
    "match hit",
    lambda: [str(sub) for sub, _ in counter.parseTerm("c(5)").match(counter.parseTerm("c(N)"), maxDepth=0)],
)
capture(
    "match miss",
    lambda: [str(sub) for sub, _ in counter.parseTerm("c(5)").match(counter.parseTerm("c(6)"), maxDepth=0)],
)
capture(
    "search hit",
    lambda: [
        str(solution)
        for solution, *_ in counter.parseTerm("c(0)").search(maude.ANY_STEPS, counter.parseTerm("c(N)"), depth=2)
    ],
)
capture(
    "search miss",
    lambda: [
        str(solution)
        for solution, *_ in counter.parseTerm("c(0)").search(maude.ONE_STEP, counter.parseTerm("c(9)"), depth=2)
    ],
)

capture("load clean", lambda: maude.load("tests/integration/fixtures/hello.maude"))
out_idx = capture("load with warnings", lambda: maude.load("tests/integration/fixtures/broken-recoverable.maude"))
print("load capture returned:", out_idx)
