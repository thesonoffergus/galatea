"""Tests for the world graph and zone layer."""
from pathlib import Path

import pytest

from world.zone import Feature, Item, PropertyValue, Zone
from world.graph import WorldGraph
from world.terrain import TerrainType
from world.loader import load_world

SEED_PATH = Path(__file__).parent.parent / "data" / "village_seed.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_graph() -> WorldGraph:
    g = WorldGraph()
    g.add_zone(Zone(id="wilderness", name="Wilderness", terrain_type=TerrainType.WILDERNESS))
    g.add_zone(Zone(id="village", name="Village", terrain_type=TerrainType.SETTLEMENT, tags={"settlement", "outdoor"}))
    g.add_zone(Zone(id="smithy", name="Smithy", tags={"indoor", "forge", "heat_source", "anvil"}))
    g.add_zone(Zone(id="forest", name="Forest", tags={"outdoor", "forest", "timber"}))
    g.set_parent("village", "wilderness")
    g.set_parent("smithy", "village")
    g.add_connection("village", "forest")
    g.add_connection("village", "smithy")
    return g


@pytest.fixture
def seed_graph() -> WorldGraph:
    return load_world(SEED_PATH)


# ── Zone construction ─────────────────────────────────────────────────────────

def test_zone_effective_tags_includes_own_tags():
    zone = Zone(id="z1", name="Z1", tags={"outdoor", "forest"})
    assert "outdoor" in zone.effective_tags()
    assert "forest" in zone.effective_tags()


def test_zone_effective_tags_includes_feature_tags():
    forge_feature = Feature(name="Forge", tags={"forge", "heat_source"})
    zone = Zone(id="z1", name="Smithy", features=[forge_feature])
    tags = zone.effective_tags()
    assert "forge" in tags
    assert "heat_source" in tags


def test_zone_effective_tags_includes_item_tags():
    item = Item(id="i1", name="Anvil", item_type="anvil", tags={"anvil", "tool"})
    zone = Zone(id="z1", name="Smithy", item_ids=["i1"])
    tags = zone.effective_tags(item_registry={"i1": item})
    assert "anvil" in tags


def test_property_value_roundtrip():
    pv = PropertyValue.of(42)
    assert pv.type == "int"
    assert pv.value == 42

    pv2 = PropertyValue.of("hello")
    assert pv2.type == "str"


# ── Graph structure ────────────────────────────────────────────────────────────

def test_parent_child_roundtrip(simple_graph):
    village = simple_graph.get_zone("village")
    smithy = simple_graph.get_zone("smithy")
    assert simple_graph.parent("village").id == "wilderness"
    assert simple_graph.parent("smithy").id == "village"
    assert any(z.id == "village" for z in simple_graph.children("wilderness"))
    assert any(z.id == "smithy" for z in simple_graph.children("village"))


def test_connections_are_bidirectional(simple_graph):
    village_conns = {z.id for z in simple_graph.connections("village")}
    forest_conns = {z.id for z in simple_graph.connections("forest")}
    assert "forest" in village_conns
    assert "village" in forest_conns


def test_reassigning_parent(simple_graph):
    simple_graph.add_zone(Zone(id="other", name="Other"))
    simple_graph.set_parent("smithy", "other")
    assert simple_graph.parent("smithy").id == "other"
    # village should no longer have smithy as child
    assert not any(z.id == "smithy" for z in simple_graph.children("village"))


def test_duplicate_zone_raises(simple_graph):
    with pytest.raises(ValueError, match="already registered"):
        simple_graph.add_zone(Zone(id="village", name="Duplicate"))


def test_neighbors_within_radius(simple_graph):
    # village connects to forest; radius=1 should include village + forest + smithy
    neighbors = simple_graph.neighbors_within("village", hops=1)
    assert "village" in neighbors
    assert "forest" in neighbors
    assert "smithy" in neighbors
    # wilderness is parent, not a CONNECTS neighbor
    assert "wilderness" not in neighbors


def test_zones_with_tag(simple_graph):
    zones = simple_graph.zones_with_tag("forge")
    assert any(z.id == "smithy" for z in zones)
    assert not any(z.id == "forest" for z in zones)


# ── NPC and item placement ────────────────────────────────────────────────────

def test_place_and_move_npc(simple_graph):
    simple_graph.place_npc("npc_01", "village")
    assert "npc_01" in simple_graph.get_zone("village").npc_ids
    assert simple_graph.npc_location("npc_01").id == "village"

    simple_graph.move_npc("npc_01", "forest")
    assert "npc_01" not in simple_graph.get_zone("village").npc_ids
    assert simple_graph.npc_location("npc_01").id == "forest"


def test_place_and_move_item(simple_graph):
    item = Item(id="sword_01", name="Iron Sword", item_type="sword", tags={"weapon"})
    simple_graph.add_item(item)
    simple_graph.place_item("sword_01", "smithy")
    assert "sword_01" in simple_graph.get_zone("smithy").item_ids

    simple_graph.move_item("sword_01", "village")
    assert "sword_01" not in simple_graph.get_zone("smithy").item_ids
    assert "sword_01" in simple_graph.get_zone("village").item_ids


def test_item_tags_flow_into_effective_tags(simple_graph):
    item = Item(id="anvil_01", name="Portable Anvil", item_type="anvil", tags={"anvil"})
    simple_graph.add_item(item)
    simple_graph.place_item("anvil_01", "forest")
    tags = simple_graph.effective_tags("forest")
    assert "anvil" in tags


# ── Path finding ──────────────────────────────────────────────────────────────

def test_shortest_path_exists(simple_graph):
    path = simple_graph.shortest_path("forest", "smithy")
    assert path is not None
    assert path[0] == "forest"
    assert path[-1] == "smithy"


def test_shortest_path_unreachable(simple_graph):
    simple_graph.add_zone(Zone(id="island", name="Island"))
    assert simple_graph.shortest_path("village", "island") is None


# ── Seed loader ───────────────────────────────────────────────────────────────

def test_seed_loads_without_error(seed_graph):
    assert seed_graph.zone_count() > 0


def test_seed_has_expected_zones(seed_graph):
    for zone_id in ["wilderness", "village_of_thornhaven", "forge_room", "grey_river", "ironvein_hill"]:
        zone = seed_graph.get_zone(zone_id)
        assert zone is not None, f"Expected zone '{zone_id}' not found"


def test_seed_containment_hierarchy(seed_graph):
    forge = seed_graph.get_zone("forge_room")
    smithy = seed_graph.parent("forge_room")
    assert smithy is not None
    assert smithy.id == "the_hammer_and_tongs"

    village = seed_graph.parent("the_hammer_and_tongs")
    assert village is not None
    assert village.id == "village_of_thornhaven"


def test_seed_forge_room_has_crafting_tags(seed_graph):
    tags = seed_graph.effective_tags("forge_room")
    assert "forge" in tags
    assert "heat_source" in tags
    assert "anvil" in tags


def test_seed_connections_exist(seed_graph):
    village_conns = {z.id for z in seed_graph.connections("village_of_thornhaven")}
    assert "thornwood_forest" in village_conns
    assert "grey_river" in village_conns
    assert "ironvein_hill" in village_conns


def test_seed_river_has_fish(seed_graph):
    tags = seed_graph.effective_tags("grey_river")
    assert "fish_population" in tags
    assert "water_source" in tags


def test_seed_zone_summary(seed_graph):
    summary = seed_graph.summary("forge_room")
    assert summary["name"] == "Forge Room"
    assert "forge" in summary["effective_tags"]
    assert summary["parent"] == "The Hammer and Tongs"


def test_seed_all_descendants_of_village(seed_graph):
    descendants = seed_graph.all_descendants("village_of_thornhaven")
    desc_ids = {z.id for z in descendants}
    assert "the_hammer_and_tongs" in desc_ids
    assert "forge_room" in desc_ids
    assert "tavern_common_room" in desc_ids
