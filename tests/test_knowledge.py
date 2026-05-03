"""Tests for knowledge/memory, community KB, store, and retrieval."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from knowledge.community_kb import CommunityKB, KBEntry
from knowledge.memory import TIER_MAX_ENTRIES, IndividualMemory, MemoryEntry
from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
from knowledge.store import MemoryStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry(npc_id: str, content: str, salience: float = 1.0, tags: set[str] | None = None) -> MemoryEntry:
    return MemoryEntry(
        npc_id=npc_id,
        content=content,
        salience=salience,
        topic_tags=tags or set(),
    )


def _kb_entry(content: str, gossip: float = 1.0, tags: set[str] | None = None) -> KBEntry:
    return KBEntry(content=content, gossip_weight=gossip, topic_tags=tags or set())


# ── TIER_MAX_ENTRIES ──────────────────────────────────────────────────────────

def test_tier_max_entries_values():
    assert TIER_MAX_ENTRIES[0] == 0
    assert TIER_MAX_ENTRIES[1] == 5
    assert TIER_MAX_ENTRIES[2] == 25
    assert TIER_MAX_ENTRIES[3] == 200


# ── IndividualMemory ──────────────────────────────────────────────────────────

def test_individual_memory_add_and_len():
    mem = IndividualMemory("npc_a", max_entries=5)
    mem.add(_entry("npc_a", "First"))
    mem.add(_entry("npc_a", "Second"))
    assert len(mem) == 2


def test_individual_memory_zero_capacity():
    mem = IndividualMemory("npc_a", max_entries=0)
    mem.add(_entry("npc_a", "Should be dropped"))
    assert len(mem) == 0


def test_individual_memory_evicts_lowest_salience():
    mem = IndividualMemory("npc_a", max_entries=3)
    mem.add(_entry("npc_a", "High", salience=2.0))
    mem.add(_entry("npc_a", "Med", salience=1.0))
    mem.add(_entry("npc_a", "Low", salience=0.1))
    # At capacity; add a new entry — should evict "Low"
    mem.add(_entry("npc_a", "New", salience=1.5))
    contents = [e.content for e in mem.all_entries()]
    assert "Low" not in contents
    assert "New" in contents
    assert len(mem) == 3


def test_individual_memory_all_entries_chronological():
    mem = IndividualMemory("npc_a", max_entries=10)
    for i in range(5):
        mem.add(_entry("npc_a", str(i)))
    entries = mem.all_entries()
    # Timestamps should be non-decreasing
    for i in range(len(entries) - 1):
        assert entries[i].timestamp <= entries[i + 1].timestamp


def test_individual_memory_recent_newest_first():
    mem = IndividualMemory("npc_a", max_entries=10)
    for i in range(5):
        mem.add(_entry("npc_a", f"entry_{i}"))
    recent = mem.recent(3)
    assert len(recent) == 3
    assert recent[0].content == "entry_4"
    assert recent[2].content == "entry_2"


def test_individual_memory_recent_fewer_than_n():
    mem = IndividualMemory("npc_a", max_entries=10)
    mem.add(_entry("npc_a", "only one"))
    assert len(mem.recent(5)) == 1


# ── CommunityKB ───────────────────────────────────────────────────────────────

def test_community_kb_add_and_len():
    kb = CommunityKB()
    kb.add(_kb_entry("A wolf was seen."))
    kb.add(_kb_entry("Prices are rising."))
    assert len(kb) == 2


def test_community_kb_by_tag():
    kb = CommunityKB()
    kb.add(_kb_entry("Wolf sighting", tags={"danger", "forest"}))
    kb.add(_kb_entry("Price hike", tags={"trade", "economy"}))
    kb.add(_kb_entry("Flood damage", tags={"danger", "infrastructure"}))
    danger = kb.by_tag("danger")
    assert len(danger) == 2
    assert all("danger" in e.topic_tags for e in danger)


def test_community_kb_by_zone():
    kb = CommunityKB()
    e1 = KBEntry(content="Forest news", involved_zone_id="thornwood_forest")
    e2 = KBEntry(content="Mill news", involved_zone_id="thornhaven_mill")
    kb.add(e1)
    kb.add(e2)
    forest = kb.by_zone("thornwood_forest")
    assert len(forest) == 1
    assert forest[0].content == "Forest news"


def test_community_kb_remove():
    kb = CommunityKB()
    e = _kb_entry("Removable fact")
    kb.add(e)
    assert kb.remove(e.id) is True
    assert len(kb) == 0
    assert kb.remove("nonexistent") is False


def test_community_kb_all_entries_order():
    kb = CommunityKB()
    kb.add(_kb_entry("First"))
    kb.add(_kb_entry("Second"))
    entries = kb.all_entries()
    assert entries[0].content == "First"
    assert entries[1].content == "Second"


# ── MemoryStore ───────────────────────────────────────────────────────────────

def test_memory_store_register_sets_capacity():
    store = MemoryStore()
    mem = store.register_npc("npc_a", tier=1)
    assert mem.max_entries == TIER_MAX_ENTRIES[1]


def test_memory_store_get_lazy_creates_zero_capacity():
    store = MemoryStore()
    mem = store.get("npc_unknown")
    assert mem.max_entries == 0


def test_memory_store_contains():
    store = MemoryStore()
    store.register_npc("npc_a", tier=2)
    assert "npc_a" in store
    assert "npc_b" not in store


def test_memory_store_community_kb_accessible():
    store = MemoryStore()
    store.community_kb.add(_kb_entry("Global fact"))
    assert len(store.community_kb) == 1


# ── Retrieval ─────────────────────────────────────────────────────────────────

def test_retrieval_empty_store():
    store = MemoryStore()
    store.register_npc("npc_a", tier=2)
    query = RetrievalQuery(topic_tags={"trade"})
    result = retrieve_for_prompt(store, "npc_a", query)
    assert result.individual == []
    assert result.community == []


def test_retrieval_ranks_by_tag_overlap():
    store = MemoryStore()
    mem = store.register_npc("npc_a", tier=3)
    mem.add(_entry("npc_a", "High match", tags={"trade", "economy"}))
    mem.add(_entry("npc_a", "Low match", tags={"weather"}))

    query = RetrievalQuery(topic_tags={"trade", "economy"})
    result = retrieve_for_prompt(store, "npc_a", query)
    assert result.individual[0].content == "High match"


def test_retrieval_npc_overlap_boosts_score():
    store = MemoryStore()
    mem = store.register_npc("npc_a", tier=3)
    mem.add(_entry("npc_a", "Involves player", tags=set()))
    # Manually set involved_npc_ids
    mem.all_entries()[0].involved_npc_ids = {"player"}
    mem.add(_entry("npc_a", "No involvement", tags=set()))

    query = RetrievalQuery(involved_npc_ids={"player"})
    result = retrieve_for_prompt(store, "npc_a", query)
    assert result.individual[0].content == "Involves player"


def test_retrieval_max_individual_and_community_respected():
    store = MemoryStore()
    mem = store.register_npc("npc_a", tier=3)
    for i in range(20):
        mem.add(_entry("npc_a", f"mem_{i}", tags={"x"}))
    for i in range(10):
        store.community_kb.add(_kb_entry(f"kb_{i}", tags={"x"}))

    query = RetrievalQuery(topic_tags={"x"})
    result = retrieve_for_prompt(store, "npc_a", query, max_individual=5, max_community=3)
    assert len(result.individual) == 5
    assert len(result.community) == 3


def test_retrieval_community_gossip_weight_influences_rank():
    store = MemoryStore()
    store.register_npc("npc_a", tier=2)
    store.community_kb.add(_kb_entry("Heavy gossip", gossip=3.0, tags={"trade"}))
    store.community_kb.add(_kb_entry("Light gossip", gossip=0.1, tags={"trade"}))

    query = RetrievalQuery(topic_tags={"trade"})
    result = retrieve_for_prompt(store, "npc_a", query)
    assert result.community[0].content == "Heavy gossip"
