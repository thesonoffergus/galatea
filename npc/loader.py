"""
Load NPCs from a world seed YAML file.

Reads the `npcs:` section of the same file used by world/loader.py.
Returns an NPCRegistry with all NPCs populated, and a placement map
{npc_id: zone_id} so the caller can wire them into a WorldGraph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crafting.recipes import RecipeSource, RecipeStore
from npc.schema import BigFive, Goal, GoalPriority, NPC, NPCTier, PhysicalTraits, Relationship
from npc.registry import NPCRegistry
from world.graph import WorldGraph


def load_npcs(
    seed_path: Path | str,
    graph: WorldGraph | None = None,
) -> tuple[NPCRegistry, dict[str, str]]:
    """
    Parse the `npcs:` section of a seed YAML file.

    Returns:
        (registry, placements) where placements is {npc_id: zone_id}.
        If `graph` is provided, NPCs are placed into it immediately and
        their current_zone_id is set. Otherwise, placement is deferred.
    """
    data = yaml.safe_load(Path(seed_path).read_text())
    registry = NPCRegistry()
    placements: dict[str, str] = {}

    for rec in data.get("npcs", []):
        npc = _npc_from_record(rec)
        registry.register(npc)
        if zone_id := rec.get("starting_zone"):
            placements[npc.id] = zone_id

    if graph is not None:
        registry.place_all_in_world(graph, placements)

    return registry, placements


def _npc_from_record(rec: dict[str, Any]) -> NPC:
    tier_raw = rec.get("tier", 1)
    tier = NPCTier(int(tier_raw))

    big_five_raw = rec.get("big_five", {})
    big_five = BigFive(**big_five_raw) if big_five_raw else BigFive()

    physical_raw = rec.get("physical", {})
    physical = PhysicalTraits(**physical_raw) if physical_raw else PhysicalTraits()

    known_recipes = RecipeStore.from_id_list(
        rec.get("known_recipes", []),
        source=RecipeSource.INNATE,
    )

    skills_raw = rec.get("skills", {})
    skills = {k: float(v) for k, v in skills_raw.items()}

    goals_raw = rec.get("goals", [])
    goals = [_goal_from_record(g) for g in goals_raw]

    relationships_raw = rec.get("relationships", [])
    relationships: dict[str, Relationship] = {}
    for r in relationships_raw:
        rel = Relationship(
            other_id=r["other_id"],
            affinity=float(r.get("affinity", 0.0)),
            trust=float(r.get("trust", 0.3)),
            familiarity=float(r.get("familiarity", 0.0)),
            tags=set(r.get("tags", [])),
        )
        relationships[rel.other_id] = rel

    return NPC(
        id=rec["id"],
        name=rec["name"],
        role=rec.get("role", "Villager"),
        description=rec.get("description", ""),
        is_player=bool(rec.get("is_player", False)),
        tier=tier,
        big_five=big_five,
        trait_tags=list(rec.get("trait_tags", [])),
        skills=skills,
        known_recipes=known_recipes,
        values=list(rec.get("values", [])),
        goals=goals,
        relationships=relationships,
        physical=physical,
    )


def _goal_from_record(rec: dict[str, Any]) -> Goal:
    priority_raw = rec.get("priority", "medium")
    try:
        priority = GoalPriority(priority_raw)
    except ValueError:
        priority = GoalPriority.MEDIUM
    return Goal(
        description=rec["description"],
        priority=priority,
    )
