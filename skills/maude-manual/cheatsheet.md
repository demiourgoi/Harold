# Cheatsheet — Maude 3.5.1 Manual

## Which module kind?
| Goal | Use |
|---|---|
| functions / data (deterministic) | `fmod` |
| concurrent transitions / nondeterminism | `mod` |
| objects, messages, classes | `omod` (sugar for `mod` on CONFIGURATION) |
| reusable algorithm over rules | `smod` (strategies) |
| parameter interface | `fth` (functional reqs), never imported into a module |

## Rewrite/search decision
```
ask?                          execute?
├─ one run, top-fair────────── rewrite [n]
├─ one run, reaches starved── frewrite [n, k]
├─ external objects involved─ erewrite  (+ portal <> in config)
├─ execute a policy───────── srew/dsrew using α   (strategy world)
└─ collect all runs/patterns─ search [n, m] init =>1/=>+/=>*/=>!/=># pattern [such that cond]
```
- `=>!` asks "deadlocked/terminal?" — use it or `=>#` for trouble-shapes.
- Never unbounded `search` unless known finite; `=>+` with bounds is safer in big systems.

## Unification tier picker
| You need | Command | Equations honored? |
|---|---|---|
| structural solve | `match/xmatch` | only as reductions |
| solve modulo attributes (A, AC, ACU, iter...) | `unify [n]` / `irredundant unify` | no (attributes only) |
| solve modulo declare mxl equations | `variant unify`/`filtered variant unify` (needs [variant] + FVP) | yes |
| E ∪ Ax matching (one side ground) | `variant match` | yes |
| symbol reachability with rule (symbolic init states) | `{fold/vfold,path} vu-narrow` (+ `[narrowing]` rules) | yes (`[variant]`) |

## Strategy combinator quick picks
- "A else B (A first): `A or-else B`"  • "loop until stuck": `α !`  • "optional α": `try(α)`
- "dive into a subterm": `matchrew P(X) by X using α` (add `top(...)` to avoid inner rule fanout)
- "one answer, fast": `one(α)` — but only if answers are interchangeable (never `one(move)*` — you loop)

## Importation mode cheats
- **protecting**: no new data, no identified old data (most user data-type imports).
- **extending**: new junk allowed, no confusion (syntax growth, conf extensions).
- **generated-by**: no junk, maybe confusion (`NAT/3`-style quotients).
- **including**: no claims — when in doubt use `including` (never make a false claim).
- Others' modes transitively stick unless you override: diamond defaults resolve strongest-wins.

## Common failure smells → first probes
| Smell | Probe |
|---|---|
| canonical form keeps symbols | `set print color on .` — red/magenta = bug locus |
| rule never fires | trace it (`trace select my-rule`) — check starvation vs `rewrite`; try `frewrite` |
| nontermination | loop? — look for reifiable cycle patterns (`f(X,Y)=f(Y,X)` styles); missing orientation; use `strat` or strategies |
| wrong answer from conditions | trace conditions; remember left-to-right + all matches may be tried |
| search hangs | non-finite reachable set — bound `[n,m]`, abstract, or recheck coherence assumptions |
| unify returns `No unifier` with `mb`-defined sort | memberships are ignored in Ax-unification — restate without them |

## Toolchain duties (all user-owned, Maude trusts you)
- termination (MTT), confluence (CRC), sufficient completeness (SCC), coherence (ChC) — required by claims of protecting/fvp/symbolic tiers; treat "no warnings" as "unproven", not "true".

## Attribute-quick map
- never write `eq f(X,Y) = f(Y,X)` for commutativity — declare `[comm]`.
- `assoc + idem` forbidden → write `eq N ; N = N` explicitly.
- `id:`/`idem` patterns may collapse unexpectedly (`f(X, a)` matches `a` with `X ↦ e`) — prefer tighter-sorted pattern variables.
- divide-and-conquer cost → `[memo]` (memory trade-off).
- membership axioms don't fold into `assoc`/`iter` sorts — declare operators at kind level and give sort by `mb` (or use subsorted overloads).

## Command hygiene for long runs
- `set show timing/stats off` for silent scripting; `set profile off` whenever done profiling.
- SIGINFO (Mac `^T`) / `kill -USR1` for status, never `^C` while external objects run (breaks their events).
- label everything (`rl [name] ... [label ...]`) — counters, traces, and breakpoints are name-driven.
