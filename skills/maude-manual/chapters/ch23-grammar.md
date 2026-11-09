# Chapter 23 (Appendix B): Maude Grammar

## Core Idea
The complete syntax of Maude in extended BNF — the authoritative resolution of every "is this legal?" question: metaparentheses `( )`, alternatives `|`, optional `[ ]`, repetition `*`/`+`; `A(, A)*` lists; plus the official synonyms table and the lexical rules (tokenization, comments, identifier conventions).

## Frameworks Introduced
- **Top-level shape**: a Maude input is a sequence of modules/theories/views, commands, debugger commands, and system commands:
  ```
  MaudeTop ::= (SystemCommand | Command | DebuggerCommand | Module | Theory | View)+
  ```
  with the module/theory quadruples (`fmod...endfm | mod...endm | omod...endom | smod...endsm`, and the matching `fth/th/oth/sth`), views `view Id [Params] from ModExp to ModExp is ViewElt* endv`, and parameter declarations `ParameterList ::= { P :: ModExp (, P :: ModExp)* }`.
- **Module element grammar (`ModElt`)**: imports (`including/extending/protecting/generated-by ⟨ModExp⟩ .`), `sorts S+ .`, `subsorts S+ (< S+)+ .`, single/multiple operator declarations with full type/attribute slots, `vars V+ : T .`, and statements with statement attributes (equational: `mb/cmb/eq/ceq`; primed variants add rules `rl/crl` with rewrite conditions; smod elements add `strats`/`sd/csd`).
- **The language of module expressions**:
  ```
  ModExp ::= ModId | (ModExp) | ModExp + ModExp | ModExp * Renaming | ModExp { ViewId(, ViewId)* }
  ```
  with declared precedence: **instantiation > renaming > summation**.
- **Renamings and view elements**: renaming items (`sort S to S`, `label l to l'`, `op f [_ : ... -> ...] to f' [Attr]`, plus class/attr/msg/strat items); view adds the `to term` and `to expr` (strategy) mappings.
- **Types and sorts**: `Type ::= Sort | Kind`, `Kind ::= [Sort(, Sort)*]`, `Sort ::= SortId | Sort{Sort(, Sort)*}` (structured sorts); `Arrow ::= -> | ~>` (partiality sugar).
- **Conditions**: `Condition ::= CondFragment(/\ CondFragment)*` with fragments `t = t'`, `t := t'`, `t : Sort` — and for rules the primed grammar adds `t => t'`.
- **Attributes**: operator attributes (assoc comm idem iter memo ditto config obj msg pcons ctor portal metadata strat(...) poly(...) frozen[...] prec gather format special hooks, latex); statement attributes (nonexec, dnt, metadata, label, print) with per-kind extensions: equations (`otherwise|variant`), rules (`narrowing`), strategies (`[metadata "..." ]`).
- **Strategy expression grammar**: `idle | fail | RuleApp | top(RuleApp) | α ? β : γ | TestVariant⟨Term⟩[such that cond] | α ; β | α | β | α* | MrewVariant⟨Term⟩[s.t. C] by VarStratList | StratCall | α+ | α or-else β | not(α) | α ! | try(α) | test(α)` — exactly the Ch 10 combinators, with `RuleApp ::= Label[[Substitution]][{Strat(,Strat)*}]`.
- **Identifier conventions (the grammar's commentary)**: `ModId` all-uppercase-with-hyphens; `ViewId` capitalized; `ParameterId` single capital; `SortId` capitalized (forbidden chars: brackets/braces/commas/periods/colons, `<`, `->`, `~>`, `@`); `VarId` no colon, capitalized; `OpId` may carry underscores; `StratId` without `@`/`:`; `AttributeId` without bracket/brace/comma.
- **Lexical issues (B.3)**: tokens are whitespace-delimited ASCII where `( ) [ ] { } ,` are single-character tokens unless backquoted; comments `***`/`---` to end of line, `***( ... )` multiline with balanced parens; string escapes follow C conventions; mismatched-paren mixfix operators warn and demote to prefix (backquote them instead); numeric guards: integer exponents/shifts are limited to `ULONG_MAX` via GMP (unless trivial: `0/1/-1` exponent, `0 << n`).

## Key Concepts
- **Synonyms (B.2) that matter daily**: `sort/sorts`, `var/vars`; command forms `red/rew/erew/frew/srew/dsrew/fvu-narrow`, `q`, `cont`, `irred`, `s.t.`, `subst`, `state(s)`; module forms `assoc/comm/ctor/pr/ex/inc/gb/pr`, `id: = identity:`, `idem`, `iter`, `owise = otherwise`, `strats = strat` (declarations; careful — in attributes `strat (...)` is the evaluation strategy), `fvu-narrow = {fold} vu-narrow`, and attribute synonyms (assoc = associative, etc.).
- **Why keep the grammar at hand**: exact spelling of rare constructs (`pconst`-style declarations in theories via hooks aside), validation of renaming expressions, and the precedence rule that settles every `M{V} + N * (r)` parsing dispute.
- **Condition-fragment duality**: the same nonterminals serve equations and rules with one addition (`=> t'`) — the formal echo of Ch 4/5's design.

## Mental Models
- Read the BNF as the ultimate arbiter after the tutorials: the meta-level `META-MODULE` constructors of Ch 17 mirror these productions almost symbol-for-symbol.
- When unsure whether a line is a `Module`, a `Command`, or a `Theory`, check its first keyword against `MaudeTop` — the grammar is deliberately parallel across module kinds.

## Anti-patterns
- **Relying on case-insensitivity**: none — the identifier conventions are just conventions except that sort names with forbidden characters would parse wrong; follow the capitalization norms to stay corner-free.
- **Mismatched parentheses in mixfix operators**: warned and demoted to prefix — write operators with backquotes from the start.
- **Assuming long-overflow-safe exponentiation**: `N ^ HugeNat` and `1 << HugeNat` hit the GMP-imposed cap and fail loudly — guard your arithmetic if exponents are data-dependent.
- **Mixing `strat` meanings**: evaluation-strategy attribute `strat (1 0)` (Ch 4) vs strategy declaration keyword `strat st : ... @ S` (Ch 10) — same word, different productions; context (attribute brackets vs module element) decides.

## Code Examples
```
--- the grammar, sampled where experience shows doubts arise
mod M{X :: TRIV, Y :: TRIV} is          --- ParameterList
  prlist M0 * (sort A to B, op f : A -> A to g) + M1{V} .
       --- renaming binds tighter than +, instantiation binds tighter than *
  subsorts NzNat Nat < Int .
  op _;_ : [Path] [Path] -> [Path] .     --- kind-level typing
  vars P Q : Path .                      --- VarId : Type
  ceq (P ; Q) ; R = P ; (Q ; R) if target(P) = source(Q) /\ target(Q) = source(R) .
  crl [eat] : P => Q if P => Q .         --- primed grammar: rewrite condition
endsm

view V from T to (A + B) is
  sort Elt to Int .  op e to term 1 .   --- to-term mapping
endv
```
- **What it demonstrates**: the combined expression grammar (instantiation/renaming/summation precedence), kind-level operator typing, both condition grammars, and view `to-term` mapping — in the grammar's own vocabulary.

## Reference Tables
| Production head | Notable members |
|---|---|
| `SystemCommand` | `in/load/sload ⟨file⟩` | `quit eof popd pwd cd pushd ls` |
| `Command` | `select`, `parse`, `[debug] reduce/rewrite/frewrite/erewrite`, `srewrite/dsrewrite ... using Strat`, `check`, `match/xmatch/variant match <=? ... [such that]`, `[irredundant] unify`, `[filtered] variant unify`, `get [irredundant] variants`, `search ⟨DoubleBound⟩ ... ⟨SearchType⟩`, `[NarrowingOptions] vu-narrow [VariantOptions]`, `continue`, `loop`, `(TokenString)`, `trace select/deselect/include/exclude`, `print conceal/reveal`, `break select/deselect`, `show ⟨ShowItem⟩`, `do clear memo`, `set ⟨SetOption⟩ on/off` |
| `SetOption` | `show ⟨ShowOption⟩` (advise stats loop-stats timing loop-timing breakdown command gc), `print ⟨PrintOption⟩` (mixfix flat with-parentheses with-aliases conceal number rat color format graph attribute attribute-newline constants-with-sorts latex), `trace [TraceOption]` (condition whole substitution select mbs eqs rls sds rewrite body), `break`, `verbose`, `profile`, `clear (memo|rules|profile)`, `protect/extend/generated-by/include/oo-include ⟨ModId⟩` |
| `SearchType` | `=>1 =>+ =>* =>! =>#` |
| `Statement` (equational) | `mb/cmb ⟨Term⟩ : ⟨Sort⟩ [label]`, `eq/ceq ⟨Term⟩ = ⟨Term⟩ if ⟨Condition⟩`; attrs: `nonexec dnt metadata label print + otherwise variant` |
| `Statement'` (rules) | `rl/crl ⟨Term⟩ => ⟨Term⟩ if ⟨Condition'⟩`; extra attr: `narrowing` |
| `Strat` | full combinator chain (idle, fail, RuleApp, tests, matchrew by, calls, or-else/+, !, try, test, not) |
| DoubleBound / VariantOption / NarrowingOption | `[Nat [,Nat]]` | `filter delay` | `fold vfold path` |

## Worked Example
Using the grammar to settle precedence and spelling questions before trial-and-error:

- Is `A + B{V} * (r)` A-plus-(B instantiated then renamed)? Parse with the precedence rule `inst > ren > +`: `B{V}` first, then `(B{V}) * (r)`, then `A + (that)` — precisely the reading the grammar mandates.
- May a rule's condition contain `t => t'`? Only in `Statement'` (`rl/crl`) which uses `Condition'` — confirmed by `ConditionFragment' ::= ConditionFragment | ⟨Term⟩ => ⟨Term⟩`.
- Is `[variant ...]` legal on an `rl`? The attribute suspension `StatementAttrRl ::= [(StatementAttr | narrowing)+]` doesn't include `variant` — variant tags belong to *equations*, exactly as Ch 14 required.
- Does `set trace body on .` exist? TraceOption list: `condition whole substitution select mbs eqs rls sds rewrite body` — yes (it traces the "body" of statements separately).

That's the appendix's operational value: disputes of form die instantly when read against MaudeTop — no repl experiments needed.

## Key Takeaways
1. The 4-module/4-theory grammar quadruple plus views and the full command/option vocabulary — every production in one appendix.
2. Module expression precedence is fixed: instantiation, then renaming, then summation.
3. Identifier conventions are indicative-but-load-bearing (forbidden sort-name characters exist because kinds and metareps need them reserved).
4. The synonyms table (B.2) explains half the scripts you'll encounter (`pr`, `ex`, `gb`, `irred`, `fvu-narrow`, `s.t.`...); use them consistently.
5. Lexically: backquotes escape everything special; either comment form to end-of-line; multiline comments need balanced parens; GMP caps exponentiation/shifts at ULONG_MAX.
6. Cross-check doubts here before running experiments — the grammar is the ground truth the parser was generated from.

## Connects To
- **Ch 3**: the syntax chapter's user-level view, of which this is the formal total.
- **Ch 7 / 10 / 17**: module expressions, strategy language, and META-MODULE constructors are 1:1 formalizations of these productions.
- **App A**: every command production here is documented with semantics there.
- **Ch 8**: `special`-hook syntax (id-hook/op-hook/term-hook) is the metalevel's window into built-ins declared by these productions.
