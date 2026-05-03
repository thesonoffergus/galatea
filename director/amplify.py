"""
Amplification primitives for the director.

These functions are the director's hands. They are exposed and functional
now; the director stub simply doesn't call them yet. Any code — including
developer tooling — can call them directly.

Three primitives:
  1. set_memory_salience  — make a specific memory survive eviction and
                            float higher in RAG retrieval.
  2. boost_kb_entry       — increase a community KB entry's gossip_weight,
                            making it appear more in dialogue prompts.
  3. nudge_goal           — inject a short-term directional goal into an
                            NPC's active goal list, steering dialogue and
                            (later) GOAP planning.
"""
from __future__ import annotations

from knowledge.community_kb import CommunityKB
from knowledge.store import MemoryStore
from npc.schema import Goal, GoalPriority, NPC


def set_memory_salience(
    store: MemoryStore,
    npc_id: str,
    memory_id: str,
    salience: float,
) -> bool:
    """
    Set the salience of a specific memory entry.

    Higher salience → survives eviction longer, floats higher in retrieval.
    Returns True if the memory was found and updated.
    """
    mem = store.get(npc_id)
    for entry in mem.all_entries():
        if entry.id == memory_id:
            entry.salience = max(0.0, salience)
            return True
    return False


def boost_kb_entry(
    kb: CommunityKB,
    entry_id: str,
    gossip_weight: float,
) -> bool:
    """
    Set the gossip_weight on a community KB entry.

    Higher weight → appears more frequently in NPC dialogue prompts via
    RAG retrieval scoring. Returns True if found and updated.
    """
    for entry in kb.all_entries():
        if entry.id == entry_id:
            entry.gossip_weight = max(0.0, gossip_weight)
            return True
    return False


def nudge_goal(
    npc: NPC,
    description: str,
    priority: GoalPriority = GoalPriority.HIGH,
) -> Goal:
    """
    Inject a short-term directional goal into an NPC's active goal list.

    The goal appears in the IDENTITY block of the system prompt, steering
    what the NPC volunteers in dialogue. It also feeds the GOAP planner
    when that is active (step 14).

    The caller is responsible for marking the goal completed or abandoned
    once the director's intention has been served.
    """
    return npc.add_goal(description, priority=priority)


def clear_nudged_goals(npc: NPC) -> int:
    """
    Remove all active goals that were likely nudged (heuristic: added after
    seed load — no planned_actions, HIGH priority).

    Returns the number of goals removed.
    """
    from npc.schema import GoalStatus
    removed = 0
    for goal in list(npc.goals):
        if (
            goal.status == GoalStatus.ACTIVE
            and goal.priority == GoalPriority.HIGH
            and not goal.planned_actions
        ):
            goal.status = GoalStatus.ABANDONED
            removed += 1
    return removed
