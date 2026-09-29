"""Reproduce the deferred `q .` quirk of `maude.load` in a long-lived worker.

Loading a file that ends with the REPL quit command `q .` (the
`no_new_module.maude` fixture) leaves a pending syntax error inside the Maude
bindings. Maude only reports it during the *next* `maude.load` call, whose fd-2
capture then contains a warning about the earlier file. The diagnostics tool
attributes every captured warning to the file it is diagnosing, so a clean
program is reported as `success=False`.

Run from the harold-mcp root (needs the project environment):

    uv run python .agents/planning/no_new_module_quirk/repro_q_quirk.py

Expected output: the first `no_new_module.maude` load is silent; the `hello.maude`
load right after it captures `Warning: "no_new_module.maude", line 2: syntax error`;
the following loads are silent again (the pending error is a one-shot).
"""

import os
import tempfile
from pathlib import Path

import maude

from harold_mcp.maude import worker

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"

SEQUENCE = ["hello.maude", "no_new_module.maude", "hello.maude", "hello2.maude", "no_new_module.maude", "hello.maude"]


def load_raw(name: str) -> None:
    """Load one fixture with fd 2 captured, printing the full raw stderr."""
    path = str(FIXTURES / name)
    with tempfile.TemporaryFile(mode="w+b") as capture:
        saved_fd = os.dup(2)
        try:
            os.dup2(capture.fileno(), 2)
            ok = bool(maude.load(path))
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
        capture.seek(0)
        raw = capture.read().decode("utf-8", errors="replace")
    print(f"--- {name}: ok={ok}")
    print("    raw stderr:", repr(raw))


def main() -> None:
    worker.init_maude()  # same initialization the pool's workers run

    for name in SEQUENCE:
        load_raw(name)


if __name__ == "__main__":
    main()
