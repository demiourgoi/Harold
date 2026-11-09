# Chapter 22 (Appendix A): Complete List of Maude Commands

## Core Idea
Appendix A is the command-line surface of the whole manual in one place: interpreter flags, rewriting/matching/search/strategy/unification/SMT commands, and the `set`/`show`/`trace`/`break`/`debug`/`profile` option families. Every option omitted from the main chapters (bounds, modes, print/show toggles) is specified here.

## Frameworks Introduced
- **Command-line flags (A.1)**: security gates (`-allow-dir`, `-allow-files`, `-allow-processes`, `-trust`); output control (`-latex-log=file`, `-xml-log=file-name`, `-no-banner`, `-no-wrap`, `-no-mixfix`, `-print-to-stderr`, `-ansi-color`/`-no-ansi-color`); runtime behavior (`-batch`, `-interactive`, `-no-prelude`, `-random-seed=number`, `-assoc-unif-depth=number`, `-early-quit=number`, `-erewrite-loop-mode`); terminal (`-tecla`/`-no-tecla`); advisories (`-always-advise`, `-no-advise`); `-debug`, `-show-pid`, `-help`, `-version`.
- **Rewriting commands (A.2)**: `reduce {in M :} t .` (equational simplification); `rewrite {[bound]} ... .`, `frewrite {[bound {,number}]} ... .` (position-fair; second number caps per-position rewrites per traversal), `erewrite {[bound {,number}]} ... .` (external events); `continue {number} .`; `loop {in M :} term .` (LOOP-MODE driver); `( identifier+ )` parenthesized input into the loop object; `set clear rules on/off .` (rule state/counter persistence — Monte-Carlo sessions).
- **Matching (A.3)**: `match {[n]} {in M :} pattern <=? subject {such that cond} .` — plain sort-level matching (membership-axiom style); `xmatch ...` — matching with extension (assoc/iter theories; equations-and-rules style; prints matched portions). Optional `such that` condition accepted.
- **Searching (A.4)**: `search {[n {,depth}]} {in M :} t1 arrow t2 {such that cond} .` with arrows `=>1 =>+ =>* =>! =>#`; the graph/path inspectors `show search graph .`, `show path n .`, `show path labels n .`, `show path states n .`
- **Strategic rewriting (A.5)**: `srewrite {[bound]} {in M :} subject using strategy .` (fair exhaustive; `srew`), `dsrewrite ...` (depth-first; `dsrew`).
- **Unification / variants / narrowing (A.6)**: `unify {irredundant} ...`; `variant unify {filtered} ...`, `variant match ...`, `get {irredundant} variants ...` (all with `[bound]`, `in`, `/\`-problem lists, and `such that ... irreducible` phrase available); `vu-narrow`/`fvu-narrow ...` `{fold|vfold|path}`/`{filter|delay}` variants with `[bound{,depth}]`; post-search inspectors `show frontier states .`, `show most general states .`
- **SMT (A.7)**: `check {in M :} term .`
- **Tracing (A.8)**: `set trace on/off .`; `set trace select on/off .`, `trace select ⟨labels/operators⟩ .`; `trace exclude ⟨modules⟩ .`; presence toggles via the `set trace X on/off` family (eq, mb, rl, sd, condition, whole, substitution, body, builtin, …).
- **Print attribute + print options (A.9–A.10)**: `set print attribute on/off .` (activates `[print]` output); the `set print X on/off` family governs normal printing: `format` (attribute-driven spacing), `color` (bug-localizing coloring), `number`/`rat` (numeric literals), `flattened` (assoc normalization display), `with parentheses`, `combine vars`, `conceal` (`print conceal symbols . / reveal`), `constants with sorts`, `graph`, `hooks`, `label attribute`.
- **Show options and commands (A.11–A.12)**: `set show timing/stats/gc/loop stats/loop timing/command on/off .` families shape the per-command banners; `show module/module-name {desugared} .`, `show modules .`, `show sorts M .`, `show components M .`, `show ops M .`, `show eqs/mbs/rls M .`, `show view {processed} V .`, plus `show desugared .` for OO modules.
- **Profiler (A.13)**: `set profile on/off .`, `show profile .` — statement counts + condition-fragment statistics (tests, backtracks, successes, failures).
- **Debugger (A.14)**: `break select ⟨labels/ops⟩ .`, `set break on/off .`; debugger-local `where .`, `step .`, `resume .`, `abort .`; `debug ⟨command⟩ .` prefix (and `^C` entry).
- **Miscellaneous (A.15)**: `parse {in M :} term .`, `select module .` (current module), `set include/protect/extend module on/off .` (automatic imports), `set clear memo on/off .` + `do clear memo .`, `set verbose on/off .`, `set advise off .`, `set print attribute ...` crossovers.
- **System level (A.16)**: `cd`, `pushd`/`popd`, `pwd`, `ls`, `in file`, `load file`, `sload file` (silent load — errors printed only on failure), `quit (q)`; in-sessions file beans may be gated by the security flags of A.1.

## Key Concepts
- **Optional syntax convention throughout**: `{}` enclose optional parts (bounds, `in` clause, `such that` conditions).
- **Bound pairs**: writing commands take `[n]` (and optionally a second number for frewrite's per-position cap); searching/unification take `[n{,m}]` = solutions and depth.
- **Command-family symmetry**: every stateful subsystem (trace/break/print/show/profile) has a `set X on/off .` master switch plus fine-grained `set trace/stat ...` selectors — learn one family and the others read the same way.
- **`in/sload` selection**: `in` echoes; `sload` is quiet; `load file-name` as plain command; `( tokens )` feeds a LOOP-MODE session instead of the interpreter.

## Mental Models
- Treat A as the "man page" of Maude: after you know a subsystem from its chapter, A tells you every dial it has.
- The requested-but-forgotten options (`set print flattened on`, `set trace builtin off`, `set show stats off`...) are typically what a session needs to become tractable.

## Anti-patterns
- **Running unbounded commands interactively**: `search`/`vu-narrow`/`srewrite` without `[n]`/depth on nonterminating systems — bound first, unbound only when the chapter's finiteness argument applies.
- **Leaving `set profile on`/`set trace on` on globally**: both tax performance — toggle around specific experiments.
- **Expecting non-`select`-ed scopes**: after `trace select`, unselected statements stop appearing — a feature; remember what you selected before assuming silence means no activity.
- **Forgetting flag-side pairings**: `-no-advise` vs `set advise off`; `-random-seed` feeds `random(...)` only, not `counter` state; `-assoc-unif-depth` only matters for A-unification beyond warnings.

## Code Examples
```
Matched portion wrappers are unnecessary here; commands speak for themselves:
red in NUMBERS : s zero + s zero .                        --- A.2
match [5] NS0:NatSeq NS1:NatSeq <=? zero zero zero .      --- A.3
search [3, 10] in VM : $ q q q =>+ a c c M .               --- A.4
srew [1] init using (buy-c or-else change) + .             --- A.5
irredundant unify in NAT : X + Y =? s s 0 .               --- A.6
check in TEST-RI : -2 < I and -2 * I > -1 and I =/== -1 . --- A.7
set trace condition off . set trace select on . trace select change .
--- A.8
set print color on .                                      --- A.10
show desugared .                                          --- A.12
set profile on . red fibo(30) . show profile . set profile off .
--- A.13
break select debit . set break on .                       --- A.14
select VENDING-MACHINE . sload tests/ smoke.maude .       --- A.15–16
```
- **What it demonstrates**: one operation per family in idiomatic spelling — the appendix in a nutshell.

## Reference Tables
| Family | Representative members (heads) |
|---|---|
| flags | `-allow-{dir,files,processes}` `-trust` `-latex-log=` `-xml-log=` `-batch` `-interactive` `-no-prelude` `-random-seed=` `-assoc-unif-depth=` `-tecla` |
| rewriting | `reduce` `rewrite` `frewrite` `erewrite` `continue` `loop` `set clear rules` |
| matching | `match` `xmatch` (+`[bound]`, `such that`) |
| searching | `search [n{,m}] ... =>1/=>+/=>*/=>!/=># ... such that`, `show search graph/path{,labels,states}` |
| strategies | `srewrite` `dsrewrite` |
| symbolic | `unify{ irredundant}` `variant unify{ filtered}` `variant match` `get{ irredundant} variants` `{fold,vfold,path,}vu-narrow{,filter,delay}` `check` |
| trace/debug/profile | `set trace ...` `trace select/exclude` `break select` `debug ⟨cmd⟩` `where/step/resume/abort` `set profile` `show profile` |
| print/show | `set print ...` `set show ...` `show module/sorts/components/rls/ops/eqs/mbs/modules/view/desugared` |
| system | `in/load/sload` `cd/pushd/popd/pwd/ls` `quit` `parse` `select` |

## Worked Example
Tuning a session in practice (chaining the appendix):

```
$ maude -no-banner -random-seed=7
Maude> set show timing off . set show stats off .   --- quiet banners for scripting
Maude> set print flattened on .                     --- see multiset/state terms unparenthesized
Maude> load vending.maude
Maude> set trace on . set trace select on .
Maude> trace select buy-a change .
Maude> search [2, 8] in VENDING-MACHINE : $ $ q q =>+ c a M:Marking .
Maude> show path labels 17 .                        --- witness follows selected rules only
Maude> set trace off . set profile on .
Maude> rew [100000] bigConf . show profile . set profile off .
Maude> set print color on .  red in BANK : fix(myAccount) .  --- blame any unreduced residue
```
Each line is exactly one appendix facility doing its one job — the point is that *nothing above needed a chapter beyond the appendix to understand*; A is where session plumbing lives.

## Key Takeaways
1. The `{}` optional-syntax convention and `[n{,m}]` bounds apply uniformly across families.
2. Security flags gate file/process/directory access at startup; runtime script commands honor them.
3. Output shaping (`set print ...`, `set show ...`) decides whether a session is debuggable or just noisy — flipped early, they cost nothing.
4. Post-analysis commands (`show search graph`, `show path`, `show profile`, `show frontier/most general states`) complement their computation commands — always know the pair.
5. `sload`/`in`/`load` and the shell-emulation commands (cd/ls/pwd/pushd) make the interpreter self-hosting for interactive development.
6. Everything in the systematic chapters (4–16) reduces to a command constructor here — this appendix is the go-to quick-reference when exact command spelling escapes memory.

## Connects To
- **Every chapter 4–21**: its commands' final authority (A.2 rewrite ↔ Ch 5; A.4 search ↔ Ch 5/11; A.5 ↔ Ch 10; A.6 ↔ Ch 13–15; A.7 ↔ Ch 16; A.8/A.13/A.14 ↔ Ch 21; A.15 set-include ↔ Ch 4/8; A.16 ↔ Ch 2).
