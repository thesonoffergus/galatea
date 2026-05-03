"""In-memory prompt log with optional JSON-lines persistence."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from llm.types import PromptLogEntry


class PromptLog:
    def __init__(self, max_entries: int = 500, log_file: Path | None = None):
        self._entries: deque[PromptLogEntry] = deque(maxlen=max_entries)
        self._log_file = log_file

    def record(self, entry: PromptLogEntry) -> None:
        """Prepend entry (most recent first) and optionally append to file."""
        self._entries.appendleft(entry)
        if self._log_file:
            try:
                with self._log_file.open("a") as fh:
                    fh.write(json.dumps(entry.to_dict()) + "\n")
            except OSError:
                pass  # never crash the simulation over logging

    def recent(self, n: int = 100, tag: str | None = None) -> list[PromptLogEntry]:
        """Return up to `n` entries, newest first. Filter by tag prefix if given."""
        entries: list[PromptLogEntry] = list(self._entries)
        if tag:
            entries = [e for e in entries if any(t == tag or t.startswith(tag + ":") for t in e.tags)]
        return entries[:n]

    def get(self, entry_id: str) -> PromptLogEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton imported by runners and tooling
prompt_log = PromptLog()
