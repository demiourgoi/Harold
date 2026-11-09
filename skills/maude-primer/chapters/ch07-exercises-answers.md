# Chapter 7: Exercises & Worked Answers

## Core Idea
The primer's per-chapter quizzes plus the author's worked answers form a self-test lab: every answer corrects a predictable beginner mistake (keyword vs. sort, missing colon, un-parenthesized mixfix) or reveals a nugget the main text skipped (object theories, gather-determined arithmetic, Oid subsort chains, meta-level null constants). This chapter is deliberately lean: it indexes the drills' teaching points rather than reproducing all six answer sets — open the appendix of the source for full text.

## Frameworks Introduced
(None new — this section is the application layer for Ch1–6. Named lessons below.)

## Key Concepts & Answers Worth Remembering

- **Ch1 drills**: identify `fmod`/`mod`/`omod`; the only Full-Maude-only module is the omod. Prefix vs. mixfix vs. constant classification (`op _^_` mixfix, `op smile : -> Expression` constant). Division without zero-division: `sorts Nat NzNat . subsort NzNat < Nat . op _/_ : Nat NzNat -> Nat .` Queue vs. Grab-bag constructors: `[assoc id: nothing]` vs `[assoc comm id: nothing]` — commutativity is the only difference. Parse predictions: an expression accepted by an operation on a supersort but fed a subsort can land in a *kind* like `[Speech, Plea]`, not a sort.
- **Ch2 drills — pick the statement keyword by shape**: `eq`/`ceq`/`mb`/`cmb` for the same math depending on whether the "if" is structural (eq), conditional (ceq), or sort-flavored (mb/cmb). An identity flag stands for an equation (`[right id: 0]` replaces `eq X - 0 = X .`); `owise` replaces the hard-to-state base/other case (`eq s X - s Y = X - Y [owise] .` alongside `ceq s X - s Y = X - Y if s X > s Y .` — wait, keep both distinct: the conditional peels, the owise case floors to 0).
- **Gather determines arithmetic**: `14 mod 5 mod 3` reduces to 0 only if `mod` is right-gathering — `gather (e E)`, so the term parses `14 mod (5 mod 3)`; left-gathering `(E e)` gives `(14 mod 5) mod 3 = 1`. Constant `0` shared by sorts via subsorts is **subsort overloading**.
- **Recursion dispatch trio** for `firstFemCard`: (i) `if_then_else_fi` inside a plain equ; (ii) `ceq ... if C :: FemCard .` with an `[owise]` skip equation; (iii) pattern-match conditions (`if Q of S:Suit := C .`) with `[owise]` skip — three idioms, one algorithm.
- **Ch3 drills**: comm flag on the `_> ` constructor is what lets `zop > zap > zip` match the winner pattern; `rl [gameend] : zop > zop > zop > zop => gameover .`; `=>!` (terminal) can find *no* solution where `=>+` finds one — pick the arrow by whether the target must be final. Read `show path` transcripts by labels: the answer identifies `scatter2` purely from states 11→16 (`win => zip > zap`).
- **Ch4 fixes** (the classic omod parse errors): `msgs ... : Oid Nat -> Msg .` (Msg is the sort); mixfix messages parenthesized in rules — `(A switch B) < A : NUMOBJ | ... >`; `class PERSON | age : Nat , sign : Zodiac .` (keyword is `class`, not `object`); object terms need the colon syntax `< A : PERSON | age : N >`.
- **Oid subsort chains**: to let a `Nat` jersey number be an object identifier: `subsorts Nat < JerseyNumber < Oid .` — identifiers don't have to be raw Qids.
- **Reverse-engineering configurations**: given only the final `result Configuration`, the three input messages are recoverable by diffing attribute deltas (`(3 fouled 34) 3A(8, true) 2A(3, false)`) — a practical audit skill.
- **Ch5 nuggets — object theories exist**: an theory for omods uses `oth ... endoth` (e.g. `(oth CLASSTHEORY is class ELT . endoth)`). Parameterized-view declaration syntax: `(view OElt-Queue(P :: OELT) from LIST(P) to QUEUE is ... endv)`. Ops may map to terms inside views only by naming the pattern variables first (`op X < Y to term X <= Y and X =/= Y .`; `op double to _times2 .`; general form `op s X to term X + 3 .`).
- **The DOUBLE/*POWER2 system** — a clean reference parameterization: theory declares `Something`/`double`; frame declares `op _*power2_ : X@Something Nat -> X@Something` with `eq S *power2 (s N) = double(S) *power2 N . eq S *power2 0 = S .`; view binds `double` to `_times2`; instantiate with `select *POWER2(Double-Int)` or import it into `EIGHT` (`eq X *power2 3` = 8x).
- **Ch6 answer grid (write it on your wall)**: module constructor ranks `Qid ImportList SortSet SubsortDeclSet OpDeclSet MembAxSet EquationSet` (+`RuleSet` for mods); `crl_=>_if_[_] : Term Term Condition AttrSet -> Rule`; `metaXapply : Module Term Qid Substitution Nat Bound Nat -> Result4Tuple`. Nulls/defaults: `nil` (ImportList), `none` (every Set, incl. AttrSet and Substitution), `0` (selector Nats), `unbounded` (Bound), `(failure).ResultTriple?` / `(failure).Result4Tuple?` (empty results).
- **Meta-rule with metadata** (CELLS mitosis answer): `rl 'X:Cell => '_&_['X:Cell, 'X:Cell] [label('mitosis) metadata("two's company")] .` — conditions too (`Condition` sort), and the `X < Y`-shaped `Result4Tuple` context can be `'phagocyte[bloodcell[[]]]` (hole nesting shows *where* extension rewrote).
- **OPPOSITE-DAY** — the meta-surgery exam: reverse every rule by structural recursion over the RuleSet (`eq reverse(rl T1 => T2 [A] . RS) = rl T2 => T1 [A] . reverse(RS) .` + `crl` variant + `reverse(none) = none`), rebuild the module with the reversed set, and descend via `oppRewrite(M, T, B) = metaRewrite(opp-day(M), T, B)`.

## Mental Models
- Treat each exercise answer as a patch for a specific parser surprise — collect the fix patterns, not just the solution.
- When a number puzzle and a parsing flag interact, ask "which way does this NEED to associate?" and choose `gather` accordingly.
- At the meta-level, always ask "what is the null/default for this sort?" before writing an auxiliary equation — the answers' null-grid covers 90% of them.

## Anti-patterns
- Confusing the statement keywords (`eq` vs. `ceq` vs. `mb` vs. `cmb`) — the exercises show each has a shape it alone fits.
- Writing `msg` where `Msg` (result sort) belongs, or `object` where `class` belongs.
- Forgetting `show path N` needs the *state number* from the listed solution, and that omitted state ids are dead ends, not errors.

## Worked Example
The OPPOSITE-DAY system end-to-end (Ch6 answers): given `mod ... endm` as data, `reverse` walks the `RuleSet` list, swapping each rule's `T1 => T2` to `T2 => T1` while preserving the AttrSet (crucially including conditional rules: `crl T2 => T1 if C [A]`); `opp-day` reassembles the module constructor with `reverse(RS)` in the RuleSet slot; `oppRewrite` descends with `metaRewrite` on the doctored module. Result: `rl [A] : a => b .` runs backwards (`b => a`) with the strategy you wrote — module interpretation itself is a rewrite system, so "run my module with rules inverted" is just three equations and one descent call.

## Key Takeaways
1. Do the drills with the answers closed; nearly every one encodes a gotcha that bit the author's students.
2. Chapter-specific lessons: attribute choice by container semantics (Ch1), statement-keyword choice by shape (Ch2), arrow/flag reading (Ch3), omod syntax repairs + Oid chains (Ch4), theory/view grammar incl. `oth/endoth` and `to term` bindings (Ch5), meta nulls and structural recursion over statements (Ch6).
3. The gather exercises make parsing decisions seem mathematical — they are: pick `(e E)` to nest right, `(E e)` to nest left.
4. META-LEVEL operator ranks and null constants, memorized once, make every meta-program sketchable on paper.

## Connects To
- **Ch 1–6**: this chapter's answers presuppose each chapter's mechanics; jump back via the Topic Index in SKILL.md.
- **Ch 8 Appendix**: several exercise modules (TENNIS, CARD-PAIR, DOG-RACING, REWRITE-EXCEPT, CIGARETTE-TEST) have canonical full listings there.
