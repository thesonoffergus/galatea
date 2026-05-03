"""Convert Python simulation objects to JSON-serializable dicts."""
from __future__ import annotations

from config import settings
from sim.tick import current_tick
from tools.state import AppState


def serialize_item(item) -> dict:
    return {"id": item.id, "name": item.name, "item_type": item.item_type, "quality": item.quality}


def serialize_feature(feature) -> dict:
    return {"name": feature.name, "description": feature.description}


def serialize_zone(zone_id: str, state: AppState) -> dict:
    zone = state.graph.get_zone(zone_id)
    connections = [z.id for z in state.graph.connections(zone_id)]
    parent = state.graph.parent(zone_id)
    children = [z.id for z in state.graph.children(zone_id)]
    items = [serialize_item(i) for i in state.graph.items_in_zone(zone_id)]
    return {
        "id": zone.id,
        "name": zone.name,
        "description": zone.description,
        "terrain_type": str(zone.terrain_type),
        "tags": sorted(zone.tags),
        "connections": connections,
        "parent_id": parent.id if parent else None,
        "children": children,
        "items": items,
        "npcs": list(zone.npc_ids),
        "features": [serialize_feature(f) for f in zone.features],
    }


def serialize_npc(npc) -> dict:
    return {
        "id": npc.id,
        "name": npc.name,
        "role": npc.role,
        "description": npc.description,
        "tier": int(npc.tier),
        "current_zone_id": npc.current_zone_id,
        "is_player": npc.is_player,
        "mood": npc.mood,
        "physical": {
            "build": npc.physical.build,
            "hair": npc.physical.hair,
            "notable": npc.physical.notable,
            "age_appearance": npc.physical.age_appearance,
        },
    }


def serialize_player(state: AppState) -> dict | None:
    player = state.npc_registry.player()
    if player is None:
        return None
    carried = [
        serialize_item(i)
        for item_id in player.carried_item_ids
        if (i := state.graph.get_item(item_id)) is not None
    ]
    return {
        "id": player.id,
        "name": player.name,
        "current_zone_id": player.current_zone_id,
        "carried_items": carried,
    }


def _game_time(tick: int) -> dict:
    tph = settings.time.ticks_per_game_hour
    hpd = settings.time.game_hours_per_day
    hours_elapsed = tick / tph
    total_hours = 6.0 + hours_elapsed       # simulation starts at 6am day 1
    day = int(total_hours // hpd) + 1
    game_hour = total_hours % hpd
    if 6 <= game_hour < 12:
        period = "morning"
    elif 12 <= game_hour < 18:
        period = "afternoon"
    elif 18 <= game_hour < 22:
        period = "evening"
    else:
        period = "night"
    return {"tick": tick, "game_hour": round(game_hour, 2), "day": day, "period": period}


def serialize_full_state(state: AppState) -> dict:
    zones = [serialize_zone(z.id, state) for z in state.graph.zones()]
    npcs = [serialize_npc(n) for n in state.npc_registry.all_npcs() if not n.is_player]
    return {
        "type": "full_state",
        "world": {"zones": zones},
        "npcs": npcs,
        "player": serialize_player(state),
        "time": _game_time(current_tick()),
    }


def serialize_tick_result(result, recent_events: list) -> dict:
    events = [
        {"type": str(e.event_type), "description": e.description, "zone_id": e.zone_id}
        for e in recent_events[-20:]
    ]
    return {
        "type": "tick_result",
        "tick_number": result.tick_number,
        "actions_taken": result.actions_taken,
        "gossip_events": result.gossip_events,
        "events": events,
        "time": _game_time(result.tick_number),
    }
