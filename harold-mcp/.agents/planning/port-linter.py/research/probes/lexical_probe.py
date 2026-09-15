"""Lexical probes against the installed Maude 3.5.1 interpreter (design grounding).

Purpose: settle the lexical facts the ported linter's masking layer depends on:
whether string literals can span lines, whether `***`/`---`/`--` inside a string
are comments, and whether an apostrophe is identifier material or the start of a
quoted identifier.

Run from the design-time environment:

    python3 lexical_probe.py

Each probe is written to a temporary directory and loaded with the Maude CLI
(`load <file>`). A clean load (no `Warning:`/`Error:` line) means Maude accepted
the construct.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

MAUDE = "/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/maude"

PROBES: dict[str, str] = {
    "string_multiline": 'fmod T is\n    protecting STRING .\n    op s : -> String .\n    eq s = "line one\nline two" .\nendfm\n',
    "comment_marker_in_string": (
        'fmod T is\n    protecting STRING .\n    op s : -> String .\n    eq s = "a *** b --- c -- d" .\nendfm\n'
    ),
    "comment_in_string_then_code": (
        'fmod T is\n    protecting BOOL .\n    eq "*** not a comment" == "*** not a comment" = true .\nendfm\n'
    ),
    "apostrophe_in_identifier": (
        "fmod T is\n    protecting NAT .\n    op f : Nat -> Nat .\n    var A' : Nat .\n    eq f(A') = A' .\nendfm\n"
    ),
    "apostrophe_identifier_middle": (
        "fmod T is\n    protecting NAT .\n    op f : Nat -> Nat .\n    var A'b : Nat .\n    eq f(A'b) = A'b .\nendfm\n"
    ),
    "quoted_identifier_after_identifier": (
        "fmod T is\n    protecting QID .\n    op q : -> Qid .\n    eq q = 'when .\nendfm\n"
    ),
    "quoted_identifier_range": ("fmod T is\n    protecting QID .\n    op q : -> Qid .\n    eq q = 'a b .\nendfm\n"),
    "string_with_when_and_equals": (
        'fmod T is\n    protecting STRING .\n    op s : -> String .\n    eq s = "when -- = café" .\nendfm\n'
    ),
    "dash_dash_inside_operator": ("fmod T is\n    protecting NAT .\n    op _--_ : Nat Nat -> Nat .\nendfm\n"),
    "hashtag_comment_style": (
        "fmod T is\n    protecting NAT .\n    op a : -> Nat .\n    eq a = 1 . *** trailing comment\nendfm\n"
    ),
    "question_mark_sort_trailing": "fmod T is\n    sort A? .\nendfm\n",
    "question_mark_sort_middle": "fmod T is\n    sort A?B .\nendfm\n",
    "question_mark_sort_leading": "fmod T is\n    sort ?A .\nendfm\n",
    "question_mark_sort_parameterized": "fmod T{X :: TRIV} is\n    sort A?{X} .\nendfm\n",
}

INTERESTING = re.compile(r"(Warning|Error|Advisory):")


def run_probe(directory: Path, name: str, source: str) -> list[str]:
    path = directory / f"{name}.maude"
    _ = path.write_text(source, encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - fixed interpreter path, no shell
        [MAUDE],
        input=f"load {path}\nquit\n",
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = completed.stdout + completed.stderr
    return [line for line in output.splitlines() if INTERESTING.search(line)]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, source in PROBES.items():
            findings = run_probe(directory, name, source)
            verdict = "CLEAN" if not findings else "REPORTED"
            print(f"=== {name}: {verdict}")
            if findings:
                for line in findings:
                    print(f"    {line}")
        print(f"\nprobe sources written to {directory} (temporary, now deleted)")


if __name__ == "__main__":
    main()
