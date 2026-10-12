"""Minimal reproduction: `maude.load()` leaves the parser half-parsed after `q .`/`quit .`.

Loading a file that contains a period-terminated quit command (`q .` or `quit .`) leaves
the parser half-parsed: `maude.load` returns `True` with empty stderr, but the interrupted
command (and any statements that follow it) stay pending and are consumed by the *next*
`maude.load` in the same process — the deferred warning lands in that call's capture.
The documented `eof` command (Maude manual, Appendix A.16) stops a file cleanly instead.

The Maude files are the real inputs, next to this script (see `repro/`):

    repro/q.maude      red in NAT : 1 + 2 .   /  q .
    repro/quit.maude   red in NAT : 1 + 2 .   /  quit .
    repro/eof.maude    red in NAT : 1 + 2 .   /  eof
    repro/clean.maude  fmod CLEAN is pr NAT . op m : -> Nat . endfm

Run with the `maude` bindings installed (reproduced with `maude==1.6.0`, Maude 3.5.1):

    python repro_minimal.py

Observed output (Maude 3.5.1, Python 3.14.2, Linux):

    1.   load q.maude      -> ok=True, stderr=''
    2.   load clean.maude    -> ok=True, stderr='Warning: "q.maude", line 2: syntax error\n'
    3.   load clean.maude 2  -> ok=True, stderr=''
    4.   load quit.maude   -> ok=True, stderr=''
    5.   load clean.maude    -> ok=True, stderr='Warning: "quit.maude", line 2: syntax error\n'
    6.   load clean.maude 2  -> ok=True, stderr=''
    7.   load eof.maude    -> ok=True, stderr=''
    8.   load clean.maude    -> ok=True, stderr=''
    9.   load clean.maude 2  -> ok=True, stderr=''

Every `stderr` above is the fd-2 capture of that single `maude.load` call (ANSI escapes
stripped and Maude's stdout silenced for a stable output); step 2 (and 5) is the bug: the
warning belongs to the *previous* file and the previous call.
"""

import os
import re
import tempfile
from pathlib import Path

import maude

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
REPRO_DIR = Path(__file__).resolve().parent / "repro"


def load_capturing_stderr(name: str) -> tuple[bool, str]:
    """Load `repro/<name>` with fd 2 captured and fd 1 silenced (`red` output is noise here)."""
    with tempfile.TemporaryFile(mode="w+b") as capture, open(os.devnull, "wb") as sink:
        saved_err = os.dup(2)
        saved_out = os.dup(1)
        try:
            os.dup2(capture.fileno(), 2)
            os.dup2(sink.fileno(), 1)
            ok = bool(maude.load(str(REPRO_DIR / name)))
        finally:
            os.dup2(saved_err, 2)
            os.dup2(saved_out, 1)
            os.close(saved_err)
            os.close(saved_out)
        _ = capture.seek(0)
        text = capture.read().decode("utf-8", errors="replace")
    # Maude colorizes stderr when it is a TTY; strip ANSI for a stable report.
    return ok, _ANSI_ESCAPE_RE.sub("", text)


def main() -> None:
    assert maude.init(loadPrelude=True, advise=False)

    def scenario(first_name: str, step: int) -> int:
        ok, stderr = load_capturing_stderr(first_name)
        print(f"{step}.   load {first_name:<12} -> ok={ok}, stderr={stderr!r}")
        ok, stderr = load_capturing_stderr("clean.maude")
        print(f"{step + 1}.   load clean.maude    -> ok={ok}, stderr={stderr!r}")
        ok, stderr = load_capturing_stderr("clean.maude")
        print(f"{step + 2}.   load clean.maude 2  -> ok={ok}, stderr={stderr!r}")
        return step + 3

    step = scenario("q.maude", 1)
    step = scenario("quit.maude", step)
    _ = scenario("eof.maude", step)


if __name__ == "__main__":
    main()
