"""Tests for GOAP-lite, action executor, and the tick system."""
from __future__ import annotations

import pytest

from affordances.registry import ActionRegistry
from affordances.schema import (
    Action,
    ActionCategory,
    AdvancesSkillEffect,
    AndPrecondition,
    ProducesEffect,
    ConsumesEffect,
)
from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore
from npc.registry import NPCRegistry
from npc.schema import BigFive, NPC, NPCTier
from sim.goap import _score_action, select_action
from sim.tick import TickResult, reset_tick_count, tick
from world.graph import WorldGraph
from world.zone import Zone


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_ticks():
    reset_tick_count()
    yield
    reset_tick_count()


def _make_zone(zone_id: str = "test_zone", tags: set[str] | None = None) -> Zone:
    return Zone(id=zone_id, name=zone_id, terrain_type="settlement",
                tags=tags or {"forge", "workshop"})


def _make_npc(tier: int = 2, zone_id: str = "test_zone") -> NPC:
    return NPC(
        id="npc_test",
        name="Test NPC",
        role="Smith",
        tier=NPCTier(tier),
        big_five=BigFive(),
        current_zone_id=zone_id,
        skills={"smithing": 0.7},
    )


_TRUE = AndPrecondition(conditions=[])


def _make_craft_action(action_id: str = "smith_blade") -> Action:
    return Action(
        id=action_id,
        name="Smith a Blade",
        category=ActionCategory.CRAFTING,
        preconditions=_TRUE,
        effects=[ProducesEffect(item_type="iron_blade", quantity=1)],
    )


def _make_gather_action(action_id: str = "gather_ore") -> Action:
    return Action(
        id=action_id,
        name="Gather Iron Ore",
        category=ActionCategory.GATHERING,
        preconditions=_TRUE,
        effects=[ProducesEffect(item_type="iron_ore", quantity=2)],
    )


def _simple_graph(zone_id: str = "test_zone") -> WorldGraph:
    graph = WorldGraph()
    graph.add_zone(_make_zone(zone_id))
    return graph


def _simple_registry(*actions: Action) -> ActionRegistry:
    registry = ActionRegistry()
    for a in actions:
        registry._register(a)
    return registry


# ── _score_action ─────────────────────────────────────────────────────────────

def test_score_action_no_goals_returns_zero():
    action = _make_craft_action()
    assert _score_action(action, []) == 0.0


def test_score_action_matching_goal_scores_positive():
    from npc.schema import Goal, GoalPriority
    action = _make_craft_action("smith_blade")
    goal = Goal(description="smith a blade for the market", priority=GoalPriority.HIGH)
    score = _score_action(action, [goal])
    assert score > 0.0


def test_score_action_category_tokens_boost_score():
    from npc.schema import Goal, GoalPriority
    action = _make_craft_action("smith_blade")
    goal = Goal(description="craft something useful", priority=GoalPriority.MEDIUM)
    score = _score_action(action, [goal])
    assert score > 0.0  # "craft" is in action_tokens for CRAFTING category


def test_score_action_unrelated_goal_scores_zero():
    from npc.schema import Goal, GoalPriority
    action = _make_craft_action()
    goal = Goal(description="visit the healer", priority=GoalPriority.HIGH)
    score = _score_action(action, [goal])
    assert score == 0.0


# ── select_action ─────────────────────────────────────────────────────────────

def test_select_action_returns_none_with_no_available_actions():
    npc = _make_npc()
    graph = _simple_graph()
    registry = _simple_registry()
    result = select_action(npc, "test_zone", graph, registry)
    assert result is None


def test_select_action_returns_action_when_available():
    npc = _make_npc()
    # No recipe precondition on our test action → available without known_recipes
    graph = _simple_graph()
    action = _make_craft_action()
    registry = _simple_registry(action)
    # No preconditions → always available
    result = select_action(npc, "test_zone", graph, registry)
    assert result is not None


def test_select_action_prefers_goal_matching_action():
    from npc.schema import GoalPriority
    npc = _make_npc()
    npc.add_goal("smith a blade", priority=GoalPriority.HIGH)
    graph = _simple_graph()
    blade_action = _make_craft_action("smith_blade")
    ore_action = _make_gather_action("gather_ore")
    registry = _simple_registry(blade_action, ore_action)
    result = select_action(npc, "test_zone", graph, registry)
    assert result is not None
    assert result.id == "smith_blade"


def test_select_action_uses_planned_actions_first():
    from npc.schema import GoalPriority
    npc = _make_npc()
    goal = npc.add_goal("Execute the plan", priority=GoalPriority.HIGH)
    goal.planned_actions = ["gather_ore"]
    graph = _simple_graph()
    blade_action = _make_craft_action("smith_blade")
    ore_action = _make_gather_action("gather_ore")
    registry = _simple_registry(blade_action, ore_action)
    result = select_action(npc, "test_zone", graph, registry)
    assert result is not None
    assert result.id == "gather_ore"


# ── execute_action ────────────────────────────────────────────────────────────

def test_execute_action_produces_item_in_zone():
    from sim.action_executor import execute_action
    npc = _make_npc()
    graph = _simple_graph()
    action = _make_craft_action()
    result = execute_action(npc, action, graph)
    assert result.success
    assert "iron_blade" in result.produced
    items = graph.items_in_zone("test_zone")
    assert any(i.item_type == "iron_blade" for i in items)


def test_execute_action_advances_skill():
    from sim.action_executor import execute_action
    action = Action(
        id="practice",
        name="Practice Smithing",
        category=ActionCategory.CRAFTING,
        preconditions=_TRUE,
        effects=[AdvancesSkillEffect(skill="smithing", amount=0.05)],
    )
    npc = _make_npc()
    npc.skills["smithing"] = 0.5
    graph = _simple_graph()
    execute_action(npc, action, graph)
    assert npc.skills["smithing"] == pytest.approx(0.55)


def test_execute_action_skill_capped_at_one():
    from sim.action_executor import execute_action
    action = Action(
        id="master",
        name="Master Smithing",
        category=ActionCategory.CRAFTING,
        preconditions=_TRUE,
        effects=[AdvancesSkillEffect(skill="smithing", amount=0.5)],
    )
    npc = _make_npc()
    npc.skills["smithing"] = 0.9
    graph = _simple_graph()
    execute_action(npc, action, graph)
    assert npc.skills["smithing"] == 1.0


# ── tick ──────────────────────────────────────────────────────────────────────

def _minimal_tick_state(tier: int = 2):
    """Build a minimal registry/graph/action_registry/memory_store for tick tests."""
    npc = _make_npc(tier=tier)
    graph = _simple_graph()
    graph.place_npc(npc.id, "test_zone")
    registry = NPCRegistry()
    registry.register(npc)
    action_registry = _simple_registry(_make_craft_action(), _make_gather_action())
    memory_store = MemoryStore()
    memory_store.register_npc(npc.id, npc.tier)
    return registry, graph, action_registry, memory_store, npc


def test_tick_increments_tick_number():
    from sim.tick import current_tick
    registry, graph, action_registry, memory_store, _ = _minimal_tick_state()
    assert current_tick() == 0
    tick(registry, graph, action_registry, memory_store)
    assert current_tick() == 1


def test_tick_returns_tick_result():
    registry, graph, action_registry, memory_store, _ = _minimal_tick_state()
    result = tick(registry, graph, action_registry, memory_store)
    assert isinstance(result, TickResult)
    assert result.tick_number == 1


def test_tick_t0_npc_is_skipped():
    registry, graph, action_registry, memory_store, npc = _minimal_tick_state(tier=0)
    result = tick(registry, graph, action_registry, memory_store)
    assert result.actions_taken == 0
    assert len(result.npc_results) == 0


def test_tick_t2_npc_may_act():
    """T2 NPC always attempts action (not probabilistic like T1)."""
    registry, graph, action_registry, memory_store, npc = _minimal_tick_state(tier=2)
    result = tick(registry, graph, action_registry, memory_store)
    # Actions were available and no preconditions block them → should have acted
    assert result.actions_taken == 1


def test_tick_multiple_ticks_increment_counter():
    registry, graph, action_registry, memory_store, _ = _minimal_tick_state()
    for _ in range(5):
        tick(registry, graph, action_registry, memory_store)
    from sim.tick import current_tick
    assert current_tick() == 5


def test_tick_gossip_propagates_salient_memory():
    import random
    registry, graph, action_registry, memory_store, npc = _minimal_tick_state()
    # Seed a salient memory
    mem = MemoryEntry(npc_id=npc.id, content="The mine is nearly exhausted.", salience=2.5,
                      topic_tags={"ore", "economy"})
    memory_store.get(npc.id).add(mem)

    # Force gossip to fire by patching random
    original = random.random
    calls = [0]
    def _controlled():
        calls[0] += 1
        # First call is for action phase, second is for gossip
        return 0.0  # always fires everything
    random.random = _controlled
    try:
        tick(registry, graph, action_registry, memory_store)
    finally:
        random.random = original

    # The salient memory should now be in the community KB
    kb_contents = {e.content for e in memory_store.community_kb.all_entries()}
    assert "The mine is nearly exhausted." in kb_contents


# ── WorldGraph.remove_item ────────────────────────────────────────────────────

def test_world_graph_remove_item():
    from world.zone import Item
    graph = _simple_graph()
    item = Item(id="itm_1", name="Ore", item_type="iron_ore", quality=1.0)
    graph.add_item(item)
    graph.place_item("itm_1", "test_zone")
    assert graph.get_item("itm_1") is not None
    assert "itm_1" in graph.get_zone("test_zone").item_ids
    graph.remove_item("itm_1")
    assert graph.get_item("itm_1") is None
    assert "itm_1" not in graph.get_zone("test_zone").item_ids


def test_world_graph_add_item_then_place_in_zone():
    from world.zone import Item
    graph = _simple_graph()
    item = Item(id="itm_2", name="Blade", item_type="iron_blade", quality=0.8)
    graph.add_item(item)
    graph.place_item("itm_2", "test_zone")
    assert "itm_2" in graph.get_zone("test_zone").item_ids
