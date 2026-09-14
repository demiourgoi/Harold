# Idea Honing — Port linter.py as part of the diagnostics tool

This document records the requirements-clarification Q&A for this project.

## Q1 — Autofix policy: apply fixes, or report suggestions?

**Context:** the source linter (`improve-rag/improvement/linter.py`) has a deterministic
`autofix()` that rewrites Unicode punctuation. Harold's existing tool is annotated
`readOnlyHint=True` / `destructiveHint=False`. Should the ported tool apply fixes to the
user's file, or report them?

**Decision (user, 2026-09-13):** **Report-only.** Add an **optional fix-suggestions field**
to the tool response; the tool must never modify the source file, keeping the read-only
annotation profile valid.

**Alternatives considered:**
- *Apply the autofix in place* — rejected: mutates user files, invalidates the read-only
  annotation.
- *Separate mutating tool with `readOnlyHint=False`* — not chosen: unnecessary once
  suggestions are exposed through the diagnostics result; can be revisited later.

## Q2 — What should a fix suggestion contain?

**Question:** Should a fix suggestion be:

- **(a) Applyable edits** — a precise span (line/column range) plus replacement text, so a
  client can apply it mechanically without re-deriving the change; or
- **(b) Human-readable advice only** — a text hint (e.g. "replace U+2019 with `'`") that the
  model/agent must locate and apply itself; or
- **(c) Both** — advice text plus applyable edits where the fix is deterministic.

**Answer (user, 2026-09-14):** Option **(c)** — advice plus applyable edits, as
recommended:

- the human/model-readable advice stays in `message`;
- an optional `fix` field carries the mechanical part for deterministic fixes: a short
  `description` plus `edits: [{range, new_text}]`;
- today only the Unicode-punctuation autofix (the 8 substitutions) is deterministic; rules
  without a deterministic fix (`when`, `--`, `=`, non-linear patterns) carry no `fix`;
- `MaudePosition.column` becomes populated for fix-carrying diagnostics — a documented
  change from "always `null`, reserved for future sources".

**Notes on implications (as recorded when the question was posed):**
- (a)/(c) require the linter to emit exact columns. The linter *can* (it processes raw text),
  but Maude never reports columns, so `MaudePosition.column` would change from "always
  `None`, reserved" to "populated for linter-produced fixes" — a documented semantic change.
- (b) keeps the model in charge and the payload tiny, but leaves mechanical work to it.

**Context update (2026-09-14):** the decisions recorded below (Q3–Q8) constrain this question:
a fix suggestion belongs to a `heuristic-linter`-sourced diagnostic (Q5) and is identified
by its rule `code` (Q5); the new prelude-redeclaration rule (Q7) is `info` and carries no
fix. If fixes carry precise positions, `MaudePosition.column` stops being always-`null`
for them (see the notes above).

## Q3 — Tool shape: one composite tool (interpreter + heuristics)

**Question:** extend `maude_program_diagnostics` with the heuristic pass, create a
separate static-only `maude_program_lint`, or both over a shared internal seam?
(`research/integration-options.md` §2, options A/B/C.)

**Decision (user, 2026-09-14):** **one tool for both jobs** — `maude_program_diagnostics`
runs the interpreter load *and* the heuristic pass in a single call. The interpreter is
fast, so the combined call is not a latency concern, and one call gives the agent the
complete picture with no client-side orchestration. No separate `maude_program_lint` tool
for now. The *structural* seam of Option C is still adopted (Q4).

**Provider failures (resolved 2026-09-14):** the tool attempts **all** available providers
(so the failure report can name every provider that failed). The original preference was
to still return the successful providers' diagnostics *and* report an error; verified
against the MCP spec 2025-06-18 and the FastMCP v3 docs, that is **not expressible**: tool
execution errors are reported only through `isError: true` (a whole-call flag), and
FastMCP surfaces them by raising (`ToolError`/exception) — `ToolResult` offers content,
structured content and meta, but no error flag, and clients treat `isError` as a failed
call rather than a successful partial result. Per the user's fallback rule, **if any
diagnostic provider fails, the tool call fails** (`isError`) and the successful
providers' diagnostics are **not** returned. The error message should name the failing
provider(s) and the cause (crash vs. timeout). Revisit if MCP gains partial-result
semantics.

- **Implementation requirement (user, 2026-09-14):** a code comment at the
  failure-handling site must state that partial results (returning the successful
  providers' diagnostics alongside the error) are deliberately not returned because the
  MCP protocol does not support partial result + failure yet.

*References: [MCP 2025-06-18 Tools §Error Handling](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#error-handling),
[FastMCP v3 Tools §Error Handling / §ToolResult](https://gofastmcp.com/v3/servers/tools#error-handling).*

## Q4 — Internal architecture: diagnostic-provider seam (Option C)

**Question:** how should the port be structured so future Maude linters and static
analysis tools plug in without rewrites?

**Decision (user, 2026-09-14):** build the shared internal seam of Option C: a Python
`Protocol` for a **diagnostic provider**, with two initial implementations:

1. `interpreter` — the Maude interpreter (worker load + captured stderr warnings);
2. `heuristic-linter` — the rules ported from `improve-rag/improvement/linter.py`.

More Maude linters and static-analysis tools are expected behind the same seam in the
future; the project is a work in progress, so the server `instructions` wording
("linters and other static checks", plural) is correct and stays.

**Notes / design details:**
- Protocol **name: `DiagnosticProvider`** (confirmed by the user, 2026-09-14). Candidates
  considered and rejected: `DiagnosticSource` (mirrors the LSP `source` field, but
  collides with that field's string values), `DiagnosticEngine`, `DiagnosticProducer`,
  `Analyzer`/`Checker`.
- Providers differ in execution: the interpreter provider crosses the worker boundary
  (executor client + adapter); the heuristic linter is pure text and runs in the server
  process (no `maude` import; works even if the worker is down).
- The providers' internal diagnostic type need not equal the public result model; an
  adapter maps provider output into `MaudeDiagnostic`. The provider's stable name should
  be the single source for the `source` value (Q5).

## Q5 — Provenance and rule codes (LSP `source` and `code`)

**Question:** how does a client tell where a diagnostic came from, and which rule
produced it?

**Decision (user, 2026-09-14):** every diagnostic carries LSP-style provenance:

- `source` — `"interpreter"` for diagnostics from the Maude load (recoverable warnings
  and the synthesized unrecoverable-load error); `"heuristic-linter"` for the ported
  heuristic rules.
- `code` — the interpreter provider emits a **single fixed code** for all its
  diagnostics; working value `"compiler"` (agreed: one mechanism, one honest code; the
  `source` field is what separates providers). The heuristic linter emits **one code per
  rule**; the source linter has no codes today, so the port introduces them. Working
  names: `unicode-punctuation`, `when-guard`, `dash-comment`, `eq-in-term`,
  `non-linear-pattern`, `undeclared-identifier`, and the new `prelude-sort-redeclared`
  (exact strings to settle in design).
- The **tool description must explain both sources** and the per-source severity
  definitions (Q6), so AI agents understand the implications — notably that
  `heuristic-linter` findings are heuristics and may be false positives.
- Both providers always emit a `source` and a `code`, so both fields can be required in
  the model; exact typing (e.g. `Literal[...]` vs `str`) is a design detail.
- **Protocol surface (confirmed 2026-09-14):** the provider exposes its **stable name** as
  a read-only property (`name: str`) — not a getter method — and the aggregator uses it
  as the `source` value, so each source string lives in exactly one place.
- Each diagnostic returned by a provider carries its own **`code`** — it belongs to the
  diagnostic, not to the provider, because one provider can emit several kinds. The
  interpreter provider stamps its single constant (`"compiler"`) on every diagnostic;
  the heuristic linter stamps the per-rule code.

## Q6 — Severity model: three levels, defined per source

**Question:** `fatal`/`warning` in the source linter, `warning`/`error` in Harold —
what is the mapping, and do we add `info`?

**Decision (user, 2026-09-14):** the severity vocabulary gains a third level, `info`
(v1 had deliberately deferred it). `warning` and `error` are defined **per source**:

| source | `error` | `warning` | `info` |
| --- | --- | --- | --- |
| `interpreter` | unrecoverable load failure (synthesized, whole-file) | problem Maude recovers from | — (unused for now) |
| `heuristic-linter` | only findings that cannot be false positives (per-rule mapping to settle in design; conservative default is `warning`) | findings that **may be false positives** | non-critical observations (e.g. redeclared prelude sorts, Q7) |

- Consequence: `severity="error"` no longer means *only* the interpreter's load failure;
  the model field docs, the tool description, and the knowledge base must say so.
- `MaudeDiagnosticsSummary` gains an `info` count.

## Q7 — New heuristic rule: redeclared prelude sorts

**Question:** the rough idea mentions a redeclared-`Qid` rule that `linter.py` does not
implement; do we add it?

**Decision (user, 2026-09-14):** yes — a new heuristic rule reports an `info` diagnostic
every time a sort declared in `prelude.maude` is redeclared.

- Driving case: `sort Qid .` in `tests/integration/fixtures/redeclare_prelude.maude`.
  Maude 3.5.1 accepts it **silently** (CLI check: `load redeclare_prelude.maude` prints
  nothing); the prelude declares `Qid` in module `QID` (installed 3.5.1 copy:
  `/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/prelude.maude`, lines 842–844;
  same content in the bundled `maude-bindings/maude_java_lib/lib/.../stdlib/prelude.maude`).
- Severity `info`: not critical, and redeclaration can be legitimate.
- Expected outcome for the fixture after the port: zero interpreter diagnostics, one
  `info` heuristic diagnostic, `success=True` (Q8).
- Open design details: the exact sort set ("any sort in `prelude.maude`" — including
  parameterized-module sorts such as `List{X}`, `$Split{X}`, `Elt`, or only the top-level
  built-ins such as `Bool`, `Nat`, `Int`, `Float`, `String`, `Qid`); and how the rule
  obtains it — a bundled snapshot (hermetic; risks drift with Maude versions) vs. reading
  the installation's `prelude.maude` (matching the interpreter actually in use; needs
  discovery/configuration and caching).

## Q8 — `success` with `info` diagnostics

**Question:** does an `info`-only result count as failure?

**Decision (user, 2026-09-14):** `success` stays the one-bit verdict, extended to all
sources:

```text
success = worker_result["ok"] and no diagnostic has severity "warning" or "error"
```

`info`-only results (e.g. a lone redeclared-prelude-sort finding) keep `success=True`;
any heuristic `warning`/`error` makes it `False`.

## Q9 — Scope: which rules does the port include?

**Question:** `improve-rag/improvement/linter.py` has 6 heuristic rules, and the rough
idea adds a 7th (redeclared prelude sorts, Q7). Should the port:

- **(a)** port the 6 rules as-is (same detection behavior; English messages; rule codes),
  plus the new prelude-sort rule — keeping the current false-positive characteristics;
- **(b)** do (a) plus minimal false-positive hardening — e.g. make the rules string-literal
  and quoted-identifier aware (today only comments are stripped, so a `when`, a `--`, or
  an `=` inside a string literal or a quoted identifier can be flagged), and revisit
  rule 6's small keyword allow-list; or
- **(c)** do (b) plus an expanded taxonomy (heuristics beyond the current 6 + 1)?

**Context:**
- Q6 assigns `warning` to heuristic findings that may be false positives, which mitigates
  but does not remove over-flagging; noisy findings erode trust in a diagnostics tool
  (`research/integration-options.md` §4.6).
- A verbatim port keeps the scope tight and the behavior traceable to the source linter;
  hardening adds lexical work (string literals, quoted identifiers, escapes) and tests.
- **Recommendation (agent): (b)** — the existing taxonomy is the proven core; spending the
  effort on precision (no obvious false positives) serves the `warning`-severity policy
  and the tool's credibility better than inventing new rules. Exact hardening per rule to
  be settled in design.

**Answer (user, 2026-09-14):** Option **(b)** — port the 6 rules plus the new
prelude-sort rule, with minimal false-positive hardening (string-literal and
quoted-identifier awareness where it prevents obvious false positives; revisit rule 6's
keyword allow-list). No taxonomy expansion in this project. Exact per-rule hardening to
be settled in design.

## Q10 — Where does the prelude-sort rule get its list?

**Question:** the Q7 rule compares redeclared sorts against the sorts declared in
`prelude.maude`. Where does that list come from?

- **(a) Bundled snapshot** — a bundled list (Python constant or data file) of the sort
  names, with a provenance comment (Maude version, source file, extraction date),
  generated from the prelude. Hermetic (no filesystem/env dependency; fully
  deterministic tests); must be regenerated when Maude is upgraded (documented step).
- **(b) Read the installed prelude at runtime** — locate `prelude.maude` in the Maude
  installation (a `HAROLD_*` setting, or discovery) and parse it (cached). Always matches
  the interpreter in use; adds path discovery/configuration, unreadable/missing failure
  modes, and parsing code. The heuristic linter must not import `maude`, so the path must
  come from configuration/discovery rather than from the bindings.
- **(c) Hybrid** — bundled snapshot by default, with an optional path override to match a
  customized/newer Maude installation.

**Context:**
- The `maude` dependency is pinned, so drift is limited to deliberate upgrades — but a
  silent snapshot would then make the rule miss (or invent) sorts.
- Where the prelude lives depends on the Maude installation (in this environment:
  `/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/prelude.maude`; also bundled in
  `maude-bindings/maude_java_lib/lib/.../stdlib/prelude.maude`), so runtime discovery
  needs a configuration story to work across installs.
- Extraction nuance, any option: only real declarations count — the prelude's `view`
  bodies contain sort *mappings* (`sort Elt to Nat .`), not declarations; decide whether
  theory sorts (`Elt` in `fth TRIV`) are included.
- **Recommendation (agent): (a)** — smallest, hermetic and testable; an override setting
  (c) can be added later if users need to match custom Maude versions.

**Answer (user, 2026-09-14):** Option **(a)** — bundled snapshot. Additionally, **the
snapshot-update script is part of this task's scope**: a bash or Python script that, given
the absolute path of a `prelude.maude` file, regenerates the bundled snapshot. "Only real
declarations count" is confirmed (e.g. `view` sort mappings are not declarations); whether
theory sorts such as `Elt` in `fth TRIV` are included is a design detail.

## Q11 — Definition of done for this project

**Question:** what counts as "done"? Proposed acceptance criteria (confirm or amend):

1. `maude_program_diagnostics` returns merged diagnostics from all providers, each with
   `source`, `code`, `severity`, `range`, `message`, and `fix` where deterministic; the
   tool description explains the sources and the per-source severity meanings (Q5/Q6).
2. Severity/success semantics: any `warning` or `error` diagnostic (from either source)
   makes `success=False`; `info`-only results keep `success=True` (Q8).
3. Fixture outcomes: clean → success, no diagnostics; recoverable warning → interpreter
   warning; unrecoverable load → synthesized interpreter error; `redeclare_prelude.maude`
   → interpreter silent + exactly one `info`/`heuristic-linter` diagnostic (Q7).
4. One test fixture per heuristic rule (6 ported + prelude-sort rule), exercising the
   hardened detection (string literals / quoted identifiers) and, for the Unicode rule, an
   applyable `fix` with populated columns (Q2/Q9).
5. Provider-failure semantics (Q3): a simulated worker crash/timeout fails the whole call
   with an error naming the provider and cause; the failure-handling code carries the
   explanatory comment; the next call recovers on the recreated worker.
6. Unit tests (rules, provider adapter, result mapping, success rule) and integration
   tests (real interpreter, existing + new fixtures) are green; `make release`
   (install + check + test + docs-test) passes.
7. Snapshot maintenance (Q10): the bundled prelude-sort snapshot carries provenance
   (Maude version, source path, extraction date) and the update script regenerates it
   from an absolute path to a `prelude.maude`.
8. Repo hygiene per the project conventions: new modules added to `docs/modules.md`;
   README tool list/description updated; `CHANGELOG.md` entry; a suggested minor version
   bump in `pyproject.toml`; the user is prompted to re-run the codebase-summary skill.
9. Non-goals / fixed scope decisions: no separate lint tool (Q3); no mutation of the
   diagnosed file (Q1); `improve-rag/improvement/linter.py` is left untouched (Harold's
   port is independent); messages are English-only, no locale mechanism.

**Answer (user, 2026-09-14):** Confirmed as-is — items 1–9 are the definition of done for
this project.
