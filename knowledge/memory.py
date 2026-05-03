"""Per-NPC individual memory store."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

# Maximum entries per tier (T0 has no memory)
TIER_MAX_ENTRIES: dict[int, int] = {0: 0, 1: 5, 2: 25, 3: 200}


@dataclass
class MemoryEntry:
    npc_id: str
    content: str                           # human-readable fact/event
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    salience: float = 1.0                  # director hook — higher floats to top
    topic_tags: set[str] = field(default_factory=set)
    involved_npc_ids: set[str] = field(default_factory=set)
    involved_zone_id: str | None = None
    source: str = "observed"              # "observed"|"told"|"inferred"|"seeded"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "npc_id": self.npc_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "salience": self.salience,
            "topic_tags": sorted(self.topic_tags),
            "involved_npc_ids": sorted(self.involved_npc_ids),
            "involved_zone_id": self.involved_zone_id,
            "source": self.source,
        }


class IndividualMemory:
    """
    Episodic memory for a single NPC.

    Entries are stored newest-last. When capacity is exceeded the
    lowest-salience entry is evicted (not the oldest), so salient
    memories survive longer.
    """

    def __init__(self, npc_id: str, max_entries: int = 25):
        self.npc_id = npc_id
        self.max_entries = max_entries
        self._entries: list[MemoryEntry] = []

    def add(self, entry: MemoryEntry) -> None:
        if self.max_entries == 0:
            return
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            # Evict lowest-salience entry (stable sort keeps order among ties)
            self._entries.sort(key=lambda e: e.salience, reverse=True)
            self._entries.pop()  # remove the now-last (lowest-salience) entry
            # Re-sort chronologically
            self._entries.sort(key=lambda e: e.timestamp)

    def all_entries(self) -> list[MemoryEntry]:
        """All entries in chronological order (oldest first)."""
        return list(self._entries)

    def recent(self, n: int = 10) -> list[MemoryEntry]:
        """Most recent n entries, newest first."""
        return list(reversed(self._entries[-n:]))

    def __len__(self) -> int:
        return len(self._entries)
