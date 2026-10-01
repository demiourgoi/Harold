"""Scratch: debug module inspection + resolution rule, fresh process per case."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="harold-resolve3-"))
DIR_A = ROOT / "a"
DIR_B = ROOT / "b"
DIR_A.mkdir()
DIR_B.mkdir()

script_template = r"""
import os
os.chdir({cwd!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
ok = bool(maude.load({main!r}))
m = maude.getModule("DEP")
print("CASE ok=", ok)
if m is not None:
    sorts = [str(s) for s in m.getSorts()]
    print("CASE DEP sorts=", sorts)
    print("CASE DEP defline sample=", str(m).splitlines()[:2])
else:
    print("CASE DEP module is None")
"""


def case(name: str, dep_a: bool, dep_b: bool, cwd: Path) -> None:
    dep = f"{name}_dep.maude"
    main = DIR_A / f"{name}_main.maude"
    main.write_text(f"load {dep} .\nfmod {name.upper()} is including DEP . endfm\n")
    if dep_a:
        (DIR_A / dep).write_text("fmod DEP is sort FromFileDir . endfm\n")
    if dep_b:
        (DIR_B / dep).write_text("fmod DEP is sort FromCwd . endfm\n")

    result = subprocess.run(
        [sys.executable, "-c", script_template.format(cwd=str(cwd), main=str(main))],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(f"--- {name} (file-dir={dep_a}, cwd={dep_b}, cwd dir={cwd.name}) ---")
    for line in result.stdout.splitlines():
        print(line)
    for line in result.stderr.splitlines():
        print("  [stderr]", line)


case("both", True, True, DIR_B)
case("fileonly", True, False, DIR_B)
case("cwdonly", False, True, DIR_B)
case("none", False, False, DIR_B)
