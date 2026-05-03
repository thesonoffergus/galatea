"""Load seed memories and community KB entries from YAML into a MemoryStore."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from knowledge.community_kb import KBEntry
from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore
from npc.registry import NPCRegistry


def load_memory_store(seed_path: Path, npc_registry: NPCRegistry) -> MemoryStore:
    store = MemoryStore()

    # Register all NPCs at their correct tier capacity
    for npc in npc_registry.all_npcs():
        if not npc.is_player:
            store.register_npc(npc.id, npc.tier)

    raw: dict[str, Any] = yaml.safe_load(seed_path.read_text())

    # Load community KB entries
    for entry_data in raw.get("community_kb", []):
        entry = KBEntry(
            content=entry_data["content"],
            topic_tags=set(entry_data.get("topic_tags", [])),
            involved_npc_ids=set(entry_data.get("involved_npc_ids", [])),
            involved_zone_id=entry_data.get("involved_zone_id"),
            source_npc_id=entry_data.get("source_npc_id"),
            gossip_weight=float(entry_data.get("gossip_weight", 1.0)),
        )
        store.community_kb.add(entry)

    # Load per-NPC seed memories
    for npc_data in raw.get("npcs", []):
        npc_id = npc_data["id"]
        for mem_data in npc_data.get("memories", []):
            entry = MemoryEntry(
                npc_id=npc_id,
                content=mem_data["content"],
                salience=float(mem_data.get("salience", 1.0)),
                topic_tags=set(mem_data.get("topic_tags", [])),
                involved_npc_ids=set(mem_data.get("involved_npc_ids", [])),
                involved_zone_id=mem_data.get("involved_zone_id"),
                source=mem_data.get("source", "seeded"),
            )
            store.get(npc_id).add(entry)

    return store
