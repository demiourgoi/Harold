"""Scratch: filename printed in warnings for deps in subdirectories (misattribution fix data)."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="harold-attr-"))
SUB = ROOT / "lib"
SUB.mkdir()
dep = SUB / "baddep.maude"
dep.write_text("fmod BADDEP is\n    pr NAT .\n    op f : -> Nat .\n    eq f = s .\nendfm\n")
main = ROOT / "main.maude"
main.write_text("load lib/baddep.maude .\nfmod MAIN is including BADDEP . op m : -> Nat . endfm\n")
# also a plain sibling dep with a warning
sib = ROOT / "sibdep.maude"
sib.write_text("fmod SIBDEP is\n    op f : -> Nat .\nendfm\n")
main2 = ROOT / "main2.maude"
main2.write_text("load sibdep.maude .\nfmod MAIN2 is including SIBDEP . endfm\n")

code = f"""
import os
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE subdir-dep ok=", bool(maude.load({str(main)!r})))
print("CASE sibling-dep ok=", bool(maude.load({str(main2)!r})))
"""
result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
for line in result.stdout.splitlines():
    print(line)
for line in result.stderr.splitlines():
    print("  [stderr]", line)
