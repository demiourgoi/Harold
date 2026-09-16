"""Unit tests for the heuristic rules (one positive per rule, plus hardening negatives)."""

from harold_mcp.diagnostics import FixEdit
from harold_mcp.heuristic.lexical import SourceView
from harold_mcp.heuristic.rules import RULES, RuleFinding

APOSTROPHE = "\u2019"
ACCENTED_E = "\u00e9"


def _findings(text: str, code: str) -> list[RuleFinding]:
    rule = next(rule for rule in RULES if rule.code == code)
    return rule.detect(SourceView.from_text(text))


def test_rule_1_reports_every_non_ascii_character_in_code() -> None:
    text = f"fmod T is\n    op L{APOSTROPHE} : -> Nat .\n    eq L{APOSTROPHE} = 1 .\nendfm\n"

    findings = _findings(text, "non-ascii-character")

    assert [(finding.line, finding.column, finding.end_column) for finding in findings] == [(2, 9, 10), (3, 9, 10)]
    finding = findings[0]
    assert finding.message == (
        f"Non-ASCII character {APOSTROPHE!r} (RIGHT SINGLE QUOTATION MARK): Maude accepts it in identifiers, "
        "but this is usually a typographic-punctuation paste — replace it with an ASCII apostrophe "
        "(a fix is available)."
    )
    assert finding.fix is not None
    assert finding.fix.description == f'Replace the typographic character {APOSTROPHE!r} with "\'".'
    assert finding.fix.edits == (
        FixEdit(line=2, start_column=9, end_column=10, new_text="'"),  # exclusive end: exactly one character
    )


def test_rule_1_ignores_ascii_input() -> None:
    assert _findings("fmod T is\n    eq f = 1 .\nendfm\n", "non-ascii-character") == []


def test_rule_1_ignores_non_ascii_inside_a_string_literal() -> None:
    text = f'fmod T is\n    eq s = "when -- = caf{ACCENTED_E}" .\nendfm\n'

    assert _findings(text, "non-ascii-character") == []


def test_rule_1_ignores_non_ascii_inside_a_comment() -> None:
    text = f"fmod T is\n    eq f = 1 . *** caf{ACCENTED_E}\nendfm\n"

    assert _findings(text, "non-ascii-character") == []


def test_rule_1_reports_a_character_without_a_substitution_without_a_fix() -> None:
    text = f"fmod T is\n    op caf{ACCENTED_E} : -> Nat .\nendfm\n"

    findings = _findings(text, "non-ascii-character")

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.line, finding.column, finding.end_column) == (2, 11, 12)
    assert finding.message == (
        f"Non-ASCII character {ACCENTED_E!r} (LATIN SMALL LETTER E WITH ACUTE): Maude accepts it in identifiers, "
        "but this is usually a typographic-punctuation paste — replace it with an ASCII equivalent unless it is "
        "intentional."
    )
    assert finding.fix is None


def test_rule_1_skips_the_lossy_decode_replacement_character() -> None:
    """U+FFFD is an artifact of reading a binary file, not something the author wrote."""
    assert _findings("fmod T is\n    eq f = \ufffd .\nendfm\n", "non-ascii-character") == []


def test_rule_1_metadata() -> None:
    rule = next(rule for rule in RULES if rule.code == "non-ascii-character")

    assert rule.severity == "info"
    assert rule.code == "non-ascii-character"


# --- Rule 2: when-guard -------------------------------------------------------------


def test_rule_2_reports_a_when_guard_with_its_span() -> None:
    text = "fmod T is\n    eq f(N) = g(N) when N =/= 0 .\nendfm\n"

    findings = _findings(text, "when-guard")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(2, 20, 24)]
    assert findings[0].message == (
        "`when` is not Maude syntax (it is a Haskell/SML guard): write a conditional equation "
        "or rule instead, `ceq <lhs> = <rhs> if <condition> .`"
    )
    assert findings[0].fix is None


def test_rule_2_reports_every_occurrence() -> None:
    text = "ceq when(1) = when(2) when true .\n"

    assert [(f.column, f.end_column) for f in _findings(text, "when-guard")] == [(5, 9), (15, 19), (23, 27)]


def test_rule_2_ignores_when_inside_strings_and_quoted_identifiers() -> None:
    text = 'eq q = "when" .\neq r = \'when .\n'

    assert _findings(text, "when-guard") == []


def test_rule_2_ignores_declaration_lines() -> None:
    text = "    op when : Bool -> Bool .\n    var when : Bool .\n    op when : Bool -> Bool .\n"

    assert _findings(text, "when-guard") == []


def test_rule_2_still_fires_on_a_when_operator_used_in_a_statement() -> None:
    """Documented false positive (Appendix D.7): the rule keeps the source linter's detection."""
    assert len(_findings("eq when(B) = B .\n", "when-guard")) == 1


# --- Rule 3: dash-comment -----------------------------------------------------------


def test_rule_3_reports_a_whitespace_delimited_dash_dash() -> None:
    text = "fmod T is\n    eq f = 1 . -- helper\nendfm\n"

    findings = _findings(text, "dash-comment")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(2, 16, 18)]
    assert findings[0].message == (
        "`--` does not start a comment in Maude (only `***` and `---` do), so the rest of the line "
        "is parsed as code — use `***` or `---`."
    )


def test_rule_3_reports_every_occurrence_but_not_triple_dashes() -> None:
    text = "eq f = 1 . -- one -- two --- three\n"

    assert [(f.column, f.end_column) for f in _findings(text, "dash-comment")] == [(12, 14), (19, 21)]


def test_rule_3_ignores_strings_quoted_identifiers_and_declarations() -> None:
    text = 'eq q = \'-- .\neq s = "--" .\n    op _--_ : Nat Nat -> Nat .\n    var -- : Nat .\n'

    assert _findings(text, "dash-comment") == []


# --- Rule 4: eq-in-term -------------------------------------------------------------


def test_rule_4_reports_a_lone_equals_inside_if_then() -> None:
    text = "fmod T is\n    eq f(N) = if N = 0 then 0 else 1 fi .\nendfm\n"

    findings = _findings(text, "eq-in-term")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(2, 20, 21)]
    assert findings[0].message == (
        "A single `=` is not a test in a term: inside `if … then … else … fi` use `==` "
        "(the `=` sign only separates the two sides of an equation or rule)."
    )


def test_rule_4_reports_every_occurrence_in_the_span() -> None:
    text = "eq f = if N = 0 and M = 1 then 2 else 3 fi .\n"

    assert [(f.column, f.end_column) for f in _findings(text, "eq-in-term")] == [(13, 14), (23, 24)]


def test_rule_4_accepts_the_equality_operators() -> None:
    text = "eq f = if N == 0 then 0 else 1 fi .\neq g = if N =/= 0 then 0 else 1 fi .\n"

    assert _findings(text, "eq-in-term") == []


def test_rule_4_ignores_equals_outside_an_if_then_span() -> None:
    text = "eq f(N) = N + 1 .\nceq g = h if N <= 2 /\\ true .\n"

    assert _findings(text, "eq-in-term") == []


def test_rule_4_ignores_an_equals_inside_a_string() -> None:
    text = 'eq s = "if N = 0 then" .\n'

    assert _findings(text, "eq-in-term") == []


# --- Rule 5: non-linear-pattern -----------------------------------------------------


def test_rule_5_reports_a_repeated_declared_variable_at_its_first_occurrence() -> None:
    text = "vars F-val F-ignore : Float .\nvars B-ignore : Bool .\neq first(h(F-val, B-ignore, F-ignore, B-ignore)) = F-val .\n"

    findings = _findings(text, "non-linear-pattern")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(3, 19, 27)]
    assert findings[0].message == (
        "The variable `B-ignore` appears 2 times in the left-hand side (non-linear pattern): legal "
        "in Maude (it forces the matched subterms to be equal) but often unintentional — use a "
        "fresh variable if equality was not intended."
    )


def test_rule_5_reports_each_repeated_variable_in_column_order() -> None:
    text = "vars A B : Nat .\neq f(A, B, A, B) = A .\n"

    assert [(f.column, f.end_column) for f in _findings(text, "non-linear-pattern")] == [(6, 7), (9, 10)]


def test_rule_5_ignores_single_occurrences_and_undeclared_tokens() -> None:
    text = "vars A B : Nat .\neq f(A, B, C) = B .\n"

    assert _findings(text, "non-linear-pattern") == []


def test_rule_5_ignores_rules_and_conditional_equations() -> None:
    text = "vars A : Nat .\nrl f(A, A) => A .\nceq g(A, A) = A if A == 0 .\n"

    # `ceq` is covered (`ceq g(A, A)` repeats A), `rl` is not: rules are position-sensitive.
    assert [(f.line, f.column) for f in _findings(text, "non-linear-pattern")] == [(3, 7)]


# --- Rule 6: undeclared-identifier --------------------------------------------------


def test_rule_6_reports_an_undeclared_capitalized_identifier() -> None:
    text = "fmod T is\n    protecting NAT .\n    op f : Nat -> Nat .\n    var N : Nat .\n    eq f(N) = Foo .\nendfm\n"

    findings = _findings(text, "undeclared-identifier")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(5, 15, 18)]
    assert findings[0].message == (
        "`Foo` is used in a statement but is not declared as a variable, operator, or sort: if it is "
        "a variable, declare it (`var Foo : Nat .`) or annotate it inline (`Foo:Nat`)."
    )


def test_rule_6_deduplicates_a_token_per_line_at_its_first_occurrence() -> None:
    text = "eq f(Foo, Foo) = Foo .\n"

    assert [(f.column, f.end_column) for f in _findings(text, "undeclared-identifier")] == [(6, 9)]


def test_rule_6_reports_tokens_in_column_order() -> None:
    text = "eq f(Zeta, Alpha, Zeta, Alpha) = Beta .\n"

    assert [(f.column, f.end_column) for f in _findings(text, "undeclared-identifier")] == [
        (6, 10),
        (12, 17),
        (34, 38),
    ]


def test_rule_6_accepts_declared_variables_operators_and_sorts() -> None:
    text = (
        "fmod T is\n"
        "    sorts Foo .\n"
        "    op Bar : Nat -> Nat .\n"
        "    var Baz : Nat .\n"
        "    op f : Nat -> Nat .\n"
        "    eq Bar(Baz) = Bar(Foo) .\n"
        "endfm\n"
    )

    assert _findings(text, "undeclared-identifier") == []


def test_rule_6_accepts_an_inline_annotation_and_its_sort() -> None:
    text = (
        "fmod T is\n    sorts Box{X} .\n    var V : nat .\n    op f : nat -> nat .\n    eq f(V:Box{nat}) = V .\nendfm\n"
    )

    assert _findings(text, "undeclared-identifier") == []


def test_rule_6_accepts_a_capitalized_label() -> None:
    text = "vars X : Nat .\nop f : Nat -> Nat .\neq [Rewrite] : f(X) = X .\n"

    assert _findings(text, "undeclared-identifier") == []


def test_rule_6_silences_the_source_linter_keywords() -> None:
    """Documented behavior (Appendix D.3): `True`/`False` are in the ported keyword list."""
    text = "eq f = True and False .\n"

    assert _findings(text, "undeclared-identifier") == []


def test_rule_6_ignores_non_statement_lines() -> None:
    text = "fmod Foo is\n    sorts Foo .\nendfm\n"

    assert _findings(text, "undeclared-identifier") == []


def test_rule_6_accepts_the_prelude_sorts_declared_nowhere_in_the_file() -> None:
    """`PRELUDE_SORT_BASES` is the single source of truth for the built-in sorts."""
    text = "fmod T is\n    eq f(M:List{Nat}) = M:List{Nat} .\nendfm\n"

    assert _findings(text, "undeclared-identifier") == []


# --- Rule 7: prelude-sort-redeclared -------------------------------------------------


def test_rule_7_reports_a_redeclared_prelude_sort() -> None:
    text = "fmod REDECLARE is\n    sort Qid .\nendfm\n"

    findings = _findings(text, "prelude-sort-redeclared")

    assert [(f.line, f.column, f.end_column) for f in findings] == [(2, 10, 13)]
    assert findings[0].message == (
        "The sort `Qid` is already declared by the Maude prelude (module QID): redeclaring it shadows "
        "the prelude sort in this module — rename it unless the shadowing is intentional."
    )
    assert findings[0].fix is None


def test_rule_7_reports_each_redeclaration() -> None:
    text = "fmod REDECLARE is\n    sorts Qid Bool .\nendfm\n"

    assert [(f.column, f.end_column) for f in _findings(text, "prelude-sort-redeclared")] == [(11, 14), (15, 19)]


def test_rule_7_matches_parameterized_names_as_declared() -> None:
    text = "fmod T is\n    sort List{X} .\nendfm\n"

    findings = _findings(text, "prelude-sort-redeclared")

    assert [(f.column, f.end_column) for f in findings] == [(10, 17)]
    assert "module LIST" in findings[0].message


def test_rule_7_ignores_user_sorts() -> None:
    text = "fmod T is\n    sorts Vector Point .\nendfm\n"

    assert _findings(text, "prelude-sort-redeclared") == []


def test_rule_7_ignores_theory_sorts() -> None:
    """`Elt` is not in the snapshot (review D6): redeclaring a theory interface sort is normal."""
    text = "fmod T is\n    sort Elt .\nendfm\n"

    assert _findings(text, "prelude-sort-redeclared") == []


def test_rule_7_ignores_a_prelude_name_declared_in_a_view_body() -> None:
    text = "view V from TRIV to NAT is\n    sort Elt to Nat .\nendv\n"

    assert _findings(text, "prelude-sort-redeclared") == []


# --- Registry -----------------------------------------------------------------------


def test_rule_registry_metadata() -> None:
    assert [(rule.code, rule.severity) for rule in RULES] == [
        ("non-ascii-character", "info"),
        ("when-guard", "warning"),
        ("dash-comment", "warning"),
        ("eq-in-term", "warning"),
        ("non-linear-pattern", "warning"),
        ("undeclared-identifier", "warning"),
        ("prelude-sort-redeclared", "info"),
    ]
