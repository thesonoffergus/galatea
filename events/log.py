"""Event log: append-only ring buffer with director-ready metadata on every entry."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class EventType(StrEnum):
    # World / social
    DIALOGUE        = "dialogue"
    RELATIONSHIP    = "relationship"
    MOVE            = "move"
    TIER_CHANGE     = "tier_change"
    GOAL_SET        = "goal_set"
    GOAL_COMPLETED  = "goal_completed"
    GOAL_ABANDONED  = "goal_abandoned"
    # Crafting / economy
    CRAFT_SUCCESS   = "craft_success"
    CRAFT_FAILURE   = "craft_failure"
    RECIPE_LEARNED  = "recipe_learned"
    RECIPE_LOST     = "recipe_lost"
    GATHER          = "gather"
    TRADE           = "trade"
    # World events
    GENERIC         = "generic"


class EventSeverity(StrEnum):
    TRIVIAL   = "trivial"   # background noise
    MINOR     = "minor"     # mildly notable
    MODERATE  = "moderate"  # worth tracking
    MAJOR     = "major"     # story-significant
    CRITICAL  = "critical"  # world-changing


@dataclass
class NPCRole:
    """An NPC's role within a specific event (e.g. actor, target, witness)."""
    npc_id: str
    role: str  # "actor" | "target" | "witness" | "recipient" | custom


@dataclass
class EventEntry:
    """
    A single timestamped event in the simulation.

    All fields needed by a future director scorer are present from day one.
    """
    event_type: EventType
    description: str                            # human-readable summary

    id: str = field(default_factory=lambda: uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Who was involved and in what capacity
    npc_roles: list[NPCRole] = field(default_factory=list)

    # Where it happened
    zone_id: str | None = None

    # Severity for director scoring
    severity: EventSeverity = EventSeverity.MINOR

    # Searchable tags (e.g. "craft", "iron", "recipe_discovery", "conflict")
    tags: set[str] = field(default_factory=set)

    # Arbitrary structured payload (recipe id, item quality, delta values, etc.)
    payload: dict = field(default_factory=dict)

    # Director hook — set > 1.0 to amplify propagation through gossip/memory
    amplification: float = 1.0

    def actor_ids(self) -> list[str]:
        return [r.npc_id for r in self.npc_roles if r.role == "actor"]

    def involved_npc_ids(self) -> list[str]:
        return [r.npc_id for r in self.npc_roles]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "npc_roles": [{"npc_id": r.npc_id, "role": r.role} for r in self.npc_roles],
            "zone_id": self.zone_id,
            "severity": self.severity,
            "tags": sorted(self.tags),
            "payload": self.payload,
            "amplification": self.amplification,
        }


class EventLog:
    """
    Append-only ring buffer of simulation events.

    Oldest entries are dropped once `max_entries` is exceeded.
    All filtering is done by slicing/comprehension — no secondary index
    at this scale.
    """

    def __init__(self, max_entries: int = 2000) -> None:
        self.max_entries = max_entries
        self._entries: deque[EventEntry] = deque(maxlen=max_entries)

    def record(self, entry: EventEntry) -> EventEntry:
        self._entries.append(entry)
        return entry

    # ── Convenience factory ───────────────────────────────────────────────────

    def emit(
        self,
        event_type: EventType,
        description: str,
        *,
        npc_roles: list[NPCRole] | None = None,
        zone_id: str | None = None,
        severity: EventSeverity = EventSeverity.MINOR,
        tags: set[str] | None = None,
        payload: dict | None = None,
        amplification: float = 1.0,
    ) -> EventEntry:
        entry = EventEntry(
            event_type=event_type,
            description=description,
            npc_roles=npc_roles or [],
            zone_id=zone_id,
            severity=severity,
            tags=tags or set(),
            payload=payload or {},
            amplification=amplification,
        )
        return self.record(entry)

    # ── Queries ───────────────────────────────────────────────────────────────

    def all(self) -> list[EventEntry]:
        """All entries, oldest first."""
        return list(self._entries)

    def recent(self, n: int = 50) -> list[EventEntry]:
        """Most recent n entries, newest first."""
        entries = list(self._entries)
        return list(reversed(entries[-n:]))

    def by_type(self, event_type: EventType) -> list[EventEntry]:
        return [e for e in self._entries if e.event_type == event_type]

    def by_npc(self, npc_id: str) -> list[EventEntry]:
        return [e for e in self._entries if npc_id in e.involved_npc_ids()]

    def by_zone(self, zone_id: str) -> list[EventEntry]:
        return [e for e in self._entries if e.zone_id == zone_id]

    def by_tag(self, tag: str) -> list[EventEntry]:
        return [e for e in self._entries if tag in e.tags]

    def by_severity(self, min_severity: EventSeverity) -> list[EventEntry]:
        _order = list(EventSeverity)
        min_idx = _order.index(min_severity)
        return [e for e in self._entries if _order.index(e.severity) >= min_idx]

    def since(self, ts: datetime) -> list[EventEntry]:
        return [e for e in self._entries if e.timestamp >= ts]

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton — same pattern as prompt_log
event_log = EventLog()
