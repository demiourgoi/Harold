"""Scratch: raw stderr around maude.load(loads_bad_dependency) — the dropped warning line."""

import os
import tempfile
from pathlib import Path

import maude

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"

assert maude.init(loadPrelude=True, advise=False)

with tempfile.TemporaryFile(mode="w+b") as capture:
    saved_fd = os.dup(2)
    try:
        os.dup2(capture.fileno(), 2)
        ok = bool(maude.load(str(FIXTURES / "loads_bad_dependency.maude")))
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
    capture.seek(0)
    raw = capture.read().decode("utf-8", errors="replace")

print("ok:", ok)
print("raw stderr:")
for line in raw.splitlines():
    print("  ", repr(line))
