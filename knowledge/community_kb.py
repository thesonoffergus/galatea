"""Zone-level shared knowledge base."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class KBEntry:
    content: str                            # human-readable shared fact
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    topic_tags: set[str] = field(default_factory=set)
    involved_npc_ids: set[str] = field(default_factory=set)
    involved_zone_id: str | None = None
    source_npc_id: str | None = None        # who introduced this fact
    gossip_weight: float = 1.0              # director hook — higher = spreads faster

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "topic_tags": sorted(self.topic_tags),
            "involved_npc_ids": sorted(self.involved_npc_ids),
            "involved_zone_id": self.involved_zone_id,
            "source_npc_id": self.source_npc_id,
            "gossip_weight": self.gossip_weight,
        }


class CommunityKB:
    """
    Shared knowledge base for a zone or the entire world.

    Entries are stored in insertion order (oldest first).
    There is no hard cap — the director is expected to prune via
    explicit removal if needed.
    """

    def __init__(self) -> None:
        self._entries: list[KBEntry] = []

    def add(self, entry: KBEntry) -> None:
        self._entries.append(entry)

    def all_entries(self) -> list[KBEntry]:
        """All entries, oldest first."""
        return list(self._entries)

    def by_tag(self, tag: str) -> list[KBEntry]:
        """Entries whose topic_tags contain *tag*."""
        return [e for e in self._entries if tag in e.topic_tags]

    def by_zone(self, zone_id: str) -> list[KBEntry]:
        """Entries associated with a specific zone."""
        return [e for e in self._entries if e.involved_zone_id == zone_id]

    def remove(self, entry_id: str) -> bool:
        """Remove entry by id. Returns True if found and removed."""
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                self._entries.pop(i)
                return True
        return False

    def __len__(self) -> int:
        return len(self._entries)
