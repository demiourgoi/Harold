# Chapter 1: Introduction

## Core Idea
Maude is a declarative language in the strict sense: a program is a logical theory and a computation is logical deduction. Its design simultaneous maximizes simplicity, expressiveness, and performance — the same module serves as program, executable formal specification, and verifiable mathematical model.

## Frameworks Introduced
- **The three-dimension design triad**: simplicity, expressiveness, performance judged together; expressiveness is the key dimension because languages are representational devices.
  - When to use: evaluating any design decision in a Maude module.
  - How: prefer the representation that makes the problem natural (mixfix syntax, equational matching, subsorts), not the one that pleases a compiler.
- **Equations vs. rules (functional vs. system modules)**: equations (`eq`/`ceq`) are simplification rules applied left-to-right with deterministic final values; rules (`rl`/`crl`) are local concurrent transition rules with no determinism assumption.
  - When to use: functions/data → equations in a functional module (`fmod`); concurrent/nondeterministic system behavior → rules in a system module (`mod`).
  - How: express data canonically with equations first, then add rules for transitions.
- **Program = theory, computation = deduction**: every module denotes its intended mathematical model — the *initial* algebra `T_Σ/E∪A` (functional) or initial model `T_R` (system), an algebraic labeled transition system.
  - When to use: whenever you reason about what a module "means" or verify a property; satisfaction is always satisfaction in the initial model.
- **Agreement theorem (math semantics = operational semantics)**: under executability conditions — Church-Rosser + termination (functional) and coherence (system) — the canonical term algebra computed by the interpreter is isomorphic to the initial algebra. This is what makes the same module both a specification and its own implementation.
- **Three uses of a module**: (1) as a program, (2) as an executable specification/prototype, (3) as a model to be analyzed — e.g., termination, Church-Rosser, invariants, temporal-logic properties. Specification/code distinction is "in the eyes of the beholder".
- **Maude as a high-performance metalanguage**: not a domain-specific language but a metalanguage in which many DSLs, formalisms, and other logics can be represented, thanks to mixfix syntax and reflection.

## Key Concepts
- **Functional module**: program of equations only; specifies a theory in membership equational logic, `(Σ, E ∪ A)`.
- **System module**: specifies a rewrite theory `R = (Σ, E ∪ A, ϕ, R)` in rewriting logic; `ϕ` is the frozen-argument function.
- **Equational simplification**: "replacement of equals by equals" oriented left-to-right.
- **Rewrite theory 4-tuple**: signature `Σ` (sorts, subsorts, kinds, overloaded operators), equations `E`, equational attributes `A` (assoc, comm, …), freezing `ϕ`, rules `R`.
- **Multiset rewriting**: configuration "soup" with empty-syntax multiset union declared `[assoc comm]`; rules match and apply anywhere in the soup.
- **Equational pattern matching**: each operator is matched modulo its declared equational attributes (A-C matching, identity, idempotency).
- **Mixfix syntax**: underscores mark argument positions (`_._`, `__`, `if_then_else_fi`); keeps representations close to original syntax.
- **Sorts vs. kinds**: sorts = well-defined data; kinds include error elements → partial functions in a total setting (`4 + 7/0` stays at the number kind).
- **Conditional membership**: `cmb (P ; Q) : Path if target(P) = source(Q) .` — sorts defined by equational conditions.
- **Parameterized modules/theories**: parameters are theories (e.g., `TOSET`) with semantic requirements, not just type placeholders; analogous to parametric polymorphism plus dependent types (e.g., `NAT mod n`, arrays of length `n`).
- **Sublogic inclusion**: membership equational logic embedded in rewriting logic; a functional module is the degenerate rewrite theory with no rules.
- **Church-Rosser & termination**: the executability assumptions making equation application confluent and finite.
- **Coherence**: the condition guaranteeing that simplifying to canonical form before applying rules misses no possible rule application.
- **Descent functions**: reflective computations push metalevel work down to the object level (efficient; linear representation-change cost at the boundaries only).
- **Memo attribute**: operator-level result caching that trades space for time.

## Mental Models
- Use the **soup model** when modeling distributed systems: objects and messages float in an unordered multiset; a rule is a local concurrent interaction, and A-C matching lets partners "find" each other regardless of placement.
- Think of Maude's interpreter as **computing in the canonical term algebra** — its output *is* the mathematical result, provided your module is Church-Rosser and terminating.
- Use equations for "what data is", rules for "what can happen next" — never rules to define a function's value.
- Treat Maude as a **metalanguage**: when embedding another language/logic, keep its surface syntax via mixfix operators rather than inventing encodings.

## Anti-patterns
- **Expecting rewrite rules to be deterministic or confluent**: rules are transitions; different orders may give different outcomes (e.g., debits failing for insufficient funds depending on order).
- **Mixing equations freely with rules without coherence**: simplifying eagerly before rewriting can miss rewrites that were possible en route.
- **Declaring a function on a sort when its results are only at the kind level**: partiality must be intentional; undefined-on-those-arguments is the kind reading.
- **Associativity combined with idempotency**: not supported in one operator's attributes.
- **Verifying against an arbitrary model**: properties hold or fail *in the initial model* — the module's denotation, not some convenient algebra.

## Code Examples
```maude
op nil : -> List .  op _._ : Qid List -> List .
op length : List -> Nat .  op _in_ : Qid List -> Bool .
vars I J : Qid .  var L : List .
eq length(nil) = 0 .
eq length(I . L) = s length(L) .
eq I in nil = false .
eq I in J . L = (I == J) or (I in L) .
```
- **What it demonstrates**: a functional module fragment — equations as simplification rules define `length` and membership; evaluation `length('a . 'b . 'c . nil) → s s s 0` is equational rewriting.

```maude
var I : Qid .  vars N M : Nat .
rl  < I : Account | bal : M > credit(I, N)
 => < I : Account | bal : (M + N) > .
crl < I : Account | bal : M > debit(I, N)
 => < I : Account | bal : (M - N) > if M >= N .
```
- **What it demonstrates**: local transition rules over object-message soups; the debit rule is conditional — concurrent, order-dependent outcomes are the intended semantics, not a bug.

## Reference Tables
| Dimension | Functional module (`fmod`) | System module (`mod`) |
|---|---|---|
| Statements | equations + memberships (`eq`, `ceq`, `mb`, `cmb`) | as functional, plus rules (`rl`, `crl`) |
| Logic | membership equational logic `(Σ, E ∪ A)` | rewriting logic `R = (Σ, E ∪ A, ϕ, R)` |
| Computation | equational simplification (deterministic) | simplification intermixed with rule application (concurrent, nondeterministic) |
| Intended model | initial algebra `T_Σ/E∪A` = canonical term algebra if Church-Rosser + terminating | initial model `T_R` = algebraic labeled transition system; needs coherence |
| Typical use | functions, data types | distributed systems, concurrent processes |

## Worked Example
Bank-account soup, walked end-to-end. State (order immaterial, multiset union `__` declared `[assoc comm]`):

```
< 'A-001 : Account | bal : 200 > < 'A-002 : Account | bal : 150 > credit('A-002, 50) debit('A-001, 25)
```

Both rules apply concurrently to disjoint fragments; after applying each once:

```
< 'A-001 : Account | bal : 175 > < 'A-002 : Account | bal : 200 >
```

The lesson: the same state allows multiple runs (debit first vs. credit first matters if balances are tight), matching is modulo A-C anywhere in the soup, and the transition system of *all* such concurrent computations is exactly the initial model `T_R` denoted by the system module.

## Key Takeaways
1. Maximize expressiveness first; Maude is a metalanguage, not a fixed DSL — mixfix syntax, equational matching, subsorts, parameterized theories, objects, and reflection are the levers.
2. Equations define deterministic data computations; rules define concurrent system transitions; functional modules are the special degenerate case of system modules with no rules.
3. A module denotes its initial model; under Church-Rosser + termination (+ coherence for rules) the interpreter's results coincide with the mathematics — this is the license to treat the running program as a formal specification.
4. Equational attributes (`assoc`, `comm`, identities, idempotency) are matched modulo by generated algorithms — data like lists, multisets, and sets are *specified*, not coded.
5. Reflection is made practical by descent functions: metalevel computations run at object level, paying representation change only at the boundary.
6. Most of this manual also appears in *All About Maude* (Springer LNCS 4350), which has more examples and applications.

## Connects To
- **Ch 3**: sorts, kinds, mixfix operator declarations get their precise syntax treatment.
- **Ch 4**: functional modules, executability (admissible modules), matching modulo; the Church-Rosser conditions assume concrete form.
- **Ch 5**: system modules, rewrite/frewrite/search commands, and the coherence criterion for admissible modules.
- **Ch 6**: the object notation `< I : Class | attr : value >` and fair object-message rewriting.
- **Ch 7**: theories and views — the parameterized-module machinery behind `TOSET`-style requirements.
- **Ch 17**: META-LEVEL and descent functions make the reflection story concrete.
