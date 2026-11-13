"""Probe: one-shot Pipe IPC for a dedicated process per call.

Validates the mechanics Harold needs:

- large response payloads (the Maude result caps allow ~1 MB strings);
- JSON encoding without ASCII escaping;
- EOF detection when the child dies abruptly (SIGSEGV analogue);
- deadline enforcement via ``poll`` + ``kill`` for a stuck child;
- concurrent calls from several server threads.

Run from ``harold-mcp``::

    UV_CACHE_DIR=/tmp/uv-cache uv run python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_ipc.py
"""

import json
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def worker(conn) -> None:  # noqa: ANN001 - probe script
    try:
        raw = conn.recv_bytes()
    except EOFError:
        return
    req = json.loads(raw)
    method = req.get("method")
    if method == "echo":
        resp = {"status": "ok", "payload": req["payload"]}
    elif method == "crash":
        os._exit(7)
    elif method == "hang":
        time.sleep(60)
        resp = {"status": "ok"}
    else:
        resp = {"status": "error", "message": f"unknown method {method!r}"}
    try:
        conn.send_bytes(json.dumps(resp, ensure_ascii=False).encode())
    except (BrokenPipeError, OSError):
        pass
    finally:
        conn.close()


def call(payload: dict, timeout: float) -> tuple[str, object, float]:
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe()
    proc = ctx.Process(target=worker, args=(child,), daemon=True)
    started = time.monotonic()
    proc.start()
    child.close()
    try:
        parent.send_bytes(json.dumps(payload, ensure_ascii=False).encode())
        deadline = started + timeout
        if not parent.poll(max(0.0, deadline - time.monotonic())):
            return "timeout", None, time.monotonic() - started
        try:
            raw = parent.recv_bytes()
        except EOFError:
            return "eof", None, time.monotonic() - started
        return "ok", json.loads(raw), time.monotonic() - started
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(5)


def main() -> None:
    print("python:", sys.version.split()[0])
    payload = "x" * (1_000_000) + " · Maude output with non-ASCII"
    kind, response, elapsed = call({"method": "echo", "payload": payload}, timeout=30)
    echoed = response.get("payload") if isinstance(response, dict) else None
    print(f"large echo: kind={kind} elapsed={elapsed:.2f}s identical={echoed == payload}")

    kind, response, elapsed = call({"method": "crash"}, timeout=30)
    print(f"child crash: kind={kind} elapsed={elapsed:.2f}s")

    kind, response, elapsed = call({"method": "hang"}, timeout=0.5)
    print(f"stuck child: kind={kind} elapsed={elapsed:.2f}s")

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _i: call({"method": "echo", "payload": "y" * 100_000}, timeout=30), range(4)))
    print(
        "concurrent: "
        + ", ".join(f"{kind}/{elapsed:.2f}s" for kind, _response, elapsed in results)
        + f" total={time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
