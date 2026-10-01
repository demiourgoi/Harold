"""Scratch: nested `load` resolution — main.maude loads sub/nested.maude which loads dep.maude.

Where does the nested file's `load dep.maude .` resolve: sub/ (its own dir) or the
top file's dir? Fresh process, decoys in every candidate directory with
distinguishable modules.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="harold-nested-"))
DIR_A = ROOT / "a"
SUB = DIR_A / "sub"
SUB.mkdir(parents=True)
CWD = ROOT / "cwd"
CWD.mkdir()

# Nested file (sub/nested.maude) loads dep.maude and defines a module that uses it.
nested = SUB / "nested.maude"
nested.write_text("load dep.maude .\nfmod NESTED is including DEP . endfm\n")
# Top file loads the nested file.
main = DIR_A / "main.maude"
main.write_text("load sub/nested.maude .\nfmod MAIN is including NESTED . endfm\n")
# Decoys:
(SUB / "dep.maude").write_text("fmod DEP is sort FromNestedDir . endfm\n")
(DIR_A / "dep.maude").write_text("fmod DEP is sort FromTopDir . endfm\n")
(CWD / "dep.maude").write_text("fmod DEP is sort FromCwd . endfm\n")

code = f"""
import os
os.chdir({str(CWD)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
ok = bool(maude.load({str(main)!r}))
m = maude.getModule("DEP")
sorts = [str(s) for s in m.getSorts()] if m is not None else None
print("CASE ok=", ok, "| DEP sorts=", sorts)
"""
print("--- nested: dep decoys in nested-dir, top-dir and cwd ---")
result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
for line in result.stdout.splitlines():
    print(line)
for line in result.stderr.splitlines():
    print("  [stderr]", line)
