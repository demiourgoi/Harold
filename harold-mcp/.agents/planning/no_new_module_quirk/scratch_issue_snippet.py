"""Scratch: run the issue's inline snippet verbatim to confirm its stated output.

Identical to the snippet in `maude-bindings-issue.md` except for the first line:
`_HERE` points into `repro/`, because this file lives one level above the .maude files.
"""

import os
import re
import tempfile
from pathlib import Path

import maude

_HERE = Path(__file__).resolve().parent / "repro"  # the .maude files live next to this script
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
