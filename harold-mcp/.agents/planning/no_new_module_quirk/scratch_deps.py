"""Scratch: how does maude.load resolve `load X .`/`in X .` inside a file?

Pin down:
- resolution rule (file's dir vs process cwd) with decoy files,
- what happens when the dependency is missing (ok flag, warning attribution),
- whether warnings from the dependency get attributed to the dependency or the top file,
- whether the q-quirk triggers through `load` (q . inside the dependency).
"""

import os
import tempfile
from pathlib import Path

import maude

assert maude.init(loadPrelude=True, advise=False)

tmp = Path(tempfile.mkdtemp(prefix="harold-dep-"))
other = Path(tempfile.mkdtemp(prefix="harold-cwd-"))

dep = tmp / "dep.maude"
dep.write_text("fmod DEP is sort S . op c : -> S . endfm\n")
main = tmp / "main.maude"
main.write_text("load dep.maude .\nfmod MAIN is including DEP . op m : -> S . endfm\n")

# Decoy with the same name in another directory.
decoy = other / "dep.maude"
decoy.write_text("fmod DEP is sort Q . op z : -> Q . endfm\n")

# --- 1. bare name; cwd contains a decoy with the same basename ---
os.chdir(other)
ok = bool(maude.load(str(main)))
mod = maude.getModule("DEP")
print("=== 1. load dep.maude (bare), cwd has decoy ===")
print("ok:", ok, "| DEP from file-dir or cwd? ->", "file-dir" if mod is not None and "op c" in str(mod) else "?", mod is not None)
print("   DEP has sort S:", mod is not None and "sort S" in str(mod))

# --- 2. subdir relative path, cwd != file dir ---
sub = tmp / "sub"
sub.mkdir()
subdep = sub / "subdep.maude"
subdep.write_text("fmod SUBDEP is sort T . op d : -> T . endfm\n")
main4 = tmp / "main4.maude"
main4.write_text("load sub/subdep.maude .\nfmod MAIN4 is including SUBDEP . op m : -> T . endfm\n")
os.chdir(other)
ok4 = bool(maude.load(str(main4)))
print("=== 2. load sub/subdep.maude (relative), cwd=other ===")
print("ok:", ok4, "| SUBDEP found:", maude.getModule("SUBDEP") is not None)

# --- 3. missing dependency ---
main_missing = tmp / "main_missing.maude"
main_missing.write_text("load missing.maude .\nfmod MM is including NOPE . op m : -> Nat . endfm\n")
print("=== 3. missing dependency ===")
print("ok:", bool(maude.load(str(main_missing))))

# --- 4. dependency with a syntax warning: attribution ---
baddep = tmp / "baddep.maude"
baddep.write_text("fmod BADDEP is\n    pr NAT .\n    op f : -> Nat .\n    eq f = 1 .\nendfm\n")
# line 4: `eq f = 1 .` is missing `is`... actually `eq f = 1 .` is fine syntax (lhs = rhs, no condition).
# Make a real recoverable warning instead:
baddep.write_text("fmod BADDEP is\n    pr NAT .\n    op f : -> Nat .\n    eq f = s .\nendfm\n")
badmain = tmp / "badmain.maude"
badmain.write_text("load baddep.maude .\nfmod BADMAIN is including BADDEP . op m : -> Nat . endfm\n")
print("=== 4. dependency with a warning: does ok stay True, where does the warning point? ===")
print("ok:", bool(maude.load(str(badmain))))

# --- 5. q . inside the dependency (does the quirk travel through `load`?) ---
qdep = tmp / "qdep.maude"
qdep.write_text("red in NAT : 1 + 2 .\nq .\n")
qmain = tmp / "qmain.maude"
qmain.write_text("load qdep.maude .\nfmod QMAIN is op m : -> Nat . endfm\n")
print("=== 5. q . inside the loaded dependency ===")
print("ok:", bool(maude.load(str(qmain))))
# and the next load — does it get contaminated?
clean = tmp / "clean.maude"
clean.write_text("fmod CLEAN is op m : -> Nat . endfm\n")
print("   next load (clean.maude): ok:", bool(maude.load(str(clean))))

# --- 6. `load` vs `in`: `in` semantics ---
inmain = tmp / "inmain.maude"
inmain.write_text("in dep.maude .\nfmod INMAIN is including DEP . op m : -> S . endfm\n")
os.chdir(other)
print("=== 6. `in dep.maude .` ===")
print("ok:", bool(maude.load(str(inmain))))
