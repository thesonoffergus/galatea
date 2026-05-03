"""
Affordance query primitives — the two core queries the whole system builds on:

  1. what_can_actor_do(actor, zone_id, graph, registry)
     → actions whose full preconditions (zone + actor) are satisfied

  2. where_can_action_be_done(action, graph)
     → zones whose zone-side preconditions are satisfied, ignoring actor clauses

Actor-specific preconditions (skill, inventory, known recipes) are skipped in
query 2 — the caller assumes a qualified actor. This is intentional: the
question "where can a sword be smithed?" has a zone-only answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from affordances.schema import (
    Action,
    ActorHasItemPrecondition,
    ActorKnowsRecipePrecondition,
    ActorSkillPrecondition,
    AndPrecondition,
    NotPrecondition,
    NpcPresentPrecondition,
    NearbyTagPrecondition,
    OrPrecondition,
    Precondition,
    ZoneHasItemPrecondition,
    ZoneHasTagPrecondition,
    ZoneIsAccessiblePrecondition,
)
from affordances.registry import ActionRegistry
from world.graph import WorldGraph
from world.zone import Zone


# ── Evaluation context ────────────────────────────────────────────────────────


@dataclass
class ActorContext:
    """
    Lightweight actor snapshot used for precondition evaluation.
    The full NPC schema (step 4) will satisfy this interface — nothing here
    should need to change when NPCs are wired in.
    """
    actor_id: str
    skills: dict[str, float] = field(default_factory=dict)
    known_recipes: set[str] = field(default_factory=set)
    inventory: dict[str, int] = field(default_factory=dict)  # item_type → quantity
    role_tags: set[str] = field(default_factory=set)


@dataclass
class EvalContext:
    """Full context for precondition evaluation (actor + zone + graph)."""
    zone_id: str
    graph: WorldGraph
    actor: ActorContext | None = None   # None → zone-only query (skip actor clauses)
    nearby_hops: int = 1
    # Maps npc_id → set of tags (role_tags + trait tags) for NpcPresentPrecondition.
    # Built from NPCRegistry.build_npc_tag_map(); may be None if registry not available.
    npc_tag_map: dict[str, set[str]] | None = None


# ── Core evaluator ────────────────────────────────────────────────────────────


def evaluate_precondition(precond: Precondition, ctx: EvalContext) -> bool:
    """
    Evaluate a single precondition against the given context.
    When ctx.actor is None (zone-only mode), actor-specific predicates
    return True unconditionally so zone-side filtering still applies.
    """
    match precond:
        case NearbyTagPrecondition(tag=tag, hops=hops):
            return tag in ctx.graph.effective_tags_in_radius(ctx.zone_id, hops)

        case ZoneHasTagPrecondition(tag=tag):
            return tag in ctx.graph.effective_tags(ctx.zone_id)

        case ActorHasItemPrecondition(item_type=item_type, quantity=qty):
            if ctx.actor is None:
                return True
            return ctx.actor.inventory.get(item_type, 0) >= qty

        case ZoneHasItemPrecondition(item_type=item_type, quantity=qty):
            zone = ctx.graph.get_zone(ctx.zone_id)
            count = sum(
                1
                for iid in zone.item_ids
                if (item := ctx.graph.get_item(iid)) and item.item_type == item_type
            )
            return count >= qty

        case ActorSkillPrecondition(skill=skill, min_value=min_val):
            if ctx.actor is None:
                return True
            return ctx.actor.skills.get(skill, 0.0) >= min_val

        case ActorKnowsRecipePrecondition(recipe_id=recipe_id):
            if ctx.actor is None:
                return True
            return recipe_id in ctx.actor.known_recipes

        case NpcPresentPrecondition(role=role):
            zone = ctx.graph.get_zone(ctx.zone_id)
            others = [
                n for n in zone.npc_ids
                if ctx.actor is None or n != ctx.actor.actor_id
            ]
            if not others:
                return False
            if role is None:
                return True
            # Check whether any present NPC carries the required role tag.
            # npc_tag_map is populated from NPCRegistry.build_npc_tag_map().
            if ctx.npc_tag_map is not None:
                return any(
                    role in ctx.npc_tag_map.get(nid, set())
                    for nid in others
                )
            # No tag map available — fall back to True (any NPC satisfies)
            return True

        case ZoneIsAccessiblePrecondition():
            zone = ctx.graph.get_zone(ctx.zone_id)
            return "locked" not in zone.tags

        case AndPrecondition(conditions=conditions):
            return all(evaluate_precondition(c, ctx) for c in conditions)

        case OrPrecondition(conditions=conditions):
            return any(evaluate_precondition(c, ctx) for c in conditions)

        case NotPrecondition(condition=condition):
            return not evaluate_precondition(condition, ctx)

    # Unknown precondition type — fail safe (deny)
    return False


# ── Public query API ──────────────────────────────────────────────────────────


def what_can_actor_do(
    actor: ActorContext,
    zone_id: str,
    graph: WorldGraph,
    registry: ActionRegistry,
    nearby_hops: int = 1,
    npc_tag_map: dict[str, set[str]] | None = None,
) -> list[Action]:
    """
    Query 1: What can actor A do here, now?

    Returns all actions in the registry whose preconditions are satisfied
    by the actor's current state and the zone's current contents.
    Parametric actions are included if their zone/actor requirements are met —
    the caller is responsible for binding parameter values.

    Pass `npc_tag_map` (from NPCRegistry.build_npc_tag_map()) to enable
    role-based NpcPresentPrecondition filtering.
    """
    ctx = EvalContext(
        zone_id=zone_id,
        graph=graph,
        actor=actor,
        nearby_hops=nearby_hops,
        npc_tag_map=npc_tag_map,
    )
    return [
        action
        for action in registry
        if evaluate_precondition(action.preconditions, ctx)
    ]


def where_can_action_be_done(
    action: Action,
    graph: WorldGraph,
    nearby_hops: int = 1,
) -> list[Zone]:
    """
    Query 2: Where can action X be performed?

    Returns zones whose zone-side preconditions are satisfied.
    Actor-specific predicates (skill, inventory, known recipes) are ignored —
    this answers the navigation question "where is the right place?"
    without filtering on actor capability.
    """
    results = []
    for zone in graph.zones():
        ctx = EvalContext(
            zone_id=zone.id,
            graph=graph,
            actor=None,  # zone-only mode
            nearby_hops=nearby_hops,
        )
        if evaluate_precondition(action.preconditions, ctx):
            results.append(zone)
    return results


def actions_available_in_zone(
    zone_id: str,
    graph: WorldGraph,
    registry: ActionRegistry,
    nearby_hops: int = 1,
) -> list[Action]:
    """
    Zone-only variant: which actions are possible in this zone regardless of
    who's there? Useful for the world inspector and affordance digest in
    NPC prompt composition.
    """
    ctx = EvalContext(
        zone_id=zone_id,
        graph=graph,
        actor=None,
        nearby_hops=nearby_hops,
    )
    return [
        action
        for action in registry
        if evaluate_precondition(action.preconditions, ctx)
    ]
