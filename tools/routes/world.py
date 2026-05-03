from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from affordances.query import actions_available_in_zone
from tools.state import get_state

router = APIRouter(prefix="/world")
templates = Jinja2Templates(directory="tools/templates")


def _zone_context(zone_id: str, state) -> dict:
    graph = state.graph
    zone = graph.get_zone(zone_id)
    npc_tag_map = state.npc_registry.build_npc_tag_map()
    npcs = []
    for nid in zone.npc_ids:
        try:
            npcs.append(state.npc_registry.get(nid))
        except KeyError:
            pass
    return {
        "zone": zone,
        "parent": graph.parent(zone_id),
        "children": graph.children(zone_id),
        "connections": graph.connections(zone_id),
        "items": graph.items_in_zone(zone_id),
        "npcs": npcs,
        "effective_tags": sorted(graph.effective_tags(zone_id, npc_tag_map)),
        "available_actions": actions_available_in_zone(zone_id, graph, state.action_registry),
    }


@router.get("/", response_class=HTMLResponse)
async def world_index(request: Request):
    state = get_state()
    zones = sorted(state.graph.zones(), key=lambda z: z.name)
    return templates.TemplateResponse(
        request, "world/index.html",
        {"zones": zones, "selected": None},
    )


@router.get("/{zone_id}", response_class=HTMLResponse)
async def zone_detail(request: Request, zone_id: str):
    state = get_state()
    try:
        ctx = _zone_context(zone_id, state)
    except KeyError:
        return HTMLResponse(f"<p>Zone <code>{zone_id}</code> not found.</p>", status_code=404)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "world/_zone.html", ctx)

    zones = sorted(state.graph.zones(), key=lambda z: z.name)
    return templates.TemplateResponse(
        request, "world/index.html",
        {"zones": zones, "selected": ctx["zone"], **ctx},
    )
