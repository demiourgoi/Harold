# Research — which commands can produce paths (and how)

> The rough idea asks whether other commands would benefit from the same treatment as
> `search` paths. This note inventories the path-like facilities in Maude and in the
> bindings, for the commands Harold exposes today and for plausible future ones.

## 1. Summary

| Maude command | `maude_run` step today | Path-like data available? | Where |
| --- | --- | --- | --- |
| `search` | `search` | **Yes** — direct per-solution path thunk | `RewriteSequenceSearch` (bindings) |
| `rewrite` / `frewrite` / `erewrite` / `reduce` | yes | No. Only the final term and the rewrite counter. Maude's `trace` facility emits a trace, not a path to a solution. | — |
| `match` / `xmatch` | `match` | No. A match is a single step (with a context), not a sequence of states. | — |
| `srewrite` / `dsrewrite` | no | Yes, in the bindings: `StrategySequenceSearch` yields a path of terms interleaved with **transitions** that are either a rule application or an opaque strategy step, plus the strategy continuation. The CLI does not print paths for these commands. | `StrategySequenceSearch` |
| `vu-narrow` (narrowing) | no | Yes, but only when the `path` option (`NarrowingFlags.PATH`) is requested; the manual documents `show path` and `show path states` for it. Expensive (the flag description says "allow for narrowing trace reconstruction (expensive)"). | `NarrowingSequenceSearch3` |
| `modelCheck` (LTL) | no (reachable via `reduce` only if the module is loaded) | A counterexample/witness is a pair of transition lists (lead-in + cycle), each transition being `{state, ruleName}` — path-like but a different shape. | `MODEL-CHECKER` / `StateTransitionGraph` |
| `show search graph` | no | The whole search graph, not a per-solution path. Unbounded size, not suitable for an MCP result. | search object internals |
| `show path N` / `show path labels N` / `show path states N` | no | Requires a state number from a previous search in the same interpreter; useful only within one call. | CLI commands |
| `metaSearchPath` | no | The meta-level equivalent: returns a `Trace` of `{term, type, rule}` triples for a path, *excluding the final state*. | `META-LEVEL` |

## 2. `search` — the only command Harold runs that has paths today

The bindings give a path for every solution without any extra command (see
[`maude-bindings-search-path.md`](maude-bindings-search-path.md)). This is the v1 scope:
no CLI `show path`, no state numbers, no second search.

## 3. Rewriting and matching — no path

- `reduce`/`rewrite`/`frewrite`/`erewrite` apply a built-in strategy and return a single
  term plus a rewrite counter. Maude's `set trace` / `trace rewrite` facilities print a
  trace of applications, but the bindings do not expose a structured trace for these
  commands, and a trace is not "the path that reaches a requested solution".
- `match`/`xmatch` return substitutions (and a context function); there is no state
  sequence.

If a future feature wants "the rules applied by a `rewrite`", that is a different
problem (tracing), not search paths.

## 4. Strategy search (`srewrite` / `dsrewrite`) — path-like, different element type

The bindings' strategy search iterator yields:

```python
(term, substitution, path_thunk, strategy_continuation, rewrite_count)
```

and `pathTo(n)` interleaves terms with `StrategyGraphTransition` objects. A transition
is one of `RULE_APPLICATION`, `OPAQUE_STRATEGY` or `SOLUTION`; it exposes `getType()`,
`getRule()` or `getStrategy()`, and `str(transition)` prints the rule or the strategy.
The manual's §10.4 describes `srewrite`/`dsrewrite` output (results only, no path
printing).

Design consequence for v1: even though `maude_run` has no strategy-search step, a path
wire model should not assume every transition is a `Rule`. A generic transition
(`{rule: {...}}` now, optionally `{strategy: ...}`, or a flat `{kind, label, text}`)
keeps the door open without extra cost today.

## 5. Narrowing (`vu-narrow`) — path requires an opt-in flag

`EasyTerm.vu_narrow(type, target, depth=-1, flags=0)` accepts `NarrowingFlags.PATH`
(alias of `KEEP_PATHS`), described as "allow for narrowing trace reconstruction
(expensive)". The manual §15.6 and §15.6.5 document that the `path` option must be given
at the beginning of the `vu-narrow` command for `show path`/`show path states` to work.

Narrowing is not exposed by `maude_run`, and adding it is a separate feature; if it is
added later, path support would reuse the same wire model but with its own opt-in (the
flag is expensive, so always-on would be a poor default).

## 6. LTL model checking — counterexample lists, not paths

`modelCheck` returns `true`/`false` or a `ModelCheckResult`: `counterexample(leadIn,
cycle)` (or `witness`), where each list contains `{state, ruleName}` transitions. The
bindings expose `StateTransitionGraph` (`getStateTerm`, `getRule(origin, dest)`,
`getStateParent`) for this graph. This is a related but distinct feature (a cycle plus a
finite lead-in, and rule names may be `unlabeled`/`deadlock`), not a search-solution path.
`maude_run` does not expose model checking.

## 7. `show path` as a step command — possible but redundant and fragile

A design could add a `show_path` step that takes a state number and returns the path.
It would require:

- search steps to return `Solution N (state M)` numbers so the agent can reference one;
- the referenced search to have run earlier **in the same call** (state numbers are
  per-search and the interpreter is recycled after each call);
- a second command implementation and more session state;
- handling invalid/stale numbers as per-step errors.

The bindings already attach the path to the solution and state numbers are not durable,
so this adds surface without adding capability. It is only worth considering if state
numbers become useful for other reasons (e.g. a future `show search graph` step).

## 8. `metaSearchPath` — an alternative route, not needed

The meta-level `metaSearchPath(module, start, pattern, condition, type, bound, solNr)`
returns a `Trace` of `{term, type, rule}` triples leading to the solution, **excluding
the final state** (the solution term itself), and is documented to share caching with
`metaSearch`. Using it would mean metarepresenting the module and terms and re-running
search logic through `META-LEVEL`. The object-level `pathTo` is direct, already in hand,
and matches `show path` output, so the meta-level route is only a fallback if the
object-level API ever regresses.

## 9. Recommendation

1. Scope the feature to `search` solutions. It is the only command Harold runs that has a
   per-solution path today.
2. Model path transitions generically (a rule today; room for a strategy/opaque step
   later), so `srewrite`/narrowing can reuse the model without a breaking change.
3. Do not add a `show_path` step or expose state numbers: the path travels with the
   solution, and state numbers do not survive the call.
4. Keep `show search graph`, `modelCheck` and `metaSearchPath` out of scope.

## References

- Maude 3.5.1 manual, §5.4.3 (search and `show path`), §10.4 (`srewrite`/`dsrewrite`),
  §12 (LTL model checking, counterexamples), §15.6 and §15.6.5 (narrowing paths),
  §17.6.6 (`metaSearch`/`metaSearchPath`), Appendix A (command list).
- `maude-bindings/swig/term.i` (`StrategySequenceSearch`, `NarrowingSequenceSearch3`,
  `NarrowingFlags`), `maude-bindings/swig/misc.i` (`StrategyTransitionGraph`),
  `maude-bindings/swig/specific/python.i` (`StrategySequenceSearch.pathTo`).
