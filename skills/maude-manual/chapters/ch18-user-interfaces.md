# Chapter 18: User Interfaces and Metalanguage Applications

## Core Idea
With META-LEVEL (Ch 17) + STD-STREAM (Ch 9) + LEXICAL (tokenize/printTokens) + LOOP-MODE, Maude can host *interactive environments*: read user syntax, metaparse it against a grammar module, `downTerm` it, update an object state, execute via metalevel strategies, pretty-print results — the full REPL pattern implemented in Maude itself, for any DSL you define.

## Frameworks Introduced
- **The user-interface pattern (18.1–18.2)**: four ingredients:
  1. a grammar datatype module (`VENDING-MACHINE-GRAMMAR`: `Action` constructors — `insert $`, `buy__(s)`, `show basket`, ...);
  2. a stateful object (`class VM | action : Action, marking : Marking`) with an `idle` action as the wait-state;
  3. I/O rules over STD-STREAM forming the loop: `wrote` → `getLine(stdin, self, "> ")` prompt; `gotLine(O, stream, Str)` → `tokenize(Str)`, then either `'quit` goodbye, `metaParse(VM-GRAMMAR, tokens, 'Action)` success → store `downTerm(getTerm(...), idle)` as the new action, or invalid → error message and continue;
  4. action-processing rules — per action read the marking, `upTerm` it, run the metalevel strategy (`insertCoin('add-q, upTerm(M))`, `onlyNitems(upTerm(M), 'buy-c, N)`), `downTerm(..., null)` the new marking back, and `write` the reply.
  Drive everything with **`erewrite`** from a configuration constant holding the `<>` portal, the object, and a welcome `write`.
- **Tokens, bubbles, metaparsing (18.3)**: a *metalanguage application* is one level deeper — the object language has user-definable module syntax (Maude itself is the case study). Two-level syntax: a top-level grammar with **bubbles** (built-in datatypes: `token : Qid -> Token [special (id-hook Bubble (1 1))]` — length-1; `bubble : QidList -> Bubble [id-hook Bubble (1 -1) ...]` — any length; balanced variants like `'( ')`; `id-hook Exclude` for char sets).
- **Maude-in-Maude parsing (MINI-MAUDE)**: the pipeline from raw text to a real `FModule`:
  1. `metaParse(upModule('MINI-MAUDE-SYNTAX, false), tokens, 'PreModule)` — top-level parse; `sort_.`, `op_:_->_.`, `eq_=_.` constructors hold *bubbles* for module-internal pieces (`token('Nat3)`, `bubble('s 's 's '0)`), because the inner grammar is unknown yet;
  2. `extractSignature(T)` — walk the PreModule, accumulating sorts/op decls/imports into an initially empty `FModule` (via `addSort`, `addOpDecl`, `addImport` — FModule as an accumulator!);
  3. `solveBubbles(T, M)` / `solveBubblesAux` — for each equation, `metaParse(M, downTerm(bubble-tokens, nil), anyType)` **with the just-extracted signature**; `addEquations` merges the results;
  4. `processModule(T) = solveBubbles(T, extractSignature(T))` — returns a well-formed `FModule` term.
- **LOOP-MODE (18.4)**: a minimal alternative to STD-STREAM: `mod LOOP-MODE is op [_,_,_] : QidList State QidList -> System .` — a loop object with input list, generic state, output list. *Parenthesized input at the Maude prompt* (e.g. `(insert $)`) is tokenized to a QidList placed in slot 1; the output slot is unquoted and printed, then cleared on the next input. `State` has no constructors: your importing module defines the state's shape (subsort `Object < State` in the vending loop) and the rewrite rules that consume input/produce output; start execution with the `loop` command on a System constant.

## Key Concepts
- **`tokenize` / `printTokens`** (from `LEXICAL`, Sec 8.12): String ↔ QidList conversions under the token-marking convention (see Ch 8 for the `<1>` index markers).
- **`metaParse` as the language boundary**: input strings become `ResultPair`s of Metaterms; `downTerm` moves accepted parses to real terms of your grammar module's sorts; failed parses are `noParse(...)` data (Ch 17) → your friendly error message of choice.
- **`ResultPair ::` checking before `downTerm`**: the manual's idiom `if metaParse(G, tokens, 'Sort) :: ResultPair then ... else "Invalid input" fi` — no exceptions, just structured failure.
- **Bubble-then-parse discipline**: defer parsing module-internal syntax until the signature is known — the exact strategy Maude's own front end uses for your modules' terms.
- **Object state as session**: persistent marking/action attributes survive each `erewrite` turn? No — each `erewrite` re-runs from a constant; for multi-turn persistence use LOOP-MODE whose loop object *persists between inputs* driven by the `loop` command.

## Mental Models
- See the pattern as **MVC-in-Maude**: the grammar module is the model vocabulary, the VM object is the model state, STD-STREAM/LOOP-MODE is the view+controller, and rules are the event handlers.
- Bubbles are **quoted raw text + a promise**: "parse me later with the right grammar" — the mechanism that lets a metalanguage defer user-syntax decisions to exactly when they become decidable.

## Anti-patterns
- **Parsing bubbles with the wrong level of grammar**: top-level MINI-MAUDE parse yields bubbles; only after `extractSignature` can bubble contents be parsed — mixing the two stages destroys well-formedness.
- **Assuming STD-STREAM strings arrive tokenized**: `gotLine` carries a `String`; `metaParse` wants a QidList — always `tokenize` first.
- **`downTerm` without a fallback**: the second argument (e.g. `idle`, `null`) is your recovery channel for ill-formed moves — omit it and kind-level failures crawl upward.
- **Expecting the output slot of LOOP-MODE to flush predictably**: output prints; it clears only when the next input arrives — design rules independent of that timing.
- **Trying one giant `erewrite` for an interactive session**: with STD-STREAM you must define the whole conversation up front; sessions with persistent state want `loop` + LOOP-MODE.

## Code Examples
```maude
rl < O : VM | action : idle > gotLine(O, O', Str) =>
  if tokenize(Str) == 'quit
  then write(stdout, O, "goodbye\n")
  else if metaParse(VM-GRAMMAR, tokenize(Str), 'Action) :: ResultPair
       then < O : VM | action : downTerm(getTerm(
                metaParse(VM-GRAMMAR, tokenize(Str), 'Action)), idle) >
       else < O : VM | action : idle >
            write(stdout, O, "Invalid input\n") fi fi .
```
- **What it demonstrates**: the input-dispatch rule — tokenize, quit check, metaparse with grammar-typed target, downTerm with fallback, structured error route.

```maude
--- MINI-MAUDE's bubble resolution, heart of the Maude-in-Maude pipeline
op processTerm : Term Module ~> ResultPair .
eq processTerm('bubble[T], M) = metaParse(M, downTerm(T, nil), anyType) .
```
- **What it demonstrates**: a bubble's payload is re-parsed *with the extracted signature of the module being processed* — the deferral points where two-level syntax becomes one computed module.

## Reference Tables
| Component | Module | Role |
|---|---|---|
| grammar datatypes | e.g. `VENDING-MACHINE-GRAMMAR` | action/command syntax to parse against |
| I/O objects + portal | STD-STREAM (`<>`, getLine/write) | terminal dialogue |
| token bridges | LEXICAL (`tokenize`, `printTokens`) | String ↔ QidList |
| parse/move | META-LEVEL (`metaParse`, `downTerm`, `upTerm`) | grammar checking, term crossing |
| execution | metalevel strategies (`insertCoin`, `onlyNitems`) | action semantics |
| driver | `erewrite in X : init .` | event loop |
| simple loop | LOOP-MODE `[in, state, out]` + `loop` command | persistent-session alternative |
| raw-syntax carriers | `token(1 1)`, `bubble(1 -1)`, balanced variants (`'( '))` | two-level languages |

## Worked Example
A MINI-MAUDE session, end to end — defining `fmod NAT3 is sort Nat3 . op s_ : Nat3 -> Nat3 . op 0 : -> Nat3 . eq s s s 0 = 0 . endfm` as text:

1. Top-level parse: `metaParse(upModule('MINI-MAUDE-SYNTAX, false), 'fmod 'NAT3 'is 'sort 'Nat3 '. ..., 'PreModule)` returns `{fmod_is_endfm['token[''NAT3.Qid], __[sort_.[token[''Nat3.Qid]], op_:_->_.[...], op_:'->_.[...], eq_=_.[bubble['s 's 's '0], bubble['0]]]], 'PreModule}` — types and names recognized, equation sides still bubbles.
2. `extractSignature(...)` rewrites its `Term` argument into an empty-shape FModule accumulating `'NAT3 sorts 'Nat3 . op '0 ..., op 's_ ...` (22 rewrites).
3. `processModule(...)` = signature + resolved bubbles: `result FModule: fmod 'NAT3 is nil sorts 'Nat3 . ... eq 's_['s_['s_['0.Nat3]]] = '0.Nat3 [none] .` — a term you can now feed to `metaReduce`, instantiate, or re-enter into a running Maude (Ch 19's meta-interpreters do exactly that).

What this teaches is the *metalanguage contract*: your language's front end is (top-grammar, bubble datatypes, extract-signature, solve-bubbles) and its back end is whatever descent functions over freshly computed `Module`s you need. Any DSL, any command set, same skeleton.

## Key Takeaways
1. Interactive Maude applications follow one recipe: grammar module + state object + STD-STREAM or LOOP-MODE + metaparse dispatch + metalevel-strategy action rules.
2. `metaParse`+`downTerm`+`::` is the input-validation idiom; `upTerm`+strategy+`downTerm` is the execution idiom — both from Ch 17, now at the service loop.
3. Bubbles encode two-level syntax — the defining mechanism for languages whose modules carry their own grammar; parse them only with the extracted signature of the module under process.
4. LOOP-MODE = minimal persistent REPL (parenthesized input; generic state slot; `loop` command) when STD-STREAM's external-object machinery is overkill.
5. Building a language in Maude gives you its IDE for free: the same Maude machinery parses, executes, and pretty-prints your DSL's terms — Maude as a metalanguage, not just an interpreter.

## Connects To
- **Ch 9**: portals/streams wire the terminal; `erewrite` drives the loop.
- **Ch 8.12**: `tokenize`/`printTokens`/QidList conversions underpin both interfaces.
- **Ch 17**: `metaParse`, `metaPrettyPrint`, `upTerm/downTerm`, Module data structure and its selectors/builders (`addOpDecl`- style accumulator functions).
- **Ch 10 / 17.7**: strategies (internal or object-level) provide action semantics.
- **Ch 19**: meta-interpreters as external objects = the next step beyond this chapter's *interface* level — running fresh modules instead of parsing them.
