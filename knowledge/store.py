"""Central registry for all NPC memories and the community KB."""
from __future__ import annotations

from knowledge.community_kb import CommunityKB
from knowledge.memory import TIER_MAX_ENTRIES, IndividualMemory


class MemoryStore:
    """
    Holds one IndividualMemory per NPC and a single CommunityKB.

    NPCs are registered lazily — accessing an unknown npc_id creates
    an empty IndividualMemory with max_entries=0 (effectively T0).
    Call register_npc() explicitly during load to set the correct tier.
    """

    def __init__(self) -> None:
        self._memories: dict[str, IndividualMemory] = {}
        self.community_kb: CommunityKB = CommunityKB()

    def register_npc(self, npc_id: str, tier: int) -> IndividualMemory:
        max_entries = TIER_MAX_ENTRIES.get(tier, 0)
        mem = IndividualMemory(npc_id=npc_id, max_entries=max_entries)
        self._memories[npc_id] = mem
        return mem

    def get(self, npc_id: str) -> IndividualMemory:
        if npc_id not in self._memories:
            self._memories[npc_id] = IndividualMemory(npc_id=npc_id, max_entries=0)
        return self._memories[npc_id]

    def all_npc_ids(self) -> list[str]:
        return list(self._memories.keys())

    def __contains__(self, npc_id: str) -> bool:
        return npc_id in self._memories
