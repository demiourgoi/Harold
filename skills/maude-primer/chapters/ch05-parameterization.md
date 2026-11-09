# Chapter 5: Parameterization

## Core Idea
Parameterization is the "electrical outlet" pattern: a permanent frame (a parameterized module) accepts swappable modules (parameters) that satisfy a contract (a theory), and everything is connected by explicit adapters (views). It is the most powerful way to connect modules "from the inside" — `Roster(teacher)`, `Roster(student)`, `Roster(administrator)` from one `ROSTER` definition. All of it lives in Full Maude, so every declaration is parenthesized.

## Frameworks Introduced

- **Theory** (`fth ... endfth`) — the contract a parameter must fulfill: sorts and operations the parameter must provide, *with no fixed meaning*. `TRIV` (built in) just requires a sort:
  ```maude
  (fth TRIV is sort Elt . endfth)
  ```
  A richer contract still leaves operations uninterpreted:
  ```maude
  (fth GRAPH is sorts Node Edge . ops node1 node2 : Edge -> Node . endfth)
  ```
- **Parameterized module** — `(fmod EXAMPLE(X :: TRIV) is ... endfm)`. Rules of labeling: every parameterized sort carries its label `Sort(X)` everywhere; every sort imported from the theory is written `X@Sort` (e.g. `X@Node`); operations from the theory carry **no** label. Pick one label (convention: `X`) and stay consistent.
- **Parameter module** — an ordinary module (e.g. `GREEK-GRAPH` with `sort Letter` and `source/target` equations) written *separately* from the parameterized module, ready to be plugged in.
- **View** (`view Name from THEORY to MODULE is ... endv`) — the adapter mapping each theory sort/op to a concrete one: `sort Node to Letter . op node1 to source .` Theory element first, keyword `to` always. Views may also bind an operation to an arbitrary **term**:
  ```maude
  (view Peano-3Nat from PEANO to THREE-NAT is
      sort Num to 3Nat .  var X : Num .
      op 0 to 0 .
      op s X to term X + 3 .
  endv)
  ```
- **Instantiation** — plugging a parameter in via a view, in the environment or an importing module:
  ```text
  ( select NETWORK(Graph-GreekGraph) . )
  ( red in NETWORK(Graph-GreekGraph) : lambda in (alpha beta lambda phi) .)
  ```
  ```maude
  (fmod GREEK-NETWORK is protecting NETWORK(Graph-GreekGraph) . ... endfm)
  ```
  Every place that had `(X)` now shows `(ViewName)`.
- **Multiple parameters** — `(fmod PAIRS(X :: OELT | Y :: TRIV) is ... endfm)`; sorts written `Pair(X | Y)`; distinct `X@Elt` vs `Y@Elt` keep theory collisions straight; instantiation lists views bar-separated: `PAIRS(OElt-Nat | Triv-String)`.
- **Parameterized views** — views that are themselves parameterized, e.g. `(view Triv-Stack(X :: TRIV) from TRIV to STACK(X) is sort Elt to Stack(X) . endv)`, then nested inside instantiation: `pr PAIRS(OElt-Color | Triv-Stack(Triv-Card)) .`
- **Parameterized theories** — theories with their own parameters: `(fth FUNCTION(X :: TRIV | Y :: TRIV) is op f : X@Elt -> Y@Elt . endfth)`, consumed by a module like `(fmod FMAP(F :: FUNCTION(X :: TRIV | Y :: TRIV)) is ... endfm)` — function-sets mapped element-wise via `f`.

## Key Concepts
- **fth vs fmod-theory flavor** — a *functional theory* constrains functional modules; nothing about it limits system/omod use unless it mentions rewrite laws or classes.
- **X@Sort** — "the theory's sort, as bound through label X"; the single most error-prone token in the syntax.
- **The pairing `*` rule** — "all you bases are covered": every theory-to-parameter correspondence must be a view, and every view (parameterized or not) must appear in the instantiation, or the system silently mis-binds.
- **Loose-syntax hazard** — Full Maude syntax is itself terms being rewritten by Core Maude modules; a declaration that *looks* right can parse and still mean something else ("If you want a surefire way to get the syntax correct, read the signature of Full Maude").
- **IN-operator idiom** — membership-test `_in_` built from two equations, the second `[owise]` — the canonical parameterized-module utility.

## Mental Models
- Think of the theory as a wall socket specification, the parameterized module as an appliance frame, the parameter as the appliance, and the view as the plug adapter you choose.
- Think of `X@Elt` as "Elt as seen through X's eyes" — always trace which theory a sort came from when two theories both declare `Elt`.
- Think of instantiation as a find-and-replace on labels: `(X)` occurrences become `(ViewName)` occurrences.
- Treat view construction as interface binding (theory = interface, parameter = implementation, view = explicit binding).

## Anti-patterns
- **Defining the parameter inside the parameterized module** — parameters are separate modules by design; they get attached only through views.
- **Unlabeled theory-dependent sorts** — "once you declare a label for a theory, that label has to follow around consistently every sort or module" associated with it (operations are the lucky exception).
- **Half-connected systems**: a view defined but not used in the instantiation, or a theory sort with no `to` mapping — that's when whole systems fail to run.
- **Trusting your eyes on weird nested declarations** — Full Maude "will also allow a whole number of combinations that make no sense at all, but these won't run."

## Code Examples

The full minimal network system — contract, frame, plug, adapter:

```maude
(fth GRAPH is sorts Node Edge .
    ops node1 node2 : Edge -> Node .
endfth)

(fmod NETWORK(X :: GRAPH) is
    sorts NodeSet(X) EdgeSet(X) Network .
    subsort X@Node < NodeSet(X) .
    subsort X@Edge < EdgeSet(X) .
    op _net_ : NodeSet(X) EdgeSet(X) -> Network [ctor] .
    op __ : NodeSet(X) NodeSet(X) -> NodeSet(X) [ctor assoc comm id: nnil] .
    op __ : EdgeSet(X) EdgeSet(X) -> EdgeSet(X) [ctor assoc comm id: nil] .
    op nnil : -> NodeSet(X) [ctor] .
    op nil  : -> EdgeSet(X) [ctor] .
    op _in_ : X@Node NodeSet(X) -> Bool .
    op _in_ : X@Edge EdgeSet(X) -> Bool .
    var N : X@Node .  var NS : NodeSet(X) .
    var E : X@Edge .  var ES : EdgeSet(X) .
    eq N in N NS = true .
    eq N in NS = false [owise] .
    eq E in E ES = true .
    eq E in ES = false [owise] .
endfm)
```

The parameter and its view (theory elements first in each mapping):

```maude
(fmod GREEK-GRAPH is pr NAT . sort Letter .
    ops alpha beta gamma delta epsilon lambda theta phi : -> Letter .
    ops source target : Nat -> Letter .
    eq source(1) = epsilon . eq target(1) = lambda .
    ... endfm)

(view Graph-GreekGraph from GRAPH to GREEK-GRAPH is
    sort Node to Letter .
    sort Edge to Nat .
    op node1 to source .
    op node2 to target .
endv)
```

## Reference Tables

The five pieces (the author's "bare minimum"):

| Piece | Declaration | Role |
|---|---|---|
| theory | `(fth NAME is ... endfth)` | contract/requirements |
| parameterized module | `(fmod NAME(X :: T) is ... endfm)` | frame with `Sort(X)` / `X@Sort` |
| parameter | ordinary `fmod` | concrete plug-in |
| view | `(view V from T to M is ... endv)` | theory→module binding |
| instantiation | `select M(V)` / `pr M(V)` | connection |

Parameterized-sort spelling:

| Context | Appearance |
|---|---|
| sort declaration inside frame | `sorts Pair(X | Y) PairList .` |
| sort from the theory | `X@Elt`, `Y@Elt` (labels differ) |
| theory operation | `f`, `node1` — no label ever |
| after instantiation | `NodeSet(Graph-GreekGraph)` — view name replaces `X` |

The author's three survival rules: (1) declare all theories and their labels up front; (2) keep the label on every theory-dependent sort/module; (3) track instantiations — right views in right slots, bar-separated, parameterized views included.

## Worked Example
The whole chapter's worked example is one end-to-end system: a highway map, a power grid, or an encyclopedia share the GRAPH structure, so `NETWORK(X :: GRAPH)` is written once. `GREEK-GRAPH` provides concrete nodes (Greek letters) and edges (naturals with `source`/`target` equations). The view `Graph-GreekGraph` binds `Node→Letter`, `Edge→Nat`, `node1→source`, `node2→target`. Typing `( red in NETWORK(Graph-GreekGraph) : lambda in (alpha beta lambda phi) .)` reuses every `_in_` equation from the frame against the concrete data — nothing in NETWORK knows about Greek letters. To model domain-objects-and-paths instead, write one new parameter and one new view; the frame is untouched. That reusability is the entire value proposition.

## Key Takeaways
1. Parameterize when one structure recurs over many element types (rosters, stacks, networks) — resist both a single merged sort and copy-paste modules.
2. Declare theories uninterpreted; give the contract, not semantics — meaning arrives with the parameter.
3. Master the labeling grammar: `Sort(X)` for frame sorts, `X@Sort` for theory sorts, unlabeled theory operations, `X replaced by (ViewName)` after instantiation.
4. Views are explicit and cheap: sort mappings, op mappings, or `op f to term <expr>` bindings.
5. Multiple parameters use `|` in both declaration and instantiation, and theory collisions (`OELT@Elt` vs `TRIV@Elt`) are resolved by distinct labels.
6. Parameterized views and parameterized theories exist when the binding itself needs arguments; keep every view accounted for in the instantiation ("all you bases are covered").
7. When a parameterization looks right but misbehaves, suspect the loose Full Maude parser first — read the signature, check each rule of the three-rule list, "experiment, be flexible."

## Connects To
- **Ch 2**: junk/confusion discipline governs theory-to-parameter relation — theories forbid both on imported structure, which is why instantiations stay type-safe.
- **Ch 4**: parameterization is Full Maude's other great extension; LOOP-MODE's "give Maude new keywords" is why this syntax is flimsier than Core Maude's.
- **Ch 6**: the meta-level connects modules "from the outside" — the complementary coordination axis; parameterization is the inside.
- **Ch 8 Appendix**: network path-search example given there expands the `NETWORK` module.
- **External**: generics/templates (but contract-first: SML functors are the direct ancestor); Toffler's *Future Shock* plug-in architecture analogy.
