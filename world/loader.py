"""
Load a hand-authored world seed (YAML) into a WorldGraph.

The loader is intentionally strict: unknown zone IDs in connects_to or parent
references raise immediately rather than silently dropping the edge. This
ensures the seed file stays consistent with the world graph.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

from world.graph import WorldGraph
from world.zone import Feature, Item, PropertyValue, Zone
from world.terrain import TerrainType


def load_world(seed_path: Path | str) -> WorldGraph:
    """Parse a seed YAML file and return a fully wired WorldGraph."""
    data = yaml.safe_load(Path(seed_path).read_text())
    graph = WorldGraph()

    zone_records: list[dict[str, Any]] = data.get("zones", [])

    # Pass 1 — create all zones (no edges yet)
    for rec in zone_records:
        zone = _zone_from_record(rec)
        graph.add_zone(zone)

    # Pass 2 — wire containment and connection edges
    for rec in zone_records:
        zone_id: str = rec["id"]

        parent_id = rec.get("parent")
        if parent_id:
            graph.set_parent(zone_id, parent_id)

        for conn_id in rec.get("connects_to", []):
            try:
                graph.add_connection(zone_id, conn_id)
            except KeyError:
                raise ValueError(
                    f"Zone '{zone_id}' references unknown connection target '{conn_id}'"
                )

    # Pass 3 — place starting items
    for rec in data.get("items", []):
        item = _item_from_record(rec)
        graph.add_item(item)
        zone_id = rec.get("zone_id")
        if zone_id:
            if zone_id not in {z.id for z in graph.zones()}:
                raise ValueError(
                    f"Item '{item.id}' references unknown zone '{zone_id}'"
                )
            graph.place_item(item.id, zone_id)

    return graph


def _zone_from_record(rec: dict[str, Any]) -> Zone:
    features = [_feature_from_record(f) for f in rec.get("features", [])]
    raw_props = rec.get("properties", {})
    properties = {k: PropertyValue.of(v) for k, v in raw_props.items()}

    terrain_raw = rec.get("terrain_type", "ground")
    try:
        terrain = TerrainType(terrain_raw)
    except ValueError:
        terrain = TerrainType.GROUND

    return Zone(
        id=rec["id"],
        name=rec["name"],
        description=rec.get("description", ""),
        terrain_type=terrain,
        tags=set(rec.get("tags", [])),
        properties=properties,
        features=features,
        owner_ids=list(rec.get("owner_ids", [])),
        appearance=rec.get("appearance"),
    )


def _item_from_record(rec: dict[str, Any]) -> Item:
    raw_props = rec.get("properties", {})
    properties = {k: PropertyValue.of(v) for k, v in raw_props.items()}
    return Item(
        id=rec["id"],
        name=rec["name"],
        item_type=rec["item_type"],
        tags=set(rec.get("tags", [])),
        properties=properties,
        quality=float(rec.get("quality", 1.0)),
        quantity=int(rec.get("quantity", 1)),
        owner_id=rec.get("owner_id"),
    )


def _feature_from_record(rec: dict[str, Any]) -> Feature:
    raw_props = rec.get("properties", {})
    properties = {k: PropertyValue.of(v) for k, v in raw_props.items()}
    return Feature(
        name=rec["name"],
        description=rec.get("description", ""),
        tags=set(rec.get("tags", [])),
        properties=properties,
        quality=float(rec.get("quality", 1.0)),
    )
