# Chapter 21: Debugging and Troubleshooting

## Core Idea
Four families of tools — tracing, term coloring, an interactive re-entrant debugger, and a profiler — expose what the interpreter actually did; plus a catalog of "traps": known interactions of attributes/memberships that surprise even experienced users. The chapter is where Ch 3–5's warnings become hands-on diagnosis procedures.

## Frameworks Introduced
- **Tracing (21.1.1)**: `set trace on .`; selective tracing `set trace select on . trace select foo bar ([_,_]) .` (labels **or** operator names; objects need not exist yet — metaprogramming-safe), module exclusion `trace exclude FOO BAR .`; and a set of `set trace ...` switches — mute equations (`set trace eq off .`), mute memberships (`mb off`), hide conditions (`condition off`), whole-term display (`whole on`), substitutions off, etc. Trace output shows per application: the statement tried (with trial numbers), the matching substitution, condition-fragment solving (`/\`-pieces evaluated left to right, failure discards the trial), success + rewritten terms, and built-in equations (e.g. `_>=_`) appearing inline. **The rewrite bound counts rules only** — equations run unbounded, so a `[1]`-bounded trace can show many steps.
- **Term coloring (21.1.2)**: `set print color on .` paints re-executed terms by reduction status (needs honest `[ctor]` usage): reduced ctor = plain; reduced non-ctor with strangeness below = **blue** (secondary damage); reduced non-ctor clean below = **red** (bug locus); unreduced with no reduced above = green (pending); unreduced under a directly reduced parent = **magenta** (bug locus); under a deeper reduced ancestor = cyan. Read red/magenta as "start here", blue/cyan as consequences. (`format`-attribute colors are ignored in this mode.)
- **The debugger (21.1.3)**: three entries — `^C` during rewriting, `debug` command prefix (`debug rew bankConf .`), break points (`set break on . break select debit .`). Fully re-entrant (`Debug(2)>` after entering from `Debug(1)`); breakpoints persist across `resume` until `set break off`. Four debugger commands: `where .` (stack of pending rewrites with provenance — top-level command, condition fragment being checked, …), `step .` (one rewrite, traced), `resume .`, `abort .`. Entering the debugger at a condition shows e.g. `Current term is: 300 >= 150 which arose while checking a condition ...`.
- **Status report (21.1.4)**: out-of-band peek without `^C` (which disturbs files/sockets): `^T` / `kill -INFO` (Mac), `kill -USR1` (Linux) → current time, rewrite counts, activity summary on stderr.
- **The profiler (21.1.5)**: `set profile on .` counts per-statement executions and per-condition-fragment statistics (initial tests, backtracking tests, successes, failures); `show profile .` displays; `set profile off .` when done (profiling slows execution substantially). Use it to compare algorithm variants: e.g. `mergesort` vs `insertion-sort` vs `improved-insertion-sort` on sorted lists (measured rewrites vs runtime; memoized `fibo` revisited: memo wins big but trade-offs exist).
- **Strategy debugging (21.2)**: same instrumentation on `srew`/`dsrew`: `set trace sd on/off .` gates strategy-definition usage; `set trace whole on .` shows the subject; trace lines include the definition applied, call term, and matching substitution; label strategy definitions (`[label moveAll]`) for `trace select`/`break select`. Interleaving warning: `srewrite` explores fairly (paths interleave in the trace — the 8-queens trace shows `1 2 4` expanded only after other continuations), `dsrewrite` is depth-first and gives near-path traces (17 calls vs 140). `debug srew` and breakpoints work identically.
- **Traps catalog (21.3)**: see Reference Tables.

## Key Concepts
- **Strangeness**: unreduced/nonconstructor content in a canonical form — coloring localizes where it *started*, which raw greps cannot.
- **Trial/success trace structure**: conditional statements show numbered trials — a failing condition fragment is normal control flow, not necessarily an error.
- **Trap fixes recap**: explicit idempotency equation instead of `[assoc idem]` (ignored silently!); kind-level declarations + membership axioms to restore expected sort computation for `assoc`/`iter` operators; avoiding identity-topped lefthand sides or lowering pattern variable sorts below the identity; `ulimit -s` for legitimate deep recursion.
- **Status-report etiquette**: prefer SIGINFO/USR1 over `^C` for long runs — use `^C` only when you *want* the debugger, since interrupts external-event states.

## Mental Models
- Read tracing as *narrating the interpreter*, the debugger as *pausing it*, coloring as *blaming the output*, profiling as *billing each statement* — four orthogonal instruments; pick by symptom (wrong step vs wrong branch vs unreducible garbage vs slow).
- Read the traps section as the manual's own "known gotchas" FAQ — recheck against it before blaming your logic, since every one of them fails silently or with a cryptic warning.

## Anti-patterns
- **Tracing unbounded runs raw**: `set trace ...` your way in (`select`, `condition off`, module `exclude`) before anything big; capture logs with `script`/xterm logging.
- **Diagnosing with a `[1]`-bounded trace then miscounting**: the bound rules out only rule rewrites — equations keep applying; don't read "rewrites: 4" for a `[1]` as a bug.
- **Using `[assoc idem]` anyway**: `idem` is silently dropped — the symptom is duplicates surviving in results; write the `eq N ; N = N .`
- **Identity elements at the top of lefthand sides**: collapse matching (`f(X, a)` also matches `a` with `X ← e`; with `idem`, subterm duplication can be nonterminating); prefer tighter pattern sorts or strategies for such rewrites.
- **Sort-level assoc/iter declarations needing subterm memberships**: memberships apply only at top during sort computation — workaround: kind-level declaration + membership for the sort-level effect, or all-membership style lists.
- **`idem`-poisoned sorts should not rewrite by equations**: constructors (+comm etc.) only; defined functions may *analyze* them, but rewriting the terms themselves under equations is unsound with the current implementation.

## Code Examples
```maude
Maude> set trace on . Maude> set trace eq off .
Maude> trace select transfer .   --- watch only the transfer rule
Maude> set trace substitution off .
Maude> rew bankConf .

--- And the debugger round:
Maude> set break on . Maude> break select debit .
Maude> rew bankConf .
break on labeled rule: crl [debit] : debit(A:Oid, M:Nat) < ... >
Debug(1)> where .      --- pending-rewrite stack with provenance
Debug(1)> step .        --- exactly one traced rewrite
Debug(1)> resume .      --- continue; abort . to discard the run
```
- **What it demonstrates**: the complete toolkit workflow — selective trace → controlled pause → stack inspection → single-stepping.

## Reference Tables
| Tool | Turn on | Key commands |
|---|---|---|
| tracing | `set trace on .` | `trace select l1 (op) .` / `trace exclude MOD .`; `set trace eq/mb/rl/sd/condition/whole/substitution on/off .` |
| term coloring | `set print color on .` | red/magenta = bug locus; blue/cyan = secondary; green = pending |
| debugger | `^C`, `debug ⟨command⟩`, `break select ⟨labels⟩` | `where . step . resume . abort .`; `set break off .` |
| status report | `^T` (Mac) / `kill -USR1 ⟨pid⟩` (Linux) | reads time, counts, activity |
| profiler | `set profile on .` | `show profile .` — counts + condition-fragment stats |

| Trap (21.3.n) | Symptom | Remedy |
|---|---|---|
| assoc+idem | duplicates persist; attribute silently ignored | write `eq N ; N = N .` (idem is poison — see notes) |
| internal errors | "Maude internal error" / self-check failure | report with crash.maude; don't mix prelude versions |
| stack overflow | "Fatal error: stack overflow" | infinite loops vs deep legal recursion → `ulimit -s` |
| bare variable LHS | mysterious nontermination (memberships on every Nat!) | keep for `[nonexec]`-strategized statements only |
| overloading vs assoc | warnings: kinds clash / "because of associativity" | one top-sort declaration covering all arities, or full overload coverage |
| preregularity modulo attributes | sorted flattenings disagree (`(s1,s1,s2)` trouple) | unique top-sort declaration or complete overload set |
| collapse theories | `f(X, a)` matches `a`; unbounded duplication under `idem` | rethink patterns; strategy-drive rewrites of poisoned sorts |
| assoc+one-sided identity | matches "portions that were not apparent" | understand: those matches simulate equivalence-class rewriting |
| memberships × assoc/iter | sorts wrong on subterms; once-per-module warning | kind-level `op ... ~> ...` + membership for the sort-level effect |
| print ambiguity | `print` attribute format items ambiguous | check attribute-formatted vars (21.3.10) |

## Worked Example
Profiling a slowdown (Fibonacci, then sorting variants): enable the profiler and compare:
```
Maude> set profile on .
Maude> red fibo(30) .            --- shows dizzying eq counts for fibo's two recursive calls
--- after adding [memo] to fibo: counts collapse; compare before/after
Maude> show profile .
Maude> red insertion-sort(...) . --- vs mergesort(...): counts per statement,
--- condition fragment stats (initial vs backtracking vs success) tell you
--- why (e.g. repeated failed matching in leq-elems), guiding the rewrite.
Maude> set profile off .
```
Read the condition-fragment table closely: high *backtracking* counts with low *success* counts mean your conditional equations are searching combinatorially — the signature of an overgeneral pattern; high `trial` counts on built-ins mean missing cases. Profiles convert "feels slow" into "these three statements, in this order, are your bill."

## Key Takeaways
1. Tracing with selection and per-kind switches scales to real modules; the debugger's `where`/`step` pair turns a pain point into a checkpoint.
2. Term coloring turns sufficiency-completeness bugs from needle-in-haystack into color-coded blame; it needs disciplined `[ctor]` annotation.
3. Profilers quantify — use them before optimizing, compare variants after; remember profiling itself costs.
4. Strategy debugging mirrors everything (`sd`-traces, breakable definitions) — but expect `srew`'s interleaving and prefer `dsrew` for comprehension.
5. The traps catalog names the silent/quiet failure modes (assoc+idem ignored; collapse matching; membership/sort interactions on assoc/iter); re-check it before debugging your own axioms.
6. Interrupt-less status reports (SIGINFO/USR1) protect external-object work from `^C` collateral damage.

## Connects To
- **Ch 3–5**: the warnings issued at parse time (preregularity, overloading, advisories on object-module transformation and collapse) reappear here as diagnosis.
- **Ch 4 / 7**: `ctor` discipline feeds coloring; SCC/termination tools close the loop on strangeness.
- **Ch 9**: interrupts and external-event states - why status reports exist.
- **Ch 10 / 17.7**: strategy tracing/breakpoints; internal strategies are just equations and trace the ordinary way.
- **App A**: full option tables for trace/break/profile/print settings.
