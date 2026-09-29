"""Flush experiments: scenario runner (one scenario per process).

After `maude.load(<file with q .>)`, can the deferred syntax error be consumed
so the next real load stays clean? Scenarios test `maude.input` (unsafe: the
`input_*` scenarios after a q-file segfault with exit 139) and a dummy
`maude.load` of an empty/minute file (safe: consumes the pending error).

Run from the harold-mcp root (needs the project environment):

    uv run python .agents/planning/no_new_module_quirk/scratch_flush2.py <scenario>

Scenarios: input_before_load, input_empty_after_q, input_space_after_q,
input_red_after_q, empty_load_alone, comment_load_alone, minimal_load_alone,
dummy_load_after_q, same_call_flush_empty, same_call_flush_comment,
same_call_flush_minimal, same_call_flush_empty_twice, relative_alone,
relative_after_q, relative_after_clean, relative_after_q_flush.
"""

import os
import sys
import tempfile
from pathlib import Path

import maude

FIXTURES = str(Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures")


def captured(fn):
    """Run one zero-arg call with fd 2 captured; return (result, raw stderr)."""
    with tempfile.TemporaryFile(mode="w+b") as capture:
        saved_fd = os.dup(2)
        try:
            os.dup2(capture.fileno(), 2)
            result = fn()
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
        capture.seek(0)
        raw = capture.read().decode("utf-8", errors="replace")
    return result, raw


def one_capture(*calls):
    """Run several zero-arg calls inside a single fd 2 capture (one worker call)."""
    with tempfile.TemporaryFile(mode="w+b") as capture:
        saved_fd = os.dup(2)
        try:
            os.dup2(capture.fileno(), 2)
            results = [call() for call in calls]
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
        capture.seek(0)
        raw = capture.read().decode("utf-8", errors="replace")
    return results, raw


def main() -> None:
    scenario = sys.argv[1]
    maude.init(loadPrelude=True, advise=False)
    maude.setAllowDir(False)
    maude.setAllowFiles(False)
    maude.setAllowProcesses(False)

    q_file = os.path.join(FIXTURES, "no_new_module.maude")
    clean = os.path.join(FIXTURES, "hello.maude")

    scratch = tempfile.mkdtemp()
    empty = os.path.join(scratch, "empty.maude")
    with open(empty, "w", encoding="utf-8"):
        pass
    comment = os.path.join(scratch, "comment.maude")
    with open(comment, "w", encoding="utf-8") as stream:
        stream.write("--- no-op\n")
    minimal = os.path.join(scratch, "minimal.maude")
    with open(minimal, "w", encoding="utf-8") as stream:
        stream.write("fmod EMPTY-FLUSH is\nendfm\n")

    def show(label, fn):
        result, raw = captured(fn)
        print(f"{label}: result={result!r} stderr={raw!r}", flush=True)

    if scenario == "input_before_load":
        show("input('red ...')", lambda: maude.input("red in NAT : 1 ."))

    elif scenario == "input_empty_after_q":
        show("load q", lambda: maude.load(q_file))
        show("input('')", lambda: maude.input(""))

    elif scenario == "input_space_after_q":
        show("load q", lambda: maude.load(q_file))
        show("input(' ')", lambda: maude.input(" "))

    elif scenario == "input_red_after_q":
        show("load q", lambda: maude.load(q_file))
        show("input('red ...')", lambda: maude.input("red in NAT : 1 ."))

    elif scenario == "relative_alone":
        show("load relative clean", lambda: maude.load("tests/integration/fixtures/hello.maude"))

    elif scenario == "relative_after_q":
        show("load q", lambda: maude.load(q_file))
        show("load relative clean", lambda: maude.load("tests/integration/fixtures/hello.maude"))

    elif scenario == "relative_after_clean":
        show("load clean (absolute)", lambda: maude.load(clean))
        show("load relative hello2", lambda: maude.load("tests/integration/fixtures/hello2.maude"))

    elif scenario == "relative_after_q_flush":
        show("load q", lambda: maude.load(q_file))
        show("load empty (flush)", lambda: maude.load(empty))
        show("load relative hello2", lambda: maude.load("tests/integration/fixtures/hello2.maude"))

    elif scenario == "empty_load_alone":
        show("load empty", lambda: maude.load(empty))
        show("load clean", lambda: maude.load(clean))

    elif scenario == "comment_load_alone":
        show("load comment", lambda: maude.load(comment))
        show("load clean", lambda: maude.load(clean))

    elif scenario == "minimal_load_alone":
        show("load minimal", lambda: maude.load(minimal))
        show("load clean", lambda: maude.load(clean))

    elif scenario == "same_call_flush_empty":
        results, raw = one_capture(lambda: maude.load(q_file), lambda: maude.load(empty))
        print(f"call [load q, load empty]: results={results} stderr={raw!r}", flush=True)
        show("load clean", lambda: maude.load(clean))

    elif scenario == "same_call_flush_minimal":
        results, raw = one_capture(lambda: maude.load(q_file), lambda: maude.load(minimal))
        print(f"call [load q, load minimal]: results={results} stderr={raw!r}", flush=True)
        show("load clean", lambda: maude.load(clean))

    elif scenario == "same_call_flush_comment":
        results, raw = one_capture(lambda: maude.load(q_file), lambda: maude.load(comment))
        print(f"call [load q, load comment]: results={results} stderr={raw!r}", flush=True)
        show("load clean", lambda: maude.load(clean))

    elif scenario == "same_call_flush_empty_twice":
        results, raw = one_capture(lambda: maude.load(q_file), lambda: maude.load(empty))
        print(f"call 1 [load q, load empty]: results={results} stderr={raw!r}", flush=True)
        results, raw = one_capture(lambda: maude.load(q_file), lambda: maude.load(empty))
        print(f"call 2 [load q, load empty]: results={results} stderr={raw!r}", flush=True)
        show("load clean", lambda: maude.load(clean))

    else:
        raise SystemExit(f"unknown scenario: {scenario}")


if __name__ == "__main__":
    main()
