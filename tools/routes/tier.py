"""Tier management endpoints for the dev tooling."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from events.log import EventSeverity, EventType, NPCRole, event_log
from llm.factory import get_runner
from npc.schema import NPCTier
from npc.tier import TierChangeResult, compute_reach_score, force_tier
from tools.state import get_state

router = APIRouter(prefix="/tier")
templates = Jinja2Templates(directory="tools/templates")


@router.post("/{npc_id}/set", response_class=HTMLResponse)
async def set_tier(
    request: Request,
    npc_id: str,
    new_tier: int = Form(...),
    compress: bool = Form(default=False),
):
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f"NPC {npc_id!r} not found.", status_code=404)

    runner = get_runner() if compress else None
    result = force_tier(npc, state.memory_store, NPCTier(new_tier), runner=runner)

    # Refresh reach score
    npc.reach_score = compute_reach_score(npc, state.memory_store.get(npc_id))

    event_log.emit(
        EventType.TIER_CHANGE,
        f"{npc.name} moved from T{result.old_tier} to T{result.new_tier} (director override).",
        npc_roles=[NPCRole(npc_id=npc.id, role="subject")],
        zone_id=npc.current_zone_id,
        severity=EventSeverity.MODERATE,
        tags={"tier_change", "director"},
        payload={"old_tier": result.old_tier, "new_tier": result.new_tier,
                 "compressed": bool(result.narrative_summary)},
    )

    msg_parts = [
        f"{npc.name}: T{result.old_tier} → T{result.new_tier}",
    ]
    if result.narrative_summary:
        msg_parts.append(f"Summary written ({len(result.narrative_summary)} chars).")

    if request.headers.get("HX-Request") == "true":
        status_class = "msg-success" if result.new_tier >= result.old_tier else "msg-error"
        html = (
            f'<span class="{status_class}">'
            + " ".join(msg_parts)
            + "</span>"
        )
        return HTMLResponse(html)

    return HTMLResponse(" ".join(msg_parts))


@router.get("/{npc_id}/score", response_class=HTMLResponse)
async def reach_score(request: Request, npc_id: str):
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f"NPC {npc_id!r} not found.", status_code=404)

    score = compute_reach_score(npc, state.memory_store.get(npc_id))
    npc.reach_score = score
    return HTMLResponse(f"{score:.2f}")
