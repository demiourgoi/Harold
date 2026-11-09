# Chapter 20: LaTeX Support

## Core Idea
Maude can generate a LaTeX log of an entire session — modules, commands, outputs — via the `-latex-log=⟨file⟩.tex` flag, typeset with the bundled `maude.sty`. The goal: session documentation for papers/reports, with searchable command markers and paste-able excerpts; plus per-operator typesetting control via the `latex` operator attribute.

## Frameworks Introduced
- **The log pipeline**: run `maude -latex-log=output.tex`; interact normally; each command+response becomes a self-contained LaTeX chunk preceded by a locator comment:
  ```latex
  % % ⟨command with arguments⟩
  % ⟨latex code for command and results⟩
  % % End of ⟨command⟩ %
  ```
  Compile with pdflatex; copy excerpts into documents that `\usepackage{maude}`.
- **The `maude` LaTeX package options**: default mode typesets with a mathematical look — `->`, `~>`, `=>`, `/\` become `→`, `⇝`, `⇒`, `∧` (also `f^n` for `iter`, `<=?`/`=?` for match/unify, search arrows `=>1/+/*/!/#`, and path/arc annotations) — beautiful but **cannot be pasted back into Maude**; `[ASCII]` option keeps the literal ASCII symbols round-trippable.
- **What the log includes**: most commands and their outputs; entered modules appear via `show module` (as typed) and `show desugared` (internal representation with imports/prec/gather made explicit); terminology flips like proportional fonts re-line-breaking definitions; **paste-ins and error messages are not logged** — the log records the session as reconstructed by commands, not raw keystrokes.
- **The `latex` operator attribute** (20.2): custom typesetting per operator:
  ```maude
  op integral : Expr Expr Expr Var -> Expr [latex (\int_{#1}^{#2}{#3}\,d{#4})] .
  ```
  `#n` placeholders (any order, reusable, beyond `#9`, but not exceeding arity); backslashes written raw (the attribute is parenthesized, not string-quoted — so LaTeX `\,\d{...}` needs no escaping); parentheses after size commands (`\left \big ...`) are command-internal and don't close the attribute — enclose code in braces when a literal closing paren is needed (`[latex ({)#1,#2(})]`). Terms print in inline math mode (attribute code must not change mode); `latex` applies to terms in statements/results — not to bare declarations/renamings; **all subsort-overloaded instances of an operator must share the same latex attribute** (get them via `ditto` or renamings) — e.g. renaming `-_`/`_^_` from FLOAT onto Expr-land just to attach `[latex ({#1})]`/`[latex ({#1}^{#2})]`, giving `-2` and `2^3` the familiar look.

## Key Concepts
- **Terminal width matters**: Maude breaks lines at the terminal width when logging — set it for the layout you want.
- **Log time vs paste time**: `show module` output in the log = your syntax; `show desugared` = canonical internals (precedence, explicit imports, split variable declarations) — use the one that suits your document's purpose.
- **GAUSSIAN example**: a module whose operators (infinity, e, x, integral with bounds/differential) typeset as real math — the demonstration that a Maude-readable session and a publishable formula are the same terms.

## Mental Models
- Think of `-latex-log` as *session literate programming*: run once, get a document; `maude.sty` is its stylesheet; command comments are its table of contents.
- The `latex` attribute is print-only metadata — like `format`, it changes appearance, never semantics; keep it syntactically balanced so the annotation itself stays single-identifier sane.

## Anti-patterns
- **Pasting math-mode output back into Maude**: default-mode (`⇒ → ...`) text is for humans; export with `[ASCII]` if round-tripping matters.
- **Unbalanced parens/braces in `latex (...)` attributes**: the attribute ends where the parentheses balance (modulo the size-command exception) — brace-wrap awkward code.
- **Adding `latex` to one overloaded instance only**: subsort-overloaded families must agree — use `ditto` or rename-with-attribute; otherwise expect parse-time complaints.
- **Unescaped-mode thinking**: don't write `\\int` (string escape) — the attribute parenthesization is precisely to let you write `\int` plainly.

## Code Examples
```maude
fmod GAUSSIAN is
  pr FLOAT * (op -_ to -_ [latex (-{#1})],
              op _^_ to _^_ [latex ({#1}^{#2})]) .
  sort Var Expr . subsort Var Float < Expr .
  op infinity : -> Float [latex (\infty)] .
  op e : -> Float .  op x : -> Var .  op gaussian : -> Expr .
  op integral : Expr Expr Expr Var -> Expr [latex (\int_{#1}^{#2}{#3}\,d{#4})] .
  op -_ : Expr -> Expr [ditto] .   op _^_ : Expr Expr -> Expr [ditto] .
  eq gaussian = integral(- infinity, infinity, e ^ (- (x ^ 2.0)), x) .
endfm
--- in the -latex-log output this reduces/typesets as ∫_{-∞}^{∞} e^{-(x^2)} dx
```
- **What it demonstrates**: renamings carrying `latex` attributes into overloaded families; `#n` placeholders composing a real formula rendering of `gaussian`.

## Reference Tables
| Concern | Mechanism |
|---|---|
| start logging | `maude -latex-log=file.tex` |
| styles | `\usepackage{maude}` or `\usepackage[ASCII]{maude}` |
| excerpt location | `% % ⟨command⟩` comments around each chunk |
| operator typesetting | `[latex (⟨code with #n⟩)]` attribute |
| symbol replacements (default mode) | `-> ~> => /\ f^` ... → math symbols (not re-parseable) |

## Worked Example
A minimal session from shell to PDF:

```bash
$ maude -latex-log=output.tex
           \||||||||||||||||||/
     --- Welcome to Maude ---
           /||||||||||||||||||\
Maude> fmod SIMPLE-NAT is ... endfm     --- paste a module (not logged)
Maude> show module .                     --- logged: your syntax
Maude> show desugared .                  --- logged: canonical form
Maude> red s s zero + s s zero .         --- logged: command + result
Maude> q
$ pdflatex output.tex                    --- -> output.pdf (Figure 20.1)
```

What to notice: the paste and the parse error the user made on the way are *absent* from the log (raw input is not captured); what is captured is the module via `show module`/`show desugared` and the successful reduce. The generated comments let you `grep` for `reduce`/`show` blocks when assembling your paper, and the same `output.tex` compiles twice — once per package mode — depending on whether the reader should see `→` arrows or ASCII `->` they can copy.

## Key Takeaways
1. `-latex-log=...` + `maude.sty` turn sessions into LaTeX documents; command-marker comments make excerpt hunting mechanical.
2. Mathematical symbol replacement is display-only — compile with `[ASCII]` for copyable text.
3. The `latex` attribute gives per-operator typesetting (`#n` placeholders, raw backslashes); overload families must agree on it.
4. `show module` (your syntax) vs `show desugared` (canonical internals) are the two lenses the log offers on modules.
5. Terminal width influences the log's line-breaking; set it deliberately.

## Connects To
- **Ch 2**: `show module`, `show desugared` first appear here in documentation duty (full list in App A.12).
- **Ch 3 / 4**: the `format` attribute family — `latex` is its print-only sibling (mode must not change inside).
- **Ch 7**: renamings transporting operator attributes (`* (op -_ to -_ [latex (...)])`).
- **Ch 5 / 15**: search/narrowing arrows (`=>1 =>+ =>* =>! =>#`) drawn as their math symbols in default mode.
