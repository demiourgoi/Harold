# Patterns — Maude 3.5.1 Manual

## Pattern: Soup/multiset state
**When to use**: distributed systems, object configurations, resource pools.
**How**: top sort with `__ [assoc comm id: none]`; singletons via subsort; rules mention fragments via variables (`M => M q`, never `null => q` — no extension from the identity).
**Trade-offs**: natural concurrency semantics + AC matching cost; nested structure invisible in pattern (think in fragments).

## Pattern: Module-as-accumulator (metalevel builders)
**When to use**: generating/transforming modules with equations (Mini-Maude, tool front ends).
**How**: function `extractSignature : Term ~> FModule` threading a partial FModule through recursive cases with addSort/addOpDecl/addImport/addEquations; then bubble resolution with the accumulated signature.
**Trade-offs**: draft-and-fill clarity vs. partiality (kind-level failures on malformed input).

## Pattern: Tag for the symbolic tier
**When to use**: using your equations in unify/variants/narrowing.
**How**: duplicate definitional equations as `[variant]`; tag collaborative rules `[narrowing]`; add `[nonexec]` for extra-RHS-variable generator rules; observe each tier's requirements (no `owise`; unconditional; coherence-with-variable forms like `q q q q M = $ M`).
**Trade-offs**: strategic separation of concerns vs double declarations to maintain.

## Pattern: variables-to-position control
**When to use**: rules needing top-level fairness (vending machines) or strategy locality.
**How**: add a ranging variable to force top (`$ M => c M` needs `__` top so `buy-*` beats `add-*` under `rewrite`); use `top(label)` in strategies; `matchrew <H, N> by H using α, N using top(inc)` for inner rewriting.
**Trade-offs**: explicit anchoring costs one positioning variable; forget it and rules starve (BB-TEST pathology).

## Pattern: import-mode honesty
**When to use**: extending modules over submodules.
**How**: protect only what inductively holds; extending for pure additions (new syntax), generated-by for new confusion; include when unknown; override diamond defaults explicitly when needed; `including` for rule/base-extension modules like CONFIGURATION with protocol overhead.
**Trade-offs**: nothing checked — errors surface as later theorem/proving surprises, not runtime bugs.

## Pattern: owise-closure
**When to use**: totalizing partial predicates/functions.
**How**: define positive cases by (conditional) equations; add `eq f(x̄) = default [owise] .`; keep `strat` effects in mind (owise applies only after the operator's final 0-position trial).
**Trade-offs**: compact totality (checks cleaner for formal tools may require explicit true/false duplicates).

## Pattern: named catch (enough-of-a-kind) in analysis modules
**When to use**: invariant checking, verification-state refinement.
**How**: patterns characterize violations structurally (`< s(N), s(M) >` for broken mutex; `=>!` for deadlocks); write predicates as `eq <X : C | attr: ...> C |= p = true .` + `owise` false; superset sorts (`ResultTriple?`/`failure`) discriminate outcomes via `::` tests.
**Trade-offs**: strong pattern = zero-predicate proofs but requires careful formulation by violation shape.

## Pattern: descent-function internal strategy
**When to use**: algorithmic execution control no strategy language idiom covers (generic over modules, best-solution selection, extra data flow).
**How**: in `fmod` over `META-LEVEL`, bind `metaXapply(M, T, label, none, 0, unbounded, 0)` via matching equation into a `[Result4Tuple]` var; recursion driving `getTerm`; `::`-test for failure; `owise` for invalid inputs.
**Trade-offs**: full power — at the price of working with metarepresented terms and correct lifted modules (`upModule('M, false)`).

## Pattern: lazy data via strategies
**When to use**: infinite structures on demand (SIEVE primes; big list prefixes).
**How**: constructor `_._ [assoc id: nil strat (0)]`; force-demand operators `strat (1 2 0)`; `show upTo n` case-splits via `if`.
**Trade-offs**: canonical forms become strategy-relative; termination guarantees are tangled with strategy proofs.

## Pattern: abstraction-driven finitization
**When to use**: verifying invariants on infinite-state systems.
**How**: add collapse equations `G` (e.g. `< s(s(N)), 0 > = < s(0), 0 >`); keep the extensions `E ∪ G` church-Rosser/terminating (MTT), protect Bool (no true/false equations; SCC); re-cohere rules (ChC); check the abstraction-kripke transition-sequence on the abstract system → conclude for the concrete.
**Trade-offs**: potential spurious counterexamples — refine G when found.

## Pattern: request/reply protocol objects
**When to use**: external I/O, distributed agents, process orchestration.
**How**: uniform message constructor `msg(...) [message]` (receiver first), reply messages named likewise (`getReq/getReply` pending-request sets via SET{Request}, pal attributes); keep replies pending on both process sockets; `waitForExit` before finishing.
**Trade-offs**: robust asynchronous object models — every component must obey name/freshness discipline; debugging entails tracing by protocol state, not just rules.

## Pattern: readability-preserving renames
**When to use**: application-specific views of predefined data; multiple same-base instances.
**How**: `protecting MAP{K, V} * (sort Map{K, V} to Dict{K, V}, op _[_] to lookup, op insert to update) .` — renaming transplants submodules consistently; renaming moves are typed with kinds ([Foo, Bar]) so subsort widening is respected.
**Trade-offs**: copies cost module-instantiation time — but reuse beats re-declaration.

## Pattern: honest grammar extension (bubble + solve)
**When to use**: embedding a DSL or extending Maude syntax.
**How**: define Token/Bubble sorts with `id-hook Bubble`; top-level grammar (MINI-MAUDE-SYNTAX) producing PreModule terms; extract signatures before solving equation-side bubbles (module-database order matters in meta-interpreters); `metaParse(M, downTerm(bubble, nil), anyType)` resolves.
**Trade-offs**: two-pass complexity — vs. unsafe single-pass parses that can't know user syntax.
