"""Scratch: `in` resolution; `quit .` variant; content after `q .`; relative path load."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="harold-quirks-"))
DIR_A = ROOT / "a"
DIR_B = ROOT / "b"
DIR_A.mkdir()
DIR_B.mkdir()


def run(label: str, code: str) -> None:
    print(f"--- {label} ---")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    for line in result.stdout.splitlines():
        print(line)
    for line in result.stderr.splitlines():
        print("  [stderr]", line)


# 1. `in` command resolution: dep only in cwd -> found? (fresh process)
dep = "in_dep.maude"
main = DIR_A / "in_main.maude"
main.write_text(f"in {dep} .\nfmod INMAIN is including DEP . endfm\n")
(DIR_B / dep).write_text("fmod DEP is sort InCwd . endfm\n")
run(
    "1. `in dep.maude .`, dep only in cwd (file-dir has none)",
    f"""
import os
os.chdir({str(DIR_B)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
ok = bool(maude.load({str(main)!r}))
m = maude.getModule("DEP")
print("CASE ok=", ok, "| DEP:", None if m is None else [str(s) for s in m.getSorts()])
""",
)

# 2. `quit .` in a file: does it leave the same residue?
qmain = DIR_A / "quit_main.maude"
qmain.write_text("red in NAT : 1 + 2 .\nquit .\n")
clean = DIR_A / "quit_clean.maude"
clean.write_text("fmod QTCLEAN is pr NAT . op m : -> Nat . endfm\n")
run(
    "2. `quit .` residue: load quit-file then clean-file",
    f"""
import os
os.chdir({str(DIR_A)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE q-load ok=", bool(maude.load({str(qmain)!r})))
print("CASE next-load ok=", bool(maude.load({str(clean)!r})))
""",
)

# 3. content after `q .` in the same file
after = DIR_A / "after.maude"
after.write_text("red in NAT : 1 + 2 .\nq .  foo bar\nfmod NEVER is pr NAT . endfm\n")
clean2 = DIR_A / "after_clean.maude"
clean2.write_text("fmod ATCLEAN is pr NAT . op m : -> Nat . endfm\n")
run(
    "3. content after `q .` in the same file (same line + next line)",
    f"""
import os
os.chdir({str(DIR_A)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE q-load ok=", bool(maude.load({str(after)!r})))
print("CASE next-load ok=", bool(maude.load({str(clean2)!r})))
print("CASE NEVER module exists:", maude.getModule("NEVER") is not None)
""",
)

# 4. relative path passed to maude.load directly, cwd=DIR_A: resolves against cwd
rel_clean = DIR_A / "rel_clean.maude"
rel_clean.write_text("fmod RELCLEAN is pr NAT . op m : -> Nat . endfm\n")
run(
    "4. relative path to maude.load (cwd=DIR_A, file exists there)",
    f"""
import os
os.chdir({str(DIR_A)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE rel-load ok=", bool(maude.load("rel_clean.maude")))
""",
)

# 5. relative path after a q-file (the README's relative-path variant)
qfirst = DIR_A / "qfirst.maude"
qfirst.write_text("red in NAT : 1 + 2 .\nq .\n")
run(
    "5. q-file then RELATIVE path load (cwd=DIR_A; file exists in DIR_A)",
    f"""
import os
os.chdir({str(DIR_A)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE q-load ok=", bool(maude.load({str(qfirst)!r})))
print("CASE rel-load ok=", bool(maude.load("rel_clean.maude")))
""",
)

# 6. q-file (absolute) then relative load with cwd=DIR_B where rel file does NOT exist
run(
    "6. q-file (abs) then relative load from DIR_B (file only in DIR_A)",
    f"""
import os
os.chdir({str(DIR_B)!r})
import maude
assert maude.init(loadPrelude=True, advise=False)
print("CASE q-load ok=", bool(maude.load({str(qfirst)!r})))
print("CASE rel-load ok=", bool(maude.load("rel_clean.maude")))
""",
)
