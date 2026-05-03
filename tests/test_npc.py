"""Tests for NPC schema, registry, loader, and affordance integration."""
from pathlib import Path

import pytest

from affordances.query import ActorContext, EvalContext, what_can_actor_do
from affordances.registry import ActionRegistry
from affordances.schema import NpcPresentPrecondition
from crafting.recipes import RecipeSource, RecipeStore
from npc.schema import (
    BigFive, Goal, GoalPriority, GoalStatus,
    NPC, NPCTier, PhysicalTraits, Relationship,
)
from npc.registry import NPCRegistry
from npc.loader import load_npcs
from world.graph import WorldGraph
from world.loader import load_world
from world.zone import Zone

SEED_PATH = Path(__file__).parent.parent / "data" / "village_seed.yaml"
ACTIONS_PATH = Path(__file__).parent.parent / "data" / "actions.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def seed_graph() -> WorldGraph:
    return load_world(SEED_PATH)


@pytest.fixture
def npc_registry(seed_graph) -> NPCRegistry:
    registry, _ = load_npcs(SEED_PATH, graph=seed_graph)
    return registry


@pytest.fixture
def action_registry() -> ActionRegistry:
    return ActionRegistry.from_yaml(ACTIONS_PATH)


@pytest.fixture
def aldric(npc_registry) -> NPC:
    return npc_registry.get("npc_aldric_stonehand")


@pytest.fixture
def maren(npc_registry) -> NPC:
    return npc_registry.get("npc_maren_coldwater")


# ── BigFive ───────────────────────────────────────────────────────────────────

def test_big_five_defaults():
    b = BigFive()
    assert b.openness == 0.5
    assert b.extraversion == 0.5


def test_big_five_validation_rejects_out_of_range():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        BigFive(openness=1.5)
    with pytest.raises(ValidationError):
        BigFive(conscientiousness=-0.1)


def test_big_five_as_dict():
    b = BigFive(openness=0.7, conscientiousness=0.8, extraversion=0.3,
                agreeableness=0.6, neuroticism=0.2)
    d = b.as_dict()
    assert d["openness"] == 0.7
    assert set(d.keys()) == {
        "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"
    }


# ── NPC construction ──────────────────────────────────────────────────────────

def test_npc_minimal_construction():
    npc = NPC(id="test_npc", name="Test", role="Farmer")
    assert npc.tier == NPCTier.T1
    assert npc.is_player is False
    assert npc.mood == 0.0
    assert len(npc.skills) == 0
    assert len(npc.goals) == 0


def test_npc_tier_values():
    assert NPCTier.T0 == 0
    assert NPCTier.T3 == 3
    assert NPCTier.T2 > NPCTier.T1


def test_npc_skill_level():
    npc = NPC(id="n1", name="N", role="Smith", skills={"smithing": 0.75})
    assert npc.skill_level("smithing") == 0.75
    assert npc.skill_level("farming") == 0.0  # default


def test_npc_has_recipe():
    store = RecipeStore.from_id_list(["smith_sword", "smith_axe"])
    npc = NPC(id="n1", name="N", role="Smith", known_recipes=store)
    assert npc.has_recipe("smith_sword") is True
    assert npc.has_recipe("brew_potion") is False


# ── Goals ─────────────────────────────────────────────────────────────────────

def test_add_goal():
    npc = NPC(id="n1", name="N", role="Farmer")
    goal = npc.add_goal("Harvest the wheat field", GoalPriority.HIGH)
    assert len(npc.goals) == 1
    assert goal.priority == GoalPriority.HIGH
    assert goal.status == GoalStatus.ACTIVE


def test_active_goals_filter():
    npc = NPC(id="n1", name="N", role="Farmer")
    g1 = npc.add_goal("Active goal")
    g2 = npc.add_goal("Another goal")
    g2.status = GoalStatus.COMPLETED
    active = npc.active_goals()
    assert len(active) == 1
    assert active[0] is g1


# ── Relationships ─────────────────────────────────────────────────────────────

def test_relationship_defaults():
    rel = Relationship(other_id="npc_02")
    assert rel.affinity == 0.0
    assert rel.trust == 0.3
    assert rel.familiarity == 0.0


def test_set_and_get_relationship():
    npc = NPC(id="n1", name="N", role="Farmer")
    rel = Relationship(other_id="n2", affinity=0.5, trust=0.7)
    npc.set_relationship(rel)
    retrieved = npc.get_relationship("n2")
    assert retrieved is not None
    assert retrieved.affinity == 0.5


def test_adjust_relationship_creates_if_missing():
    npc = NPC(id="n1", name="N", role="Farmer")
    rel = npc.adjust_relationship("n2", affinity_delta=0.2, trust_delta=0.1)
    assert rel.affinity == 0.2
    assert abs(rel.trust - 0.4) < 1e-6  # 0.3 default + 0.1


def test_adjust_relationship_clamps():
    npc = NPC(id="n1", name="N", role="Farmer")
    npc.set_relationship(Relationship(other_id="n2", affinity=0.9))
    npc.adjust_relationship("n2", affinity_delta=0.5)  # would exceed 1.0
    assert npc.get_relationship("n2").affinity == 1.0


def test_relationship_asymmetry():
    """A loves B who doesn't know A exists."""
    npc_a = NPC(id="a", name="A", role="Farmer")
    npc_b = NPC(id="b", name="B", role="Smith")
    npc_a.set_relationship(Relationship(other_id="b", affinity=0.9))
    assert npc_b.get_relationship("a") is None  # B has no relationship with A


# ── Effective tags ────────────────────────────────────────────────────────────

def test_npc_effective_tags_includes_role():
    npc = NPC(id="n1", name="N", role="Blacksmith")
    tags = npc.effective_tags()
    assert "blacksmith" in tags
    assert "npc" in tags


def test_npc_effective_tags_player_flag():
    npc = NPC(id="n1", name="N", role="Wanderer", is_player=True)
    tags = npc.effective_tags()
    assert "player" in tags
    assert "wanderer" in tags


def test_npc_effective_tags_role_normalisation():
    """Role with spaces and caps becomes snake_case tag."""
    npc = NPC(id="n1", name="N", role="Shrine Keeper")
    tags = npc.effective_tags()
    assert "shrine_keeper" in tags


# ── as_actor_context ──────────────────────────────────────────────────────────

def test_as_actor_context_without_graph(aldric):
    ctx = aldric.as_actor_context()
    assert ctx.actor_id == "npc_aldric_stonehand"
    assert ctx.skills["smithing"] == 0.90
    assert "smith_sword" in ctx.known_recipes
    assert ctx.inventory == {}  # no graph, no items resolved


def test_as_actor_context_with_carried_items(seed_graph):
    npc = NPC(
        id="test_carrier",
        name="Test",
        role="Smith",
        skills={"smithing": 0.5},
        carried_item_ids=["item_forge_iron_ingot_01"],
    )
    ctx = npc.as_actor_context(graph=seed_graph)
    assert ctx.inventory.get("iron_ingot", 0) >= 1


def test_as_actor_context_role_tags(aldric):
    ctx = aldric.as_actor_context()
    assert "blacksmith" in ctx.role_tags
    assert "npc" in ctx.role_tags


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_register_and_get():
    reg = NPCRegistry()
    npc = NPC(id="n1", name="N", role="Farmer")
    reg.register(npc)
    assert reg.get("n1") is npc


def test_registry_duplicate_raises():
    reg = NPCRegistry()
    npc = NPC(id="n1", name="N", role="Farmer")
    reg.register(npc)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(NPC(id="n1", name="Other", role="Smith"))


def test_registry_get_unknown_raises():
    reg = NPCRegistry()
    with pytest.raises(KeyError):
        reg.get("nobody")


def test_registry_by_tier(npc_registry):
    t3s = npc_registry.by_tier(NPCTier.T3)
    t3_ids = {n.id for n in t3s}
    assert "npc_aldric_stonehand" in t3_ids
    assert "npc_wren_thatch" in t3_ids


def test_registry_by_tier_min(npc_registry):
    t2_plus = npc_registry.by_tier_min(NPCTier.T2)
    for npc in t2_plus:
        assert npc.tier >= NPCTier.T2


def test_registry_player(npc_registry):
    player = npc_registry.player()
    assert player is not None
    assert player.is_player is True
    assert player.id == "player"


def test_registry_npcs_in_zone(npc_registry, seed_graph):
    npcs_in_forge = npc_registry.npcs_in_zone("forge_room", seed_graph)
    ids = {n.id for n in npcs_in_forge}
    assert "npc_aldric_stonehand" in ids


def test_registry_build_npc_tag_map(npc_registry):
    tag_map = npc_registry.build_npc_tag_map()
    assert "npc_aldric_stonehand" in tag_map
    assert "blacksmith" in tag_map["npc_aldric_stonehand"]
    assert "player" in tag_map["player"]


# ── Seed loading ──────────────────────────────────────────────────────────────

def test_seed_loads_all_npcs(npc_registry):
    # 10 villagers + 1 player = 11 total
    assert len(npc_registry) == 11


def test_seed_aldric_skills(aldric):
    assert aldric.skill_level("smithing") == 0.90
    assert aldric.skill_level("mining") == 0.40


def test_seed_aldric_recipes(aldric):
    assert aldric.has_recipe("smith_sword")
    assert aldric.has_recipe("smelt_iron")
    assert not aldric.has_recipe("brew_potion")


def test_seed_aldric_big_five(aldric):
    assert aldric.big_five.conscientiousness == 0.85
    assert aldric.big_five.openness == 0.35


def test_seed_aldric_physical(aldric):
    assert "broad" in aldric.physical.build
    assert "burn scars" in aldric.physical.notable


def test_seed_aldric_placed_in_forge(aldric):
    assert aldric.current_zone_id == "forge_room"


def test_seed_wren_is_t3(npc_registry):
    wren = npc_registry.get("npc_wren_thatch")
    assert wren.tier == NPCTier.T3


def test_seed_petra_is_t0(npc_registry):
    petra = npc_registry.get("npc_petra_fieldsmay")
    assert petra.tier == NPCTier.T0


def test_seed_player_is_blank(npc_registry):
    player = npc_registry.player()
    assert len(player.skills) == 0
    assert player.known_recipes.count() == 0
    assert len(player.trait_tags) == 0


def test_seed_maren_values(maren):
    assert "knowledge" in maren.values
    assert "health" in maren.values


def test_seed_npcs_placed_in_world(seed_graph, npc_registry):
    """All NPCs with a starting_zone should appear in the world graph."""
    for npc in npc_registry:
        if npc.current_zone_id:
            zone = seed_graph.get_zone(npc.current_zone_id)
            assert npc.id in zone.npc_ids, (
                f"{npc.name} has current_zone_id={npc.current_zone_id} "
                f"but is not in that zone's npc_ids"
            )


# ── Affordance integration ────────────────────────────────────────────────────

def test_npc_tag_map_enables_role_filtering(seed_graph, npc_registry, action_registry):
    """teach_recipe requires npc_present — with tag map, role filtering works."""
    tag_map = npc_registry.build_npc_tag_map()
    player = npc_registry.player()
    # Player is in village_square with Aldric's connections nearby
    # trade action just needs any NPC present
    aldric = npc_registry.get("npc_aldric_stonehand")
    # Put player in forge_room so Aldric (a blacksmith) is present
    seed_graph.place_npc("player", "forge_room")
    player.current_zone_id = "forge_room"

    player_ctx = player.as_actor_context(graph=seed_graph)
    available = what_can_actor_do(
        player_ctx, "forge_room", seed_graph, action_registry,
        npc_tag_map=tag_map,
    )
    action_ids = {a.id for a in available}
    assert "trade" in action_ids  # Aldric is present in forge_room


def test_npc_present_role_check_with_tag_map(seed_graph, npc_registry):
    """NpcPresentPrecondition(role='blacksmith') passes only when a smith is present."""
    tag_map = npc_registry.build_npc_tag_map()

    # forge_room has Aldric (blacksmith)
    ctx_with_smith = EvalContext(
        zone_id="forge_room",
        graph=seed_graph,
        actor=ActorContext(actor_id="player"),
        npc_tag_map=tag_map,
    )
    from affordances.query import evaluate_precondition
    p = NpcPresentPrecondition(role="blacksmith")
    assert evaluate_precondition(p, ctx_with_smith) is True

    # village_square has no NPC placed yet
    ctx_empty = EvalContext(
        zone_id="village_square",
        graph=seed_graph,
        actor=ActorContext(actor_id="player"),
        npc_tag_map=tag_map,
    )
    assert evaluate_precondition(p, ctx_empty) is False


def test_aldric_can_smith_in_forge(aldric, seed_graph, action_registry):
    """Aldric with his skills and recipes can perform smithing actions in the forge."""
    ctx = aldric.as_actor_context(graph=seed_graph)
    # Give Aldric iron ingots (he has 2 in the forge room, but they're zone items not carried)
    ctx.inventory["iron_ingot"] = 5
    ctx.inventory["iron_ore"] = 4
    ctx.inventory["wood_log"] = 3

    available = what_can_actor_do(ctx, "forge_room", seed_graph, action_registry)
    action_ids = {a.id for a in available}
    assert "smith_sword" in action_ids
    assert "smith_axe" in action_ids
    assert "smelt_iron" in action_ids


def test_novice_cannot_smith_sword(seed_graph, action_registry):
    """Player with no skills cannot smith a sword."""
    novice = ActorContext(actor_id="player", skills={}, known_recipes=set(), inventory={})
    available = what_can_actor_do(novice, "forge_room", seed_graph, action_registry)
    action_ids = {a.id for a in available}
    assert "smith_sword" not in action_ids
