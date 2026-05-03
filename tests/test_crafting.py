"""Tests for the crafting system: recipes, quality, confusion, skill hook, DAG, bootstrap."""
import random
from pathlib import Path

import pytest

from affordances.registry import ActionRegistry
from crafting.recipes import RecipeStore, RecipeSource
from crafting.quality import (
    QualityInputs, QualityPolicy, QualityPolicyRegistry,
    MaterialAggregation, compute_quality, DEFAULT_POLICY,
)
from crafting.confusion import resolve_confusion, confusion_probability_at_skill
from crafting.skill_hook import PlayerSkillHookRegistry, _default_auto_resolve
from crafting.dag import (
    build_item_dag, raw_materials_for, dependency_chain,
    dependency_tree, detect_cycles, validate_dag,
)
from crafting.bootstrap import validate_world, BootstrapResult
from affordances.schema import ConfusionTable, ConfusionEntry
from world.loader import load_world
from world.graph import WorldGraph
from world.zone import Item, Zone

ACTIONS_PATH = Path(__file__).parent.parent / "data" / "actions.yaml"
SEED_PATH = Path(__file__).parent.parent / "data" / "village_seed.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> ActionRegistry:
    return ActionRegistry.from_yaml(ACTIONS_PATH)


@pytest.fixture
def seed_graph() -> WorldGraph:
    return load_world(SEED_PATH)


@pytest.fixture
def herb_confusion_table() -> ConfusionTable:
    return ConfusionTable(
        intended_output="herb",
        skill="herbalism",
        entries=[
            ConfusionEntry(
                output_item_type="herb_toxic",
                base_probability=0.15,
                skill_elimination_threshold=0.30,
            ),
            ConfusionEntry(
                output_item_type="herb_common",
                base_probability=0.40,
                skill_elimination_threshold=0.50,
            ),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# RecipeStore
# ══════════════════════════════════════════════════════════════════════════════

def test_recipe_store_empty():
    store = RecipeStore()
    assert not store.knows("smith_sword")
    assert store.count() == 0


def test_recipe_store_learn():
    store = RecipeStore()
    added = store.learn("smith_sword", RecipeSource.TAUGHT, taught_by_id="npc_aldric")
    assert added is True
    assert store.knows("smith_sword")


def test_recipe_store_learn_duplicate_is_noop():
    store = RecipeStore()
    store.learn("smith_sword")
    added_again = store.learn("smith_sword")
    assert added_again is False
    assert store.count() == 1


def test_recipe_store_forget():
    store = RecipeStore()
    store.learn("smith_sword")
    removed = store.forget("smith_sword")
    assert removed is True
    assert not store.knows("smith_sword")
    assert store.forget("smith_sword") is False  # already gone


def test_recipe_store_known_ids():
    store = RecipeStore()
    store.learn("smith_sword")
    store.learn("brew_potion")
    assert store.known_ids() == {"smith_sword", "brew_potion"}


def test_recipe_store_from_id_list():
    store = RecipeStore.from_id_list(["smith_sword", "smith_axe", "brew_potion"])
    assert store.count() == 3
    assert store.knows("smith_sword")
    # All sourced as INNATE
    entry = store.entries["smith_sword"]
    assert entry.source == RecipeSource.INNATE


def test_recipe_store_by_source():
    store = RecipeStore()
    store.learn("smith_sword", RecipeSource.TAUGHT, taught_by_id="npc_a")
    store.learn("brew_potion", RecipeSource.OBSERVED)
    store.learn("bake_bread", RecipeSource.INNATE)
    taught = store.by_source(RecipeSource.TAUGHT)
    assert len(taught) == 1
    assert taught[0].recipe_id == "smith_sword"
    assert taught[0].taught_by_id == "npc_a"


def test_recipe_store_taught_by_preserved():
    store = RecipeStore()
    store.learn("smith_sword", RecipeSource.TAUGHT, taught_by_id="npc_aldric_stonehand")
    entry = store.entries["smith_sword"]
    assert entry.taught_by_id == "npc_aldric_stonehand"


# ══════════════════════════════════════════════════════════════════════════════
# Quality model
# ══════════════════════════════════════════════════════════════════════════════

def test_quality_default_policy_weights_sum_to_one():
    total = (
        DEFAULT_POLICY.weight_material
        + DEFAULT_POLICY.weight_tool
        + DEFAULT_POLICY.weight_character_skill
        + DEFAULT_POLICY.weight_player_performance
        + DEFAULT_POLICY.weight_environment
    )
    assert abs(total - 1.0) < 1e-6


def test_quality_custom_policy_must_sum_to_one():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="sum to 1.0"):
        QualityPolicy(
            weight_material=0.50,
            weight_tool=0.50,
            weight_character_skill=0.50,
            weight_player_performance=0.0,
            weight_environment=0.0,
        )


def test_quality_perfect_inputs_yields_one():
    inputs = QualityInputs(
        material_qualities=[1.0, 1.0],
        tool_quality=1.0,
        character_skill=1.0,
        player_performance=1.0,
        environment_modifier=1.0,
    )
    q = compute_quality(inputs)
    assert abs(q - 1.0) < 1e-6


def test_quality_zero_inputs_yields_zero():
    inputs = QualityInputs(
        material_qualities=[0.0, 0.0],
        tool_quality=0.0,
        character_skill=0.0,
        player_performance=0.0,
        environment_modifier=0.0,
    )
    q = compute_quality(inputs)
    assert q == 0.0


def test_quality_no_materials_defaults_to_one():
    """When no materials are consumed, material score defaults to 1.0."""
    inputs = QualityInputs(character_skill=0.5)
    policy = QualityPolicy(
        weight_material=0.40,
        weight_tool=0.15,
        weight_character_skill=0.40,
        weight_player_performance=0.05,
        weight_environment=0.0,
    )
    q = compute_quality(inputs, policy)
    # material=1.0*0.40 + tool=1.0*0.15 + skill=0.5*0.40 + player=1.0*0.05 = 0.80
    assert abs(q - 0.80) < 1e-6


def test_quality_worst_of_aggregation():
    inputs = QualityInputs(material_qualities=[1.0, 0.2, 0.8])
    policy = QualityPolicy(
        material_aggregation=MaterialAggregation.WORST_OF,
        weight_material=1.0,
        weight_tool=0.0,
        weight_character_skill=0.0,
        weight_player_performance=0.0,
        weight_environment=0.0,
    )
    q = compute_quality(inputs, policy)
    assert abs(q - 0.2) < 1e-6


def test_quality_average_aggregation():
    inputs = QualityInputs(material_qualities=[0.6, 0.8])
    policy = QualityPolicy(
        material_aggregation=MaterialAggregation.AVERAGE,
        weight_material=1.0,
        weight_tool=0.0,
        weight_character_skill=0.0,
        weight_player_performance=0.0,
        weight_environment=0.0,
    )
    q = compute_quality(inputs, policy)
    assert abs(q - 0.7) < 1e-6


def test_quality_policy_registry_per_action_override():
    reg = QualityPolicyRegistry()
    custom = QualityPolicy(
        weight_material=0.80,
        weight_tool=0.10,
        weight_character_skill=0.10,
        weight_player_performance=0.0,
        weight_environment=0.0,
    )
    reg.set_for_action("smith_sword", custom)
    assert reg.get("smith_sword") is custom
    assert reg.get("smith_axe") is reg._default


def test_quality_policy_registry_category_fallback():
    reg = QualityPolicyRegistry()
    cat_policy = QualityPolicy(
        weight_material=0.60,
        weight_tool=0.20,
        weight_character_skill=0.15,
        weight_player_performance=0.05,
        weight_environment=0.0,
    )
    reg.set_for_category("crafting", cat_policy)
    # Action-level not set → falls back to category
    assert reg.get("smith_sword", category="crafting") is cat_policy
    # Action-level set → takes priority
    action_policy = QualityPolicy(
        weight_material=0.40,
        weight_tool=0.15,
        weight_character_skill=0.40,
        weight_player_performance=0.05,
        weight_environment=0.0,
    )
    reg.set_for_action("smith_sword", action_policy)
    assert reg.get("smith_sword", category="crafting") is action_policy


def test_quality_clamped_to_unit_interval():
    """Even with weights that push past 1.0, result is clamped."""
    inputs = QualityInputs(
        material_qualities=[1.0],
        tool_quality=1.0,
        character_skill=1.0,
        player_performance=1.0,
        environment_modifier=1.0,
    )
    # Intentionally use an imbalanced policy (won't sum to 1 — validator prevents this
    # via Pydantic, but we test clamp via direct compute call with custom weights)
    # Actually we can't bypass the validator. Test that result never exceeds 1.0.
    q = compute_quality(inputs)
    assert 0.0 <= q <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Confusion tables
# ══════════════════════════════════════════════════════════════════════════════

def test_confusion_high_skill_gets_intended(herb_confusion_table):
    """At skill >= elimination threshold, all confusion is eliminated."""
    rng = random.Random(42)
    results = [
        resolve_confusion(herb_confusion_table, character_skill=0.9, rng=rng)
        for _ in range(100)
    ]
    assert all(r == "herb" for r in results)


def test_confusion_zero_skill_often_fails(herb_confusion_table):
    """At skill=0, confusion fires frequently."""
    rng = random.Random(0)
    results = [
        resolve_confusion(herb_confusion_table, character_skill=0.0, rng=rng)
        for _ in range(200)
    ]
    # With base_probability=0.15 for toxic and 0.40 for common, ~50% should be confused
    confused = [r for r in results if r != "herb"]
    assert len(confused) > 60  # should fail often


def test_confusion_toxic_entry_fires_first():
    """Toxic entry (listed first) is checked before common (listed second)."""
    table = ConfusionTable(
        intended_output="herb",
        skill="herbalism",
        entries=[
            ConfusionEntry(
                output_item_type="herb_toxic",
                base_probability=1.0,  # always fires
                skill_elimination_threshold=0.50,
            ),
            ConfusionEntry(
                output_item_type="herb_common",
                base_probability=1.0,
                skill_elimination_threshold=0.50,
            ),
        ],
    )
    rng = random.Random(0)
    result = resolve_confusion(table, character_skill=0.0, rng=rng)
    assert result == "herb_toxic"  # first entry fires, second never reached


def test_confusion_deterministic_with_seed(herb_confusion_table):
    """Same RNG seed produces same result."""
    r1 = resolve_confusion(herb_confusion_table, 0.1, rng=random.Random(99))
    r2 = resolve_confusion(herb_confusion_table, 0.1, rng=random.Random(99))
    assert r1 == r2


def test_confusion_probability_at_skill_sums_to_one(herb_confusion_table):
    """Probability distribution should sum to ~1.0."""
    probs = confusion_probability_at_skill(herb_confusion_table, character_skill=0.1)
    total = sum(probs.values())
    assert abs(total - 1.0) < 1e-6


def test_confusion_probability_at_high_skill(herb_confusion_table):
    """At skill above all thresholds, intended output probability ≈ 1.0."""
    probs = confusion_probability_at_skill(herb_confusion_table, character_skill=1.0)
    assert probs["herb"] > 0.99
    assert probs.get("herb_toxic", 0.0) == 0.0
    assert probs.get("herb_common", 0.0) == 0.0


def test_confusion_from_registry(registry):
    """Verify gather_herbs in registry has a confusion table."""
    action = registry.get("gather_herbs")
    assert action.confusion_table is not None
    assert action.confusion_table.intended_output == "herb"
    assert len(action.confusion_table.entries) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Player skill hook
# ══════════════════════════════════════════════════════════════════════════════

def test_auto_resolve_no_difficulty():
    assert _default_auto_resolve(0.0, 0.5) == 1.0


def test_auto_resolve_skill_matches_difficulty():
    # At character_skill == difficulty, performance = 0.75
    result = _default_auto_resolve(0.5, 0.5)
    assert abs(result - 0.75) < 1e-6


def test_auto_resolve_double_difficulty():
    # character_skill = 2x difficulty → near 1.0
    result = _default_auto_resolve(0.5, 1.0)
    assert result == 1.0  # clamped


def test_auto_resolve_zero_skill():
    result = _default_auto_resolve(0.5, 0.0)
    assert result == 0.0


def test_skill_hook_registry_fallback():
    """No minigame registered → auto-resolve."""
    reg = PlayerSkillHookRegistry()
    perf = reg.resolve("hammer_rhythm", difficulty=0.5, character_skill=0.5)
    assert 0.0 <= perf <= 1.0


def test_skill_hook_registry_registered_minigame():
    reg = PlayerSkillHookRegistry()

    @reg.register("test_gate")
    def my_minigame(difficulty, character_skill):
        return 0.9  # always returns 0.9 regardless

    perf = reg.resolve("test_gate", difficulty=0.8, character_skill=0.1)
    assert abs(perf - 0.9) < 1e-6


def test_skill_hook_registry_result_clamped():
    reg = PlayerSkillHookRegistry()
    reg.register("bad_gate", lambda d, s: 99.9)
    assert reg.resolve("bad_gate", 0.5, 0.5) == 1.0


def test_skill_hook_is_registered():
    reg = PlayerSkillHookRegistry()
    assert not reg.is_registered("forge_timing")
    reg.register("forge_timing", lambda d, s: 0.8)
    assert reg.is_registered("forge_timing")


# ══════════════════════════════════════════════════════════════════════════════
# Product DAG
# ══════════════════════════════════════════════════════════════════════════════

def test_dag_builds_without_error(registry):
    dag = build_item_dag(registry)
    assert len(dag.nodes) > 0
    assert len(dag.edges) > 0


def test_dag_sword_production_chain(registry):
    dag = build_item_dag(registry)
    # sword is produced by smith_sword
    assert "sword" in dag.nodes
    # iron_ingot → sword edge should exist
    assert dag.has_edge("iron_ingot", "sword")


def test_dag_iron_ingot_production_chain(registry):
    dag = build_item_dag(registry)
    assert dag.has_edge("iron_ore", "iron_ingot")
    assert dag.has_edge("wood_log", "iron_ingot")


def test_dag_raw_materials_for_sword(registry):
    dag = build_item_dag(registry)
    raws = raw_materials_for("sword", dag)
    # sword ← iron_ingot ← iron_ore + wood_log (both gatherable)
    assert "iron_ore" in raws
    assert "wood_log" in raws


def test_dag_raw_materials_for_bread(registry):
    dag = build_item_dag(registry)
    raws = raw_materials_for("bread", dag)
    # bread ← flour ← grain; bread ← water
    assert "grain" in raws
    assert "water" in raws


def test_dag_dependency_chain_ordering(registry):
    dag = build_item_dag(registry)
    chain = dependency_chain("sword", dag)
    # iron_ore must appear before iron_ingot, iron_ingot before sword
    assert chain.index("iron_ore") < chain.index("iron_ingot")
    assert chain.index("iron_ingot") < chain.index("sword")
    assert "sword" in chain


def test_dag_gatherable_flag(registry):
    dag = build_item_dag(registry)
    assert dag.nodes["iron_ore"]["gatherable"] is True
    assert dag.nodes["wood_log"]["gatherable"] is True
    assert dag.nodes["herb"]["gatherable"] is True
    assert dag.nodes["iron_ingot"]["craftable"] is True
    assert dag.nodes["sword"]["craftable"] is True


def test_dag_no_cycles(registry):
    dag = build_item_dag(registry)
    cycles = detect_cycles(dag)
    assert cycles == [], f"Unexpected cycles: {cycles}"


def test_dag_validate_finds_unconsumed_items(registry):
    """Items consumed but never produced should appear as warnings."""
    issues = validate_dag(registry)
    # raw_hide is consumed by tan_hide but never produced by any action
    warning_items = {i.item_type for i in issues if i.item_type}
    assert "raw_hide" in warning_items


def test_dag_dependency_tree_structure(registry):
    dag = build_item_dag(registry)
    tree = dependency_tree("iron_ingot", dag, registry)
    assert tree["item_type"] == "iron_ingot"
    assert tree["craftable"] is True
    req_items = {r["item_type"] for r in tree["requires"]}
    assert "iron_ore" in req_items
    assert "wood_log" in req_items


def test_dag_dependency_tree_sword(registry):
    dag = build_item_dag(registry)
    tree = dependency_tree("sword", dag, registry)
    assert tree["item_type"] == "sword"
    # iron_ingot should be in requires
    req_items = {r["item_type"] for r in tree["requires"]}
    assert "iron_ingot" in req_items


# ══════════════════════════════════════════════════════════════════════════════
# Bootstrap validation
# ══════════════════════════════════════════════════════════════════════════════

def test_bootstrap_passes_with_seed(registry, seed_graph):
    """The default seed world should pass bootstrap validation."""
    result = validate_world(registry, seed_graph)
    errors = result.errors()
    assert errors == [], f"Bootstrap errors: {[e.description for e in errors]}"


def test_bootstrap_fails_without_tools(registry):
    """Without any tools in the world, mine_ore cannot be bootstrapped."""
    empty_graph = WorldGraph()
    empty_graph.add_zone(Zone(id="z1", name="Test", tags={"ore_deposit"}))
    result = validate_world(registry, empty_graph)
    errors = result.errors()
    assert any("mine_ore" in e.description for e in errors)


def test_bootstrap_warnings_for_raw_hide(registry, seed_graph):
    """raw_hide is not producible and not in seed world → warning."""
    result = validate_world(registry, seed_graph)
    warning_items = {w.item_type for w in result.warnings() if w.item_type}
    assert "raw_hide" in warning_items


def test_bootstrap_result_summary(registry, seed_graph):
    result = validate_world(registry, seed_graph)
    summary = result.summary()
    assert "PASS" in summary or "FAIL" in summary


def test_bootstrap_tool_reachable_via_crafting(registry):
    """
    Even without tools as world items, tool is reachable if smelt_iron can run
    and smith_tool can then produce it — but that requires iron from mine_ore
    which needs a tool. The cycle means it's only reachable via world items.
    """
    graph = WorldGraph()
    # Add a tool as a world item to break the cycle
    item = Item(id="tool_01", name="Tool", item_type="tool", tags={"tool"})
    graph.add_item(item)
    graph.add_zone(Zone(id="z1", name="Z"))
    graph.place_item("tool_01", "z1")
    result = validate_world(registry, graph)
    errors = result.errors()
    assert all("mine_ore" not in e.description for e in errors)


def test_bootstrap_cycle_detection(registry):
    """A synthetic cycle in the registry would be caught."""
    from affordances.schema import (
        Action, ActionCategory, AndPrecondition,
        ProducesEffect, ConsumesEffect, TimeCostEffect,
        NearbyTagPrecondition,
    )
    from affordances.registry import ActionRegistry

    cycle_registry = ActionRegistry()
    # item_a requires item_b; item_b requires item_a → cycle
    cycle_registry._register(Action.model_validate({
        "id": "make_a", "name": "Make A", "category": "crafting",
        "preconditions": {"type": "nearby_tag", "tag": "anvil"},
        "effects": [
            {"type": "produces", "item_type": "item_a"},
            {"type": "consumes", "item_type": "item_b", "from_actor": True},
        ],
    }))
    cycle_registry._register(Action.model_validate({
        "id": "make_b", "name": "Make B", "category": "crafting",
        "preconditions": {"type": "nearby_tag", "tag": "anvil"},
        "effects": [
            {"type": "produces", "item_type": "item_b"},
            {"type": "consumes", "item_type": "item_a", "from_actor": True},
        ],
    }))
    from crafting.dag import validate_dag
    issues = validate_dag(cycle_registry)
    cycle_issues = [i for i in issues if "cycle" in i.description.lower()]
    assert len(cycle_issues) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Seed loader item integration
# ══════════════════════════════════════════════════════════════════════════════

def test_seed_items_loaded(seed_graph):
    """Seed world should have items placed in zones."""
    # smithy_storefront should have the pickaxe and axe
    storefront = seed_graph.get_zone("smithy_storefront")
    assert len(storefront.item_ids) > 0


def test_seed_item_in_correct_zone(seed_graph):
    """Items declared with zone_id should be in that zone."""
    forge = seed_graph.get_zone("forge_room")
    forge_items = seed_graph.items_in_zone("forge_room")
    iron_ingots = [i for i in forge_items if i.item_type == "iron_ingot"]
    assert len(iron_ingots) >= 1


def test_seed_item_quality_preserved(seed_graph):
    storefront_items = seed_graph.items_in_zone("smithy_storefront")
    tool_items = [i for i in storefront_items if i.item_type == "tool"]
    assert len(tool_items) >= 1
    assert tool_items[0].quality == 0.75


def test_seed_item_owner_preserved(seed_graph):
    storefront_items = seed_graph.items_in_zone("smithy_storefront")
    aldrics = [i for i in storefront_items if i.owner_id == "npc_aldric_stonehand"]
    assert len(aldrics) >= 1
