# Maude 2.0 Primer — Patterns

## Subsort-Guard (NzNat pattern)
**When to use**: an operation has a precondition that is really a type property (non-zero divisor, non-empty stack).
**How**: declare a subsort (`subsort NzNat < Nat .`) and type the offending argument with it (`op _/_ : Nat NzNat -> Nat .`); add `cmb` to classify computed results into the subsort when needed.
**Trade-offs**: pushes errors from runtime into parse-time kinds; over-refinement forces extra membership axioms downstream (Ch 1, 2, 7).

## Constructor-Minimal Algebra (Peano discipline)
**When to use**: designing a data type module.
**How**: find the smallest set of value-generators, mark them `[ctor]` (0 and s; nil and concatenation), and define everything else as derived operations with equations.
**Trade-offs**: minimal constructors give a unique canonical form; convenience-constructors blur what reduction is supposed to reach (Ch 1, 2).

## First-Element-Rest Recursion
**When to use**: any equations walking a list-like structure (list, deck, queued states).
**How**: define the binary constructor with `assoc` (+`comm`/`id:` as semantics demand), then two equations: `eq f(nil) = <base> . eq f(E L) = <step(E)> <recurse on L> .`
**Trade-offs**: terminates in one direction; arbitrary `L1 L2` splits (middle-out) loop at the identity element (Ch 2).

## Accessor Equations over a Product Constructor
**When to use**: records/structs — one constructor holding several fields.
**How**: declare the tuple constructor `[ctor]`, then one equation per field: `eq CardNum(N of S) = N .` Variables pattern-match the pieces.
**Trade-offs**: cheap field access; changing the schema touches every accessor (Ch 2).

## Attributes-Before-Equations
**When to use**: the "law" is symmetric (comm/assoc) or is an identity.
**How**: use the flags `[assoc comm id: nil]` instead of writing `eq N + 0 = N .`-style laws, since flag-law equations are non-simplifying and non-terminating.
**Trade-offs**: `assoc`+`idem` cannot combine (write `eq E E = E .` for idempotency when both needed); identity flags beat identity equations under recursion (Ch 1, 2).

## owise Complement Dispatch
**When to use**: one branch of a case split is much easier to state than the other.
**How**: write the specific equations first, then the catch-all: `eq f(otherwise-pattern) = <default> [owise] .`
**Trade-offs**: order-free and terse; hides the logical condition inside matcher failure (Ch 2).

## Matching-Condition Dispatch (the := trio)
**When to use**: dispatching on term shape you cannot (or don't want to) enumerate as sorts.
**How**: any of three equivalent idioms — (1) `eq reply((S:String) ?) = "..." .` direct pattern; (2) `ceq reply(I) = "..." if (S:String) ? := I .`; (3) `ceq reply(I) = "..." if T := "value" .` with T as pattern.
**Trade-offs**: readable and declarative; abused, it hides control flow in matching (Ch 2).

## Configuration Soup (State combine)
**When to use**: dynamic systems with many coexisting state facts (crane states, cells, economies).
**How**: one combining constructor `op _&_ : State State -> State [ctor assoc comm id: 1] .`; laws match just the facts they need and produce replacement facts.
**Trade-offs**: elegant local rules and out-of-the-box multiset semantics; rewriting is nondeterministic and often non-terminating — always bound or search (Ch 3).

## Data-in-State Arguments
**When to use**: transitions must compute (counters, brands, weights).
**How**: hang the data on the state constructors: `rl [smoke] : c(X) => b(X + 1) .` rather than enriching the rule with conditions.
**Trade-offs**: keeps laws unconditional and aligns data flow with state flow; state terms get noisier (Ch 3).

## Search-Driven Planning
**When to use**: "can state X ever become state Y, and how?"
**How**: `search start =>+ target-with-variables .` (use `=>!` when the target must be terminal), read solutions' `(state N)` numbers, `show path N .` for the witness, read `M:State --> ...` substitutions for the variable fills.
**Trade-offs**: gives plans/counterexamples for free; cost grows with the state space — state the target as narrowly as possible (Ch 3).

## Kind-Level Salvage
**When to use**: a function should still compute over error terms (hybrid inputs).
**How**: declare the equations' variables at the kind level (`vars N M : [Dog] .`) so the same equations apply to well- and ill-sorted terms: `speed(breed(N, M)) = (speed(N) + speed(M)) quo 2 .`
**Trade-offs**: graceful degradation instead of dead `[Kind]` results; you lose sort guarantees inside those equations (Ch 2).

## LOOP-MODE Command Interpreter
**When to use**: building a custom prompt/sub-environment or DSL.
**How**: `inc LOOP-MODE`, initialize with `loop [nil, startState, nil] .`, write input-decode rules `proc ['cmd I, S, O] => [I, newS, O]` and output-encode rules, run by typing `(cmd)` at the prompt.
**Trade-offs**: full interactive power inside Maude; State threading and Qid quoting make debugging tricky (Ch 4).

## Message-Object Rule (attribute economy)
**When to use**: object-oriented modeling in `(omod ... endom)`.
**How**: `msg m : Oid ... -> Msg .`; rule pairs message with its addressee object, naming ONLY the attributes it reads or writes: `rl [sit] : sit@(A) < A : TABLE | occupied : false > => < A : TABLE | occupied : true > .`
**Trade-offs**: attributes ride along untouched — no bookkeeping; forgetting to name a written attribute silently drops it (Ch 4).

## Five-Piece Parameterization
**When to use**: the same structure will host multiple element types (lists, networks, stacks).
**How**: (1) theory (fth — contract); (2) frame module `(fmod M(X :: T) is ... endfm)` labeling `S(X)`/`X@S`; (3) parameter module; (4) view binding theory to parameter (`sort Node to Letter .`); (5) instantiation `pr M(V)` or `( select M(V) . )`.
**Trade-offs**: max reuse with compile-time plausibility checking; syntax is heavy and unforgiving — follow the three survival rules (declare labels up front, keep labels consistent, track every view) (Ch 5).

## metaApply Enumeration Loop
**When to use**: optimizing/searching over all ways a rule could apply.
**How**: recursive equation `op test : Nat -> Set . eq test(N) = if apply(N) == (failure).ResultTriple? then none else harvest(apply(N)) test(N + 1) fi .` incrementing the application index until failure.
**Trade-offs**: turns one law into an iterator over its matches (CIGARETTE-TEST); recursion depth = number of applications (Ch 6).

## Module Surgery Strategy
**When to use**: default strategies misbehave (a rule loops; you suspect an equation is unnecessary; rules need priority).
**How**: recurse over the meta-structures — strip labeled statements (`rmv`, `SANS`), tag with `metadata`, then descend: `rewriteExcept(M, T, 'A, N) = metaRewrite(sans-rule(M, 'A), T, N)`.
**Trade-offs**: strategies become first-class data programs; debugging is hard — decompose with small accessor helpers (getTerm-like) (Ch 6).

## up/down Round-Trip Check
**When to use**: writing metaterms or meta-modules by hand.
**How**: `red up(MODULE) .` and compare against your encoding; or run your hand-built metaterm through `down M : ... .` and compare with the original.
**Trade-offs**: cheap unit tests; must be run in the right level (up is Full Maude) (Ch 6).
