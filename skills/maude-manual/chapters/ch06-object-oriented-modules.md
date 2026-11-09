# Chapter 6: Object-Oriented Modules

## Core Idea
Object-oriented modules (`omod M is ... endom`) are syntactic sugar over system modules: every class becomes a subsort of `Cid`, every attribute a term-building operation, and every rule is completed so that it fires for objects of the class *and all its subclasses*, mentioning only the attributes it cares about. The separation buys inheritance and attribute-completion for free; execution is faithful because it happens on the desugared system module.

## Frameworks Introduced
- **CONFIGURATION (implicit backbone)**: every `omod` imports `CONFIGURATION`, which declares sorts `Oid`, `Cid`, `Object`, `Msg`, `Configuration`; the object constructor `<_:_|_>`; attribute sets (_,_ assoc comm id: none); and configuration multiset `__ [assoc comm id: none config]`. Object syntax: `< O : C | a1 : v1, ..., an : vn >`.
- **Classes and inheritance**: `class C | a1 : S1, ..., an : Sn .` — class names are sort names (subsort of `Cid`, parameterizable); `subclass C < D .` is literally a subsort declaration, so attributes, messages, and rules are all inherited; **multiple inheritance** is supported (`subclasses A B C < D E < F G H .`); same-named attributes across parents are the user's problem.
- **Messages**: `msg`/`msgs ... -> Msg [ctor]` (or subsorts of `Msg`); syntax is arbitrary, but the **first argument must be the addressee** — the fair-rewriting strategy depends on it.
- **Attribute sparing in rules**: attributes mentioned only on one side are preserved / created as needed; everything unmentioned stays unchanged. The desugaring adds `Atts:AttributeSet` and a class variable (`V:Account`) so rules apply across the subclass hierarchy.
- **`dnt` (do-not-transform) attribute**: any statement containing `<_:_|_>` is a transformation candidate; `dnt` passes it through untouched (necessary for class-changing rules; otherwise advisories are printed and the statement is left untransformed anyway — details in the transformation requirements below).
- **Object–message fair rewriting** (`frewrite`): enabled by the `config` / `object` / `message` operator attributes — a fair strategy that, per configuration visit, collects objects by name, queues their messages, delivers all of them, then tries one non-object-message rewrite. Delivery is *just*, not fair: an object must be willing to accept the message for delivery to be guaranteed.
- **Object-message rule** (the shape the strategy optimizes): LHS is `config(A, B)` with `A` a message constructor term, `B` an object constructor term, both stable, and both with the same first argument. Same-message rules try round-robin.
- **Fresh-name discipline for dynamic creation**: factories keep a counter and generate names `o(a, i)`; if all objects are created by such factories, the unique-name invariant is preserved from a clean initial configuration.

## Key Concepts
- **Uniqueness of object names in a configuration**: required for delivery; violations produce runtime warnings ("saw duplicate object: ...").
- **Asynchronous vs synchronous rules**: one object + ≤1 message on the LHS = async; multi-object rules = synchronous communication abstractions.
- **Search on object configurations**: patterns may use class constants (exact class) or class *variables* (`< O:Oid : C:Account | bal : N, Atts:AttributeSet >`) to match subclasses too — deliberate matching scope control.
- **`getClass(< O : C | attrs >)`**: returns an object's actual class (useful under inheritance).
- **Profiling**: `set profile on .` … `show profile .` … `set profile off .` shows per-rule usage counts (how starvation was diagnosed in the ticker examples).
- **Portal / external-object definitions** in the rest of CONFIGURATION (used in Ch 9).
- **Translation rules (6.5)**: see Reference Tables — `show desugared .` outputs the result; transformation is idempotent; `set verbose on .` prints per-statement summaries.

## Mental Models
- Think of a class as "a Cid subsort + attribute constructors", and of inheritance as "subsort inclusion, hence rule reuse by widening the class argument to a fresh class variable."
- Think of a configuration as a mailroom: each object has a name-keyed mailbox; `frewrite` delivers everything deliverable per visit, then takes one other action.
- When a rule seems to inherit wrongly or ignore attributes, run `show desugared .` — the completed rule shows exactly what Maude will match.

## Anti-patterns
- **Redefining all attributes in every rule**: the whole point of the omod sugar is to name only relevant attributes; completion adds `Atts` automatically.
- **Class-changing rules without `dnt`**: `< O : Account | > => < O : SavingAccount | >` produces advisories ("disables object completion") and passes through untransformed; resolve deliberately (rewrite the rule or add `[dnt]`).
- **Expecting fair delivery with plain syntax**: without `config`/`object`/`message` attributes, `frewrite` is merely position-fair — the ticker/factory example shows customers starving under `rew [40]` alone.
- **Duplicate object names**: message delivery breaks; the check is runtime, not parse-time.
- **Message without addressee-first convention**: silently opts out of object-message fair rewriting.
- **Rules with extra variables (non-admissible)**: e.g. rent-a-car's `car-rental` (fresh rental id `A`, `NumDays`) must be `[nonexec]` and driven by strategies (Ch 10), not the default interpreter.

## Code Examples
```maude
omod ACCOUNT is
  protecting QID . protecting INT .
  subsort Qid < Oid .
  class Account | bal : Int .
  msgs credit debit : Oid Int -> Msg .
  msg from_to_transfer_ : Oid Oid Int -> Msg .
  vars A B : Oid . var M : Nat . vars N N' : Int .
  rl [credit] : credit(A, M) < A : Account | bal : N >
              => < A : Account | bal : N + M > .
  crl [debit] : debit(A, M) < A : Account | bal : N >
              => < A : Account | bal : N - M > if N >= M .
  crl [transfer] : (from A to B transfer M) < A : Account | bal : N > < B : Account | bal : N' >
              => < A : Account | bal : N - M > < B : Account | bal : N' + M >
              if N >= M .
endom

omod SAVING-ACCOUNT is
  including ACCOUNT . protecting FLOAT .
  class SavingAccount | rate : Float .
  subclass SavingAccount < Account .
endom
--- rew on SavingAccount objects + credit/debit messages works unchanged: inherited behavior
```
- **What it demonstrates**: classes, messages, rules; inheritance reusing account behavior on `< A : SavingAccount | bal : 5000, rate : 3.0 >`.

## Reference Tables
| Declaration | Desugars to |
|---|---|
| `class C \| a: S ...` | `sort C . subsort C < Cid . op C : -> C [ctor] .` + per attribute `op a':_ : S -> Attribute [ctor gather (&)]` |
| `subclass C < D .` | `subsort C < D .` |
| `msgs... <name> : ... -> Msg` | op declarations with the `msg` attribute |
| rule over `< O : C \| ... >` | class arg → fresh `V:C` variable (all occurrences); missing attribute-set var added (`Atts`); `none`s dropped; attribute terms appearing on one side are added to the other side as copies (with fresh kind-level variables on the pattern side) |

| Fair-rewriting attribute | On which operator |
|---|---|
| `config` | configuration multiset constructor (`__`) |
| `object` | object constructors (first arg = object name) |
| `message` | message constructors (first arg = addressee) |

## Worked Example
The desugaring of `ACCOUNT`, read side by side (`show desugared .`):

```maude
rl [credit] : credit(A, M) < A : Account | bal : N >
           => < A : Account | bal : (N + M) > .
--- becomes
rl [credit] : credit(A, M) < A : V:Account | Atts:AttributeSet, bal : N >
           => < A : V:Account | Atts:AttributeSet, bal : (M + N) > .
```

Three invisible upgrades: (1) the class constant became `V:Account`, so **SavingAccount inherits the credit rule** — same rule, wider net; (2) `Atts:AttributeSet` was injected, so strengthening subclass attributes survives the update; (3) the attribute list explicitly carries `bal` over to the result. When `change-age` names no attributes, the pattern side gets `age : A2:[...]` added (to replace the value it must first see it), and everything unmentioned rides along in `Atts`.

The rent-a-car store shows the far end of the spectrum: relationship objects (`Rental`), a model of time (`Calendar` + `new-day`), money-flow rules (`on-date`/`late-car-return`, `pay-debt`), suspension policies — where `car-rental` is `[nonexec]` because the rental's identity and duration come from outside, so execution requires the strategy language (Sec. 10.1.1).

## Key Takeaways
1. `omod` = system module + CONFIGURATION + inheritance-friendly rule transformation; the sugar never hides anything — `show desugared .` is the ground truth.
2. The first-argument-is-the-addressee convention is what makes message delivery strategic, not just decorative.
3. Class-changing or replication-ambiguous rules break the transformation's requirements — resolve explicitly, `dnt` is the opt-out.
4. `frewrite` + the three attributes gives object-message fairness; every object gets mail before anything else happens; messages to objects that reject them sit undelivered.
5. Fresh names for created objects need a systematic scheme (counter factories); Maude detects duplicates only at runtime.
6. Search patterns control inheritance matching explicitly: class constant = this class only; class variable + `Atts` = the whole subclass closure.

## Connects To
- **Ch 5**: omod is sugar over `mod` rules; starving-rules pathology and `frewrite` position-fairness apply.
- **Ch 7**: `protecting`/`extending`/`including` importation semantics (importation graphs of the banks); parameterized class names.
- **Ch 9**: `Portal` and external-object machinery in CONFIGURATION.
- **Ch 10**: strategy-controlled execution of the nonexec rent-a-car rules (`idle` strategies, `matchrew`).
- **Ch 17**: `metaFrewrite` runs the same fair strategy at the metalevel; Nonexec rules driven by internal strategies (Sec 17.7).
- **Ch 21**: profiling (`set profile on`) and the runtime duplicate-name warnings.
