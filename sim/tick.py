"""
Off-screen simulation tick.

One tick represents a unit of simulation time (e.g. one in-game hour).
Tier governs fidelity:
  T0 — skipped (no tick)
  T1 — stochastic: small chance of crafting/gathering; relationship drift
  T2 — GOAP-lite: goal-driven action selection over affordances
  T3 — same as T2 (full LLM scene simulation is out of scope at MVP)

Inter-NPC interactions: stochastic relationship drift and information
propagation (memories leak into community KB with low probability).
No dialogue content is generated for off-screen interactions.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from affordances.registry import ActionRegistry
from config import settings
from director.director import director
from events.log import EventSeverity, EventType, NPCRole, event_log
from knowledge.community_kb import KBEntry
from knowledge.memory import MemoryEntry
from knowledge.store import MemoryStore
from npc.registry import NPCRegistry
from npc.schema import NPC, NPCTier
from sim.action_executor import ExecutionResult, execute_action
from sim.goap import select_action
from world.graph import WorldGraph


# ── Tick parameters (driven by config) ───────────────────────────────────────

T1_ACTION_PROBABILITY = settings.sim.t1_action_probability
GOSSIP_PROBABILITY    = settings.sim.gossip_probability
REL_DRIFT_MAGNITUDE   = settings.sim.rel_drift_magnitude


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class NpcTickResult:
    npc_id: str
    action_result: ExecutionResult | None = None
    gossiped: bool = False
    relationships_drifted: int = 0


@dataclass
class TickResult:
    tick_number: int
    npc_results: list[NpcTickResult] = field(default_factory=list)

    @property
    def actions_taken(self) -> int:
        return sum(1 for r in self.npc_results if r.action_result is not None)

    @property
    def gossip_events(self) -> int:
        return sum(1 for r in self.npc_results if r.gossiped)


# ── Module-level tick counter ─────────────────────────────────────────────────

_tick_count = 0


def current_tick() -> int:
    return _tick_count


def tick(
    registry: NPCRegistry,
    graph: WorldGraph,
    action_registry: ActionRegistry,
    memory_store: MemoryStore,
) -> TickResult:
    """Advance simulation by one tick. Returns a summary of what happened."""
    global _tick_count
    _tick_count += 1

    npc_tag_map = registry.build_npc_tag_map()
    result = TickResult(tick_number=_tick_count)

    for npc in registry.all_npcs():
        if npc.is_player or npc.tier == NPCTier.T0:
            continue

        npc_result = NpcTickResult(npc_id=npc.id)

        # ── Action phase ──────────────────────────────────────────────────
        if npc.tier == NPCTier.T1:
            if random.random() < T1_ACTION_PROBABILITY:
                npc_result.action_result = _try_act(
                    npc, graph, action_registry, npc_tag_map
                )
        else:
            # T2+ — goal-driven
            npc_result.action_result = _try_act(
                npc, graph, action_registry, npc_tag_map
            )

        # ── Gossip phase ──────────────────────────────────────────────────
        if random.random() < GOSSIP_PROBABILITY:
            gossiped = _maybe_gossip(npc, memory_store)
            npc_result.gossiped = gossiped

        # ── Relationship drift ────────────────────────────────────────────
        drifted = _drift_relationships(npc)
        npc_result.relationships_drifted = drifted

        result.npc_results.append(npc_result)

    # ── Emit summary event ────────────────────────────────────────────────
    event_log.emit(
        EventType.GENERIC,
        f"Tick {_tick_count}: {result.actions_taken} actions, "
        f"{result.gossip_events} gossip events.",
        severity=EventSeverity.TRIVIAL,
        tags={"tick", "sim"},
        payload={
            "tick": _tick_count,
            "actions": result.actions_taken,
            "gossip": result.gossip_events,
        },
    )

    # ── Director gets a look ──────────────────────────────────────────────
    director.tick(event_log)

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_act(
    npc: NPC,
    graph: WorldGraph,
    action_registry: ActionRegistry,
    npc_tag_map: dict[str, set[str]],
) -> ExecutionResult | None:
    if not npc.current_zone_id:
        return None
    action = select_action(npc, npc.current_zone_id, graph, action_registry, npc_tag_map)
    if action is None:
        return None

    exec_result = execute_action(npc, action, graph)

    # Emit event
    event_type = (
        EventType.CRAFT_SUCCESS if exec_result.produced else EventType.GATHER
    )
    tags = {"off_screen", "sim", f"npc:{npc.id}"}
    if exec_result.produced:
        tags.update(exec_result.produced)

    event_log.emit(
        event_type,
        f"{npc.name} performed {action.name}."
        + (f" Produced: {', '.join(exec_result.produced)}." if exec_result.produced else ""),
        npc_roles=[NPCRole(npc_id=npc.id, role="actor")],
        zone_id=npc.current_zone_id,
        severity=EventSeverity.TRIVIAL,
        tags=tags,
        payload={
            "action": action.id,
            "produced": exec_result.produced,
            "consumed": exec_result.consumed,
        },
    )
    return exec_result


def _maybe_gossip(npc: NPC, memory_store: MemoryStore) -> bool:
    """
    Chance that the NPC's most salient memory leaks into the community KB.
    Returns True if something was propagated.
    """
    mem = memory_store.get(npc.id)
    entries = mem.all_entries()
    if not entries:
        return False

    # Pick the most salient memory
    best = max(entries, key=lambda e: e.salience)

    # Only propagate if salience is high enough to be "worth sharing"
    if best.salience < 1.5:
        return False

    community = memory_store.community_kb
    # Avoid exact duplicates
    existing_contents = {e.content for e in community.all_entries()}
    if best.content in existing_contents:
        return False

    kb_entry = KBEntry(
        content=best.content,
        topic_tags=set(best.topic_tags),
        involved_npc_ids=set(best.involved_npc_ids),
        involved_zone_id=best.involved_zone_id,
        source_npc_id=npc.id,
        gossip_weight=best.salience * 0.5,  # derived from memory salience
    )
    community.add(kb_entry)

    event_log.emit(
        EventType.GENERIC,
        f'{npc.name} shared knowledge: "{best.content[:60]}..."',
        npc_roles=[NPCRole(npc_id=npc.id, role="actor")],
        zone_id=npc.current_zone_id,
        severity=EventSeverity.TRIVIAL,
        tags={"gossip", "knowledge_propagation", f"npc:{npc.id}"},
    )
    return True


def _drift_relationships(npc: NPC) -> int:
    """Apply a tiny random walk to all of the NPC's relationships."""
    drifted = 0
    for rel in npc.relationships.values():
        delta = random.uniform(-REL_DRIFT_MAGNITUDE, REL_DRIFT_MAGNITUDE)
        rel.affinity = max(-1.0, min(1.0, rel.affinity + delta))
        drifted += 1
    return drifted


def reset_tick_count() -> None:
    """Test helper — resets the module-level counter."""
    global _tick_count
    _tick_count = 0
