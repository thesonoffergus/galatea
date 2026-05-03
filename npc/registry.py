"""
NPCRegistry — in-memory store of all NPCs in the simulation.

Provides lookup by ID, tier, role, and zone (via the world graph).
The registry is the authoritative source for NPC objects; the world graph
tracks spatial placement (which zone each NPC occupies) but holds only IDs.
"""

from __future__ import annotations

from typing import Iterator, Optional

from npc.schema import NPC, NPCTier
from world.graph import WorldGraph


class NPCRegistry:
    def __init__(self) -> None:
        self._npcs: dict[str, NPC] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, npc: NPC) -> None:
        if npc.id in self._npcs:
            raise ValueError(f"NPC '{npc.id}' already registered")
        self._npcs[npc.id] = npc

    def __iter__(self) -> Iterator[NPC]:
        return iter(self._npcs.values())

    def __len__(self) -> int:
        return len(self._npcs)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, npc_id: str) -> NPC:
        try:
            return self._npcs[npc_id]
        except KeyError:
            raise KeyError(f"NPC '{npc_id}' not found")

    def get_or_none(self, npc_id: str) -> Optional[NPC]:
        return self._npcs.get(npc_id)

    def all_npcs(self) -> list[NPC]:
        return list(self._npcs.values())

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------

    def by_tier(self, tier: NPCTier) -> list[NPC]:
        return [n for n in self._npcs.values() if n.tier == tier]

    def by_tier_min(self, min_tier: NPCTier) -> list[NPC]:
        """NPCs at or above a given tier."""
        return [n for n in self._npcs.values() if n.tier >= min_tier]

    def by_role(self, role: str) -> list[NPC]:
        return [n for n in self._npcs.values() if n.role.lower() == role.lower()]

    def player(self) -> Optional[NPC]:
        for npc in self._npcs.values():
            if npc.is_player:
                return npc
        return None

    def npcs_in_zone(self, zone_id: str, graph: WorldGraph) -> list[NPC]:
        """Resolve NPC IDs in a zone back to full NPC objects."""
        zone = graph.get_zone(zone_id)
        return [
            self._npcs[nid]
            for nid in zone.npc_ids
            if nid in self._npcs
        ]

    # ------------------------------------------------------------------
    # Tag map (for zone effective_tag computation)
    # ------------------------------------------------------------------

    def build_npc_tag_map(self) -> dict[str, set[str]]:
        """
        Returns a dict mapping each NPC ID to its effective_tags().
        Pass this to WorldGraph.effective_tags() as `npc_tag_map`.
        """
        return {npc.id: npc.effective_tags() for npc in self._npcs.values()}

    # ------------------------------------------------------------------
    # World placement
    # ------------------------------------------------------------------

    def place_all_in_world(self, graph: WorldGraph, placements: dict[str, str]) -> None:
        """
        Place NPCs into starting zones.
        `placements` is a dict of {npc_id: zone_id}.
        """
        for npc_id, zone_id in placements.items():
            npc = self.get(npc_id)
            graph.place_npc(npc_id, zone_id)
            npc.current_zone_id = zone_id
