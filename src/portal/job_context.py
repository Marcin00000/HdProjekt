"""Kontekst zadania w tle — logi i postęp dla portalu."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

_log_fn: Callable[[str], None] | None = None
_progress_fn: Callable[[int, str], None] | None = None
_local = threading.local()


@dataclass
class JobLogState:
    lines: list[str] = field(default_factory=list)
    progress: int = 0
    progress_message: str = ""

    def append(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > 500:
            self.lines = self.lines[-500:]

    def set_progress(self, pct: int, message: str = "") -> None:
        self.progress = max(0, min(100, int(pct)))
        if message:
            self.progress_message = message


def bind_callbacks(
    log_fn: Callable[[str], None],
    progress_fn: Callable[[int, str], None] | None = None,
) -> None:
    global _log_fn, _progress_fn
    _log_fn = log_fn
    _progress_fn = progress_fn


def clear_callbacks() -> None:
    global _log_fn, _progress_fn
    _log_fn = None
    _progress_fn = None


def log(message: str) -> None:
    text = message.rstrip()
    if not text:
        return
    if _log_fn:
        _log_fn(text)
    else:
        print(text, file=sys.stderr)


def progress(pct: int, message: str = "") -> None:
    if _progress_fn:
        _progress_fn(pct, message)
    if message:
        log(message)


@contextmanager
def capture_stdout_to_log():
    """Przekierowuje print() do log() w trakcie zadania."""
    class _Writer:
        def write(self, s: str) -> int:
            if s.strip():
                for line in s.splitlines():
                    log(line)
            return len(s)

        def flush(self) -> None:
            pass

    old = sys.stdout
    sys.stdout = _Writer()
    try:
        yield
    finally:
        sys.stdout = old
