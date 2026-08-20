from threading import Lock
from typing import Any

import maude


class MaudeRuntime:
    def get_module(self, module_name: str) -> Any:
        init_maude()
        return maude.getModule(module_name)


_INIT_LOCK = Lock()
_maude_initialized = False


def init_maude() -> None:
    global _maude_initialized
    if _maude_initialized:
        return
    with _INIT_LOCK:
        if _maude_initialized:
            return
        maude.init()
        _maude_initialized = True
