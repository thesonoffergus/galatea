"""RAG-lite retrieval: score and rank memories/KB entries for a prompt context."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from knowledge.community_kb import KBEntry
from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore


@dataclass
class RetrievalQuery:
    """What the prompt builder tells retrieval to look for."""
    topic_tags: set[str] = field(default_factory=set)
    involved_npc_ids: set[str] = field(default_factory=set)
    involved_zone_id: str | None = None


@dataclass
class MemoryExcerpts:
    """Ranked results handed back to the prompt builder."""
    individual: list[MemoryEntry]
    community: list[KBEntry]


def _recency_bonus(ts: datetime, now: datetime) -> float:
    """Decay factor: 1.0 at t=0, ~0 after 30 simulated days (seconds used as proxy)."""
    age_seconds = max(0.0, (now - ts).total_seconds())
    decay_days = age_seconds / 86_400
    return max(0.0, 1.0 - decay_days / 30.0)


def _score_memory(entry: MemoryEntry, query: RetrievalQuery, now: datetime) -> float:
    tag_overlap = len(entry.topic_tags & query.topic_tags)
    npc_overlap = len(entry.involved_npc_ids & query.involved_npc_ids)
    zone_bonus = 0.5 if (query.involved_zone_id and entry.involved_zone_id == query.involved_zone_id) else 0.0
    recency = _recency_bonus(entry.timestamp, now)
    return tag_overlap + npc_overlap * 2 + entry.salience * 1.5 + recency + zone_bonus


def _score_kb(entry: KBEntry, query: RetrievalQuery, now: datetime) -> float:
    tag_overlap = len(entry.topic_tags & query.topic_tags)
    npc_overlap = len(entry.involved_npc_ids & query.involved_npc_ids)
    zone_bonus = 0.5 if (query.involved_zone_id and entry.involved_zone_id == query.involved_zone_id) else 0.0
    recency = _recency_bonus(entry.timestamp, now)
    return tag_overlap + npc_overlap * 2 + entry.gossip_weight * 0.5 + recency + zone_bonus


def retrieve_for_prompt(
    store: MemoryStore,
    npc_id: str,
    query: RetrievalQuery,
    max_individual: int = 8,
    max_community: int = 6,
) -> MemoryExcerpts:
    now = datetime.now(timezone.utc)

    individual_mem = store.get(npc_id)
    scored_ind = sorted(
        individual_mem.all_entries(),
        key=lambda e: _score_memory(e, query, now),
        reverse=True,
    )

    scored_kb = sorted(
        store.community_kb.all_entries(),
        key=lambda e: _score_kb(e, query, now),
        reverse=True,
    )

    return MemoryExcerpts(
        individual=scored_ind[:max_individual],
        community=scored_kb[:max_community],
    )
