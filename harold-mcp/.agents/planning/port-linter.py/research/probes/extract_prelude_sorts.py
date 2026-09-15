"""Research probe: validate the Q10 prelude-sort extraction algorithm.

Purpose: check that the extraction rules in `research/prelude-sorts.md` §3 are
implementable as a line-oriented script and produce a sensible snapshot: real
`sort`/`sorts` declarations inside `fmod`/`fth`/`mod`/`smod` bodies only, with
view bodies, renaming instantiations, comments, `set` commands and the
`(sth ... sorts none . ... endsth)` meta-term placeholder excluded.

Validated on 2026-09-15 against Maude 3.5.1 (3234-line prelude): 165 names from 25
modules, no junk. The rules this probe validates are the ones specified in
`design/detailed-design.md` §4.5 and implemented by
`scripts/update_prelude_sorts.py`.

Run with the installed prelude (default) or any path:

    python3 extract_prelude_sorts.py [path/to/prelude.maude]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PRELUDE = "/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/prelude.maude"

# `fmod LIST{X :: TRIV} is`, `fth TRIV is`, `view List{X :: TRIV} from TRIV to LIST{X} is`;
# everything between the module name and the closing `is` is parameters/view header.
MODULE_OPEN_RE = re.compile(r"^\s*(fmod|fth|mod|smod|th|view)\s+([^\s{]+)(.*?)\bis\b")
MODULE_CLOSE_RE = re.compile(r"^\s*(endfm|endfth|endm|endsm|endv|endth)\b")
# A module opened and closed on the same line (`view TRIV from TRIV to TRIV is endv`).
INLINE_CLOSE_RE = re.compile(r"\b(?:endfm|endfth|endm|endsm|endv|endth)\b")
SORT_STMT_RE = re.compile(r"^\s*sorts?\s+(.+?)\.\s*$")
# A sort name as Maude writes them: an identifier (`?` is identifier material, per
# `lexical_probe.py`), optionally parameterized.
SORT_NAME_RE = re.compile(r"^[A-Za-z_$][\w'\-?]*(?:\{[^}]*\})?$")
COMMENT_MARKERS = ("***", "---")
# Maude's placeholder in module expressions (`sorts none .` inside `(sth ... endsth)`);
# never a real sort declaration.
PLACEHOLDER_NAMES = frozenset({"none", "}"})


def strip_comments(line: str) -> str:
    """Truncate a line at the first `***` or `---` comment marker."""
    cuts = [line.find(marker) for marker in COMMENT_MARKERS]
    cuts = [cut for cut in cuts if cut != -1]
    return line[: min(cuts)] if cuts else line


def _collect_statement(
    statement: str, module: tuple[str, str] | None, sorts: dict[str, str], excluded: Counter[str]
) -> None:
    """Apply the exclusion rules to one complete `sorts ... .` statement."""
    body = SORT_STMT_RE.match(statement)
    if body is None:
        excluded["unparsed sorts statement"] += 1
        return
    names = body.group(1).split()
    if module is None:
        excluded["no module context"] += len(names)
        return
    if module[0] == "view":
        excluded["view body (sort mapping)"] += len(names)
        return
    if " to " in f" {body.group(1)} ":
        excluded["renaming instantiation (sort mapping)"] += len(names)
        return
    for name in names:
        if name in PLACEHOLDER_NAMES:
            excluded["placeholder (none)"] += 1
        elif not SORT_NAME_RE.match(name):
            excluded[f"non-name token ({name!r})"] += 1
        else:
            sorts.setdefault(name, module[1])


def extract(text: str) -> tuple[dict[str, str], Counter[str]]:
    """Return ({sort name: declaring module}, exclusion reasons)."""
    sorts: dict[str, str] = {}
    excluded: Counter[str] = Counter()
    module: tuple[str, str] | None = None  # (kind, name)
    pending: list[str] = []  # a `sorts ...` statement continued over several lines
    for raw_line in text.splitlines():
        line = strip_comments(raw_line)
        opening = MODULE_OPEN_RE.match(line)
        if opening:
            inline_close = INLINE_CLOSE_RE.search(line[opening.end() :])
            module = None if inline_close else (opening.group(1), opening.group(2))
            continue
        if MODULE_CLOSE_RE.match(line):
            module = None
            continue
        if pending or re.match(r"^\s*sorts?\s", line):
            pending.append(line)
            if line.rstrip().endswith("."):
                _collect_statement(" ".join(pending), module, sorts, excluded)
                pending = []
    return sorts, excluded


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PRELUDE)
    text = path.read_text(encoding="utf-8", errors="replace")
    sorts, excluded = extract(text)

    print(f"prelude: {path} ({len(text.splitlines())} lines)")
    print(f"extracted sort names: {len(sorts)}")
    print(f"declaring modules: {len(set(sorts.values()))} -> {sorted(set(sorts.values()))}")
    print("\nexclusion reasons:")
    for reason, count in excluded.most_common():
        print(f"  {reason}: {count}")

    print("\nspot checks (expected):")
    for name, expected in (
        ("Qid", "QID"),
        ("Bool", "TRUTH-VALUE"),
        ("Nat", "NAT"),
        ("Zero", "NAT"),
        ("Elt", "TRIV"),
        ("List{X}", "LIST"),
        ("NeList{X}", "LIST"),
        ("Entry{X,Y}", "MAP"),
        ("$Split{X}", "WEAKLY-SORTABLE-LIST"),
        ("Term", "META-TERM"),
        ("State", "LOOP-MODE"),
    ):
        actual = sorts.get(name)
        print(f"  {name!r}: {actual!r} {'ok' if actual == expected else 'MISMATCH, expected ' + expected!r}")
    print("\nmust be absent:")
    for name in ("none", "NatList", "QidList", "NeNatList", "endsth)", "."):
        print(f"  {name!r}: {'ABSENT (ok)' if name not in sorts else 'PRESENT (bug)'}")

    base_names = sorted({name.split("{", 1)[0] for name in sorts})
    print(f"\nbase names for the undeclared-identifier allow-list ({len(base_names)}):")
    print("  " + " ".join(base_names))
    print("\nall names (sorted):")
    print("  " + " ".join(sorted(sorts)))


if __name__ == "__main__":
    main()
