"""Event log viewer."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from events.log import EventSeverity, EventType, event_log
from tools.state import get_state

router = APIRouter(prefix="/events")
templates = Jinja2Templates(directory="tools/templates")

_ALL_TYPES = list(EventType)
_ALL_SEVERITIES = list(EventSeverity)


@router.get("/", response_class=HTMLResponse)
async def event_log_index(request: Request):
    state = get_state()

    # Filter params
    q_type     = request.query_params.get("type", "").strip()
    q_npc      = request.query_params.get("npc", "").strip()
    q_zone     = request.query_params.get("zone", "").strip()
    q_tag      = request.query_params.get("tag", "").strip()
    q_severity = request.query_params.get("severity", "").strip()

    entries = event_log.recent(500)

    if q_type:
        entries = [e for e in entries if e.event_type == q_type]
    if q_npc:
        entries = [e for e in entries if q_npc in e.involved_npc_ids()]
    if q_zone:
        entries = [e for e in entries if e.zone_id == q_zone]
    if q_tag:
        entries = [e for e in entries if q_tag in e.tags]
    if q_severity:
        sev_order = _ALL_SEVERITIES
        try:
            min_idx = sev_order.index(EventSeverity(q_severity))
            entries = [e for e in entries if sev_order.index(e.severity) >= min_idx]
        except ValueError:
            pass

    # Collect all tags for filter cloud
    all_tags: set[str] = set()
    for e in event_log.all():
        all_tags.update(e.tags)

    npcs = sorted(state.npc_registry.all_npcs(), key=lambda n: n.name)

    return templates.TemplateResponse(
        request, "events/index.html",
        {
            "entries": entries,
            "total_logged": len(event_log),
            "all_types": _ALL_TYPES,
            "all_severities": _ALL_SEVERITIES,
            "all_tags": sorted(all_tags),
            "npcs": npcs,
            "q_type": q_type,
            "q_npc": q_npc,
            "q_zone": q_zone,
            "q_tag": q_tag,
            "q_severity": q_severity,
        },
    )
