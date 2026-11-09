# Chapter 9: External Objects and IO

## Core Idea
Maude configurations can talk to the world: external objects (streams, files, directories, sockets, processes, timers, PRNGs, and later meta-interpreters) live outside the configuration but communicate by the same message-passing discipline, driven by `erewrite` — a `frewrite` that polls external events and suspends when only the environment can advance the computation.

## Frameworks Introduced
- **Portals**: a configuration exchanging messages with external objects must contain a portal — the constant `<>` (`op <> : -> Portal [ctor portal] .` in CONFIGURATION). Configurations are ephemeral and un-identifiable; the portal is what makes external message *delivery* decidable (only portal configurations receive from outside; in nested configurations only the outer one should have a portal).
- **`erewrite` (erew) semantics**: (1) external events checked after every fair traversal; (2) an event injects messages enabling more internal rewrites; (3) when no internal rewrites remain but requests are pending (socket read, process wait), Maude **suspends** instead of returning to the prompt — abort with `^C`; (4) external-object transactions never show in tracing/profiling/rewrite counts; and external objects created during one `erewrite` do not survive it. Bad/early messages to external objects **stay in the configuration** (deliverable later, or valuable for debugging).
- **The manager pattern**: unique built-in objects (`fileManager`, `directoryManager`, `socketManager`, `processManager`, `timeManager`, `prngManager`) accept *create* messages and answer with handle objects named by constructors — `file(N)`, `socket(N)`, `process(N)`, `timer(n)`, `prng(N)` — plus a distinct request/reply message pair per operation (`openFile`/`openedFile`, `createClientTcpSocket`/`createdSocket`, `getLine`/`gotLine`, ...). Errors come back as `fileError` / `socketError` / `streamError` / `processError` / `timeError` / `prngError` with textual reasons.
- **Security gating**: file handling, process execution, and directory access are **disabled by default**; enable per feature with `-allow-files`, `-allow-processes`, `-allow-dir`, or everything with `-trust` (Appendix A.1). Rationale: Maude programs are easy to eyeball wrongly, and meta-interpreters can assemble and run code.
- **Standard streams** (`STD-STREAM`): `stdin`/`stdout`/`stderr` as permanent external objects. `write(STREAM, ME, TEXT)` → `wrote`; stdout/stderr are auto-flushed and accept nothing else, empty strings are errors. `getLine(stdin, ME, PROMPT)` → `gotLine(ME, stdin, TEXT)` (line-oriented; backslash-newline continues input; `"\n"` = empty line, `""` = EOF/error); non-blocking and cancellable (`cancelGetLine` → `canceledGetLine`, quietly discarded if no read pending).

## Key Concepts
- **FILE (`-allow-files`)**: `openFile(fileManager, ME, PATH, MODE)` with C-stdio modes `r r+ w w+ a a+`; reads via `getLine` or `getChars(FH, ME, N)`; writes via `write`; `setPosition/getPosition` (with `start/current/end` bases), `flush`, `closeFile`, `removeFile`, `makeLink(..., hard|symbolic)`; errors like `"Bad mode."`, `"No such file or directory"` (bare strings come from the OS).
- **DIRECTORY (`-allow-dir`)**: `getDirectoryEntries` returns `(name, EntryType?)` pairs — `file`, `directory`, `socket`, `pipe`, `charDevice`, `blockDevice`, `symbolLink(T)`, and `endOfDirectory` (in the bigger `EntryType?` sort so patterns can target only real entries); `makeDirectory`/`removeDirectory` (empty dirs only).
- **SOCKET**: `createClientTcpSocket(manager, ME, ADDRESS, PORT)` or `createServerTcpSocket`; server side `acceptClient` → `acceptedClient(HOST, CLIENT-SOCKET)`; `send`/`sent`, `receive`/`received`; **all client-socket errors are handled by closing the socket** (`closedSocket(ME, SOCK, REASON)`); a closed socket's name may be reused — messaging a stale name silently corrupts; buffered socket variants exist (9.4.3).
- **PROCESS (`-allow-processes`)**: `createProcess(manager, ME, CMD, StringList, opts)` → `createdProcess(ME, mgr, PROCESS, INOUT-SOCKET, ERR-SOCKET)` — the process's stdin/stdout and its stderr **are sockets**, use the socket interface; keep `receive`s pending on both to avoid stalls; `signalProcess` for signals; `waitForExit` → `exited(normalExit(CODE) | terminatedBySignal(NAME))`; always wait — Maude returns to the prompt when *it* has nothing left to do, zombies are your problem otherwise.
- **TIME (`timeManager`)**: `getTimeSinceEpoch` (nanoseconds); `getDateAndTime` / `getLocalDateAndTime` → `Date` (`Y \ M \ D`), `Time` (`H : M : S`), timezone `[NAME, ABBR, OFFSET, DST]`; **timers**: `createTimer` (`timer(n)` objects), `startTimer(T, oneShot|periodic, NS)` → `timeOut` messages (periodic repeats; re-starting resets), `stopTimer`/`deleteTimer` (stopping a quiescent timer is legal — race conditions are acknowledged); units by suffix: `N us`, `N ms`, `N seconds` (all into nanoseconds).
- **PRNG objects (`prngManager`)**: `createPrng(ME, REQ, "MT32"|"MT64")` → `prng(N)`; `setSeed` (any size seed; low bits used — seed an MT32 from nanoseconds-since-epoch), `getNext` → `gotNext`, `deletePrng`.
- **Ctrl-C discipline (9.8)**: during `erew` suspension, `^C` aborts the command; interrupts during stream reads return empty strings and may enqueue debugger entries.

## Mental Models
- Think of `erewrite` as rewriting *plus an event loop*: internal rewriting to a stuck point, poll the environment, inject events, repeat, suspend — your object system is both a Maude term and a Unix program.
- Treat the manager objects as system-call schools and their handle objects as file descriptors; message pairs are request/response syscalls with the requester Oid as return address.
- Design with the state-machine-of-your-object discipline (see HELLO): one rule per (state, message) pair; replies move you forward.

## Anti-patterns
- **Forgetting the portal**: no `<>`, no external conversation — messages from external objects are undeliverable.
- **Using `rew`/`frew` for external I/O**: they never poll events; only `erewrite` runs the event loop.
- **Writing to sockets that may have closed**: errors close the socket and its name gets reused; guard with state and drop references after `closedSocket`.
- **Signalling process exit expectations**: without `waitForExit`, Maude happily finishes while your child lives on; without pending `receive`s on both process sockets, the child stalls on full buffers.
- **Assuming external rewrites appear in rewrite counts or traces**: they don't — don't debug programs by counting.
- **Expecting external objects to persist** across `erew` commands: they die with the command that created them.
- **Reading reply-strings programmatically**: error strings are for humans ("Bad mode." vs OS strings); match on constructors (`fileError` etc.), not on reason text.

## Code Examples
```maude
omod HELLO is
  inc STD-STREAM . pr NAT .
  class MyClass | state : Nat .
  op myObj : -> Oid .
  op run : -> Configuration .
  var O : Oid . vars S : String .
  eq run = <> < myObj : MyClass | state : 0 > .
  rl < myObj : MyClass | state : 0 >
     => < myObj : MyClass | state : 1 > getLine(stdin, myObj, "What is your name? ") .
  rl < myObj : MyClass | > gotLine(myObj, O, S)
     => < myObj : MyClass | >
        if S =/= "" then write(stdout, myObj, "Hello " + S) else none fi .
endom

Maude> erew run .
What is your name? Zaphod Beeblebrox
Hello Zaphod Beeblebrox
result Configuration: <> wrote(myObj, stdout) < myObj : MyClass | state : 1 >
```
- **What it demonstrates**: the canonical external-interaction skeleton — `<>` portal + one state rule sending a request + one reply rule reacting, all under `erew`.

```maude
--- a process child + socket conversation (PROCESS module)
createProcess(processManager, me, "bc", ("-i" ; nil), none)
--- reply: createdProcess(me, processManager, PROCESS, INOUT, ERR)
--- keep receive(INOUT, me) and receive(ERR, me) pending;
--- finish with waitForExit(PROCESS, me) -> exited(normalExit(0))
```
- **What it demonstrates**: the process pattern — its pipes are sockets, so all socket discipline applies; the desk-calculator and Python/Maude process examples in the chapter follow exactly this skeleton.

## Reference Tables
| Feature | Enable flag | Manager | Key request → reply pairs |
|---|---|---|---|
| std streams | (always) | — (objects `stdin stdout stderr`) | `write`→`wrote`, `getLine`→`gotLine`, `cancelGetLine`→`canceledGetLine` |
| files | `-allow-files` | `fileManager` | `openFile`→`openedFile|fileError`, `getChars`→`gotChars`, `getLine`→`gotLine`, `setPosition`/`getPosition`, `flush`, `closeFile`→`closedFile`, `removeFile`, `makeLink` |
| directories | `-allow-dir` | `directoryManager` | `getDirectoryEntries`→`gotDirectoryEntry(name, EntryType?)`, `makeDirectory`, `removeDirectory` |
| TCP sockets | (always) | `socketManager` | `createClientTcpSocket`/`createServerTcpSocket`→`createdSocket`, `acceptClient`→`acceptedClient`, `send`→`sent`, `receive`→`received`, `closeSocket`→`closedSocket` |
| processes | `-allow-processes` | `processManager` | `createProcess`→`createdProcess`, `signalProcess`→`signaledProcess`, `waitForExit`→`exited(normalExit|terminatedBySignal)` |
| time/timers | (always) | `timeManager` | `getTimeSinceEpoch`→ns, `getDateAndTime`/`getLocalDateAndTime`, `createTimer`→`timer(N)`, `startTimer(oneShot|periodic, NS)`→`startedTimer` + asynchronous `timeOut` |
| PRNGs | (always) | `prngManager` | `createPrng("MT32"|"MT64")`, `setSeed`→`seedSet`, `getNext`→`gotNext`, `deletePrng` |

## Worked Example
The HTTP/1.0 client (9.4.1) — the pattern for every network protocol:

1. `createClientTcpSocket(socketManager, self, "www.google.com", 80)` → `createdSocket(self, mgr, S)`.
2. Send a request line as one string: `send(S, self, "GET / HTTP/1.0\r\n\r\n")` → `sent`.
3. `receive(S, self)` → `received(S, self, DATA)`, splitting into pages and printing each via the streams API.
4. `closeSocket(S, self)` → `closedSocket(..., "")`.

What this teaches about Maude I/O design: all sequencing is *your object's state machine* (typically an attribute counting connection phases), all OS knowledge is behind manager objects, and the same five-step skeleton serves a chat server (`createServerTcpSocket` + `acceptClient` loop), the timed vending simulation (`TIME` timers as heartbeat), or scripting a Unix tool via `PROCESS`. Combine `TIME` + `PRNG` when the model needs real-time stochastic behavior — nanosecond clocks seed MT32 generators idiomaticly.

## Key Takeaways
1. The external world is just more objects: unique managers create handle objects; message pairs do syscalls; errors come back structured.
2. `erewrite` is the only driver: it integrates external events into fair rewriting, suspends on pending-only states, and gives deterministic command lifetimes.
3. Portals gate external contact — exactly one per communicating (nested outermost) configuration.
4. Dangerous features default off: `-allow-files/-allow-processes/-allow-dir`, `-trust` to open all; treat Maude programs as untrusted code.
5. External rewrites are invisible to rewrite counts (and mostly to traces) — plan debugging around structured state in your objects.
6. Reply messages carry return addresses (the requester's Oid, second argument); keep that convention when writing your own protocol layers.

## Connects To
- **Ch 6**: portal/attribute basics; object-message fair rewriting drives the internal half of every interaction.
- **Ch 8**: `random`/`COUNTER`'s twins here — PRNG/timer objects are the external, stateful versions for real-time simulation.
- **Ch 10**: strategies can drive externally interacting systems; timer `timeOut` messages are classic asynchronous drivers.
- **Ch 19**: meta-interpreters (external Maude-in-Maude) use exactly this machinery via meta-`process` idiom.
- **App A.1**: the full command-line flag table (`-trust`, feature gates).
- **Ch 21**: interrupt/debugger interplay when `^C` hits a suspended `erewrite`.
