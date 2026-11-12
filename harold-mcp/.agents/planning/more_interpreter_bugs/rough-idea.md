# More bugs on the interpreter tool

This is a follow up of .agents/planning/Unexpected_failure_during_search to try to reproduce the bug that was not reproduced there.
The files `reproduction_attempt-*` show an investigation performed on a host much slower than this one, for the following commit: 

fbff888 (HEAD -> main, origin/main, origin/HEAD) Keep the 0.0.5.dev0 version and fold search paths into its changelog section

The first reproduction attempt was done on .agents/planning/Unexpected_failure_during_search, and then following the numbering of the files:

- attempt 2 : reproduction_attempt-2.md
- attempt 3 : reproduction_attempt-3.md
- attempt 4 : reproduction_attempt-4.md

Specifically .agents/planning/more_interpreter_bugs/reproduction_attempt-3.diff is the uncommitted changes on top of commit fbff888, after .agents/planning/more_interpreter_bugs/reproduction_attempt-3.md

Please see .agents/summary/index.md for an introduction to this codebase

We have to 

- reproduce all the errors
- find the root causes
- fix the issues
