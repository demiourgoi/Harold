# Idea Honing — Port `maude_eval.py` into Harold

> Requirements clarification log for the rough idea in [`rough-idea.md`](rough-idea.md).
> Q&A are appended in order; the decision dates are recorded per question.
> Research that supports the answers: [`research/contribution.md`](research/contribution.md),
> [`research/placement.md`](research/placement.md), [`research/consumers.md`](research/consumers.md).

## Q1 — Go/no-go: is porting `maude_eval.py` worth it, and where would the capability live?

**Context.** `improve-rag/improvement/maude_eval.py` is the isolated evaluator of the repair loop:
a subprocess that loads a Maude file, parses/reduces a list of terms, returns the values as JSON
and separates load-phase warnings from term-phase warnings. Harold has the load half already
(`InterpreterDiagnosticProvider` + the worker's fd-2 capture) but nothing that evaluates a term.
The candidate design question was whether that half belongs in `maude_program_diagnostics` —
possibly as one more provider behind the diagnostics seam — or in a tool of its own.

**Answer (2026-09-16).** **Implement it, but not just now, and as a new tool.**

- *Worth it:* yes for the **capability** — evaluating terms against a loaded file is the missing
  semantic half of Harold's feedback loop and the seed of the project's second goal ("run Maude
  programs"). Diagnostics can only report what the loader and text heuristics see; it cannot say
  "this term reduces to 1024" or "this term no longer parses because you changed a signature".
  See [`research/contribution.md`](research/contribution.md) §2.1.
- *Not in `maude_program_diagnostics`:* the diagnostics tool is contractually "`{path}` in,
  problems with that file out" (v1 R2, LP4, LP8); term outcomes are data about a
  *(file, terms)* pair, have no position, and would force a second meaning into `success`,
  `summary` and the `DiagnosticSource` vocabulary. See [`research/placement.md`](research/placement.md) §2.
- *New tool:* a separate MCP tool (working name `maude_evaluate_terms`), one new worker op reusing
  `MaudeExecutor` for crash/timeout recovery, tagged with the already-reserved `interpreter` tag
  (`harold_mcp/server/tags.py` L29). `diagnostics/` stays untouched.
- *Timing:* **deferred** — this cycle produces the decision and the research record only; no code
  changes in `harold-mcp` and `improve-rag`. The work to resume is listed in
  [`summary.md`](summary.md) → Next steps.

**Alternatives considered.**

| Alternative | Why not now |
| --- | --- |
| Add an optional `terms` argument (and a term-evaluation provider) to `maude_program_diagnostics` | Breaks the documented schema (R2) and the "one composite tool, all providers attempted" rule (LP4); overloads `success`/`summary`/ordering with a second meaning. Rejected on design grounds, not just sequencing. |
| Port `maude_eval.py` faithfully, `improve-rag` compatibility included (same JSON, `===TERMES===` protocol, `times`, `rlapp_`/`arlapp_`) | The transport (subprocess per call) is superseded by Harold's worker pool, and the extra fields serve the research harness (ranking, rule-module conventions, TOML specs), which stays in `improve-rag`. See [`research/consumers.md`](research/consumers.md) §2. |
| Do nothing at all | Loses the semantic feedback loop, which is the main gap for models under-trained in Maude; the capability is wanted eventually, so the decision is "defer", not "reject". |

## Q2 — Tool shape: one tool per operation, one tool with an operation parameter, or one tool with a command list?

**Context.** The tool runs Maude interpreter commands against terms (at least `reduce` and
`rewrite`; `match` is under consideration). Three shapes are on the table. Deciding factors:
(a) every MCP tool carries its own description the LLM must read; (b) every tool invocation
spawns a fresh interpreter process (~0.6–1.2 s of spawn + prelude init, per the
`no_new_module_quirk` isolation-cost research), so multi-step computations split across
invocations pay that cost per step plus re-serializing intermediate terms through the client;
(c) the result payload differs per command (`reduce` → term + step count, `match` →
boolean/matches, a future `search` → term list), so any single tool needs a command-tagged
result model.

**Options.**

| Option | Shape | Pros | Cons |
| --- | --- | --- | --- |
| 1 | One tool per operation (`maude_reduce`, `maude_rewrite`, ...) | Each schema/description is small and command-specific; no tagged payload | N descriptions compete for the LLM's context; multi-step work costs one fresh interpreter + round-trip per step; the surface grows with every command |
| 2 | One tool + `command` parameter (single command per call) | One description; simple input | Multi-step work still costs per-call interpreters + round-trips; the result model must be a union of all command outcomes |
| 3 | One tool + `steps: list` of commands (pipeline), returning all intermediate results in order | One description; one call runs a whole REPL-like session on a single interpreter; a one-step list degenerates to option 2; matches the Maude REPL's current-term threading; easiest for a coding agent | Result model is a list of command-tagged step outcomes (still heterogeneous); the most design work |

**Recommendation: option 3.** It subsumes option 2 (a one-step list is a single command), avoids
option 1's description and round-trip overhead, and matches the user's observation that a
pipeline is "easier for a coding agent". The within-call interpreter is stateful (steps can
operate on the term produced by the previous step, REPL-style), while the call itself stays
hermetic.

**Answer (2026-10-17): option 3.** "A quite natural port of a bounded Maude interpreter
session": a single tool taking a list of commands (steps) and returning all intermediate
results in order. The within-call session is stateful (steps can operate on the term produced
by the previous step, REPL-style); the call itself stays hermetic. The user also added that
the tool should capture the Maude interpreter's output and return it as part of the result,
and suggested generalizing the `load_diagnostics` fd-2 capture in `worker.py` into a helper
that works for both diagnostics and the new commands, capturing **both stdout and stderr**
(recorded in the rough idea).

## Q3 — v1 command set

**Context.** With the step-list shape settled, which Maude interpreter commands does the tool
support in v1? Candidates from the `maude.Term` bindings and the Maude manual's Appendix A
(reduce/rewrite family): `reduce` (equational reduction to normal form), `rewrite` (rule
rewrites, bounded by a limit), `frewrite` (fair rewrite), `erewrite` (position-fair rewrite),
`match` (pattern matching against the current term), `search` (bounded reachability analysis).
Each command adds a step-outcome variant to the result model; `search` can return large
result sets and would force size caps into v1. The user's guidance: at least `reduce` +
`rewrite`; consider `match`; module-level functionality (strategy parsing) is out of scope for
now.

**Options.**

| Option | Commands | Assessment |
| --- | --- | --- |
| 1 | `reduce`, `rewrite` | Minimal; the result model stays small (term + step count); covers the `maude_eval`-style use cases (equational + bounded rule rewrites) |
| 2 | + `match` | Adds a boolean/substitution outcome; covers "does this pattern match the current term" checks for equation/rule debugging; the exact bindings API and semantics need a probe |
| 3 | + `search` | Reaches rule-based-program workflows (one-step successors, reachability) but drags bounded result-set caps and list-typed outcomes into v1 |

**Recommendation: option 2.** `reduce` + `rewrite` cover the original `maude_eval` scenarios
(equational modules and bounded rule steps); `match` is a scalar outcome that answers the
"does this rule's left-hand side apply" question cheaply. `search` (and `frewrite`/`erewrite`)
are natural v2 additions once the step/result scaffolding exists.

**Answer (2026-10-17): option 4 — all six commands in v1.** `reduce`, `rewrite`, `match`,
`search`, `frewrite`, `erewrite`. Rationale: once one operation is implemented, adding the
others should be easy, and the six-command surface is also a test of the interface's
extensibility. `search` therefore brings result-set caps into v1.

## Q4 — Step semantics: REPL-style current-term threading vs fully explicit subjects

**Context.** In the Maude REPL each command operates on a *current term* produced by the
previous command (e.g. `red f(3) .` then `rew .` rewrites the reduced result; `match P .`
matches pattern `P` against it). With a step list as input, the tool must decide where each
step's subject term comes from.

**Options.**

| Option | Semantics | Pros | Cons |
| --- | --- | --- | --- |
| 1 | REPL-style threading: each step's subject defaults to the current term (the previous step's result); a step may carry an explicit term/pattern to override it; the result echoes the current term after every step | Matches the Maude manual and REPL; pipelines stay concise; the client never has to paste back a possibly huge intermediate term | The client must understand the threading rule (documented in the tool description) |
| 2 | Fully explicit: every step carries its full term/pattern text; no hidden state | Each step is self-contained | "Then rewrite the result" forces the client to parse the previous result and re-send it verbatim — defeats the pipeline advantage and risks transcription errors on long terms |

**Recommendation: option 1.** It is the natural port of the bounded interpreter session (Q2)
and what the Maude manual documents; option 2 would undo the main benefit of the step-list
shape. The module is fixed for the whole call (call parameter), so the per-command `in M :`
syntax of the REPL is not needed.

**Answer (2026-10-17): option 1.** REPL-style current-term threading: each step's subject
defaults to the current term; a step may carry an explicit term/pattern override; the result
echoes the current term after every step. Module is a call parameter, so the REPL's
per-command `in M :` is unnecessary.

## Q5 — Load-warning policy

**Context.** `maude.load` reports warnings for problems the interpreter recovers from
(missing declarations, etc.), including warnings attributed to `load`/`in` dependencies.
`improve-rag` treats any load warning as "not usable" (refuses to evaluate); the Phase-1
research ([`research/placement.md`](../research/placement.md) §4.3) noted that an LLM-facing
tool probably wants both signals: the warnings *and* the values that could still be computed.
Every call is hermetic (~1 s of spawn + prelude init), so refusing wastes the call.

**Options.**

| Option | Policy | Assessment |
| --- | --- | --- |
| 1 | Always evaluate the steps; report the load warnings in the result | Simple; one call yields both signals; the agent decides whether to act on the warnings (e.g. by calling `maude_program_diagnostics`) | Values computed under a broken module can mislead if the agent ignores the warnings |
| 2 | Refuse to evaluate when the load produced warnings; return the warnings only | Follows `improve-rag`; keeps values trustworthy | Wastes the hermetic call; duplicates the diagnostics tool's job; the agent must make two calls anyway |
| 3 | Evaluate by default, with an input flag to require a clean load | Most flexible | An extra parameter to describe and implement |

**Recommendation: option 1.** The load warnings travel in the result (`loaded`-style field,
warnings listed with their files/lines, mirroring the diagnostics tool's attribution), and the
step outcomes follow. Trust decisions belong to the agent, which has `maude_program_diagnostics`
for a proper load check.

**Answer (2026-10-17): option 1.** Always evaluate; report load warnings in the result (with
the diagnostics tool's file/line attribution), followed by the step outcomes. Trust decisions
belong to the agent.

## Q6 — Input and output caps

**Context.** With `search` in v1 and a step list as input, caps protect the worker from
pathological inputs (exponential rewrite blow-up, huge `search` result sets, giant terms),
in addition to the timeout (next question). Caps are hardcoded constants in v1 (not
settings), documented in the tool description. Exceeding an *input* cap is an input
validation error; exceeding an *output* cap is a per-step "too large" outcome.

**Proposed caps.**

| Cap | Value | Behavior when exceeded |
| --- | --- | --- |
| Steps per call | 20 | input validation error |
| `rewrite`/`frewrite`/`erewrite` bound | ≤ 100 steps per step | input validation error |
| `search` solutions per step | 20 | fixed worker-side cap |
| Term/pattern text length | 10,000 chars | input validation error |
| Result term text length | 100,000 chars | per-step outcome "term too large to return" — never truncate: a truncated term cannot round-trip into a later call |

**Answer (2026-10-17): caps ×10, as `HAROLD_*` env-var settings with those values as
defaults.** Steps per call 200; `rewrite`/`frewrite`/`erewrite` bound ≤ 1000; `search`
solutions ≤ 200; term/pattern text ≤ 100,000 chars; result term text ≤ 1,000,000 chars.
Rationale: hardcoded caps fit nobody — Maude programmers often run expensive model checking
on powerful machines, so there is no one-size-fits-all; the caps become pydantic-settings
fields (like the worker settings) with these defaults (exact env names in the design).

## Q7 — Timeout settings: rename the existing one, add the interpreter one, per-call override

**Context.** Today `Settings.maude_worker_timeout_secs` (`HAROLD_MAUDE_WORKER_TIMEOUT_SECS`,
default `60`) is the single per-call timeout used by `MaudeExecutor._run_task` — it covers the
whole worker task including interpreter startup, and is best-effort. With a second tool, each
tool needs its own timeout: the user's framing is "interpreter timeout" vs "diagnostic
timeout", both covering the whole worker call (spawn + prelude init + work) and both
best-effort, both documented in the README. Additionally, each call to the interpreter tool
should be able to override its timeout.

**Proposal.**

1. Rename `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` → `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` (default `60`)
   — it is the diagnostics tool's timeout, and also the default for the worker-subsystem's
   own calls (the fail-fast init pings). Breaking rename, acceptable pre-1.0; README/CHANGELOG
   updated.
2. Add `HAROLD_INTERPRETER_TIMEOUT_SECS` (default `60`) for the new tool.
3. `MaudeExecutor._run_task` gains a per-call `timeout` argument (default: the diagnostics
   timeout); the interpreter tool passes its own timeout.
4. The interpreter tool takes an optional `timeout_secs` parameter (`gt=0`, no upper cap —
   legitimate model checking can run long) overriding the setting for that call.

**Answer (2026-10-17): yes, all four points accepted.** Rename
`HAROLD_MAUDE_WORKER_TIMEOUT_SECS` → `HAROLD_DIAGNOSTICS_TIMEOUT_SECS`; add
`HAROLD_INTERPRETER_TIMEOUT_SECS` (both default `60`, whole worker call including
interpreter startup, best-effort, documented in the README); `_run_task` gains a per-call
`timeout` argument; the interpreter tool takes an optional `timeout_secs` parameter (`gt=0`,
no upper cap).

## Q8 — Tool name (and annotations/tags confirmation)

**Context.** Annotations: the same read-only profile as `maude_program_diagnostics`
(`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`)
— as suggested in the rough idea and accepted. Tags: `harold_tags(INTERPRETER)` (the tag
reserved in `server/tags.py`).

**Name candidates.**

| Name | Assessment |
| --- | --- |
| `maude_run` | Concise; matches project goal #2 ("run Maude programs"); imperative, LLM-friendly |
| `maude_evaluate_terms` | The old working name; the tool is now a bounded interpreter session, more than term evaluation |
| `maude_interpreter_session` | Descriptive but long |
| `maude_eval` | Short but easily confused with diagnostics |

**Recommendation: `maude_run`.** The description (drafted in the design) must explain: the
bounded-session semantics (fresh interpreter per call, one main file + module, step list with
REPL-style current-term threading), the statelessness contract (state across calls is kept by
re-submitting a saved result term or by writing a wrapper module), per-command semantics and
caps, load-warning reporting, the `timeout_secs` override, and the captured interpreter output.

**Answer (2026-10-17): `maude_run`.**

## Q9 — Captured interpreter output: representation in the result

**Context.** The tool captures the Maude interpreter's output and returns it in the result;
the `load_diagnostics` fd-2 capture in `worker.py` is generalized into a helper that
redirects both stdout and stderr to temp files around a callable, used by diagnostics and by
the new op. (With Maude IO disabled in the worker, program output is limited, but bindings
warnings/echoes and any `print`-attribute output land here.)

**Options.**

| Option | Representation | Pros | Cons |
| --- | --- | --- | --- |
| 1 | Per-phase, two streams: `load: {stdout, stderr}` plus an `output: {stdout, stderr}` on every step outcome | Attribution: each step's noise travels with that step; mirrors the diagnostics load-phase capture | More fields in the result model |
| 2 | One pair for the whole call: `output: {stdout, stderr}` | Simplest | No attribution to steps |
| 3 | Per-phase, single combined text | Fewer fields | Loses the stream distinction (warnings are stderr; stdout/stderr order is not reconstructable from separate files anyway) |

**Recommendation: option 1.** The two streams stay separate strings (they are captured to
separate temp files; interleaving order cannot be reconstructed).

**Answer (2026-10-17): option 1.** Per-phase, two streams: `load: {stdout, stderr}` and an
`output: {stdout, stderr}` on every step outcome.

## Q10 — Per-step outcome vocabulary and pipeline failure semantics

**Context.** Each step returns a structured outcome. Command-specific success payloads plus
the failure markers below; a step failure is *data*, not an exception.

**Proposed statuses.**

| Status | Payload | When |
| --- | --- | --- |
| `ok` | `term` + `steps` (reduce/rewrite/frewrite/erewrite) | The command ran; `steps == 0` means the term was already irreducible / no rule applied |
| `ok` | `matched: bool` + substitution when the bindings expose one | `match` (the substitution's shape depends on the bindings API — to be confirmed in research) |
| `ok` | `solutions: [term, ...]` + `truncated: bool` (true when the solutions cap was hit) | `search` |
| `parse-error` | `message` (the interpreter's message from captured stderr) | The step's term/pattern does not parse in the module |
| `too-large` | `limit` | The result term exceeded the result-length cap |

The result term of every `ok` step becomes the current term for the next step (Q4).

**Pipeline semantics after a failed step.**

| Option | Semantics | Assessment |
| --- | --- | --- |
| 1 | Stop at the first failed step; return all outcomes so far (successes + the failure); the call itself succeeds | The agent sees exactly where the pipeline broke and fixes the input; no ambiguity about "result of step N" for later steps |
| 2 | Continue, keeping the current term unchanged (REPL-like) | Matches the interactive REPL, but later steps may depend on a result that never happened — confusing |
| 3 | Whole-call error on the first failed step | Loses the outcomes computed so far; treats expected events as exceptional |

**Recommendation: statuses as proposed + pipeline option 1.**

**Answer (2026-10-17): statuses as proposed + pipeline option 1**, to be made very clear in
the tool description so agents understand how to use it. Clarification confirmed with the
user: with 3 input commands where the 2nd fails, the result carries 2 outcomes — one for the
1st command (success) and one for the 2nd (failure); the 3rd is never executed and produces
no outcome (the outcomes list has one entry per executed step).

## Q11 — Whole-call failure conditions

**Context.** Per-step failures are structured outcomes (Q10); everything below is exceptional
and fails the whole call (the tool raises an error, following the repo's error-layering
convention: a tool-specific error type with `MaudeError` types chained as causes).

**Proposed whole-call failures.**

| Condition | Behavior |
| --- | --- |
| Path does not exist / is not a file | Input validation error (mirror `SourceFile.from_path` pre-check) |
| `maude.load` returns `False` | Whole-call error carrying the load-phase stderr (rare — per the empirical facts, `load` returns `True` for most garbage) |
| Requested module is not defined after the load | Whole-call error naming the requested module and the loaded path, suggesting `maude_program_diagnostics`; if the bindings expose an enumeration, the error may list the defined module names (research item) |
| Worker crash or timeout (incl. the per-call `timeout_secs` expiring) | Whole-call error wrapping the `MaudeError` as chained cause; executor semantics unchanged (pool replaced, the failed call is never retried — the MCP client retries) |

**Answer (2026-10-17): accepted as proposed.** All four conditions fail the whole call as
tool-level errors (`MaudeError` types chained as causes).
