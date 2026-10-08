# Research: the dependency-warning misattribution (is it fixable? whose bug is it?)

Scratch script: `scratch_attribution.py`.

## Whose bug is it?

**Not Maude's.** Maude attributes every warning to the correct file — including
dependency files loaded via `load`/`in` inside the diagnosed file. Example capture
when `main.maude` does `load lib/baddep.maude .`:

```text
Warning: "baddep.maude", line 4 (fmod BADDEP) : unexpected end of tokens.
Warning: "baddep.maude", line 4 (fmod BADDEP): no parse for statement
eq f = s .
```

Maude prints only the **basename** of the file (no directory component), even for a
dependency in a subdirectory. The bug is in harold-mcp: `worker._parse_warnings`
(`_WARNING_RE`) discards the filename and keeps only `(line, message)`, and
`InterpreterDiagnosticProvider` attributes every parsed warning to the file being
diagnosed. A dependency's warning at its line 4 is therefore reported as if it were
the diagnosed file's line 4 — wrong file, plausible-looking wrong location.

This is exactly the option-C latent bug from the planning README, exposed by
dependencies; the README already noted it ("warnings about included files … are
reported as if they belonged to the diagnosed file"). The same mechanism hid the
deferred `q .` warning (attributed to the wrong file at the wrong line).

## Can we fix it? Yes — minimally, without a schema change

The worker can keep the filename and pass it through; the provider can then decide
where the warning belongs. The comparison works because Maude prints basenames and the
worker knows the path it loaded:

- warning filename == basename of the file being loaded → diagnostic as today
  (line + message).
- warning filename == `<standard input>` → attribute to the loaded file (some
  first-line warnings carry this attribution; see the maude-bindings research note).
- warning filename is some **other** basename → the warning belongs to a dependency
  (or, before the isolation fix, to a residue leak): report it as a **whole-file**
  diagnostic (`line=None`) on the diagnosed file with a message that names the real
  source, e.g. `In "baddep.maude", line 4: unexpected end of tokens.` The client learns
  the diagnosed file has a dependency with a problem, and the message carries the
  dependency's name and line; no position in the diagnosed file is fabricated.

Limitations (documented, not blocking):

- Same-basename collision: if the diagnosed file and a dependency share a basename
  (different directories), warnings cannot be told apart — they are attributed to the
  diagnosed file. Rare in practice; the heuristic errs toward today's behavior.
- The wire schema stays single-file (`path` names only the diagnosed file). Honest
  whole-file diagnostics are the right granularity until multi-file diagnostics exists
  (explicitly out of scope per the user's decision).

## Should the tool document it?

Yes, regardless of the fix: the tool description should state that interpreter
diagnostics reflect the *whole load* (the file plus everything it `load`s/`in`s), that
problems found in a dependency are reported as whole-file diagnostics naming the
dependency, and that line numbers always refer to the file named in the message.
