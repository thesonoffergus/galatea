"""
One handler function per client message type.

Handlers are thin: they call into existing Galatea APIs and return
a JSON-serializable dict. No simulation logic lives here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from affordances.query import what_can_actor_do
from dialogue.engine import DialogueEngine
from dialogue.prompt_builder import DialogueContext
from dialogue.session import DialogueSession, DialogueTurn
from events.log import EventSeverity, EventType, NPCRole, event_log
from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
from llm.runner import LLMRunner
from npc.schema import NPCTier
from server.serializers import (
    serialize_full_state,
    serialize_npc,
    serialize_player,
    serialize_tick_result,
    serialize_zone,
    _game_time,
)
from sim.tick import current_tick, tick
from tools.state import AppState

log = logging.getLogger(__name__)


# ── connect ───────────────────────────────────────────────────────────────────

def handle_connect(state: AppState) -> dict:
    return serialize_full_state(state)


# ── player_move ───────────────────────────────────────────────────────────────

def handle_player_move(state: AppState, data: dict) -> dict:
    zone_id: str = data.get("zone_id", "")
    player = state.npc_registry.player()
    if player is None:
        return {"type": "move_result", "success": False, "reason": "no player"}
    try:
        state.graph.get_zone(zone_id)
    except KeyError:
        return {"type": "move_result", "success": False, "reason": f"unknown zone {zone_id!r}"}

    current_connections = {z.id for z in state.graph.connections(player.current_zone_id or "")}
    if zone_id not in current_connections:
        return {"type": "move_result", "success": False, "reason": "zone not adjacent"}

    state.graph.move_npc(player.id, zone_id)
    player.current_zone_id = zone_id
    event_log.emit(
        EventType.MOVE,
        f"{player.name} moved to {state.graph.get_zone(zone_id).name}.",
        npc_roles=[NPCRole(npc_id=player.id, role="actor")],
        zone_id=zone_id,
        severity=EventSeverity.TRIVIAL,
        tags={"player", "move"},
    )
    return {
        "type": "move_result",
        "success": True,
        "zone_id": zone_id,
        "zone_data": serialize_zone(zone_id, state),
    }


# ── player_interact ───────────────────────────────────────────────────────────

def handle_player_interact(
    state: AppState,
    data: dict,
    sessions: dict[str, DialogueSession],
    runner: LLMRunner,
) -> dict:
    npc_id: str = data.get("npc_id", "")
    npc = state.npc_registry.get_or_none(npc_id)
    if npc is None or npc.tier == NPCTier.T0:
        return {"type": "error", "reason": f"NPC {npc_id!r} not found or T0"}

    player = state.npc_registry.player()
    zone = state.graph.get_zone(npc.current_zone_id or "")
    zone_npcs = state.npc_registry.npcs_in_zone(zone.id, state.graph)
    actions = what_can_actor_do(
        actor=npc.as_actor_context(state.graph),
        zone_id=zone.id,
        graph=state.graph,
        registry=state.action_registry,
    )
    excerpts = retrieve_for_prompt(
        state.memory_store,
        npc.id,
        RetrievalQuery(
            involved_npc_ids={player.id} if player else set(),
            involved_zone_id=zone.id,
        ),
    )
    ctx = DialogueContext(
        npc=npc,
        player=player,
        zone=zone,
        zone_npcs=[n for n in zone_npcs if n.id not in (npc.id, (player.id if player else ""))],
        available_actions=actions,
        memory_excerpts=[e.content for e in excerpts.individual + excerpts.community],
    )
    session = DialogueSession(
        npc_id=npc.id,
        player_id=player.id if player else "player",
        zone_id=zone.id,
    )
    sessions[npc_id] = session
    engine = DialogueEngine(runner=runner)

    # Generate a greeting (empty player input triggers NPC to open)
    turn = engine.player_turn(session, "Hello.", ctx)
    event_log.emit(
        EventType.DIALOGUE,
        f"Player started dialogue with {npc.name}.",
        npc_roles=[NPCRole(npc_id=npc.id, role="subject")],
        zone_id=zone.id,
        severity=EventSeverity.MINOR,
        tags={"dialogue", "player"},
    )
    return {
        "type": "dialogue_start",
        "npc_id": npc.id,
        "npc_name": npc.name,
        "greeting": turn.npc_response,
        "menu_options": turn.menu_options,
    }


# ── dialogue_input ────────────────────────────────────────────────────────────

def handle_dialogue_input(
    state: AppState,
    data: dict,
    sessions: dict[str, DialogueSession],
    runner: LLMRunner,
) -> dict:
    npc_id: str = data.get("npc_id", "")
    player_input: str = data.get("input", "")
    session = sessions.get(npc_id)
    if session is None:
        return {"type": "error", "reason": "no active dialogue session"}

    npc = state.npc_registry.get_or_none(npc_id)
    if npc is None:
        return {"type": "error", "reason": f"NPC {npc_id!r} not found"}

    player = state.npc_registry.player()
    zone = state.graph.get_zone(npc.current_zone_id or "")
    zone_npcs = state.npc_registry.npcs_in_zone(zone.id, state.graph)
    actions = what_can_actor_do(
        actor=npc.as_actor_context(state.graph),
        zone_id=zone.id,
        graph=state.graph,
        registry=state.action_registry,
    )
    excerpts = retrieve_for_prompt(
        state.memory_store,
        npc.id,
        RetrievalQuery(
            involved_npc_ids={player.id} if player else set(),
            involved_zone_id=zone.id,
        ),
    )
    ctx = DialogueContext(
        npc=npc,
        player=player,
        zone=zone,
        zone_npcs=[n for n in zone_npcs if n.id not in (npc.id, (player.id if player else ""))],
        available_actions=actions,
        memory_excerpts=[e.content for e in excerpts.individual + excerpts.community],
    )
    engine = DialogueEngine(runner=runner)
    turn = engine.player_turn(session, player_input, ctx)
    return {
        "type": "dialogue_response",
        "npc_response": turn.npc_response,
        "menu_options": turn.menu_options,
    }


# ── dialogue_end ──────────────────────────────────────────────────────────────

def handle_dialogue_end(
    state: AppState,
    data: dict,
    sessions: dict[str, DialogueSession],
) -> dict:
    npc_id: str = data.get("npc_id", "")
    sessions.pop(npc_id, None)
    return {"type": "dialogue_ended", "npc_id": npc_id}


# ── get_affordances ───────────────────────────────────────────────────────────

def handle_get_affordances(state: AppState) -> dict:
    player = state.npc_registry.player()
    if player is None or player.current_zone_id is None:
        return {"type": "affordance_list", "actions": []}
    actions = what_can_actor_do(
        actor=player.as_actor_context(state.graph),
        zone_id=player.current_zone_id,
        graph=state.graph,
        registry=state.action_registry,
        npc_tag_map=state.npc_registry.build_npc_tag_map(),
    )
    return {
        "type": "affordance_list",
        "actions": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "category": str(a.category),
            }
            for a in actions
        ],
    }


# ── execute_action ────────────────────────────────────────────────────────────

def handle_execute_action(state: AppState, data: dict) -> dict:
    from sim.action_executor import execute_action

    action_id: str = data.get("action_id", "")
    player = state.npc_registry.player()
    if player is None:
        return {"type": "action_result", "success": False, "reason": "no player"}
    action = state.action_registry.get_or_none(action_id)
    if action is None:
        return {"type": "action_result", "success": False, "reason": f"unknown action {action_id!r}"}

    result = execute_action(player, action, state.graph)
    desc = f"{player.name} performed {action.name}."
    if result.produced:
        desc += f" Produced: {', '.join(result.produced)}."
    event_log.emit(
        EventType.CRAFT_SUCCESS if result.produced else EventType.GATHER,
        desc,
        npc_roles=[NPCRole(npc_id=player.id, role="actor")],
        zone_id=player.current_zone_id,
        severity=EventSeverity.MINOR,
        tags={"player", "action"},
        payload={"action": action_id, "produced": result.produced, "consumed": result.consumed},
    )
    return {
        "type": "action_result",
        "success": result.success,
        "produced": result.produced,
        "consumed": result.consumed,
        "description": desc,
    }


# ── tick ──────────────────────────────────────────────────────────────────────

def handle_tick(state: AppState, data: dict) -> tuple[dict, list[dict]]:
    """
    Returns (tick_result_msg, push_messages).
    push_messages contains npc_moved and world_event entries for broadcasting.
    """
    count = max(1, int(data.get("count", 1)))
    before_tick = current_tick()
    push: list[dict] = []
    last_result = None

    mark = datetime.now(timezone.utc)
    for _ in range(count):
        # Snapshot NPC locations before tick for move detection
        before_locs: dict[str, str | None] = {
            n.id: n.current_zone_id for n in state.npc_registry.all_npcs()
        }
        last_result = tick(
            state.npc_registry,
            state.graph,
            state.action_registry,
            state.memory_store,
        )
        # Build npc_moved push messages
        for npc in state.npc_registry.all_npcs():
            if npc.current_zone_id != before_locs.get(npc.id):
                push.append({
                    "type": "npc_moved",
                    "npc_id": npc.id,
                    "from_zone": before_locs.get(npc.id),
                    "to_zone": npc.current_zone_id,
                })

    # Build world_event push messages from new events
    new_events = event_log.since(mark)
    for e in new_events:
        if e.severity not in ("trivial",):
            push.append({
                "type": "world_event",
                "event_type": str(e.event_type),
                "description": e.description,
                "zone_id": e.zone_id,
            })

    push.append({
        "type": "time_update",
        **_game_time(current_tick()),
    })

    tick_msg = serialize_tick_result(last_result, event_log.recent(20))
    return tick_msg, push
