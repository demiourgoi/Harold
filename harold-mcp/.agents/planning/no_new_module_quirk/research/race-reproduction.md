# Research: reproducing opencode's claim (parallel calls race on shared interpreter state)

Scratch scripts: `scratch_race.py` (current code), `scratch_race_fixed.py`
(`max_tasks_per_child=1` via a custom factory).

## Claim (opencode, quoted by the user)

> Checked all 17 fixtures with `maude_program_diagnostics` (non_linear_pattern re-run
> alone; the first pass had a spurious interpreter error because parallel calls race on
> the shared Maude interpreter — load diagnostics are only reliable when checks are
> serialized).

## Reproduction

Diagnose all `tests/integration/fixtures/*.maude` concurrently (one thread per worker)
through `maude_program_diagnostics`, then flag any **interpreter** diagnostic on a
fixture whose interpreter load must be clean. The "interpreter-clean" set is the 11
fixtures the integration suite asserts are silent (`hello`, `hello2`,
`no_new_module`, `nonascii_apostrophe`, `string_with_specials`, `quoted_id_when_dash`,
`declarations_when_dash`, `non_linear_pattern`, `capitalized_identifiers_ok`,
`redeclare_prelude`, `elt_sort_declaration`).

Result on the current code — **21/21 rounds spurious** (7 rounds × workers 1/2/4):

| workers | victim of the spurious `syntax error` |
| --- | --- |
| 1 | `non_linear_pattern.maude` (every round) |
| 2 | `nonascii_apostrophe.maude`, `non_linear_pattern.maude`, `quoted_id_when_dash.maude` (varies) |
| 4 | `hello.maude`, `non_linear_pattern.maude`, `nonascii_apostrophe.maude` (varies) |

Every spurious diagnostic is `("interpreter", "warning", "syntax error")` at line 2 —
the deferred `q .` warning from `no_new_module.maude` attributed to whichever file the
contaminated worker happens to diagnose next.

## Correction to the claim

It is **not a race**: with `maude_workers=1` all calls are already serialized and the
spurious diagnostic still appears deterministically (victim = the file that follows
`no_new_module.maude` in submission order). The bug is *parse residue surviving across
loads in one worker process*; parallelism merely makes the victim unpredictable.
"Serializing checks" therefore does **not** make load diagnostics reliable.

## Verification of the fix

Same harness with `max_tasks_per_child=1` (via the executor factory): **9/9 rounds
clean** (3 rounds × workers 1/2/4). Each call gets a fresh process, so the residue dies
with its worker and can never reach another call.

Note: `no_new_module.maude`'s `red in NAT : 1 + 2 .` prints its reduction to stdout on
every diagnosis (normal interpreter behavior; stdout is not captured as diagnostics and
the file is a correct program).

## Implication for the test suite

A regression test can reuse this exact harness: submit all fixtures concurrently (with
≥ 2 workers to exercise parallelism) and assert the interpreter-clean set stays clean.
It fails 100% today and passes after the fix; it is fast enough to keep (spawn+init per
call is the dominant cost; see `isolation-cost.md`).
