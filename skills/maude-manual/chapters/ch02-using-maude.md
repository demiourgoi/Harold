# Chapter 2: Using Maude

## Core Idea
The practical entry path to a Maude session: how to get the system, run it, enter modules (from the prompt or from files), and what the interpreter does for you automatically (loading `prelude.maude`, defaulting to a current module).

## Frameworks Introduced
- **The session model**: `maude` binary → banner → `Maude>` prompt accepting modules and commands; every command that needs a module defaults to the **current module** (last module entered/used) unless named explicitly, and the output always echoes which module was used.
  - When to use: every interactive session.
  - How: `select MODULE .` re-sets the current module (App. A.15); always read the `reduce in <module> :` echo to know where a term was evaluated.
- **File-driven workflow**: put modules and commands in files and enter them with `in` / `load` / `sload` — a file behaves exactly as if its contents were typed at the prompt.
  - When to use: anything beyond a two-line experiment.
  - How: `in hello-world` for the current directory; Maude also probes `.maude`, `.fm`, `.obj` extensions for bare names; use full paths if the file is outside the search path.

## Key Concepts
- **`prelude.maude`**: preloaded at startup; contains the predefined Core Maude modules (Chapter 8), including `STRING`.
- **`MAUDE_LIB`**: environment variable naming directories to search — for `prelude.maude`: (1) `MAUDE_LIB` dirs, (2) executable's directory, (3) current directory. For `in`-command files: (1) current directory, (2) `MAUDE_LIB` dirs, (3) executable's directory. Set it to be safe.
- **`CONVERSION`**: the default current module right after startup; it imports `STRING`, so `red "hello" + " " + "world" .` works immediately.
- **Command abbreviation**: `red` = `reduce`, `q` = `quit`.
- **Interrupt**: Ctrl-C stops any action; during a reduction it drops you into debugging mode (Sec. 21.1.3).
- **Comments**: `---` or `***` to end of line; `***( ... )` multiline, parentheses must balance inside.
- **Mailing lists**: `maude-users@maude.cs.illinois.edu` (announcements — subscribe), `maude-help@…` (usage questions), `maude-bugs@…` (bug reports).
- **Home page**: https://maude.cs.illinois.edu — binaries (Linux, macOS), docs, primer, source of manual examples.

## Mental Models
- Treat Maude as a REPL in which "the current module" is ambient state — commands without `in <Module> :` are evaluated in that module, and Maude's echo names it.
- Treat a `.maude` file as a transcript: any interleaving of modules and commands is legal.

## Anti-patterns
- **Relying on the executable's own directory to find `prelude.maude`**: startup can fail if the binary was moved; export `MAUDE_LIB` instead.
- **Leaving out module names and assuming the module you "see" is the one used**: always check the echoed `in <Module> :` line before diagnosing a wrong result.
- **Unbalanced parentheses in `***( ... )` comments**: the comment never closes and the rest of the file is swallowed.

## Code Examples
```maude
fmod SIMPLE-NAT is
  sort Nat .
  op zero : -> Nat .  op s_ : Nat -> Nat .  op _+_ : Nat Nat -> Nat .
  vars N M : Nat .
  eq zero + N = N .
  eq s N + M = s (N + M) .
endfm

red in SIMPLE-NAT : s s zero + s s s zero .
result Nat: s s s s s zero
```
- **What it demonstrates**: defining Peano naturals at the prompt and evaluating `2 + 3` by `reduce`; output reports sort and canonical value (plus `rewrites` and timing).

## Worked Example
A minimal file-based session. File `hello-world` (extension `.maude` also works):

```maude
--- hello-world
fmod HELLO-WORLD is
  protecting STRING .
  op hw : -> String .
  eq hw = "hello" + " " + "world" .
endfm
red hw .
```

Session:

```
Maude> in hello-world
Maude> red hw .
reduce in HELLO-WORLD : hw .
rewrites: 2 in 0ms cpu
result String: "hello world"
```

Note the automatic module echo (`in HELLO-WORLD`) — no `select` or explicit `in` was needed because entering the module made it current.

## Reference Tables
| Command / mechanism | Purpose |
|---|---|
| `./maude` | start session (banner, `Maude>` prompt) |
| `quit` / `q` | exit |
| `reduce` / `red [in M :] T .` | evaluate term to canonical form |
| `select M .` | make `M` the current module |
| `in <file>` / `load` / `sload` | enter a file of modules/commands (differences: App. A.16) |
| `MAUDE_LIB` | directories for `prelude.maude` and file lookup |
| Ctrl-C | interrupt; during reduction → debugger |

## Key Takeaways
1. Start sessions with modules in files and `in`/`load`; the prompt is for exploration, not for programs.
2. `prelude.maude` (string, conversion, predefined modules) loads automatically — but set `MAUDE_LIB` so lookup cannot fail.
3. Maude always names the module a command ran in; use it as your ground truth about context.
4. Comment styles `---`/`***` and `***( ... )`; keep multiline parentheses balanced.
5. Bug reports are useful only with a self-contained reproducer file, version, OS, and processor — this is what `maude-bugs` expects.

## Connects To
- **Ch 8**: the contents of `prelude.maude` (`STRING`, `CONVERSION`, and the rest of the predefined data modules).
- **Ch 21**: the debugging mode reached via Ctrl-C during a reduction.
- **App A**: the full command list incl. `select` (A.15) and file-entering commands (A.16).
- **Maude inside Emacs**: interactive editing/running support (Appendix of the manual).
