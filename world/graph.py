"""
WorldGraph — the central data structure for the simulation.

Two edge types coexist in a single NetworkX DiGraph:
  CONTAINS  — directed parent → child (village → building → room)
  CONNECTS  — treated as undirected; stored as two directed edges
              (a ↔ b) representing passable adjacency (doors, paths)

Zones, items, and NPCs are registered here so that effective-tag
computation and affordance queries have a single resolved view of world state.
"""

from __future__ import annotations
from enum import StrEnum
from typing import Iterator, Optional

import networkx as nx

from world.zone import Feature, Item, Zone


class EdgeType(StrEnum):
    CONTAINS = "contains"
    CONNECTS = "connects"


class WorldGraph:
    def __init__(self) -> None:
        # MultiDiGraph allows both CONTAINS and CONNECTS edges between the same
        # zone pair (e.g., a smithy is contained by the village and also
        # navigably connected to it via a doorway).
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._zones: dict[str, Zone] = {}
        self._items: dict[str, Item] = {}

    # ------------------------------------------------------------------
    # Zone registration
    # ------------------------------------------------------------------

    def add_zone(self, zone: Zone) -> None:
        if zone.id in self._zones:
            raise ValueError(f"Zone '{zone.id}' already registered")
        self._zones[zone.id] = zone
        self._graph.add_node(zone.id, zone=zone)

    def get_zone(self, zone_id: str) -> Zone:
        try:
            return self._zones[zone_id]
        except KeyError:
            raise KeyError(f"Zone '{zone_id}' not found")

    def zones(self) -> Iterator[Zone]:
        return iter(self._zones.values())

    def zone_count(self) -> int:
        return len(self._zones)

    # ------------------------------------------------------------------
    # Item registration
    # ------------------------------------------------------------------

    def add_item(self, item: Item) -> None:
        self._items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    def remove_item(self, item_id: str) -> None:
        """Remove item from the item registry and its zone's item_ids list."""
        location = self.item_location(item_id)
        if location and item_id in location.item_ids:
            location.item_ids.remove(item_id)
        self._items.pop(item_id, None)

    def items_in_zone(self, zone_id: str) -> list[Item]:
        zone = self.get_zone(zone_id)
        return [self._items[iid] for iid in zone.item_ids if iid in self._items]

    # ------------------------------------------------------------------
    # Containment edges
    # ------------------------------------------------------------------

    def set_parent(self, child_id: str, parent_id: str) -> None:
        """Declare that child_id is contained within parent_id."""
        self._assert_exists(child_id)
        self._assert_exists(parent_id)
        # Remove any existing parent edge (a zone has at most one parent).
        # MultiDiGraph stores edges as {key: data_dict}, so we must match by type.
        for pred in list(self._graph.predecessors(child_id)):
            for key, data in list(self._graph[pred][child_id].items()):
                if data.get("edge_type") == EdgeType.CONTAINS:
                    self._graph.remove_edge(pred, child_id, key=key)
        self._graph.add_edge(parent_id, child_id, edge_type=EdgeType.CONTAINS)

    def parent(self, zone_id: str) -> Zone | None:
        for pred in self._graph.predecessors(zone_id):
            for data in self._graph[pred][zone_id].values():
                if data.get("edge_type") == EdgeType.CONTAINS:
                    return self._zones[pred]
        return None

    def children(self, zone_id: str) -> list[Zone]:
        result = []
        for s in self._graph.successors(zone_id):
            for data in self._graph[zone_id][s].values():
                if data.get("edge_type") == EdgeType.CONTAINS:
                    result.append(self._zones[s])
                    break
        return result

    def all_descendants(self, zone_id: str) -> list[Zone]:
        """BFS over containment edges."""
        result = []
        queue = self.children(zone_id)
        while queue:
            z = queue.pop(0)
            result.append(z)
            queue.extend(self.children(z.id))
        return result

    # ------------------------------------------------------------------
    # Adjacency / passage edges
    # ------------------------------------------------------------------

    def add_connection(self, a_id: str, b_id: str, label: str = "") -> None:
        """Add a bidirectional passable connection between two zones."""
        self._assert_exists(a_id)
        self._assert_exists(b_id)
        self._graph.add_edge(a_id, b_id, edge_type=EdgeType.CONNECTS, label=label)
        self._graph.add_edge(b_id, a_id, edge_type=EdgeType.CONNECTS, label=label)

    def connections(self, zone_id: str) -> list[Zone]:
        """Adjacent zones reachable via CONNECTS edges."""
        result = []
        for s in self._graph.successors(zone_id):
            for data in self._graph[zone_id][s].values():
                if data.get("edge_type") == EdgeType.CONNECTS:
                    result.append(self._zones[s])
                    break
        return result

    def neighbors_within(self, zone_id: str, hops: int = 1) -> set[str]:
        """
        Return zone IDs reachable within `hops` CONNECTS steps from zone_id,
        including the starting zone. Used by precondition evaluation for
        'nearby(tag)' style predicates.
        """
        visited = {zone_id}
        frontier = {zone_id}
        for _ in range(hops):
            next_frontier: set[str] = set()
            for fid in frontier:
                for s in self._graph.successors(fid):
                    if s not in visited and any(
                        d.get("edge_type") == EdgeType.CONNECTS
                        for d in self._graph[fid][s].values()
                    ):
                        next_frontier.add(s)
            visited |= next_frontier
            frontier = next_frontier
        return visited

    # ------------------------------------------------------------------
    # Tag queries
    # ------------------------------------------------------------------

    def effective_tags(self, zone_id: str, npc_tag_map: dict[str, set[str]] | None = None) -> set[str]:
        """Effective tags for a single zone (own + features + items + NPCs)."""
        zone = self.get_zone(zone_id)
        return zone.effective_tags(item_registry=self._items, npc_tag_map=npc_tag_map)

    def effective_tags_in_radius(
        self,
        zone_id: str,
        hops: int = 1,
        npc_tag_map: dict[str, set[str]] | None = None,
    ) -> set[str]:
        """Union of effective tags across all zones within `hops` of zone_id."""
        result: set[str] = set()
        for zid in self.neighbors_within(zone_id, hops):
            result |= self.effective_tags(zid, npc_tag_map)
        return result

    def zones_with_tag(self, tag: str, npc_tag_map: dict[str, set[str]] | None = None) -> list[Zone]:
        """All zones whose effective tag set includes `tag`."""
        return [
            self._zones[zid]
            for zid in self._zones
            if tag in self.effective_tags(zid, npc_tag_map)
        ]

    # ------------------------------------------------------------------
    # NPC location helpers
    # ------------------------------------------------------------------

    def npc_location(self, npc_id: str) -> Zone | None:
        """Find the zone currently containing an NPC."""
        for zone in self._zones.values():
            if npc_id in zone.npc_ids:
                return zone
        return None

    def move_npc(self, npc_id: str, to_zone_id: str) -> None:
        self._assert_exists(to_zone_id)
        current = self.npc_location(npc_id)
        if current:
            current.npc_ids.remove(npc_id)
        self._zones[to_zone_id].npc_ids.append(npc_id)

    def place_npc(self, npc_id: str, zone_id: str) -> None:
        self._assert_exists(zone_id)
        self._zones[zone_id].npc_ids.append(npc_id)

    # ------------------------------------------------------------------
    # Item location helpers
    # ------------------------------------------------------------------

    def item_location(self, item_id: str) -> Zone | None:
        for zone in self._zones.values():
            if item_id in zone.item_ids:
                return zone
        return None

    def place_item(self, item_id: str, zone_id: str) -> None:
        self._assert_exists(zone_id)
        if item_id not in self._items:
            raise KeyError(f"Item '{item_id}' not registered")
        self._zones[zone_id].item_ids.append(item_id)

    def move_item(self, item_id: str, to_zone_id: str) -> None:
        self._assert_exists(to_zone_id)
        current = self.item_location(item_id)
        if current:
            current.item_ids.remove(item_id)
        self._zones[to_zone_id].item_ids.append(item_id)

    # ------------------------------------------------------------------
    # Path finding (for NPC navigation)
    # ------------------------------------------------------------------

    def shortest_path(self, from_id: str, to_id: str) -> list[str] | None:
        """
        Shortest path over CONNECTS edges only. Returns list of zone IDs
        including start and end, or None if unreachable.
        """
        connect_graph = nx.DiGraph(
            (u, v)
            for u, v, d in self._graph.edges(data=True)
            if d.get("edge_type") == EdgeType.CONNECTS
        )
        try:
            return nx.shortest_path(connect_graph, from_id, to_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def summary(self, zone_id: str) -> dict:
        """Human-readable summary of a zone for the developer inspector."""
        zone = self.get_zone(zone_id)
        return {
            "id": zone.id,
            "name": zone.name,
            "terrain": zone.terrain_type,
            "tags": sorted(zone.tags),
            "effective_tags": sorted(self.effective_tags(zone_id)),
            "features": [{"name": f.name, "tags": sorted(f.tags)} for f in zone.features],
            "item_count": len(zone.item_ids),
            "npc_ids": list(zone.npc_ids),
            "owner_ids": list(zone.owner_ids),
            "parent": self.parent(zone_id).name if self.parent(zone_id) else None,
            "children": [z.name for z in self.children(zone_id)],
            "connections": [z.name for z in self.connections(zone_id)],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _assert_exists(self, zone_id: str) -> None:
        if zone_id not in self._zones:
            raise KeyError(f"Zone '{zone_id}' not found")
