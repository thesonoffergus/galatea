from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from affordances.query import what_can_actor_do
from tools.state import get_state

router = APIRouter(prefix="/npc")
templates = Jinja2Templates(directory="tools/templates")


def _npc_context(npc_id: str, state) -> dict:
    npc = state.npc_registry.get(npc_id)
    current_zone = None
    available_actions = []
    if npc.current_zone_id:
        try:
            current_zone = state.graph.get_zone(npc.current_zone_id)
            ctx = npc.as_actor_context(graph=state.graph)
            npc_tag_map = state.npc_registry.build_npc_tag_map()
            available_actions = what_can_actor_do(
                ctx, npc.current_zone_id, state.graph,
                state.action_registry, npc_tag_map=npc_tag_map,
            )
        except (KeyError, Exception):
            pass
    memory_entries = state.memory_store.get(npc.id).all_entries()
    return {
        "npc": npc,
        "current_zone": current_zone,
        "available_actions": available_actions,
        "memory_entries": memory_entries,
    }


@router.get("/", response_class=HTMLResponse)
async def npc_index(request: Request):
    state = get_state()
    npcs = sorted(state.npc_registry.all_npcs(), key=lambda n: n.name)
    return templates.TemplateResponse(
        request, "npc/index.html",
        {"npcs": npcs, "selected": None},
    )


@router.get("/{npc_id}", response_class=HTMLResponse)
async def npc_detail(request: Request, npc_id: str):
    state = get_state()
    try:
        ctx = _npc_context(npc_id, state)
    except KeyError:
        return HTMLResponse(f"<p>NPC <code>{npc_id}</code> not found.</p>", status_code=404)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "npc/_detail.html", ctx)

    npcs = sorted(state.npc_registry.all_npcs(), key=lambda n: n.name)
    return templates.TemplateResponse(
        request, "npc/index.html",
        {"npcs": npcs, "selected": ctx["npc"], **ctx},
    )
