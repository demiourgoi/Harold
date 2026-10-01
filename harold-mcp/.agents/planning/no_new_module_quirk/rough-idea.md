# Rough idea — PDD: fixing the deferred `q .` warning quirk (isolation via `max_tasks_per_child=1`)

This is the Prompt-Driven Development record for fixing the bug analyzed in
[`README.md`](./README.md) (the deferred `q .` warning quirk). The project name
was chosen by the user: `no_new_module_quirk` (this directory).

## User's original message (the rough idea, verbatim)

We have found a bug on `.agents/planning/no_new_module_quirk/README.md`, please read that file to get some context.

### My thoughts on this

Setting `max_tasks_per_child=1` for the process executor has some negative impact in performance: e.g. the command
`opencode --prompt 'check for problems all the source files on /home/juanrh/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures'`
for the maude diagnostic tool calls doubles the tool exec time on informal manual experiments, but times are quite variable. That is for a
12th Gen Intel(R) Core(TM) i5-1245U with 12 logical cores and 16GB RAM.

One idea is doing the same that Maude would do: stop as soon as we find `q .` even if there is something in the same line after it.
This could be by manipulating the input program, e.g. copying it to a temp dir, and deleting all the text after the first `q .`.
But editing the file to simulate the `q .` seems flaky, and using a temp file can lead to wrong paths in diagnostics.

> [REPL transcript showing `q .  foo bar` quits Maude immediately]

The flush also looks like a good idea: could have a prebuilt empty file on `src/harold_mcp/assets`. But we do not need this if we do
isolation with `max_tasks_per_child=1`.

We must definitely fix the integration tests: currently these are designed to allow a bug.

Note `q .` is not a problem in Maude: is the usual way to write automated scripts, e.g. to launch a long running search, or to write a
test, or while working. We should not emit a diagnostic message just due to `q .`. `tests/integration/fixtures/no_new_module.maude`
is a correct program.

However we do not have true isolation this way: try to construct other failing examples due to that.

What about that as default for number of workers? Or half that? But in practice diagnostics of so much Maude files at the same time is
not so common.

Also what happens when a Maude file depends on another maude file, have we tested that? That would be required for a proper diagnostics:
one idea is accepting more than 1 file as the input for the diagnostics, or a list of dependency files that are only loaded, and then the
file we are actually diagnosing: that seems too complex, doing diagnostics for several files at the same time seems simpler and how a IDE
(e.g. IntelliJ) would work for a mainstream language (e.g. Java).

Also, can we fix this behaviour on maude-bindings? But that still does not provide diagnostics isolation, that is desired. Let's just
write a bug report proposal, with a minimal reproduction code in python, to send in a github issue.

Also, opencode told me this for `opencode --prompt 'check for problems all the source files on
/home/juanrh/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures'`. This is not admissible, we should reproduce this on a test,
in red-green-refactor style. Can isolation with `max_tasks_per_child=1` fix this?

> Checked all 17 fixtures with `maude_program_diagnostics` (non_linear_pattern re-run alone; the first pass had a spurious interpreter
> error because parallel calls race on the shared Maude interpreter — load diagnostics are only reliable when checks are serialized).

### Decisions

- Option A is the best one, because:
  1. it provides strong isolation, that is what we need for diagnostics;
  2. we are in an early stage of the project, we are on time to change the semantics of the tool, but this should be documented correctly
     in the tool description;
  3. it's ok if diagnostics is a bit slow, we are not diagnosing too many files concurrently, and the user has a knob in
     `HAROLD_MAUDE_WORKERS`, but that should be `os.cpu_count() / 2` by default now (what do you think? maybe 2 or 3 is a better option?);
  4. option C is too complex and brittle, option B is unnecessary if we do A, option D is discouraging a perfectly fine language construct.
- We must definitely fix the integration tests: currently these are designed to allow a bug.
- Try to construct other failing tests that capture isolation bugs, in red-green-refactor style.
- Same for the opencode claim that "load diagnostics are only reliable when checks are serialized", if needed use pytest-repeat or
  similar to try and capture a race condition.
- We also have to deal with the idea of "Also what happens when a Maude file depends on another maude file, have we tested that?".
  Write a test to reproduce the issue, apply red-green-refactor.
- Write a bug proposal for this problem, with a minimal reproduction code in python, to send in a github issue for maude-bindings.

## User's process directive

> let's do a quick PDD project for this on `.agents/planning/no_new_module_quirk`. The requirements are clear, so go ahead with the research.

The user judged the requirements complete (no clarification needed) and directed the process to start at the research step.
