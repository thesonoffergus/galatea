"""
Execute a single affordance action for an NPC during an off-screen tick.

Applies ProducesEffect, ConsumesEffect, AdvancesSkillEffect, and
MovesActorEffect. Social and parametric effects are skipped at MVP.
Returns a summary dict for event logging.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from affordances.schema import (
    Action,
    AdvancesSkillEffect,
    ConsumesEffect,
    MovesActorEffect,
    ProducesEffect,
)
from crafting.quality import QualityInputs, compute_quality
from npc.schema import NPC
from world.graph import WorldGraph
from world.zone import Item


@dataclass
class ExecutionResult:
    action_id: str
    npc_id: str
    success: bool
    produced: list[str] = field(default_factory=list)    # item_type strings
    consumed: list[str] = field(default_factory=list)
    skill_advanced: str | None = None
    moved_to: str | None = None
    notes: str = ""


def execute_action(
    npc: NPC,
    action: Action,
    graph: WorldGraph,
) -> ExecutionResult:
    """
    Apply an action's effects to the NPC and world graph.

    Simplified for off-screen use:
    - ProducesEffect → creates an Item in the NPC's current zone
    - ConsumesEffect → removes carried items (from_actor=True) or zone items (False)
    - AdvancesSkillEffect → increments NPC skill (capped at 1.0)
    - MovesActorEffect → moves NPC to target zone
    - TeachesRecipeEffect, RelationshipEffect, NoiseEffect → ignored at this tier
    """
    result = ExecutionResult(
        action_id=action.id,
        npc_id=npc.id,
        success=True,
    )
    zone_id = npc.current_zone_id

    for effect in action.effects:
        match effect:
            case ProducesEffect(item_type=item_type, quantity=qty):
                skill_val = _dominant_skill(npc, action)
                inputs = QualityInputs(character_skill=skill_val)
                for _ in range(qty):
                    quality = compute_quality(inputs)
                    item = Item(
                        id=f"item_{npc.id[:6]}_{action.id[:8]}_{random.randint(1000, 9999)}",
                        name=item_type.replace("_", " ").title(),
                        item_type=item_type,
                        quality=quality,
                        owner_id=npc.id,
                    )
                    graph.add_item(item)
                    if zone_id:
                        try:
                            graph.place_item(item.id, zone_id)
                        except (KeyError, ValueError):
                            pass
                    result.produced.append(item_type)

            case ConsumesEffect(item_type=item_type, quantity=qty, from_actor=from_actor):
                if from_actor:
                    _remove_carried(npc, item_type, qty, graph)
                else:
                    _remove_zone_item(graph, zone_id, item_type, qty)
                result.consumed.append(item_type)

            case AdvancesSkillEffect(skill=skill, amount=amount):
                current = npc.skills.get(skill, 0.0)
                npc.skills[skill] = min(1.0, current + amount)
                result.skill_advanced = skill

            case MovesActorEffect(to_zone=to_zone):
                if to_zone.startswith("$"):
                    pass  # parametric — skip at off-screen fidelity
                else:
                    try:
                        graph.move_npc(npc.id, to_zone)
                        npc.current_zone_id = to_zone
                        result.moved_to = to_zone
                    except (KeyError, ValueError):
                        pass

    return result


def _dominant_skill(npc: NPC, action: Action) -> float:
    """Heuristic: return the NPC's best relevant skill for quality computation."""
    if not npc.skills:
        return 0.5
    return max(npc.skills.values())


def _remove_carried(npc: NPC, item_type: str, qty: int, graph: WorldGraph) -> None:
    removed = 0
    for item_id in list(npc.carried_item_ids):
        if removed >= qty:
            break
        item = graph.get_item(item_id)
        if item and item.item_type == item_type:
            npc.carried_item_ids.remove(item_id)
            graph.remove_item(item_id)
            removed += 1


def _remove_zone_item(
    graph: WorldGraph, zone_id: str | None, item_type: str, qty: int
) -> None:
    if not zone_id:
        return
    try:
        zone = graph.get_zone(zone_id)
    except KeyError:
        return
    removed = 0
    for item_id in list(zone.item_ids):
        if removed >= qty:
            break
        item = graph.get_item(item_id)
        if item and item.item_type == item_type:
            graph.remove_item(item_id)
            removed += 1
