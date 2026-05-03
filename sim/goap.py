"""
GOAP-lite: heuristic action selection for T2+ NPCs during off-screen ticks.

This is not a full planner. It scores available actions against an NPC's
active goals using keyword/tag overlap, then picks the best candidate.
If the NPC has a goal with `planned_actions`, it executes the first step
of that plan directly (bypassing scoring).
"""
from __future__ import annotations

from affordances.query import ActorContext, what_can_actor_do
from affordances.registry import ActionRegistry
from affordances.schema import Action, ActionCategory
from npc.schema import Goal, NPC
from world.graph import WorldGraph


def _score_action(action: Action, goals: list[Goal]) -> float:
    """
    Score an action against a list of active goals.

    Matching happens on:
      - action.id / action.name words ↔ goal description words
      - action.category hints (crafting if goal mentions 'make'/'craft'/'forge')
    """
    if not goals:
        return 0.0

    action_tokens = set(
        action.id.lower().replace("_", " ").split()
        + action.name.lower().split()
    )
    if action.category == ActionCategory.CRAFTING:
        action_tokens.update({"craft", "make", "forge", "brew", "build", "cook"})
    elif action.category == ActionCategory.GATHERING:
        action_tokens.update({"gather", "collect", "harvest", "fish", "mine"})
    elif action.category == ActionCategory.SOCIAL:
        action_tokens.update({"talk", "trade", "teach", "ask", "tell"})

    best = 0.0
    for goal in goals:
        goal_tokens = set(goal.description.lower().split())
        overlap = len(action_tokens & goal_tokens)
        weight = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(str(goal.priority), 1.0)
        best = max(best, overlap * weight)
    return best


def select_action(
    npc: NPC,
    zone_id: str,
    graph: WorldGraph,
    registry: ActionRegistry,
    npc_tag_map: dict[str, set[str]] | None = None,
) -> Action | None:
    """
    Pick the best action for an NPC to take in a zone, given their active goals.

    Returns None if no actions are available or no goal score > 0.
    """
    active_goals = npc.active_goals()

    # If a goal already has a planned action chain, execute the first step
    for goal in active_goals:
        if goal.planned_actions:
            action_id = goal.planned_actions[0]
            action = registry.get_or_none(action_id)
            if action is not None:
                return action

    actor_ctx = npc.as_actor_context(graph=graph)
    available = what_can_actor_do(
        actor_ctx, zone_id, graph, registry, npc_tag_map=npc_tag_map
    )
    if not available:
        return None

    # If no goals, pick at random from crafting/gathering (stochastic fallback)
    if not active_goals:
        productive = [
            a for a in available
            if a.category in (ActionCategory.CRAFTING, ActionCategory.GATHERING)
        ]
        if not productive:
            return None
        import random
        return random.choice(productive)

    scored = [(a, _score_action(a, active_goals)) for a in available]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_action, best_score = scored[0]
    return best_action if best_score > 0 else None
