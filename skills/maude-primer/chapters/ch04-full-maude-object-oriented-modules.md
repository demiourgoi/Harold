# Chapter 4: Full Maude & Object-Oriented Modules

## Core Idea
Full Maude is Core Maude modeling itself: an extension written *in* Core Maude on top of the `LOOP-MODE` read-eval-print constructor, so "we have to put everything in parentheses" — modules and commands alike. Its two big additions are object-oriented modules and parameterization (Ch5). An object `< A : TABLE | occupied : O >` is just a constructor term, a message is a note placed next to the object it affects, and object rules are ordinary rewrite laws over configurations.

## Frameworks Introduced

- **LOOP-MODE pattern** — user-defined sub-environments. The engine is one constructor:
  `op [_,_,_] : QidList State QidList -> System [ctor special (....)] .`
  User input arrives (parenthesized, so Maude converts words to Qids) as the first `QidList`; a `State` argument carries intermediate data; the final `QidList` is printed without quotes. Initialize with `loop init .` (convention: define `op init : -> System` as `[nil, none, nil]`).
- **"Safe parsing" discipline** — in Full Maude, parsing tricks that work in Core Maude "will very easily crash your program". Always parenthesize mixfix messages against their arguments (`(A borrowchairfrom B)`), backquote punctuation meant as characters inside Qids/operators ('`((', ``,`), etc.), and use whitespace deliberately.
- **Object orientation as encapsulation** — the object is a computer's "temple of memory": data grouped, made exclusive and inclusive under one name. Syntax is exactly a constructor: `op < _:_ | _ > : Oid Cid AttrSet -> Object [ctor] .`
- **Class / subclass hierarchy** — `class TABLE | occupied : Bool , chairs : Nat .` (attribute set is commutative, order irrelevant); inheritance parallels subsorts: `subclass OutDoorTABLE < TABLE .` — the subclass both is a class and inherits all attributes.
- **Message discipline** — `msg sit@ : Oid -> Msg .` Rules: first argument is always the target object's `Oid` (never a whole object, never a class), and the result sort is always the built-in `Msg`. Keywords are lowercase (`msg` is the keyword, `Msg` the sort), messages are "notes next to vials" — the object sits beside the message in the configuration until a rewrite law consumes both. One-letter solace: "key words are always lower case in Maude".
- **Configuration rewriting** — `Message Object => Object Object` and friends are ordinary rewrite laws over a configuration soup; conceptually `subsorts Message Object < Configuration` under an associative-commutative configuration constructor.
- **Attribute economy** — in a rule, mention only the attributes that matter for that law; unmentioned attributes ride along untouched (`< J : LINE | >` matches fine).

## Key Concepts
- **omod ... endom** — object-oriented module delimiters; entered in parentheses: `(omod NAME is ... endom)` — a Full Maude necessity for every module/command.
- **Oid** — built-in sort of object identifiers; object names can also be computed by constructors (e.g. a coordinate pair).
- **Attribute** — name : sort pair inside the object; attribute names are fixed by the `class` declaration, values come from variables.
- **Msg** — built-in result sort tying all messages together for configuration matching.
- **Qid skeletons** — QidList input/output; `' ` (a lone quote) is the blank-space Qid; `'smile` etc. are command tokens; backquote before `(`, `)`, `,` to use them as characters.
- **Core vs Full safety nets** — Full Maude complicates or removes some Core protections: expect more parse crashes without explicit parentheses.

## Mental Models
- Think of Full Maude as "a Great Experiment in progress": Core Maude interpreting an interpreter — the LOOP-MODE constructor *is* the REPL you're typing into.
- Think of a `msg` as half a rule: it names and carries data; the matching `rl` completes the performance of the action.
- Think of objects as labeled records, and the configuration as a multiset of records and notes; a rule is a local pattern match within that multiset.
- Think of `subclass` as subtyping for records — anywhere the parent class fits, the child fits, with extra attributes along.

## Anti-patterns
- **Forgetting the parentheses** for omods and Full Maude commands — the LOOP-MODE loop never sees the input.
- **Feeding an object where an Oid belongs**: messages take `Oid` only; `sit@(< A : TABLE | ... >)` is wrong, `sit@(A)` next to the object is right.
- **Writing mixfix messages unparenthesized in rules**: without `(A borrowchairfrom B)`, the parser grafts the following object onto the mixfix — nonsensical and unsafe.
- **Declaring every attribute in every rule**: state only the attributes the law reads or writes; the rest travel unchanged.
- **Uppercasing keywords** — `msg`, not `Msg`, when declaring.

## Code Examples

A LOOP-MODE sub-environment (user types `(smile)`, gets `:-)`), note `including` because State/System are redefined:

```maude
mod SMILE-LOOP is
    inc LOOP-MODE .
    op none : -> State .
    op startsmiling : -> System .
    eq startsmiling = [nil, none, nil] .
    var S : State .  vars I O : QidList .
    rl [smile] : ['smile I, S, O] => [I, S, O ' ': '- '`)] .
    rl [wink]  : ['wink  I, S, O] => [I, S, O ' '; '- '`)] .
    rl [gawp]  : ['gawp  I, S, O] => [I, S, O ' '8 '- '`)] .
    rl [elvis] : ['elvis I, S, O] => [I, S, O ' '? 'B '- '`)] .
endm
```

The restaurant — class, subclass, messages, and rules consuming message+object pairs:

```maude
(omod RESTAURANT is
    protecting NAT .
    class TABLE | occupied : Bool , chairs : Nat .
    class OutDoorTABLE | next2heater : Bool .
    subclass OutDoorTABLE < TABLE .
    msgs sit@ heaterswitch : Oid -> Msg .
    msgs _borrowchairfrom_ changetables : Oid Oid -> Msg .
    vars A B : Oid .  vars M N : Nat .
    rl [sit] : sit@(A) < A : TABLE | occupied : false >
        => < A : TABLE | occupied : true > .
    rl [move] : changetables(A, B)
        < A : TABLE | occupied : true > < B : TABLE | occupied : false >
        => < A : TABLE | occupied : false > < B : TABLE | occupied : true > .
    rl [takechair] : (A borrowchairfrom B)
        < A : TABLE | chairs : M > < B : TABLE | chairs : s N >
        => < A : TABLE | chairs : s M > < B : TABLE | chairs : N > .
endom)
```

Sliding-tile puzzle — Oids built by a backquoted-punctuation constructor; four conditional rules dispatch on adjacency:

```maude
op `(_`,_`) : Coord Coord -> Oid [ctor] .
crl [r] : move((R1, C1), (R1, C2))
        < (R1, C1) : Tile | val : V > < (R1, C2) : Tile | val : empty >
     => < (R1, C2) : Tile | val : V > < (R1, C1) : Tile | val : empty >
    if C2 == s C1 .
```

## Reference Tables

Object vocabulary:

| Item | Syntax | Notes |
|---|---|---|
| class | `class C \| att : Sort , ... .` | attribute set commutative |
| subclass | `subclass C' < C .` | inherits attributes |
| object term | `< A : C \| att : V , ... >` | `op < _:_ \| _ > : Oid Cid AttrSet -> Object [ctor]` |
| message | `msg m_ @_ : Oid ... -> Msg .` | first arg Oid; result sort `Msg` |
| rule shape | `Msg Obj Obj => Obj Obj` | ordinary `rl`/`crl` over configuration |

LOOP-MODE mechanics:

| Piece | Role |
|---|---|
| first `QidList` | parenthesized user input, words become Qids |
| `State` middle arg | scratch space threaded through rewrites |
| final `QidList` | printed output, quotes stripped |
| `loop init .` | start a sub-environment at `init : -> System` |

## Worked Example
MOOD-LOOP shows why the middle `State` argument exists. `init` starts the loop with a mood cell `< # ; # >` (blank placeholder `#`). Input drives `in-` laws (`['smile I, S, O] => [I, < happy ; # >, O]`); then *state-internal* laws evolve the cell (`rl [wow!] : < happy ; # > => < # ; shocked >`); finally `out-` laws emit the smiley into the output QidList and reset the cell. Pipeline: input Qids → decode into State → state machine rewrites → encode into output Qids. Full Maude generalizes exactly this diagram: its "input" is the parenthesized modules/commands you type, its interpreter is a big rewriting system over them, and its output mimics Core Maude's prompt.

## Key Takeaways
1. Full Maude = Core Maude + LOOP-MODE interpreter written in Maude; enter everything in parentheses or it never reaches the interpreter.
2. Model with `class` (record schema), `subclass` (inheritance), `< Oid : Class | attrs >` (record), `msg ... : Oid ... -> Msg` (command), and ordinary `rl`/`crl` over the configuration multiset.
3. Message rules pair the note with its addressee: match `msg(Oid)` beside `< Oid : C | ... >`, and only name the attributes the law touches.
4. Object identifiers can be computed constructor terms — great for grids, coordinates, paths.
5. Parsing is the Full Maude failure mode: parenthesize mixfix, backquote operator punctuation (`'(`, '`,`), `' '`)`, and rely on whitespace.
6. Step-debugging `set trace on` inside Full Maude is disorienting (Ch2 note) — trace in Core Maude, not in the ring.

## Connects To
- **Ch 1–3**: object/message/configuration are ordinary terms and rewrite laws — "just specific examples of everyday rewriting logic".
- **Ch 2**: the LOOP-MODE interpreter is equations + rules once more; `including LOOP-MODE` (not `protecting`) because State/System are re-sensed — junk/confusion in action.
- **Ch 5**: parameterized modules are also a Full Maude feature, entered under the same parentheses discipline.
- **Ch 6**: the meta-level `up`/`down` functions shuffle modules into terms and back; Full Maude demonstrates Maude can treat its own syntax as data.
- **External**: standard OO vocabulary (class, inheritance, message passing) mapped onto rewriting logic; LOOP-MODE descends from Maude's database/interpreter examples in the manual.
