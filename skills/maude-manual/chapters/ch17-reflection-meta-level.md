# Chapter 17: Reflection, Metalevel Computation, and Internal Strategies

## Core Idea
Rewriting logic is reflective: a universal theory U can represent any finitely presented rewrite theory R, its terms, and its rewriting as *data and computation over data*. Maude implements the useful fragment of U efficiently in the `META-LEVEL` module: metarepresentations of terms/strategies/modules/views as Qid-based data, plus **descent functions** (`metaReduce`, `metaApply`, `metaRewrite`, ...) that drop a metalevel simulation back down to the object level so reflective towers stay cheap.

## Frameworks Introduced
- **The reflective tower & descent functions**: level 0 is your module's rewriting; level 1 is a metalevel module computing *about* it; each naive level-up multiplies cost. Descent functions perform the level-0 work natively, then hand back metarepresented results — the design trick that makes reflection practical.
- **Metarepresentations (META-TERM)**: sorts/kinds are Qids (Sort grammar excludes `:` `.` `[` `]`; Kind is `''[SortList']` e.g. `''[NzNat',Zero',Nat']`); constants are `'name.Type` (`'0.Zero`), variables `'N:Nat`; operator application is `'op['t1, ..., 'tn]` (`'__['$.Coin, 'q.Coin]`); `42` metarepresents as `'s_^42['0.Zero]` (decimal is sugar). It all iterates: metarepresentation of metarepresentation is just more terms; `getName`/`getType` selectors; ground-term subsorts.
- **Strategy & condition metarepresentation (META-STRATEGY / META-CONDITION)**: combinators mirrored one-for-one as `Strategy` constructors (`idle fail`, `'label[σ]{αs}`, `top`, `match_s.t._`, `_ ; _`, `_ | _`, `matchrew ... by ...`, `one(...)`; calls are `'name[[args]]`); equivalents for derived combinators (`_*`, `try`, `test`, ...) exist as special constructors. `EqCondition` constructors: `_=_`, `_:_`, `_:=_`, `_/\\_` (+ rewrite conditions `_=>_` for rules, sort `Condition`).
- **Module & view metarepresentation (META-MODULE / META-VIEW)**: module kinds `FModule < SModule < StratModule < Module` (+ `FTheory/STheory/StratTheory`); one big constructor per kind with *fixed slot order* (imports, sorts, subsorts, ops, memberships, equations, rules, strats) — no variable declarations exist at this level; selectors `getName/getImports/getSorts/getSubsorts/getOps/getMbs/getEqs/getRls/getStrats/getSds`; `[Q:Qid]` is cheap sugar referring to a loaded module in place (no lifting); views metarepresented with `SortMapping`/`OpMapping`/`StratMapping` sets and their selectors.
- **Lifting functions**: `upModule('M, b)`, `upSorts/upOpDecls/upMbs/upEqs/upRls/upStratDecls/upSds` — second argument includes (`true`) or excludes (`false`) imported statements; `upImports` (direct submodule list); `upView`. Polymorphic `upTerm(t)` returns the metarepresentation of t's *canonical form* (reduces first), and `downTerm(t↑, fallback)` un-metarepresents — falling back gracefully to arg 2 if the term doesn't belong to the current module (kind-level result).
- **Descent-function etiquette**: results pair a Term with (sort or kind): `ResultPair {t, T}` (`metaReduce`, `metaRewrite`, `metaNormalize`); `ResultTriple {t, T, σ}` (`metaApply` — top-only rule application with partial substitution and n-th-match enumeration); the extension-aware quadruple (`metaXapply`: adds matched context and position); `failure` = "operation valid, target unreachable" (a *supersort* value, not an error), while genuine ill-formed invocations stay unreduced at the kind level — the manual's "exceptions vs errors" split.
- **The full API surface** (see table): rewriting (`metaRewrite`, `metaFrewrite`), one-step application/matching (`metaApply`/`metaXapply`, `metaMatch`/`metaXmatch`), searching (`metaSearch`, `metaSearchPath` — returns a Trace), strategies (`metaSrewrite` with breadthFirst/depthFirst options + solution index), unification (`metaUnify` with mode Qid, `metaDisjointUnify`, `metaIrredundantUnify`), variants (`metaGetVariant`, filters), variant unification/matching (`metaVariantUnify`, `metaVariantMatch`, variant option sets), narrowing (`metaNarrowingApply`, `metaNarrowingSearch`, `metaNarrowingSearchPath`), SMT (`metaCheck`), parsing/printing (`metaParse` (noParse/ambiguity results!), `metaPrettyPrint`, `metaPrintToString`, `metaParseStrategy`, `metaPrettyPrintStrategy`), sort bookkeeping (`sortLeq`, `sameKinds`, `getKind`, `getKinds`, `lesserSorts`, `leastSort`, `maximalSorts`, `minimalSorts`, `maximalAritySet`), and the well-formedness validator (`wellFormed : Module ~> Bool`).
- **Internal strategies (17.7)**: strategy = ordinary Maude function over metarepresented terms, defined by equations over descent functions in a module `protecting META-LEVEL .` — e.g. `onlyCakes(T)` recursively `metaXapply`-ing rule `buy-c` (else `change`), equivalent to the object-level `(buy-c or-else change) !`. What internal strategies can do that the strategy language can't: be *generic over modules* (`innerRightmost(M, T)` via uniform rule-labeling), *examine all solutions* of a sub-strategy (`bestSolution` iterating `metaSrewrite` and picking the maximal one), and *return extra information* (matched context/substitution, counters) via extra function arguments.

## Key Concepts
- **`metaNormalize` vs `metaReduce`**: same computation except strategy attributes (`strat`) and statement attributes (`owise`, `print`) are ignored — use it to *inspect* a module's unconditional equational content without its execution-tuning.
- **Solution enumeration discipline**: solution-taking functions take a final `Nat` index — call with 0, 1, 2, ... until `failure`; efficient order guaranteed; passing a large index does *not* skip work arbitrarily but enumerates.
- **`Bound`**: `Nat` or `unbounded`, used by rewriting/search descent functions like command-line counters.
- **Error-handling idiom**: `metaXapply(...)` returns either `Result4Tuple` (check with `::`) or `failure`; `T? :: Result4Tuple then ... else ...` + `owise` = the standard internal-strategy recursion shape (see insertCoin/onlyCakes).
- **Metalevel ↔ model-checking stack**: everything in Ch 11–16 has a mirror here (`metaSearch`, `metaSrewrite`, `metaUnify`, `metaGetVariant`, `metaNarrowing*`, `metaCheck`) — this is *how* tools like meta-interpreters and theorem-prover front ends are written.

## Mental Models
- View META-LEVEL as a *typed API into the Maude engine*: your data is metarepresented syntax; the calls are engine operations; results come back as structured data — ideal for building tools (debuggers, translators, front ends) *in Maude itself*.
- Read `upTerm` as "canonicalize, then quote" and `downTerm` as "unquote, or complain": their symmetry-of-reduction design makes reflective round-trips semantics-preserving.
- Prefer the `[Q]` quoting sugar over `upModule` when only *referring* to a known-good loaded module inside a larger metalevel computation — lifting costs data you may never need again.

## Anti-patterns
- **Expecting `metaApply` to work at non-top positions**: by definition; use `metaXapply` for subterm application (and read the extra context/position info each solution carries).
- **Confusing `failure` with an error**: a `failure` answer is a legal, expected result (match/condition didn't hold); an unreduced kind-level term is the *real* fault (bad metarepresentation, unknown module, etc.).
- **Unrestricted reflective ascent without descent**: a metalevel loop simulating rewriting instead of calling `metaRewrite` once — towers are exponentially expensive by design, so always delegate to descent functions.
- **Reading raw `Module` sort terms as trustworthy**: garbage parses to `Module` just fine; validate with `wellFormed` before feeding computed modules into descent functions.
- **Assume `upTerm` is a quotation function**: it canonicalizes first (`f(a, f(b, c))` lifts as `'f['a.Foo,'f['b.Foo,'d.Foo]]` when `c = d`) — for pre-canonicalization insight that's a feature, for byte-level round-trips it is not.

## Code Examples
```maude
fmod BUYING-STRATS is protecting META-LEVEL .
  var T : Term . var Q : Qid . var N : Nat .
  vars BuyItem? BuyCake? Change? : [Result4Tuple] .
  op insertCoin : Qid Term -> Term .
  ceq insertCoin(Q, T) =
    if BuyItem? :: Result4Tuple then getTerm(BuyItem?) else T fi
    if (Q == 'add-q or Q == 'add-$)
       /\ BuyItem? := metaXapply(upModule('VENDING-MACHINE, false),
                                 T, Q, none, 0, unbounded, 0) .
  eq insertCoin(Q, T) = T [owise] .
endfm
```
- **What it demonstrates**: the canonical internal-strategy skeleton: matching equation binding the `metaXapply` result, `::`-sort test for success vs failure, recursion on `getTerm(...)` of the result, `owise` for bad input.

```maude
red in META-LEVEL : metaRewrite(upModule('VENDING-MACHINE, false),
                                '__['$.Coin, '__['$.Coin, '__['q.Coin, 'q.Coin]], 1) .
--- result ResultPair: {'__['$.Coin, '$.Coin, 'q.Coin, 'q.Coin, 'q.Coin], 'Marking}
```
- **What it demonstrates**: metarepresented term + module + bound → the level-1 twin of `rew [1] in VENDING-MACHINE : $ $ q q .`, including automatic sort recomputation.

## Reference Tables
| Level moving | Operation |
|---|---|
| up | `upModule('M, b)`, `upSorts/upOpDecls/upMbs/upEqs/upRls/upStratDecls/upSds('M, b)`, `upImports`, `upView`, polymorphic `upTerm` |
| down | `downTerm(t↑, fallback)` |
| refer | `[Q:Qid] : Module` (sugar for loaded module, no lifting) |

| Computation at object level | Level-1 call (all partial: `~>`) | Result sort |
|---|---|---|
| `reduce` | `metaReduce(M, t)` / `metaNormalize(M, t)` (no strategies/owise/print) | `ResultPair {Term, Type}` |
| `rewrite` / `frewrite` | `metaRewrite(M, t, b)` / `metaFrewrite(M, t, b, n)` | `ResultPair` |
| top rule application n-th match | `metaApply(M, t, 'label, σ, n)` | `ResultTriple? ({t, T, σ} \| failure)` |
| extension-aware application nth | `metaXapply(M, t, 'label, σ, n, depth, position)` | `Result4Tuple?` (term, type, sub, context+position) |
| `match`/`xmatch` | `metaMatch` / `metaXmatch(M, t, t', σ, n)` | `MatchPair?` |
| `search` | `metaSearch(M, t, t', cond)`, `metaSearchPath(...)` (sets a Trace) | `ResultTriple?` / `Trace?` |
| `srewrite`/`dsrewrite` | `metaSrewrite(M, t, Strategy, breadthFirst\|depthFirst, n)` | `ResultPair?` |
| `unify`/`variant unify` etc. | `metaUnify(M, problem, mode/Qid, n+n)`, `metaIrredundantUnify`, `metaDisjointUnify`, `metaVariantUnify`, `metaVariantMatch` (variant option sets) | `UnificationPair?` |
| ``get variants`` | `metaGetVariant(M, t, var-filter, n-of-sols...)` | `Variant?` |
| `vu-narrow` | `metaNarrowingApply`, `metaNarrowingSearch`, `metaNarrowingSearchPath` | dedicated `?` results |
| SMT `check` | `metaCheck(M, t)` | `Bool` |
| parsing/printing | `metaParse(M, tokens, T?)` → ResultPair? (`noParse`/`ambiguity` data!), `metaPrettyPrint`, `metaParseStrategy`, `metaPrettyPrintStrategy` | — |
| sort ordering | `sortLeq(T1, T2, M)`, `lesserSorts`, `leastSort`, `getKind`, `maximalSorts`, `minimalSorts`, `maximalAritySet` | — |
| validity | `wellFormed : Module ~> Bool` | `Bool` |

## Worked Example
Anatomy of an internal strategy — `onlyCakes` (strategy: "buy as many cakes as possible with inserted coins"):

```maude
op onlyCakes : Term -> Term .
ceq onlyCakes(T) =
  if BuyCake? :: Result4Tuple then onlyCakes(getTerm(BuyCake?))
  else if Change? :: Result4Tuple then onlyCakes(getTerm(Change?)) else T fi fi
  if BuyCake? := metaXapply(upModule('VENDING-MACHINE, false), T, 'buy-c, none, 0, unbounded, 0)
  /\ Change? := metaXapply(upModule('VENDING-MACHINE, false), T, 'change, none, 0, unbounded, 0) .
```

Mapped to `(buy-c or-else change) !` in the object-level strategy language (Sec. 10.1.1): each recursive call is one `or-else` pass; `::` tests replace strategy failure propagation; the final plain `T` return is the `!` fixpoint. The same section scales with `onlyNitems(T, 'buy-a, sd(N, 1))` (an index-bounded loop) and `cakesAndApples` (`(onlyNitems(a,1) ; onlyNitems(c,1)) !` at the object level), showing the entire expressiveness domain: recursion for `*`/`!`/limited iteration, `sd` for counters, `buyItem?` predicates for lookahead — all ordinary Maude equational programming on metarepresented terms. The chapter closes on what's *only* possible internally: module-generic strategies and global-solution selection (`bestSolution` scanning `metaSrewrite` output under a `_<_` measure).

## Key Takeaways
1. Reflection is the *computer science payoff* of rewriting logic's math: modules/terms/strategies/views are Qid-structured data, and the engine is callable through typed descent functions with structured results.
2. Learn the conventions once — `'name.Type`, kinds as `''[...']`, fixed module slots, `[Q]` references — because every Maude tool (ITP fronts, SCC/CRC drivers, meta-interpreters (Ch 19), your debugger ideas) speaks them.
3. Descent functions are the efficiency contract: delegate every object-level computation to them instead of simulating rewriting at a higher level.
4. `failure`-vs-kind-level is deliberate API design — handle both explicitly; `::`-type tests are the internal-strategy idiom.
5. Parsing, pretty-printing, and sort-order queries are part of META-LEVEL too: tools that *generate* Maude code (views, modules, strategies) can be written in Maude end-to-end.
6. Internal strategies = strategies as equations over META-LEVEL — strictly more powerful than the strategy language (generality, global solution inspection, extra outputs), at the cost of working with explicitly metarepresented terms.

## Connects To
- **Ch 7**: every module-algebra construct (imports, renamings, views, parameters) has a metarepresentation here; automation of module expressions is data manipulation.
- **Ch 5 / 9 / 11-16**: each user-level command has a metalevel twin (`metaRewrite`, `metaSearch`, `metaSrewrite`, `metaUnify`, `metaNarrowing*`, `metaCheck`...); Ch 9's `erewrite` itself is level-0 machinery whose metalevel counterpart arrives through meta-interpreters as external objects (Ch 19).
- **Ch 10**: strategy combinators mirror as `Strategy` terms (simple transformations smod↔data).
- **Ch 18 / 19**: LOOP-MODE is Maude's own META-LEVEL-powered read-eval loop; meta-interpreters extend exactly this machinery to fresh Maude instances.
- **Ch 21**: term coloring/tracing apply unchanged to meta-level computations driving them.
