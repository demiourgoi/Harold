"""Scratch: which commands leave the parser pending when they appear inside a file?

For each candidate command C: write a file `red ...\n<C>\nfmod NEVER... .`, load it,
then load a clean file and report the next load's capture. Residue = the next load's
stderr is non-empty. One fresh process per candidate.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="harold-cmds-"))
CLEAN = ROOT / "clean.maude"
CLEAN.write_text("fmod CLEAN is pr NAT . op m : -> Nat . endfm\n")

CANDIDATES = [
    "quit",       # documented system-level quit (no period)
    "q",          # q without period
    "q .",        # the known quirk trigger
    "quit .",     # quit with period (verified to leave residue)
    "eof",        # documented "respond as if end of file"
    "eof .",      # with period
    "break .",    # debugger command
    "abort .",    # debugger command
    "resume .",   # debugger command
    "step .",     # debugger command
    "where .",    # debugger command
]

for name in CANDIDATES:
    candidate_file = ROOT / "candidate.maude"
    candidate_file.write_text(f"red in NAT : 1 + 2 .\n{name}\nfmod NEVERX is pr NAT . endfm\n")
    code = f"""
import os, sys
sys.path.insert(0, {str(ROOT)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
maude.setAllowDir(False); maude.setAllowFiles(False); maude.setAllowProcesses(False)
import tempfile
def captured(fn):
    with tempfile.TemporaryFile(mode='w+b') as cap:
        saved = os.dup(2)
        try:
            os.dup2(cap.fileno(), 2)
            result = fn()
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        cap.seek(0)
        return result, cap.read().decode('utf-8', 'replace')
r1, w1 = captured(lambda: maude.load({str(candidate_file)!r}))
r2, w2 = captured(lambda: maude.load({str(CLEAN)!r}))
print("CASE first=", r1, "next=", r2, "never_module=", maude.getModule('NEVERX') is not None)
print("CASE stderr_first=", repr(w1))
print("CASE stderr_next=", repr(w2))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    print(f"--- {name!r} ---")
    for line in result.stdout.splitlines():
        print("  ", line)
    for line in result.stderr.splitlines():
        print("  [raw stderr]", line)
