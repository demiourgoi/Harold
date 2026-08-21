# Root Cause Analysis: SIGSEGV in native Maude code under load

## Crash description

Running a Flink job with `MaudeMonitor`-based properties under heavy load eventually crashes with:

```
# A fatal error has been detected by the Java Runtime Environment:
#  SIGSEGV (0xb) at pc=0x00007fea48080168, ...
# Problematic frame:
# C  0x00007fea48080168
# The crash happened outside the Java Virtual Machine in native code.
```

The crash occurs after processing many spans/events. The `monitorModule.delete()` change (described below) was an attempted fix but did not resolve the crash; it has been reverted.

## Native object lifecycle (SWIG bindings)

Two key C++ classes underpin the Java bindings:

### `VisibleModule` (wrapped as Java `Module`)
- **Source**: `maude_wrappers.cc:265-278`, `getModule(name)` returns `premodule->getFlatModule()` — a **singleton** pointer owned by the Maude interpreter. It is NOT heap-allocated per-request; each call returns the same `VisibleModule*`.
- `getModule(name)` calls `vmod->protect()` on the returned pointer.
- The SWIG `%newobject getModule` annotation (in `maude.i:99`) tells SWIG the Java wrapper owns the pointer, so `Module.delete()` calls `delete (VisibleModule*)ptr`, whose `%extend` destructor (`module.i:36-44`) calls `$self->unprotect()` and then the C++ `delete` operator **frees the singleton**.
- **Consequence**: `Module.delete()` frees an object still owned by the Maude interpreter. Any subsequent use of that pointer (via another `getModule` call, or via Terms referencing it) is use-after-free → SIGSEGV.

### `EasyTerm` (wrapped as Java `Term`)
- **Source**: `easyTerm.cc:56-77`. Constructor calls `protect()` on the module; destructor calls `unprotect()` on the module and frees the internal `DagNode*`/`Term*`.
- Created by `Module.parseTerm(...)` (marked `%newobject` in `module.i:24`). Each call heap-allocates a new `EasyTerm*`.
- `Term.delete()` → `delete_Term(swigCPtr)` → `delete (EasyTerm*)ptr` → `~EasyTerm()` → frees native memory.

### Protect/unprotect balance per evaluation

| Operation | Module protect Δ |
|-----------|-----------------|
| `getModule(name)` | +1 |
| `parseTerm(...)` (EasyTerm ctor) | +1 |
| `Module.delete()` (explicit or via GC `finalize()`) | -1 + **frees VisibleModule** |
| `Term.delete()` (explicit or via GC `finalize()`) | -1 |

## Issues found

### 🟠 Issue #1 — `soup` Terms abandoned in the loop (lines 885-905)

Each reassignment of `soup` in the event loop discards the previous `Term` without explicit deletion:

```scala
var soup = monitorModule.parseTerm(initialSoup)   // Term #1 (native heap)
orderedEvents.foreach { event =>
    soup = monitorModule.parseTerm(nextSoup)       // Term #2; Term #1 leaked
    // ...
}
```

Each `parseTerm` heap-allocates a new native `EasyTerm`. The old one is no longer referenced, so it waits for JVM GC → `finalize()` → `delete()` → native free. __Under heavy load__ (many events per window × many concurrent keys), hundreds/thousands of __native `EasyTerm` objects accumulate before GC triggers__. The native C++ heap can exhaust before the JVM decides to GC, causing allocation failures in Maude's internal code → SIGSEGV.

### 🟠 Issue #2 — `truthTerm` leaked in `soupToTruthValue` (lines 796-805)

```scala
def soupToTruthValue(propertyModule: Module, maudeProperty: String)(soup: Term): TruthValue = {
    val truthTerm = propertyModule.parseTerm(s"""${soup.toString} |= $maudeProperty""")
    truthTerm.reduce()
    truthTerm.toString match { ... }
    // truthTerm never explicitly deleted → waits for GC
}
```

Called at least once per window evaluation (line 924), plus once per event when `onEvaluationStep` is active (line 920). Same accumulation problem as Issue #1.

### 🔴 Issue #3 — Module wrappers freed by GC `finalize()`

Even without explicit `monitorModule.delete()`, the Module wrapper created by `loadModule` (line 291, `jMaude.getModule(moduleName)`) is a local variable in `ensureModulesLoaded` / `runWithLock`. When it goes out of scope and GC runs, `finalize()` → `delete()` → frees the `VisibleModule` singleton. This creates a use-after-free hazard for:

- **Subsequent evaluations** that call `getModule(moduleName)` → returns dangling pointer.
- **Outstanding Terms** from the same module — when their `finalize()` runs, `~EasyTerm()` accesses `symbol()->getModule()` → dangling pointer.

Since `runWithLock` serializes all Maude access, the GC thread calling `delete_Module` asynchronously is a race condition with the locked thread doing `parseTerm`/`rewrite`/`reduce`.

### 🟡 Issue #4 — `IsPoliteTextOpHook.run` (example code, lower priority)

In `IsPoliteTextOpHook.scala:71-94`, `term.symbol()`, `.getModule()`, `textArg.getSort()` all create owned native wrappers (`Symbol`, `Module`, `Sort`) that are never explicitly deleted.

### 🟡 Issue #5 — Gradle daemon OOM from DEBUG log buffering

The Flink job logs verbose Maude term strings at `DEBUG` level for every `parseTerm`/`rewrite` step. When run via `make clean run EXAMPLE=...` (see `DEVELOPER_GUIDE.md`), Gradle's daemon captures stdout with only `-Xmx512m` heap and `-XX:+HeapDumpOnOutOfMemoryError`. Under load, the daemon's log buffer grows until the heap exhausts (389MB log observed), producing a heap dump and killing the daemon.

This is a Gradle/logging infrastructure issue, not a native memory leak.

**Fix**: set `logger.linoleum.level = INFO` in `log4j2.properties` to suppress term-dumping DEBUG messages in production/long-running runs.

## Proposed fix

### 1. Cache Module wrappers in `MaudeModules` (fixes Issue #3)

Add a `ConcurrentHashMap[String, MaudeModule]` to `MaudeModules`, keyed by `resourcePath + "/" + moduleName`. Before calling `jMaude.getModule()`, check the cache. Since the returned `VisibleModule*` is a singleton, caching ensures:
- Only one Java `Module` wrapper exists per underlying Maude module.
- The wrapper stays alive for the JVM lifetime (referenced by the cache), so GC never calls `finalize()` → `delete()` on it.
- No use-after-free of the `VisibleModule*` pointer.

Key format:
- Regular resources: `resourcePath + "/" + moduleName` (e.g., `"maude/linoleum/trace.maude/TRACE-CLASS-OBJECTS"`)
- Stdlib resources: `MAUDE_STDLIB_RESOURCE_PREFIX + fileName + "/" + moduleName` (e.g., `"maude/stdlib/model-checker.maude/SATISFACTION"`)

The existing `lazy val` modules (`traceTypesModule`, `satisfactionModule`, `jsonModule`) can either be migrated to use the same cache or kept as-is (they already serve the caching purpose for those specific modules).

**Thread safety**: The cache is read/written inside `runWithLock` (synchronized on `maudeRuntime`), so a non-concurrent map would also be safe. However, using `ConcurrentHashMap` or `TrieMap` adds defense-in-depth.

### 2. Explicitly delete Terms (fixes Issues #1 and #2)

- In the `evaluateWithCallback` loop, call `oldSoup.delete()` before reassigning `soup`.
- In `soupToTruthValue`, call `truthTerm.delete()` after extracting the result string.
- In `evaluateWithSteps`, the `onEvaluationStep` callback captures the `soup` Term reference — but the Term is still alive (referenced by `soup` in the loop), so no extra deletion needed there.

### 3. (Optional, lower priority) Clean up `IsPoliteTextOpHook`

Explicitly delete `Symbol`, `Module`, and `Sort` objects created in the hook's `run` method.

## Implementation steps

1. Add `private val moduleCache: TrieMap[String, MaudeModule]` to `MaudeModules`.
2. Add a private `cachedLoadModule(resourcePath: String, moduleName: String): MaudeModule` method.
3. Refactor `loadModule` and `loadStdLibModule` to use the cached method.
4. In `evaluateWithCallback`: delete previous `soup` before reassignment in the loop.
5. In `soupToTruthValue`: delete `truthTerm` after extracting the result.
6. Run tests to verify no regressions.

## Implementation notes

Every `parseTerm` call in `evaluateWithCallback` now has a corresponding explicit `delete()`:

| # | Created at | What | Deleted at |
|---|-----------|------|-----------|
| 1 | L923: `parseTerm(initialSoup)` | Initial soup | If events exist: as `oldSoup` in 1st iteration (L946). If no events: L966. |
| 2 | L944: `parseTerm(nextSoup)` (per event) | Each event's new soup | Next iteration's `oldSoup` (L946), except the last → L966 |
| 3 | L833: `parseTerm(...)` in `soupToTruthValue` | `truthTerm` | L841, inside the method |

### Loop walkthrough

```
Event 1:  oldSoup=soup(initial)  →  soup=parseTerm(ev1)  →  oldSoup.delete()  ✓
Event 2:  oldSoup=soup(ev1)      →  soup=parseTerm(ev2)  →  oldSoup.delete()  ✓
  ...
Event N:  oldSoup=soup(evN-1)    →  soup=parseTerm(evN)  →  oldSoup.delete()  ✓
After loop:  soup.toString; getTruthValue(soup); soup.delete()               ✓
```

If `orderedEvents` is empty:
```
soup(initial).toString; getTruthValue(soup); soup.delete()                   ✓
```

The only edge case where a Term could leak is if `parseTerm` returns null and `checkNotNull(soup)` throws — but this is an unrecoverable parse failure, not the normal execution path.

---

# Throughput degradation and job failure under load

## Symptoms

At ~8,800 spans/sec, the Flink job starts to slow down and eventually fails. Source operators show **HIGH backpressure** on 4/5 subtasks, while the window/sink operator reports `OK`. TaskManager slots become free as tasks fail.

```
Source: exportTracesRequests  → 4/5 subtasks HIGH backpressure, busy 18-44%, idle 0%
Window/Sink                  → 5/5 subtasks OK backpressure
```

## Root causes (non-SIGSEGV)

### 1. `evaluatedSpans.print()` — stdout sink bottleneck

`SpanStreamEvaluator.scala:91` calls `.print()` on the evaluated stream, which adds a `PrintSinkFunction` that writes **every single record to stdout**:

```scala
val evaluatedSpans = spamEvaluator(spanInfos)
evaluatedSpans.print()  // ← serial bottleneck
val linoleumSink = new LinoleumSink(linolenumCfg)
linoleumSink(evaluatedSpans)
```

At 8.8K spans/sec, writing to stdout is a significant serial bottleneck. In standalone mode with 5 TMs, stdout writes are per-TM but still slower than direct binary sinks.

### 2. Log level mismatch

`log4j2.properties` sets `io.github.demiourgoi.linoleum` to `ERROR` for load testing, but the TMs log at **INFO** level. Every Maude evaluation produces 2+ log lines (`Evaluated window...`, `Writing evaluated trace...`). At 8.8K spans/sec this generates enormous I/O pressure.

### 3. Single-threaded Maude interpreter lock

Each TaskManager runs 1 slot → 1 JVM → 1 Maude interpreter instance. The Maude C++ library has a global interpreter lock, so each TM can only process **one Maude evaluation at a time**. With `message-rewrite-bound: 100`, each window evaluation requires up to 100 sequential Maude rewrite steps.

### 4. 5-second session gap triggers many windows

Each trace has spans within a 5-second window gap. At high throughput, many traces close simultaneously, flooding the window/sink operator with evaluations. Each evaluation requires Maude rewriting, which is single-threaded per TM.

### 5. Memory pressure under sustained load

The `state-config.ttl-seconds: 86400` keeps Maude soup state for 24 hours. Under sustained load, state accumulates, increasing GC pressure and memory footprint. With 2 GB per TM and large Maude terms, this can lead to OOM or GC stalls.

## Proposed fixes

### A. Remove `evaluatedSpans.print()` in production

Make the print sink conditional or remove it entirely:

```scala
val evaluatedSpans = spamEvaluator(spanInfos)
// Only print in local/dev mode
if (linolenumCfg.localFlinkEnv) {
  evaluatedSpans.print()
}
val linoleumSink = new LinoleumSink(linolenumCfg)
linoleumSink(evaluatedSpans)
```

**Impact**: Eliminates stdout serialization bottleneck. Easy to implement.

### B. Fix log level for load tests

Ensure `log4j2.properties` is actually applied to TMs. Verify that `linoleum` logger is at ERROR or WARN level during load tests. Consider reducing per-evaluation log lines or making them DEBUG-only.

**Impact**: Reduces I/O pressure from log writes. Easy to implement.

### C. Increase parallelism / TaskManagers

With 32 GB physical RAM and 2 GB per TM, the host can support up to ~14 TMs (accounting for OS overhead). Increasing from 5 to 10 TMs would double Maude processing capacity:

```yaml
# flink-conf.yaml
parallelism.default: 10

# workers file — 10 entries
localhost
...
```

**Impact**: More parallel Maude instances. Requires more memory and JVM overhead per TM.

### D. Increase slots per TaskManager

Instead of more JVMs, increase slots per TM to reduce JVM overhead while keeping parallelism:

```yaml
taskmanager.numberOfTaskSlots: 2
parallelism.default: 10
# 5 TMs × 2 slots = 10 parallel subtasks
```

**Caveat**: Multiple slots per TM share the same Maude interpreter lock (same JVM), so this only helps if the bottleneck is NOT the Maude lock but other processing (like I/O, deserialization, MongoDB writes).

### E. Reduce session gap

Increase `session-gap-seconds` to coalesce more spans into fewer windows, reducing evaluation frequency:

```yaml
config:
  session-gap-seconds: 30  # was 5
```

**Impact**: Fewer windows → fewer Maude evaluations → lower CPU load. Trade-off: higher latency before results appear.

### F. Reduce state TTL

Lower `ttl-seconds` to reduce memory pressure from accumulated state:

```yaml
state-config:
  ttl-seconds: 3600  # 1 hour instead of 24
```

**Impact**: Less memory pressure, but state may be evicted for long-running traces.

### G. Disable stdout sink via operator chaining

Chain the MongoDB sink directly without the intermediate print:

```scala
val evaluatedSpans = spamEvaluator(spanInfos)
// Remove: evaluatedSpans.print()
val linoleumSink = new LinoleumSink(linolenumCfg)
linoleumSink(evaluatedSpans)
```

The print sink adds an extra operator that serializes every record to text, copies it, and writes to stdout — all before the MongoDB sink. Removing it eliminates one full serialization round-trip per record.

## Quick wins (in priority order)

| Priority | Fix | Effort | Expected impact |
|----------|-----|--------|-----------------|
| 1 | Remove `.print()` | 1 line | High — eliminates stdout bottleneck |
| 2 | Fix log level to ERROR | Verify config | Medium — reduces I/O |
| 3 | Increase TMs 5→10 | Config change | High — doubles Maude parallelism |
| 4 | Increase session gap 5s→30s | Config change | Medium — fewer evaluations |
| 5 | Reduce state TTL 24h→4h | Config change | Low — less memory pressure |

---

# Experiment results (2026-06-12)

## Setup

- 10 TaskManagers, 1 slot each, 2 GB per TM
- `parallelism.default: 10`
- `ttl-seconds: 60` (reduced from 86400)
- `.print()` sink disabled in standalone mode
- Maude `message-rewrite-bound: 100`, `session-gap-seconds: 5`
- Gatling load generator with staircase ramp: 100 → 500 → 1000 → 5000 → 10000 msg/s

## Throughput scaling

| Spans/sec | Sink busy (%) | Source bp | Source bp time (ms) | Notes |
|-----------|---------------|-----------|---------------------|-------|
| 2,200 | 12.5 | OK | 0 | Comfortable |
| 3,500 | 16 | OK | 0 | Linear scaling |
| 4,500 | 37 | OK | 0 | Transient spike, recovered |
| 14,000 | 72 | OK | 0 | Still linear |
| 20,000 | 76–84 | OK | 0 | Near ceiling |
| ~22,000 | 79–87 | LOW (6/10) | 78K | Saturation begins |
| **~25,000** | **91–96** | **HIGH (8/10)** | **347K** | **Peak: 19,997.6 spans/sec. Full collapse imminent** |

## Key findings

1. **2.3x throughput improvement** over baseline (8.8K with 5 TMs + print sink → 20K with 10 TMs, no print, 60s TTL)
2. **Peak: 19,997.6 spans/sec** — essentially 20K
3. **Linear scaling up to ~20K** — Maude lock per TM scales with parallelism
4. **Saturation at ~25K** — sink subtasks reach 91-96% busy, source backpressure goes HIGH on 8/10 subtasks
5. **Uneven partition distribution** — hottest sink subtask at 96.5% while coolest at 57%, suggesting Kafka partition or chat_id key skew
6. **No SIGSEGV crashes** — the 60s TTL kept native memory pressure low enough to avoid the use-after-free / heap exhaustion scenario

## Comparison: before vs after

| Metric | Before (5 TMs) | After (10 TMs) |
|--------|----------------|-----------------|
| Print sink | Yes | No (standalone) |
| State TTL | 24h | 60s |
| Sustained throughput | ~8.8K spans/s | ~20K spans/s |
| Peak throughput | — | 19,997.6 spans/s |
| Ceiling | ~8.8K (collapsed) | ~25K (saturated) |

## Further tuning: log level

### Problem

The TMs were still logging at **INFO** level despite `log4j2.properties` setting `ERROR` for `io.github.demiourgoi.linoleum`. Investigation revealed the TMs use `log4j.properties` (log4j 1.x format via the `log4j-1.2-api` bridge), **not** `log4j2.properties`:

```
-Dlog4j.configurationFile=file:.../conf/log4j.properties
```

### Fix

Created `flink-cluster/log4j.properties` with the Flink defaults plus:

```properties
logger.linoleum.name = io.github.demiourgoi.linoleum
logger.linoleum.level = ERROR
```

Updated the Makefile to copy both files to the conf directory. Will take effect on next cluster restart.
