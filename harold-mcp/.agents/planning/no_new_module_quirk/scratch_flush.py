"""First (unsafe) flush attempt: flush the deferred `q .` error with `maude.input`.

Finding: `maude.input` is a dead end. It does not parse standalone commands as
expected (`input('red in NAT : 1 .')` warns "unexpected end-of-input"), and it
**segfaults** when called after a load that left the pending `q .` state (exit
139). Do not use it as a flush. See `scratch_flush2.py` for the isolated
scenario runner and the safe (dummy `maude.load`) flush experiments.

Run from the harold-mcp root (needs the project environment); this script is
not indexed to solve the problem observed here, it records it.
"""

import os
import tempfile
from pathlib import Path

import maude

FIXTURES = str(Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures")


def captured(fn, *args):
    with tempfile.TemporaryFile(mode="w+b") as capture:
        saved_fd = os.dup(2)
        try:
            os.dup2(capture.fileno(), 2)
            result = fn(*args)
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
        capture.seek(0)
        raw = capture.read().decode("utf-8", errors="replace")
    return result, raw


def show(label, fn, *args):
    result, raw = captured(fn, *args)
    print(f"{label}: result={result!r} stderr={raw!r}")


def main() -> None:
    maude.init(loadPrelude=True, advise=False)
    maude.setAllowDir(False)
    maude.setAllowFiles(False)
    maude.setAllowProcesses(False)

    q_file = os.path.join(FIXTURES, "no_new_module.maude")
    clean = os.path.join(FIXTURES, "hello.maude")

    print("exposed names with 'input'/'parse'/'flush':")
    print([n for n in dir(maude) if any(s in n.lower() for s in ("input", "parse", "flush", "clean"))])

    print("\n-- without flush (control) --")
    show("load q_file", maude.load, q_file)
    show("load clean", maude.load, clean)

    print("\n-- flush candidate: input('') --")
    show("load q_file", maude.load, q_file)
    show("input('')", maude.input, "")
    show("load clean", maude.load, clean)

    print("\n-- flush candidate: input(' ') (single blank) --")
    show("load q_file", maude.load, q_file)
    show("input(' ')", maude.input, " ")
    show("load clean", maude.load, clean)

    print("\n-- flush candidate: input('---') (comment only) --")
    show("load q_file", maude.load, q_file)
    show("input('---')", maude.input, "---")
    show("load clean", maude.load, clean)


main()
