"""Probe: state-number/oracle API on `RewriteSequenceSearch`.

Isolates the calls that crashed ``probe_search_path.py`` after the state-chain
walk. The last call, ``getRule(0)`` on the root state (which has no incoming
rule), hard-crashes the interpreter process with exit code 255 and no traceback,
so it is deliberately the final statement of the probe.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/maude_eval_search_path/research/probes/probe_state_numbers.py
"""

from __future__ import annotations

from pathlib import Path

import maude

HERE = Path(__file__).resolve().parent

maude.init(loadPrelude=True, advise=False)
print("load:", maude.load(str(HERE / "search_path.maude")), flush=True)

shepherd = maude.getModule("SHEPHERD")
it = shepherd.parseTerm("st(l, l, l, l)").search(
    maude.ANY_STEPS, shepherd.parseTerm("st(r, r, r, r)"), depth=7
)
solution, substitution, path_thunk, rewrites = next(it)
print("solution state:", it.getStateNr(), flush=True)

print("getStateParent(9):", it.getStateParent(9), flush=True)
print("getStateParent(0):", it.getStateParent(0), flush=True)

print("getRule(1):", repr(it.getRule(1)), "| label:", repr(it.getRule(1).getLabel()), flush=True)
print("getRule(9):", repr(it.getRule(9)), "| label:", repr(it.getRule(9).getLabel()), flush=True)
print("getRule() current:", repr(it.getRule()), "| label:", repr(it.getRule().getLabel()), flush=True)

print("getStateTerm(0):", str(it.getStateTerm(0)), flush=True)
print("getStateTerm(9):", str(it.getStateTerm(9)), flush=True)

print("pathTo(0):", [str(element) for element in it.pathTo(0)], flush=True)
print("pathTo(9) length:", len(it.pathTo(9)), flush=True)

print("pathTo called twice returns the same labels:", [
    element.getLabel() for element in it.pathTo(9) if hasattr(element, "getLabel")
], flush=True)

print("calling getRule(0) as the last call; expect a hard crash", flush=True)
print("getRule(0):", repr(it.getRule(0)), flush=True)
print("unreachable", flush=True)
