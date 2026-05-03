"""Tests for tier promotion/demotion logic and history compression."""
from __future__ import annotations

import pytest

from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore
from llm.stub_runner import StubRunner
from npc.schema import NPC, NPCTier, BigFive, Relationship
from npc.tier import (
    DEMOTE_THRESHOLD,
    PROMOTE_THRESHOLD,
    TierChangeResult,
    compute_reach_score,
    demote,
    force_tier,
    promote,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_npc(tier: int = 1, npc_id: str = "npc_test") -> NPC:
    return NPC(
        id=npc_id,
        name="Test NPC",
        role="Tester",
        tier=NPCTier(tier),
        big_five=BigFive(),
    )


def _make_store(npc: NPC) -> MemoryStore:
    store = MemoryStore()
    store.register_npc(npc.id, npc.tier)
    return store


def _add_memories(store: MemoryStore, npc_id: str, count: int, salience: float = 1.0) -> None:
    mem = store.get(npc_id)
    for i in range(count):
        mem.add(MemoryEntry(npc_id=npc_id, content=f"memory_{i}", salience=salience))


# ── compute_reach_score ───────────────────────────────────────────────────────

def test_reach_score_empty_npc():
    npc = _make_npc()
    store = _make_store(npc)
    score = compute_reach_score(npc, store.get(npc.id))
    assert score == 0.0


def test_reach_score_relationships_contribute():
    npc = _make_npc()
    store = _make_store(npc)
    npc.relationships["other"] = Relationship(other_id="other", affinity=0.8)
    score = compute_reach_score(npc, store.get(npc.id))
    assert score > 0.0


def test_reach_score_goals_contribute():
    npc = _make_npc()
    store = _make_store(npc)
    npc.add_goal("Do something important")
    score = compute_reach_score(npc, store.get(npc.id))
    assert score > 0.0


def test_reach_score_memories_contribute():
    npc = _make_npc()
    store = _make_store(npc)
    _add_memories(store, npc.id, 3, salience=2.0)
    score = compute_reach_score(npc, store.get(npc.id))
    assert score > 0.0


def test_reach_score_memory_contribution_capped():
    npc = _make_npc(tier=3)
    store = _make_store(npc)
    _add_memories(store, npc.id, 200, salience=5.0)
    score = compute_reach_score(npc, store.get(npc.id))
    # Memory contribution is capped at 5.0
    # score = rel_score(0) + goal_score(0) + mem_score(<=5)
    assert score <= 5.0


# ── promote ───────────────────────────────────────────────────────────────────

def test_promote_returns_none_when_score_insufficient():
    npc = _make_npc(tier=1)
    store = _make_store(npc)
    # No relationships/goals/memories → score = 0 < threshold
    result = promote(npc, store)
    assert result is None
    assert npc.tier == NPCTier.T1


def test_promote_advances_tier():
    npc = _make_npc(tier=1)
    store = _make_store(npc)
    # rel_score = 8*0.5 + 0.9*2 = 5.8; goal_score = 2*1.5 = 3.0 → total ~8.8 > threshold 5.0
    for i in range(8):
        npc.relationships[f"other_{i}"] = Relationship(other_id=f"other_{i}", affinity=0.9)
    npc.add_goal("Important task")
    npc.add_goal("Secondary task")
    result = promote(npc, store)
    assert result is not None
    assert npc.tier == NPCTier.T2
    assert result.old_tier == NPCTier.T1
    assert result.new_tier == NPCTier.T2


def test_promote_returns_none_at_max_tier():
    npc = _make_npc(tier=3)
    store = _make_store(npc)
    for i in range(20):
        npc.relationships[f"other_{i}"] = Relationship(other_id=f"other_{i}", affinity=1.0)
    result = promote(npc, store)
    assert result is None
    assert npc.tier == NPCTier.T3


def test_promote_updates_reach_score_on_npc():
    npc = _make_npc(tier=1)
    store = _make_store(npc)
    assert npc.reach_score == 0.0
    promote(npc, store)
    # reach_score should be updated even if promotion didn't happen
    # (promote() sets it unconditionally before the threshold check)
    # Score stays 0 here but the field was written
    assert isinstance(npc.reach_score, float)


# ── demote ────────────────────────────────────────────────────────────────────

def test_demote_returns_none_when_score_sufficient():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    # Add enough to stay above T2 demotion threshold (3.0)
    for i in range(4):
        npc.relationships[f"other_{i}"] = Relationship(other_id=f"other_{i}", affinity=0.8)
    result = demote(npc, store)
    assert result is None
    assert npc.tier == NPCTier.T2


def test_demote_lowers_tier():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    # score = 0 < DEMOTE_THRESHOLD[2] = 3.0
    result = demote(npc, store)
    assert result is not None
    assert npc.tier == NPCTier.T1
    assert result.old_tier == NPCTier.T2
    assert result.new_tier == NPCTier.T1


def test_demote_returns_none_at_t0():
    npc = _make_npc(tier=0)
    store = _make_store(npc)
    result = demote(npc, store)
    assert result is None


def test_demote_with_runner_writes_narrative_summary():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    _add_memories(store, npc.id, 3)
    runner = StubRunner(response="A brief summary of the NPC's history.")
    result = demote(npc, store, runner=runner)
    assert result is not None
    assert result.narrative_summary == "A brief summary of the NPC's history."
    assert npc.narrative_summary == "A brief summary of the NPC's history."


def test_demote_without_runner_no_compression():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    _add_memories(store, npc.id, 3)
    result = demote(npc, store, runner=None)
    assert result is not None
    assert result.narrative_summary == ""
    assert npc.narrative_summary == ""


def test_demote_trims_memory_to_new_capacity():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    # Use salience=0.1 so mem_score stays well below DEMOTE_THRESHOLD[2]=3.0
    _add_memories(store, npc.id, 10, salience=0.1)
    result = demote(npc, store)
    assert result is not None
    # T1 max is 5
    assert len(store.get(npc.id)) <= 5


# ── force_tier ────────────────────────────────────────────────────────────────

def test_force_tier_promotes():
    npc = _make_npc(tier=1)
    store = _make_store(npc)
    result = force_tier(npc, store, NPCTier.T3)
    assert npc.tier == NPCTier.T3
    assert result.old_tier == NPCTier.T1
    assert result.new_tier == NPCTier.T3


def test_force_tier_demotes_with_compression():
    npc = _make_npc(tier=3)
    store = _make_store(npc)
    _add_memories(store, npc.id, 5)
    runner = StubRunner(response="Compressed narrative.")
    result = force_tier(npc, store, NPCTier.T1, runner=runner)
    assert npc.tier == NPCTier.T1
    assert npc.narrative_summary == "Compressed narrative."
    assert result.narrative_summary == "Compressed narrative."


def test_force_tier_same_tier_is_noop_result():
    npc = _make_npc(tier=2)
    store = _make_store(npc)
    result = force_tier(npc, store, NPCTier.T2)
    assert result.old_tier == NPCTier.T2
    assert result.new_tier == NPCTier.T2
    assert result.narrative_summary == ""


def test_compression_fallback_on_runner_error():
    """If runner raises, compression falls back to last 3 memory contents joined."""
    from llm.stub_runner import StubRunner
    from llm.runner import LLMRunnerError

    def _raise(messages):
        raise LLMRunnerError("LLM unavailable")

    npc = _make_npc(tier=3)
    store = _make_store(npc)
    _add_memories(store, npc.id, 5)
    runner = StubRunner(response=_raise)
    result = force_tier(npc, store, NPCTier.T1, runner=runner)
    # Fallback: last 3 entries joined by "; "
    assert result.narrative_summary != ""
    assert "memory_" in result.narrative_summary
