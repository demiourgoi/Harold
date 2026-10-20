"""Probe: is Maude's stdout captured by fd redirection, or buffered past the restore?

A Maude file may contain REPL commands (`red`, `rew`, ...); ``maude.load`` executes
them and they print to **stdout**. If the C++ stream is buffered, the text may be
flushed only after fd 1 is restored, escaping the capture (and, in the real server,
landing in the MCP stdio transport).

Two scenarios: without a flush while redirected, and with ``fflush(NULL)``.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_stdout_flush.py no-flush
    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_stdout_flush.py flush
"""

import ctypes
import os
import sys
import tempfile
from pathlib import Path

import maude


def main() -> None:
    do_flush = len(sys.argv) > 1 and sys.argv[1] == "flush"

    maude.init(loadPrelude=True, advise=False)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "prints.maude"
        source.write_text("red in NAT : 1 + 2 .\n", encoding="utf-8")

        with tempfile.TemporaryFile(mode="w+b") as out, tempfile.TemporaryFile(mode="w+b") as err:
            saved_out = os.dup(1)
            saved_err = os.dup(2)
            try:
                os.dup2(out.fileno(), 1)
                os.dup2(err.fileno(), 2)
                ok = maude.load(str(source))
                if do_flush:
                    ctypes.CDLL(None).fflush(None)
            finally:
                os.dup2(saved_out, 1)
                os.dup2(saved_err, 2)
                os.close(saved_out)
                os.close(saved_err)
            out.seek(0)
            err.seek(0)
            captured_out = out.read().decode("utf-8", errors="replace")
            captured_err = err.read().decode("utf-8", errors="replace")

    print("MARKER-BEFORE-REPORT", flush=True)
    print("flush while redirected:", do_flush, flush=True)
    print("load ok:", ok, flush=True)
    print("captured stdout:", repr(captured_out), flush=True)
    print("captured stderr:", repr(captured_err), flush=True)
    print("MARKER-AFTER-REPORT", flush=True)


if __name__ == "__main__":
    main()
