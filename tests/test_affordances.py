"""Tests for the affordance system: schema, registry, and query primitives."""
from pathlib import Path

import pytest

from affordances.schema import (
    Action, ActionCategory, ActionStep, PlayerSkillGate,
    AndPrecondition, OrPrecondition, NotPrecondition,
    NearbyTagPrecondition, ActorHasItemPrecondition, ActorSkillPrecondition,
    ActorKnowsRecipePrecondition, NpcPresentPrecondition,
    ZoneHasTagPrecondition, ZoneIsAccessiblePrecondition,
    ProducesEffect, ConsumesEffect, AdvancesSkillEffect, TimeCostEffect,
    ConfusionTable, ConfusionEntry,
)
from affordances.registry import ActionRegistry
from affordances.query import (
    ActorContext, EvalContext,
    evaluate_precondition,
    what_can_actor_do,
    where_can_action_be_done,
    actions_available_in_zone,
)
from world.graph import WorldGraph
from world.zone import Feature, Item, Zone
from world.terrain import TerrainType
from world.loader import load_world

SEED_PATH = Path(__file__).parent.parent / "data" / "village_seed.yaml"
ACTIONS_PATH = Path(__file__).parent.parent / "data" / "actions.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> ActionRegistry:
    return ActionRegistry.from_yaml(ACTIONS_PATH)


@pytest.fixture
def forge_graph() -> WorldGraph:
    """Minimal graph: village with a smithy zone that has forge + anvil features."""
    g = WorldGraph()
    g.add_zone(Zone(id="village", name="Village", tags={"outdoor", "settlement"}))
    g.add_zone(Zone(
        id="smithy",
        name="Smithy",
        tags={"indoor"},
        features=[
            Feature(name="Forge", tags={"forge", "heat_source", "air_supply"}),
            Feature(name="Anvil", tags={"anvil"}),
        ],
    ))
    g.add_zone(Zone(id="forest", name="Forest", tags={"outdoor", "forest", "timber"}))
    g.set_parent("smithy", "village")
    g.add_connection("village", "smithy")
    g.add_connection("village", "forest")
    return g


@pytest.fixture
def skilled_smith() -> ActorContext:
    return ActorContext(
        actor_id="npc_smith",
        skills={"smithing": 0.80, "mining": 0.40},
        known_recipes={"smith_sword", "smith_axe", "smith_tool", "smith_knife"},
        inventory={"iron_ingot": 5, "iron_ore": 4, "wood_log": 3},
    )


@pytest.fixture
def novice_actor() -> ActorContext:
    return ActorContext(
        actor_id="npc_novice",
        skills={},
        known_recipes=set(),
        inventory={},
    )


@pytest.fixture
def seed_graph() -> WorldGraph:
    return load_world(SEED_PATH)


# ── Schema construction ────────────────────────────────────────────────────────

def test_action_loads_from_dict():
    data = {
        "id": "test_action",
        "name": "Test",
        "category": "crafting",
        "preconditions": {"type": "nearby_tag", "tag": "anvil"},
        "effects": [{"type": "time_cost", "game_hours": 1.0}],
    }
    action = Action.model_validate(data)
    assert action.id == "test_action"
    assert action.category == ActionCategory.CRAFTING
    assert isinstance(action.preconditions, NearbyTagPrecondition)


def test_nested_and_precondition():
    data = {
        "type": "and",
        "conditions": [
            {"type": "nearby_tag", "tag": "heat_source"},
            {"type": "actor_has_item", "item_type": "iron_ingot", "quantity": 2},
        ],
    }
    from pydantic import TypeAdapter
    from affordances.schema import Precondition
    p = TypeAdapter(Precondition).validate_python(data)
    assert isinstance(p, AndPrecondition)
    assert len(p.conditions) == 2


def test_deeply_nested_precondition():
    """or(and(A, B), not(C)) — three levels of nesting."""
    from pydantic import TypeAdapter
    from affordances.schema import Precondition
    data = {
        "type": "or",
        "conditions": [
            {
                "type": "and",
                "conditions": [
                    {"type": "nearby_tag", "tag": "water_source"},
                    {"type": "nearby_tag", "tag": "tannery_vat"},
                ],
            },
            {"type": "not", "condition": {"type": "zone_has_tag", "tag": "locked"}},
        ],
    }
    p = TypeAdapter(Precondition).validate_python(data)
    assert isinstance(p, OrPrecondition)
    assert isinstance(p.conditions[0], AndPrecondition)
    assert isinstance(p.conditions[1], NotPrecondition)


def test_action_total_time_from_effects():
    data = {
        "id": "a1", "name": "A", "category": "gathering",
        "preconditions": {"type": "nearby_tag", "tag": "timber"},
        "effects": [{"type": "time_cost", "game_hours": 2.5}],
    }
    action = Action.model_validate(data)
    assert action.total_time_hours == 2.5


def test_action_total_time_from_step_list():
    """step_list time costs sum to total; TimeCostEffect at action level is ignored."""
    data = {
        "id": "a1", "name": "A", "category": "crafting",
        "preconditions": {"type": "nearby_tag", "tag": "anvil"},
        "effects": [],
        "step_list": [
            {"name": "Step 1", "time_cost_hours": 1.0},
            {"name": "Step 2", "time_cost_hours": 2.0},
            {"name": "Step 3", "time_cost_hours": 0.5},
        ],
    }
    action = Action.model_validate(data)
    assert action.total_time_hours == 3.5


def test_confusion_table_structure():
    data = {
        "id": "g1", "name": "Gather", "category": "gathering",
        "preconditions": {"type": "nearby_tag", "tag": "wild_herbs"},
        "effects": [{"type": "produces", "item_type": "herb"}],
        "confusion_table": {
            "intended_output": "herb",
            "skill": "herbalism",
            "entries": [
                {"output_item_type": "herb_toxic", "base_probability": 0.15, "skill_elimination_threshold": 0.30},
            ],
        },
    }
    action = Action.model_validate(data)
    assert action.confusion_table is not None
    assert action.confusion_table.entries[0].output_item_type == "herb_toxic"


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_loads(registry):
    assert len(registry) == 20


def test_registry_get_known_action(registry):
    action = registry.get("smith_sword")
    assert action.name == "Smith a Sword"
    assert action.category == ActionCategory.CRAFTING


def test_registry_get_unknown_raises(registry):
    with pytest.raises(KeyError):
        registry.get("nonexistent_action")


def test_registry_by_category(registry):
    gathering = registry.by_category(ActionCategory.GATHERING)
    assert len(gathering) == 6
    crafting = registry.by_category(ActionCategory.CRAFTING)
    assert len(crafting) == 10
    social = registry.by_category(ActionCategory.SOCIAL)
    assert len(social) == 2
    movement = registry.by_category(ActionCategory.MOVEMENT)
    assert len(movement) == 2


def test_registry_by_tag(registry):
    loud = registry.by_tag("loud")
    loud_ids = {a.id for a in loud}
    assert "smith_sword" in loud_ids
    assert "chop_wood" in loud_ids
    assert "fish" not in loud_ids


def test_registry_produces_item_type(registry):
    sword_actions = registry.produces_item_type("sword")
    assert len(sword_actions) == 1
    assert sword_actions[0].id == "smith_sword"


def test_registry_consumes_item_type(registry):
    consumers = registry.consumes_item_type("iron_ingot")
    consumer_ids = {a.id for a in consumers}
    assert "smith_sword" in consumer_ids
    assert "smith_axe" in consumer_ids
    assert "smith_tool" in consumer_ids


def test_registry_all_produced_item_types(registry):
    produced = registry.all_produced_item_types()
    assert "sword" in produced
    assert "iron_ingot" in produced
    assert "flour" in produced
    assert "bread" in produced


def test_registry_required_tags(registry):
    tags = registry.required_tags("smith_sword")
    assert "heat_source" in tags
    assert "anvil" in tags


def test_registry_duplicate_id_raises():
    reg = ActionRegistry()
    action_data = {
        "id": "dup", "name": "D", "category": "gathering",
        "preconditions": {"type": "nearby_tag", "tag": "timber"},
        "effects": [],
    }
    reg._register(Action.model_validate(action_data))
    with pytest.raises(ValueError, match="Duplicate"):
        reg._register(Action.model_validate(action_data))


# ── Precondition evaluation ────────────────────────────────────────────────────

def test_nearby_tag_satisfied(forge_graph):
    # smithy has forge/heat_source; village connects to smithy → within 1 hop
    ctx = EvalContext(zone_id="village", graph=forge_graph)
    p = NearbyTagPrecondition(tag="heat_source")
    assert evaluate_precondition(p, ctx) is True


def test_nearby_tag_not_satisfied(forge_graph):
    ctx = EvalContext(zone_id="village", graph=forge_graph)
    p = NearbyTagPrecondition(tag="water_source")
    assert evaluate_precondition(p, ctx) is False


def test_zone_has_tag_exact(forge_graph):
    # smithy itself has heat_source (via feature)
    ctx = EvalContext(zone_id="smithy", graph=forge_graph)
    assert evaluate_precondition(ZoneHasTagPrecondition(tag="forge"), ctx) is True
    # village does NOT have heat_source directly (only smithy does)
    ctx2 = EvalContext(zone_id="village", graph=forge_graph)
    assert evaluate_precondition(ZoneHasTagPrecondition(tag="forge"), ctx2) is False


def test_actor_has_item_sufficient(forge_graph, skilled_smith):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=skilled_smith)
    p = ActorHasItemPrecondition(item_type="iron_ingot", quantity=2)
    assert evaluate_precondition(p, ctx) is True


def test_actor_has_item_insufficient(forge_graph, novice_actor):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=novice_actor)
    p = ActorHasItemPrecondition(item_type="iron_ingot", quantity=1)
    assert evaluate_precondition(p, ctx) is False


def test_actor_skill_passes(forge_graph, skilled_smith):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=skilled_smith)
    assert evaluate_precondition(ActorSkillPrecondition(skill="smithing", min_value=0.50), ctx) is True


def test_actor_skill_fails(forge_graph, novice_actor):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=novice_actor)
    assert evaluate_precondition(ActorSkillPrecondition(skill="smithing", min_value=0.10), ctx) is False


def test_actor_knows_recipe(forge_graph, skilled_smith):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=skilled_smith)
    assert evaluate_precondition(ActorKnowsRecipePrecondition(recipe_id="smith_sword"), ctx) is True
    assert evaluate_precondition(ActorKnowsRecipePrecondition(recipe_id="brew_potion"), ctx) is False


def test_actor_predicates_pass_in_zone_only_mode(forge_graph):
    """When actor is None, actor-specific predicates always return True."""
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=None)
    assert evaluate_precondition(ActorHasItemPrecondition(item_type="iron_ingot", quantity=99), ctx) is True
    assert evaluate_precondition(ActorSkillPrecondition(skill="smithing", min_value=1.0), ctx) is True
    assert evaluate_precondition(ActorKnowsRecipePrecondition(recipe_id="any_recipe"), ctx) is True


def test_and_precondition_all_true(forge_graph, skilled_smith):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=skilled_smith)
    p = AndPrecondition(conditions=[
        NearbyTagPrecondition(tag="heat_source"),
        ActorHasItemPrecondition(item_type="iron_ingot", quantity=2),
        ActorSkillPrecondition(skill="smithing", min_value=0.20),
    ])
    assert evaluate_precondition(p, ctx) is True


def test_and_precondition_one_false(forge_graph, novice_actor):
    ctx = EvalContext(zone_id="smithy", graph=forge_graph, actor=novice_actor)
    p = AndPrecondition(conditions=[
        NearbyTagPrecondition(tag="heat_source"),  # True
        ActorHasItemPrecondition(item_type="iron_ingot", quantity=1),  # False (novice has nothing)
    ])
    assert evaluate_precondition(p, ctx) is False


def test_or_precondition(forge_graph):
    ctx = EvalContext(zone_id="village", graph=forge_graph)
    p = OrPrecondition(conditions=[
        NearbyTagPrecondition(tag="water_source"),   # False
        NearbyTagPrecondition(tag="heat_source"),    # True (smithy is nearby)
    ])
    assert evaluate_precondition(p, ctx) is True


def test_not_precondition(forge_graph):
    ctx = EvalContext(zone_id="village", graph=forge_graph)
    p = NotPrecondition(condition=NearbyTagPrecondition(tag="water_source"))
    assert evaluate_precondition(p, ctx) is True  # no water, so NOT is True


def test_npc_present_no_npcs(forge_graph):
    ctx = EvalContext(zone_id="village", graph=forge_graph, actor=ActorContext(actor_id="a1"))
    p = NpcPresentPrecondition()
    assert evaluate_precondition(p, ctx) is False


def test_npc_present_with_npc(forge_graph):
    forge_graph.place_npc("npc_smith", "village")
    ctx = EvalContext(zone_id="village", graph=forge_graph, actor=ActorContext(actor_id="player"))
    p = NpcPresentPrecondition()
    assert evaluate_precondition(p, ctx) is True


def test_zone_accessible(forge_graph):
    ctx = EvalContext(zone_id="village", graph=forge_graph)
    assert evaluate_precondition(ZoneIsAccessiblePrecondition(), ctx) is True
    # Lock the zone
    forge_graph.get_zone("village").tags.add("locked")
    assert evaluate_precondition(ZoneIsAccessiblePrecondition(), ctx) is False


# ── Query 1: what_can_actor_do ─────────────────────────────────────────────────

def test_what_can_actor_do_skilled_smith_in_smithy(forge_graph, skilled_smith, registry):
    available = what_can_actor_do(skilled_smith, "smithy", forge_graph, registry)
    action_ids = {a.id for a in available}
    assert "smith_sword" in action_ids
    assert "smith_axe" in action_ids
    assert "smith_tool" in action_ids
    # smith has iron_ore + wood_log in inventory, so smelt_iron is also available
    assert "smelt_iron" in action_ids

def test_what_can_actor_do_smith_with_ore(forge_graph, registry):
    """Smith with ore and wood can smelt."""
    smith = ActorContext(
        actor_id="s1",
        skills={"smithing": 0.5},
        known_recipes={"smith_sword"},
        inventory={"iron_ore": 4, "wood_log": 3, "iron_ingot": 2},
    )
    available = what_can_actor_do(smith, "smithy", forge_graph, registry)
    action_ids = {a.id for a in available}
    assert "smelt_iron" in action_ids
    assert "smith_sword" in action_ids


def test_what_can_actor_do_novice_in_forest(forge_graph, novice_actor, registry):
    """Novice in forest can chop wood (no skill gate) but not mine (needs pickaxe)."""
    available = what_can_actor_do(novice_actor, "forest", forge_graph, registry)
    action_ids = {a.id for a in available}
    assert "chop_wood" in action_ids
    assert "mine_ore" not in action_ids  # no pickaxe, no ore_deposit


def test_what_can_actor_do_no_relevant_zone(forge_graph, novice_actor, registry):
    """Village with no relevant tags returns mostly movement and trade actions."""
    available = what_can_actor_do(novice_actor, "village", forge_graph, registry)
    action_ids = {a.id for a in available}
    # Smithy is connected to village, so nearby_tag(heat_source) passes for village
    assert "smelt_iron" not in action_ids  # still needs items in inventory


def test_what_can_actor_do_fisher_at_river():
    """Fisher can fish at a river zone."""
    g = WorldGraph()
    g.add_zone(Zone(id="river", name="River", tags={"outdoor", "river", "fish_population", "water_source"}))
    fisher = ActorContext(actor_id="hawke", skills={"fishing": 0.8}, known_recipes=set(), inventory={})
    reg = ActionRegistry.from_yaml(ACTIONS_PATH)
    available = what_can_actor_do(fisher, "river", g, reg)
    action_ids = {a.id for a in available}
    assert "fish" in action_ids
    assert "draw_water" in action_ids


# ── Query 2: where_can_action_be_done ─────────────────────────────────────────

def test_where_can_smith_sword_be_done(forge_graph, registry):
    smith_sword = registry.get("smith_sword")
    zones = where_can_action_be_done(smith_sword, forge_graph)
    zone_ids = {z.id for z in zones}
    # smithy has heat_source + anvil directly
    assert "smithy" in zone_ids
    # village connects to smithy (1 hop), so nearby_tag passes — village also qualifies
    assert "village" in zone_ids
    # forest has neither heat_source nor anvil
    assert "forest" not in zone_ids


def test_where_can_fish_be_done(registry):
    g = WorldGraph()
    g.add_zone(Zone(id="river", name="River", tags={"fish_population", "water_source"}))
    g.add_zone(Zone(id="village", name="Village", tags={"settlement"}))
    g.add_connection("village", "river")

    fish_action = registry.get("fish")
    zones = where_can_action_be_done(fish_action, g)
    zone_ids = {z.id for z in zones}
    assert "river" in zone_ids
    assert "village" in zone_ids  # nearby (1 hop)


def test_where_can_brew_potion_be_done(registry):
    g = WorldGraph()
    g.add_zone(Zone(
        id="herbalist",
        name="Herbalist Shop",
        features=[Feature(name="Brewing Table", tags={"brewing_vessel", "workbench"})],
    ))
    g.add_zone(Zone(id="village", name="Village"))
    g.add_connection("village", "herbalist")

    brew = registry.get("brew_potion")
    zones = where_can_action_be_done(brew, g)
    zone_ids = {z.id for z in zones}
    assert "herbalist" in zone_ids
    assert "village" in zone_ids  # 1 hop from herbalist


def test_where_can_grind_grain_be_done(seed_graph, registry):
    """In the seed world, only the mill has a millstone."""
    grind = registry.get("grind_grain")
    zones = where_can_action_be_done(grind, seed_graph)
    zone_ids = {z.id for z in zones}
    assert "thornhaven_mill" in zone_ids


# ── actions_available_in_zone (zone-only) ──────────────────────────────────────

def test_actions_available_in_smithy(forge_graph, registry):
    available = actions_available_in_zone("smithy", forge_graph, registry)
    action_ids = {a.id for a in available}
    assert "smelt_iron" in action_ids
    assert "smith_sword" in action_ids
    # travel_to and enter_zone pass zone_accessible → should be present
    assert "travel_to" in action_ids


def test_actions_available_in_forest(forge_graph, registry):
    available = actions_available_in_zone("forest", forge_graph, registry)
    action_ids = {a.id for a in available}
    assert "chop_wood" in action_ids


# ── Seed world integration ─────────────────────────────────────────────────────

def test_seed_forge_room_supports_smithing(seed_graph, registry):
    available = actions_available_in_zone("forge_room", seed_graph, registry)
    action_ids = {a.id for a in available}
    assert "smith_sword" in action_ids
    assert "smelt_iron" in action_ids
    assert "smith_axe" in action_ids


def test_seed_grey_river_supports_fishing(seed_graph, registry):
    available = actions_available_in_zone("grey_river", seed_graph, registry)
    action_ids = {a.id for a in available}
    assert "fish" in action_ids
    assert "draw_water" in action_ids


def test_seed_herbalist_supports_brewing(seed_graph, registry):
    available = actions_available_in_zone("herbalist_shop", seed_graph, registry)
    action_ids = {a.id for a in available}
    assert "brew_potion" in action_ids


def test_seed_thornwood_supports_gathering(seed_graph, registry):
    available = actions_available_in_zone("thornwood_forest", seed_graph, registry)
    action_ids = {a.id for a in available}
    assert "chop_wood" in action_ids
    assert "gather_herbs" in action_ids
    assert "forage_berries" in action_ids
    # forest connects to grey_river (1 hop), so fish_population is nearby — fish is correctly available
    assert "fish" in action_ids
    # but mine_ore is not — no ore_deposit in forest or adjacent zones
    assert "mine_ore" not in action_ids


def test_smith_sword_step_list(registry):
    sword = registry.get("smith_sword")
    assert len(sword.step_list) == 4
    assert sword.total_time_hours == 4.0  # 0.5 + 2.0 + 1.0 + 0.5
    gates = [s.player_skill_gate for s in sword.step_list if s.player_skill_gate]
    assert len(gates) == 3
    assert gates[0].type_id == "forge_timing"


def test_teach_recipe_is_parametric(registry):
    teach = registry.get("teach_recipe")
    assert teach.is_parametric
    param_names = {p.name for p in teach.parameters}
    assert "recipe_id" in param_names
    assert "target_npc_id" in param_names
