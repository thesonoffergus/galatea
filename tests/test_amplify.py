"""Tests for amplification primitives and goal injection into prompts."""
from __future__ import annotations

import pytest

from director.amplify import (
    boost_kb_entry,
    clear_nudged_goals,
    nudge_goal,
    set_memory_salience,
)
from knowledge.community_kb import CommunityKB, KBEntry
from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore
from npc.schema import BigFive, GoalPriority, GoalStatus, NPC, NPCTier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_npc(tier: int = 2) -> NPC:
    return NPC(id="npc_test", name="Test", role="Tester",
               tier=NPCTier(tier), big_five=BigFive())


def _make_store(npc: NPC) -> MemoryStore:
    store = MemoryStore()
    store.register_npc(npc.id, npc.tier)
    return store


def _add_memory(store: MemoryStore, npc_id: str, content: str, salience: float = 1.0) -> MemoryEntry:
    entry = MemoryEntry(npc_id=npc_id, content=content, salience=salience)
    store.get(npc_id).add(entry)
    return entry


def _add_kb_entry(kb: CommunityKB, content: str, gossip: float = 1.0) -> KBEntry:
    entry = KBEntry(content=content, gossip_weight=gossip)
    kb.add(entry)
    return entry


# ── set_memory_salience ───────────────────────────────────────────────────────

def test_set_memory_salience_updates_entry():
    npc = _make_npc()
    store = _make_store(npc)
    entry = _add_memory(store, npc.id, "A past event", salience=1.0)
    result = set_memory_salience(store, npc.id, entry.id, 3.5)
    assert result is True
    assert store.get(npc.id).all_entries()[0].salience == 3.5


def test_set_memory_salience_clamps_to_zero():
    npc = _make_npc()
    store = _make_store(npc)
    entry = _add_memory(store, npc.id, "Event")
    set_memory_salience(store, npc.id, entry.id, -1.0)
    assert store.get(npc.id).all_entries()[0].salience == 0.0


def test_set_memory_salience_returns_false_if_not_found():
    npc = _make_npc()
    store = _make_store(npc)
    result = set_memory_salience(store, npc.id, "nonexistent_id", 2.0)
    assert result is False


def test_set_memory_salience_affects_retrieval_order():
    from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
    npc = _make_npc(tier=3)
    store = _make_store(npc)
    low = _add_memory(store, npc.id, "Low priority memory", salience=0.5)
    high = _add_memory(store, npc.id, "High priority memory", salience=0.5)

    # Without amplification, order is arbitrary at same salience
    # Boost low's salience dramatically
    set_memory_salience(store, npc.id, low.id, 5.0)

    query = RetrievalQuery()
    result = retrieve_for_prompt(store, npc.id, query)
    # "Low priority memory" (now salience=5) should rank above "High priority memory" (0.5)
    assert result.individual[0].content == "Low priority memory"


# ── boost_kb_entry ────────────────────────────────────────────────────────────

def test_boost_kb_entry_updates_weight():
    kb = CommunityKB()
    entry = _add_kb_entry(kb, "Village news", gossip=1.0)
    result = boost_kb_entry(kb, entry.id, 3.0)
    assert result is True
    assert kb.all_entries()[0].gossip_weight == 3.0


def test_boost_kb_entry_clamps_to_zero():
    kb = CommunityKB()
    entry = _add_kb_entry(kb, "News")
    boost_kb_entry(kb, entry.id, -2.0)
    assert kb.all_entries()[0].gossip_weight == 0.0


def test_boost_kb_entry_returns_false_if_not_found():
    kb = CommunityKB()
    result = boost_kb_entry(kb, "no_such_id", 2.0)
    assert result is False


def test_boost_kb_entry_affects_retrieval_order():
    from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
    store = MemoryStore()
    store.register_npc("npc_a", 2)
    low = _add_kb_entry(store.community_kb, "Low gossip entry", gossip=0.1)
    high = _add_kb_entry(store.community_kb, "High gossip entry", gossip=0.1)

    boost_kb_entry(store.community_kb, low.id, 4.0)

    query = RetrievalQuery()
    result = retrieve_for_prompt(store, "npc_a", query)
    assert result.community[0].content == "Low gossip entry"


# ── nudge_goal ────────────────────────────────────────────────────────────────

def test_nudge_goal_adds_active_goal():
    npc = _make_npc()
    goal = nudge_goal(npc, "Find out who damaged the mill.")
    assert goal in npc.goals
    assert goal.status == GoalStatus.ACTIVE
    assert goal.priority == GoalPriority.HIGH


def test_nudge_goal_custom_priority():
    npc = _make_npc()
    goal = nudge_goal(npc, "Mention the caravan.", priority=GoalPriority.MEDIUM)
    assert goal.priority == GoalPriority.MEDIUM


def test_nudge_goal_appears_in_active_goals():
    npc = _make_npc()
    nudge_goal(npc, "Ask about the wolf sighting.")
    assert len(npc.active_goals()) == 1
    assert "wolf" in npc.active_goals()[0].description


def test_nudge_goal_appears_in_system_prompt():
    from dialogue.prompt_builder import DialogueContext, build_system_prompt
    from world.zone import Zone
    npc = _make_npc()
    player = NPC(id="player", name="Player", role="Adventurer",
                 is_player=True, big_five=BigFive())
    zone = Zone(id="z", name="Test Zone", terrain_type="settlement", tags=set())

    nudge_goal(npc, "Warn the player about danger in the forest.")
    ctx = DialogueContext(npc=npc, player=player, zone=zone,
                         zone_npcs=[], available_actions=[])
    prompt = build_system_prompt(ctx)
    assert "forest" in prompt.lower()
    assert "## IDENTITY" in prompt


# ── clear_nudged_goals ────────────────────────────────────────────────────────

def test_clear_nudged_goals_removes_active_high_priority():
    npc = _make_npc()
    nudge_goal(npc, "Goal A")
    nudge_goal(npc, "Goal B")
    removed = clear_nudged_goals(npc)
    assert removed == 2
    assert len(npc.active_goals()) == 0


def test_clear_nudged_goals_leaves_completed_untouched():
    npc = _make_npc()
    g = nudge_goal(npc, "Completed goal")
    g.status = GoalStatus.COMPLETED
    removed = clear_nudged_goals(npc)
    assert removed == 0
    assert g.status == GoalStatus.COMPLETED


def test_clear_nudged_goals_leaves_medium_priority_goals():
    npc = _make_npc()
    nudge_goal(npc, "High priority", priority=GoalPriority.HIGH)
    nudge_goal(npc, "Medium priority", priority=GoalPriority.MEDIUM)
    removed = clear_nudged_goals(npc)
    assert removed == 1
    remaining_active = npc.active_goals()
    assert len(remaining_active) == 1
    assert remaining_active[0].description == "Medium priority"


# ── Prompt builder goal injection ─────────────────────────────────────────────

def test_goals_not_in_prompt_when_none():
    from dialogue.prompt_builder import DialogueContext, build_system_prompt
    from world.zone import Zone
    npc = _make_npc()
    player = NPC(id="player", name="Player", role="Adventurer",
                 is_player=True, big_five=BigFive())
    zone = Zone(id="z", name="Test Zone", terrain_type="settlement", tags=set())
    ctx = DialogueContext(npc=npc, player=player, zone=zone,
                         zone_npcs=[], available_actions=[])
    prompt = build_system_prompt(ctx)
    assert "Current goals" not in prompt


def test_multiple_goals_all_in_prompt():
    from dialogue.prompt_builder import DialogueContext, build_system_prompt
    from world.zone import Zone
    npc = _make_npc()
    player = NPC(id="player", name="Player", role="Adventurer",
                 is_player=True, big_five=BigFive())
    zone = Zone(id="z", name="Test Zone", terrain_type="settlement", tags=set())
    nudge_goal(npc, "Sell the iron ingots.")
    nudge_goal(npc, "Warn about the wolves.")
    ctx = DialogueContext(npc=npc, player=player, zone=zone,
                         zone_npcs=[], available_actions=[])
    prompt = build_system_prompt(ctx)
    assert "iron ingots" in prompt
    assert "wolves" in prompt
