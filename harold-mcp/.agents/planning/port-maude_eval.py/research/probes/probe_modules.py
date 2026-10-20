"""Probe: module selection, enumeration and dependency loading.

Answers the questions behind ``../term-api.md`` §Modules:

- what ``getCurrentModule()`` returns before and after loading files
- whether ``getModules()`` can be diffed to learn which modules a file defined
- ``getModule()`` lookup behavior (missing names, case sensitivity)
- how sibling ``load`` dependencies and broken/unusable modules show up
- what a file with embedded REPL commands writes to stdout

Each scenario runs in a fresh subprocess (fresh Maude interpreter), mirroring the
tool's hermetic calls. The driver prints the scenario's stdout and stderr
separately, so stream attribution stays visible.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_modules.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURES = Path("tests/integration/fixtures")


def init() -> "object":
    import maude

    maude.init(loadPrelude=True, advise=False)
    return maude


def headers(maude: object) -> list[tuple[str, int]]:
    return [(header.name, header.type) for header in maude.getModules()]  # type: ignore[attr-defined]


def new_modules(maude: object, before: list[tuple[str, int]]) -> list[tuple[str, int]]:
    known = {name for name, _ in before}
    return [header for header in headers(maude) if header[0] not in known]


def report_load(maude: object, path: str) -> None:
    before = headers(maude)
    print("load returned:", maude.load(path))
    fresh = new_modules(maude, before)
    print("new modules:", fresh)
    print("current module:", maude.getCurrentModule())
    for name, _type in fresh:
        module = maude.getModule(name)
        print(f"getModule({name!r}):", module)


def scenario_init() -> None:
    maude = init()
    print("module count:", len(headers(maude)))
    print("first 10:", headers(maude)[:10])
    print("current module:", maude.getCurrentModule())
    print("getModule('NAT'):", maude.getModule("NAT"))
    print("getModule('NOPE'):", maude.getModule("NOPE"))
    print("getModule('nat'):", maude.getModule("nat"))


def scenario_load(path: str) -> None:
    maude = init()
    report_load(maude, path)


def scenario_missing_dependency() -> None:
    maude = init()
    report_load(maude, str(FIXTURES / "loads_missing_dependency.maude"))
    module = maude.getModule("LOADS-MISSING-DEP")
    print("LOADS-MISSING-DEP module object:", module)
    if module is not None:
        print("parseTerm('answer') in it:", module.parseTerm("answer"))
        print("parseTerm('1 + 2') in it:", module.parseTerm("1 + 2"))


def scenario_broken_recoverable() -> None:
    maude = init()
    report_load(maude, str(FIXTURES / "broken-recoverable.maude"))
    module = maude.getModule("HELLO-WORLD")
    print("HELLO-WORLD module object:", module)
    if module is not None:
        term = module.parseTerm("f")
        print("parseTerm('f'):", term)
        if term is not None:
            print("reduce steps:", term.reduce(), "| value:", str(term))


def scenario_broken_non_recoverable() -> None:
    maude = init()
    report_load(maude, str(FIXTURES / "broken-non-recoverable.maude"))
    print("getModule('HELLO-WORLD'):", maude.getModule("HELLO-WORLD"))


def scenario_no_module(path: str) -> None:
    maude = init()
    report_load(maude, path)


def scenario_two_modules(path: str) -> None:
    maude = init()
    report_load(maude, path)


SCENARIOS = {
    "init": (scenario_init, []),
    "load": (scenario_load, [str(FIXTURES / "hello.maude")]),
    "load-dependency": (scenario_load, [str(FIXTURES / "loads_dependency.maude")]),
    "missing-dependency": (scenario_missing_dependency, []),
    "broken-recoverable": (scenario_broken_recoverable, []),
    "broken-non-recoverable": (scenario_broken_non_recoverable, []),
}


def dispatch(name: str, args: list[str]) -> None:
    if name == "two-modules":
        scenario_two_modules(args[0])
    elif name == "no-module":
        scenario_no_module(args[0])
    else:
        scenario, scenario_args = SCENARIOS[name]
        scenario(*(args or scenario_args))


def main() -> None:
    if len(sys.argv) > 1:
        dispatch(sys.argv[1], sys.argv[2:])
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        two = tmpdir / "two_modules.maude"
        two.write_text("fmod FIRST is pr NAT . endfm\nfmod SECOND is pr NAT . endfm\n", encoding="utf-8")
        no_module = tmpdir / "no_module.maude"
        no_module.write_text("red in NAT : 1 + 2 .\n", encoding="utf-8")

        scenarios = [(name, args) for name, (_scenario, args) in SCENARIOS.items()]
        scenarios += [("two-modules", [str(two)]), ("no-module", [str(no_module)])]

        for name, args in scenarios:
            print(f"\n=== scenario: {name} ===")
            result = subprocess.run([sys.executable, __file__, name, *args], capture_output=True, text=True)
            print(result.stdout, end="")
            if result.stderr.strip():
                print("--- stderr ---")
                print(result.stderr, end="")
            print("exit code:", result.returncode)


if __name__ == "__main__":
    main()
