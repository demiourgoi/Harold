# Make search path available to maude run tool

## Context

Given the following maude prgram

```maude
***(
# The Shepherd's River Crossing Problem
A shepherd needs to cross a river with three things:

- A cabbage
- A dog
- A sheep

He has a small boat that can only carry the shepherd and _one item_ at a time.

The **constraints**:

- If the sheep is left alone with the cabbage, the sheep will eat the cabbage.
- If the sheep is left alone with the dog, the dog will eat the sheep.
- The dog does not eat the lettuce.

The __question__: How can the shepherd get everything across the river without anything being eaten?
)
mod SHEPHERD is
  protecting BOOL .

  sorts Side Config .

  ops l r : -> Side .
  op other : Side -> Side .
  eq other(l) = r .
  eq other(r) = l .

  --- A bank is safe when neither forbidden pair is there without the shepherd.
  op safe : Side Side Side Side -> Bool .
  vars P C D S : Side .
  eq safe(P, C, D, S) =
    (C =/= S or P == S) and (D =/= S or P == S) .

  --- st(shepherd, cabbage, dog, sheep)
  op st : Side Side Side Side -> Config .

  crl [crossAlone] :
    st(P, C, D, S)
    =>
    st(other(P), C, D, S)
    if safe(other(P), C, D, S) .

  crl [crossWithCabbage] :
    st(P, C, D, S)
    =>
    st(other(P), other(C), D, S)
    if C == P /\ safe(other(P), other(C), D, S) .

  crl [crossWithDog] :
    st(P, C, D, S)
    =>
    st(other(P), C, other(D), S)
    if D == P /\ safe(other(P), C, other(D), S) .

  crl [crossWithSheep] :
    st(P, C, D, S)
    =>
    st(other(P), C, D, other(S))
    if S == P /\ safe(other(P), C, D, other(S)) .
endm
```

we can run the following session

```
\||||||||||||||||||/
		   --- Welcome to Maude ---
		     /||||||||||||||||||\
	    Maude 3.5.1 built: Jul 16 2025 12:00:00
	     Copyright 1997-2025 SRI International
		   Thu Oct 29 20:22:58 2026
Maude> in  shepherd.maude
==========================================
mod SHEPHERD
Maude> search [1, 7] in SHEPHERD : st(l, l, l, l) =>* st(r, r, r, r) .
search [1, 7] in SHEPHERD : st(l, l, l, l) =>* st(r, r, r, r) .

Solution 1 (state 9)
states: 10  rewrites: 427 in 0ms cpu (0ms real) (~ rewrites/second)
empty substitution
Maude> show path labels 9 .
crossWithSheep
crossAlone
crossWithCabbage
crossWithSheep
crossWithDog
crossAlone
crossWithSheep
Maude>

Maude> show path  9 .
state 0, Config: st(l, l, l, l)
===[ crl [crossWithSheep] : st(P, C, D, S) => st(other(P), C, D, other(S)) if S == P = true /\ safe(other(P), C, D,
    other(S)) = true . ]===>
state 1, Config: st(r, l, l, r)
===[ crl [crossAlone] : st(P, C, D, S) => st(other(P), C, D, S) if safe(other(P), C, D, S) = true . ]===>
state 2, Config: st(l, l, l, r)
===[ crl [crossWithCabbage] : st(P, C, D, S) => st(other(P), other(C), D, S) if C == P = true /\ safe(other(P),
    other(C), D, S) = true . ]===>
state 3, Config: st(r, r, l, r)
===[ crl [crossWithSheep] : st(P, C, D, S) => st(other(P), C, D, other(S)) if S == P = true /\ safe(other(P), C, D,
    other(S)) = true . ]===>
state 5, Config: st(l, r, l, l)
===[ crl [crossWithDog] : st(P, C, D, S) => st(other(P), C, other(D), S) if D == P = true /\ safe(other(P), C,
    other(D), S) = true . ]===>
state 7, Config: st(r, r, r, l)
===[ crl [crossAlone] : st(P, C, D, S) => st(other(P), C, D, S) if safe(other(P), C, D, S) = true . ]===>
state 8, Config: st(l, r, r, l)
===[ crl [crossWithSheep] : st(P, C, D, S) => st(other(P), C, D, other(S)) if S == P = true /\ safe(other(P), C, D,
    other(S)) = true . ]===>
state 9, Config: st(r, r, r, r)
Maude>
```

This allows use to get the rewrite path (secuence of rewrite rules) to get the founds solution.

## Problem

Currently the tool [@interpreter.py (470:477)](file:///home/juanrh/git/demiourgoi/Harold/harold-mcp/src/harold_mcp/server/tools/interpreter.py#L470:477) does not return the search path as part of the result of a search. Also, the tool does not expose a command for showing the path to a solution.  
But even if we did, the problem is that the state number for the solution is generated during the execution of the search, so even if we add a command for showing the paths, the agent could not know the state number to use. This is a consecuence of using hermetic / independent runs, which is still a very desirable feature, but that we need to handle carefully

We must design a way for the agent to get the paths together with the solution: one option is always returning the path for each search, or providing an option for the search command to request the path for searches
We also must consider if there is any other command that would benefit from a similar solution

Take .agents/summary/index.md into account to get an overview of this codebase
