# Glossary — Maude 3.5.1 Manual

**Admissible module** — functional/system module whose executable statements satisfy Church-Rosser, termination, sort-decreasingness, and the extra-variable (matching-condition) requirements needed for exact initial-model execution (Ch 4, 5).

**Attribute (equational)** — `assoc`, `comm`, `idem`, `id:`, `left id:`, `right id:` on binary operators; treated as built-in axioms A with generated matching algorithms, never as equations (Ch 4).

**Attribute (operator)** — declarations like `ctor`, `iter`, `memo`, `poly`, `strat`, `frozen`, `prec`, `gather`, `format`, `special`, `latex`, `dnt`-families; carried in `[...]` of an `op` (Ch 3, 4, 6, 20).

**Bounded model checking** — verifying invariants only up to a depth `[n, m]`; incomplete but finite evidence (Ch 11).

**Bubble** — built-in datatype (via `id-hook Bubble`) holding unparsed token sequences until a module's grammar can parse them; the basis of two-level syntax (Ch 18).

**Canonical form** — irreducible result of equational simplification modulo A; the operational representative of an initial-algebra class (Ch 1, 4).

**Church-Rosser property** — confluence: simplification order does not affect the final canonical form; required of executable equations (Ch 1, 4).

**Class** — object-oriented sort with attributes; `class C | a1 : S1, ...`; subsorting = inheritance (Ch 6).

**Coherence** — rules composable with E-canonicalization: no rewrite is lost by simplifying first; makes rewriting modulo E ∪ A decidable (Ch 5).

**Complete set of unifiers/variants** — set covering all solutions up to instantiation (Ch 13, 14).

**Configuration** — multiset of objects/messages; `__ [assoc comm id: none config]`; object-message fair rewriting unit (Ch 6, 9).

**Connected component (kind)** — maximal sort group; kinds as error supersorts, `[Sort,Sort]` (Ch 3).

**Constructor** — operator appearing in canonical forms; `[ctor]` declaration + SCC tool check (Ch 4).

**Counterexample** — `counterexample(prefix, loop)` model-checking result; two TransitionLists describing a violating computation (Ch 12).

**Descent function** — META-LEVEL built-ins (metaReduce, metaApply, ...) that run object-level work natively instead of simulating it (Ch 17).

**Diamond importation** — same module imported via several paths; default resolution: strongest mode wins (Ch 7).

**Ditto** — operator attribute inheriting the attribute set of a previous subsort-overloaded instance (Ch 4).

**Equational simplification** — using equations l→r as oriented rewrite rules; the operational semantics of functional modules (Ch 4).

**Extension-aware matching (xmatch)** — matching also within flattened A-operator fragments; how equations/rules apply modulo assoc/AC (Ch 4).

**Finite variant property (FVP)** — every term has finitely many most general variants; enables finitary variant unification (Ch 14).

**Frozen argument** — operator argument position where rule rewriting is never allowed; `[frozen (i...)]` (Ch 4, 5).

**Generated-by / Extending / Protecting / Including** — importation modes of decreasing semantic strength: surjective / injective / bijective / no claim on the state maps; never runtime-checked (Ch 7).

**Initial algebra / initial model** — no junk, no confusion model `T_Σ/E∪A` (functional) / `T_R` (system — labeled transition system = category) (Ch 1, 4, 5).

**iter** — operator attribute enabling `f^n(x)` exponent notation for huge unary towers (Ch 4, 8).

**Kripke structure** — total unlabeled transition system + labeling by state predicates; the semantic home of LTL (Ch 12).

**Kind** — see Connected component; partiality by kind-level declarations or `~>` (Ch 3).

**LTL+** — LTL with one path quantifier layer: `E φ` / `A φ` (Ch 12).

**Matching equation** — condition fragment `t := t'` binding variables against the subject's canonical form; a `let` + modulo search (Ch 4).

**Maude primer** — sibling shorter tutorial (not this manual); keyed companion text (skill `maude-primer`).

**Memo** — operator attribute caching results — `fibo` from 61G rewrites to 148 (Ch 4).

**META-LEVEL** — predefined functional module implementing reflection: metarepresentations + descent functions + sort/parsing operations (Ch 17).

**Meta-interpreter** — external-object Maude interpreter with own module database, driven by messages; nestable (Ch 19).

**Mixfix syntax** — operator form with underscores in argument positions: `_+_`, `if_then_else_fi`, empty-syntax `__` (Ch 3).

**Module expression** — `ModId`, `A + B`, `M * (renaming)`, `M{V1, ...}`; precedence: instantiation > renaming > summation (Ch 7, 23).

**Narrowing** — rewriting by E ∪ Ax-unification instead of matching; symbolic reachability via `vu-narrow` over `[narrowing]` tags (Ch 15).

**Object-message rule** — LHS configuration `A B` with message+object tops, stable, same first argument; fair rewriting candidate unit (Ch 6).

**omod > mod transformation ("desugaring")** — OO modules internally complete rules (class variables + `Atts` + attribute copies) so subclasses inherit behavior; `show desugared` displays it (Ch 6).

**owise** — statement attribute giving an "otherwise" catch-all equation, desugared into an `enabled_f` conditional equation (Ch 4).

**Pattern (M-pattern)** — term whose variable instances stay canonical; required in matching conditions (Ch 4).

**Portal** — `<>` configuration element enabling communication external objects; one per communicating configuration (Ch 9).

**Preregularity** — every well-formed argument combination has a least result sort (modulo attributes); warned at analysis time (Ch 3, 21).

**Proof obligation** — unchecked requirement (importation modes, views, sufficient completeness assumptions) owned by the specifier, not Maude (Ch 7, 8, 12).

**Search arrow** — `=>1 =>+ =>* =>! =>#`: exactly-one, one-or-more, zero-or-more, terminal-only, multi-successor-target (Ch 5).

**Strategy** — deterministic-by-construction expression layer over rules: `sdf` rule tactics, combinators `; | * ? :`, `matchrew ... by`, `one`, in `smod` modules; or Meta-Level "internal" strategies (Ch 10, 17).

**strat(...) attribute** — operator evaluation strategy; positions simplified before top: default eager `(1 ... n 0)`, lazy `(0)` (Ch 4).

**Subsort overloading** — same operator name on subtype-related typings; must share equational attributes (ditto); preregularity requirement (Ch 3, 4).

**Sufficient completeness** — every defined function fully specified on constructors; SCC tool; the strangelness-free condition (Ch 4, 8, 21).

**Theory** — declaration with loose semantics (`fth/th/oth/sth`): parameter interface requirements; can carry nonexec statements (Ch 7, 10).

**Term coloring** — debugging print mode color-coding reduced/unreduced symbols to localize sufficiency bugs (Ch 21).

**Union / division semantics of built-ins** — machinery where stale numeric arguments remain symbolic (e.g. `gcd(X:Nat, 3)`) (Ch 8).

**Variant** — pair (canonical form, substitution) obtained by instantiating a term and simplifying with `[variant]` equations (Ch 14).

**View** — named mapping `view V from Src to Tgt` interpreting a theory in a module/theory; unchecked proof obligations (Ch 7, 10).

**vu-narrow** — narrowing-based reachability command using variant unification each step; `{fold}/{vfold}` fold infinite trees (Ch 15).

**Well-sorted substitutions / wellFormed** — META-LEVEL sorts/order predicates and module validator (`wellFormed : Module ~> Bool`; `sortLeq`, `leastSort` etc. — Ch 17).

**Working strategy language combinators** — `or-else`, `α+`, `not(α)`, `α !` (normalization), `try`, `test` — derivations from `; | * ? :` (Ch 10).
