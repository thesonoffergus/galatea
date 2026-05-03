"""Dev-tool endpoints for amplification primitives."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from director.amplify import boost_kb_entry, nudge_goal, set_memory_salience
from events.log import EventSeverity, EventType, NPCRole, event_log
from npc.schema import GoalPriority
from tools.state import get_state

router = APIRouter(prefix="/amplify")


@router.post("/memory/{npc_id}/{memory_id}", response_class=HTMLResponse)
async def set_salience(
    request: Request,
    npc_id: str,
    memory_id: str,
    salience: float = Form(...),
):
    state = get_state()
    found = set_memory_salience(state.memory_store, npc_id, memory_id, salience)
    if not found:
        return HTMLResponse(
            f'<span class="msg-error">Memory {memory_id!r} not found.</span>'
        )
    return HTMLResponse(
        f'<span class="msg-success">Salience set to {salience:.1f}.</span>'
    )


@router.post("/kb/{entry_id}", response_class=HTMLResponse)
async def set_gossip_weight(
    request: Request,
    entry_id: str,
    gossip_weight: float = Form(...),
):
    state = get_state()
    found = boost_kb_entry(state.memory_store.community_kb, entry_id, gossip_weight)
    if not found:
        return HTMLResponse(
            f'<span class="msg-error">KB entry {entry_id!r} not found.</span>'
        )
    return HTMLResponse(
        f'<span class="msg-success">Gossip weight set to {gossip_weight:.1f}.</span>'
    )


@router.post("/goal/{npc_id}", response_class=HTMLResponse)
async def add_nudge_goal(
    request: Request,
    npc_id: str,
    description: str = Form(...),
    priority: str = Form(default="high"),
):
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(
            f'<span class="msg-error">NPC {npc_id!r} not found.</span>'
        )

    try:
        p = GoalPriority(priority)
    except ValueError:
        p = GoalPriority.HIGH

    goal = nudge_goal(npc, description.strip(), priority=p)
    event_log.emit(
        EventType.GOAL_SET,
        f'Director nudged {npc.name}: "{description.strip()}"',
        npc_roles=[NPCRole(npc_id=npc.id, role="subject")],
        zone_id=npc.current_zone_id,
        severity=EventSeverity.MODERATE,
        tags={"goal_nudge", "director", f"npc:{npc.id}"},
        payload={"goal_id": goal.id, "priority": priority},
    )

    return HTMLResponse(
        f'<span class="msg-success">Goal added: "{goal.description}"</span>'
    )


@router.post("/goal/{npc_id}/{goal_id}/complete", response_class=HTMLResponse)
async def complete_goal(request: Request, npc_id: str, goal_id: str):
    from npc.schema import GoalStatus
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f'<span class="msg-error">NPC not found.</span>')

    for goal in npc.goals:
        if goal.id == goal_id:
            goal.status = GoalStatus.COMPLETED
            return HTMLResponse('<span class="msg-success">Goal marked completed.</span>')
    return HTMLResponse(f'<span class="msg-error">Goal {goal_id!r} not found.</span>')


@router.post("/goal/{npc_id}/{goal_id}/abandon", response_class=HTMLResponse)
async def abandon_goal(request: Request, npc_id: str, goal_id: str):
    from npc.schema import GoalStatus
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f'<span class="msg-error">NPC not found.</span>')

    for goal in npc.goals:
        if goal.id == goal_id:
            goal.status = GoalStatus.ABANDONED
            return HTMLResponse('<span class="msg-success">Goal abandoned.</span>')
    return HTMLResponse(f'<span class="msg-error">Goal {goal_id!r} not found.</span>')
