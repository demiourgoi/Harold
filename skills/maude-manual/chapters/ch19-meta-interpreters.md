# Chapter 19: Meta-interpreters

## Core Idea
META-LEVEL is purely functional (even its bounded nondeterministic operations are deterministic functions). Meta-interpreters remove that ceiling: a meta-interpreter is an external object that is a *complete, independent Maude interpreter* with its own module/view database, driven by ordinary messages — so reflective applications gain state, sessions, and interactivity, and since each interpreter can host further interpreters, the reflective tower becomes a constructible object.

## Frameworks Introduced
- **The META-INTERPRETER API** (`meta-interpreter.maude`; `mod META-INTERPRETER is protecting META-LEVEL . including CONFIGURATION .`): `interpreterManager` (built-in factory) + handle objects `interpreter(N)`; command/reply message pairs following the addressee/sender convention:
  - `createInterpreter(mgr, ME, options)` → `createdInterpreter(ME, mgr, MI)` (options: `none`, `newProcess` — fresh OS process);
  - `insertModule(MI, ME, M)` / `insertedModule`; `insertView` / `insertedView` — populate the interpreter's database (stateful! the key advantage over META-LEVEL's stateless descent functions);
  - computation mirrors of every command: parse/pretty-print, `rewriteTerm/rewroteTerm`, `frewriteTerm`, `erewriteTerm(MI, ME, bound, n-per-position, module-name, Term)` → `erewroteTerm(ME, MI, rewrites-count, Term, Type)`; search, apply, xmatch, srewrite, unify, variant and narrowing families;
  - lifecycle `quit(MI, ME)` / `bye`, and failures `interpreterError`, `interpreterExit` (e.g. stack overflow / internal errors surfaced as messages you can handle).
- **Operational semantics of the dialogue**: requests may be *pipelined* (send many before reading replies), but arrival order is undefined and request↔reply matching is your job; stderr of a meta-interpreter interleaves with the parent's; each interpreter is a full tower — it can itself create interpreters, and META-LEVEL can be inserted and used inside.
- **RUSSIAN-DOLLS (19.2)**: the minimal showcase of towers — two rules handle `createdInterpreter` (lift your own module with `upModule('RUSSIAN-DOLLS, true)` and `insertModule` it in the child) and `insertedModule` (ask the child to `erewriteTerm` a state computed by `newMetaState(N, T)`, which *for N > 0* recursively upTerms a whole inner configuration `<> < me : User | depth: N-1, computation: T > createInterpreter(...)`). Depth 0 degenerates to plain evaluation; depth k nests k interpreter boundaries — each reply layer wrapping metarepresentations of the layer below.
- **The environment pattern (19.3, Mini-Maude)**: STD-STREAM (UI, Ch 18) + meta-interpreter (parsing/execution/state) + a stateful driver object (`class MiniMaude | mi : Maybe{Oid}, mn : Maybe{Qid}, in : QidList, st : Nat`) whose `st` attribute encodes a *statechart* (create interpreter → insert grammar module → read lines → accumulate input → parse as module or `reduce` command → for modules: extractSignature in the interpreter's context, then solveBubbles against the database; then reduce via `reduceTerm`...). Multi-line inputs, parse errors (`noParse`), and module database reuse all live naturally because the interpreter remembers previous modules.

## Key Concepts
- **Functional metalevel vs stateful meta-interpreter**: choose META-LEVEL for pure computations over known modules; choose meta-interpreters when modules must *persist* between interactions, execute *interactively*, or when the outer program should not track everything itself.
- **upTerm of configurations**: whole object configurations lift into metaterms (`newMetaState`), so one interpreter's state can include configurations meant for another interpreter to execute — towers built by data, not by code.
- **`insertModule` with `upModule(..., true)`**: modules—including-imports travel into interpreter databases; database names then resolve inside the interpreter (Mini-Maude's signature may reference previously stored modules — impossible in pure META-LEVEL, which has no memory).
- **Maybe{X} attributes + `st : Nat`**: the session-state idiom for interfaces threading external-object replies (`mi : null` until the interpreter exists; `st` separating prompt/parse/insert phases of the input protocol).

## Mental Models
- Treat a meta-interpreter as "a colleague who runs Maude": you send well-formed requests with a return address, it replies asynchronously; its database is its own; documents (modules/views) you want reused must be inserted, not assumed.
- Read the Russian-dolls trick as "configuration as message payload": because `upTerm` quotes arbitrary configurations into data, spawning recursive towers is just equationally computing the next message's content.

## Anti-patterns
- **Assuming request/reply ordering**: pipeline freely but never interpret reply N as answering request N without correlation logic; serializing (one outstanding request) is the simple, sound discipline.
- **Forgetting to insert prerequisite modules** (grammar, submodules) before asking for parses/reductions that need them — the interpreter only knows its database.
- **Expecting `erewriteTerm` semantics identical to META-LEVEL rewriting**: in the metalevel-copy of your module, external-object rules and portals work like at home — your lifted configuration must include `<>` portals for external exchanges (Russian-DOLLS' `newMetaState` inserts precisely that).
- **Ignoring `interpreterError/interpreterExit`**: stack overflows and internal errors are messages; handle or at least print them — unchecked, your session silently stalls.
- **Quitting without `quit`**: leaving interpreters alive leaks (they are processes/objects managed by the manager).

## Code Examples
```maude
--- creating and priming a meta-interpreter (RUSSIAN-DOLLS fragment)
mod RUSSIAN-DOLLS is
  extending META-INTERPRETER .
  op me : -> Oid .  op User : -> Cid .
  op depth:_ : Nat -> Attribute .   op computation:_ : Term -> Attribute .
  op newMetaState : Nat Term -> Term .
  eq newMetaState(0, T) = T .
  eq newMetaState(s N, T) = upTerm(<> < me : User | depth: N, computation: T >
                                   createInterpreter(interpreterManager, me, none)) .
  rl < X : User | AS > createdInterpreter(X, Y, Z)
     => < X : User | AS > insertModule(Z, X, upModule('RUSSIAN-DOLLS, true)) .
  rl < X : User | depth: N, computation: T, AS > insertedModule(X, Y)
     => < X : User | AS > erewriteTerm(Y, X, unbounded, 1, 'RUSSIAN-DOLLS,
                                       newMetaState(N, T)) .
endm

Maude> erewrite <> < me : User | depth: 0,
             computation: ('_+_['s_^2['0.Zero], 's_^2['0.Zero]]) >
             createInterpreter(interpreterManager, me, none) .
result Configuration: <> < me : User | none >
  erewroteTerm(me, interpreter(0), 1, 's_^4['0.Zero], 'NzNat)
```
- **What it demonstrates**: the 2-rule interpreter-boot protocol (createdInterpreter→insert own module; insertedModule→dispatch work onto the child), plus `newMetaState` generating towers by upTerm'ing configurations.

## Worked Example
Mini-Maude's session skeleton (statechart as attributes):

```maude
class MiniMaude | mi : Maybe{Oid}, mn : Maybe{Qid}, in : QidList, st : Nat .
eq minimaude = <> < o : MiniMaude | mi : null, mn : null, in : nil, st : 0 >
                write(stdout, o, "\t MiniMaude Execution Environment\n")
                createInterpreter(interpreterManager, o, none) .

rl < O : MiniMaude | mi : null, st : 0 > wrote(O, O') createdInterpreter(O, Y, MI)
   => < O : MiniMaude | mi : MI, st : 1 >
      insertModule(MI, O, upModule('MINI-MAUDE-SYNTAX, true)) .

rl < O : MiniMaude | mi : MI, st : 1 > insertedModule(O, O')
   => < O : MiniMaude | mi : MI, st : 2 > getLine(stdin, O, "minimaude> ") .
```

Walk the flow: (1) configuration births with a portal, banner, and interpreter-creation request; (2) reply binds the interpreter id into an attribute (`mi`), and the grammar module is inserted; (3) on confirmation, the prompt loop starts. Each `gotLine` either quits (`quit(MI, O)`), accumulates across lines (`in : QIL tokenize(Str)` for multi-line inputs), or dispatches a `parseTerm` into the interpreter; subsequent rules process the interpreter's replies (`parsedEquations`, `pendingBubbles`...) using Ch 18's `extractSignature`/`solveBubbles` — except now *inside the interpreter's database*, so `fmod NAT3 ... endfm` modules persist between `reduce` commands, exactly like your own Maude session. The pattern scales from toy languages to real environments: grammar in, statechart discipline, message-threaded execution.

## Key Takeaways
1. Meta-interpreters = Maude-interpreter-as-external-object: message API, own database, created/destroyed at will, arbitrarily nested (towers of reflection as runtime data structures).
2. Use them when you need *stateful reflection*: persistent module databases, interactive sessions, multiplexed computations, or embedding several isolated Maude engines in one program.
3. The API mirrors the interpreter's commands (insert/show/compute families of message pairs); lifecycle and error messages included.
4. Pipelining is supported but unordered — correlate by construction, serialize when in doubt.
5. RUSSIAN-DOLLS is the whole architecture in two rules: createdInterpreter → insert self; insertedModule → recursive erewriteTerm of an upTerm'd configuration.
6. Combined with STD-STREAM + LEXICAL + the Ch 18 bilingual (top-syntax/bubbles) stack, meta-interpreters are the final ingredient for arbitrary programming environments in Maude.

## Connects To
- **Ch 9**: interpreterManager is another manager (like fileManager/socketManager); portals and the erewrite discipline govern the exchange; `newProcess` options instantiate per-OS-process isolation.
- **Ch 17**: shared metarepresentations (`Module`, `Term`, `View`); descent-function behavior inside interpreters; `upModule`/`upTerm` used to move code between levels.
- **Ch 18**: grammar/bubble machinery (MINI-MAUDE) supplies the parsing half of the session; LOOP-MODE vs STD-STREAM remains the interface choice.
- **Ch 5 / 10**: rewriting and strategies still execute inside interpreters — the interpreter is an environment, not a different semantics.
