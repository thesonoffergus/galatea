"""Community KB viewer."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tools.state import get_state

router = APIRouter(prefix="/knowledge")
templates = Jinja2Templates(directory="tools/templates")


@router.get("/", response_class=HTMLResponse)
async def kb_index(request: Request):
    state = get_state()
    entries = state.memory_store.community_kb.all_entries()
    tag_filter = request.query_params.get("tag", "").strip()
    if tag_filter:
        entries = [e for e in entries if tag_filter in e.topic_tags]

    all_tags: set[str] = set()
    for e in state.memory_store.community_kb.all_entries():
        all_tags.update(e.topic_tags)

    return templates.TemplateResponse(
        request, "knowledge/index.html",
        {
            "entries": entries,
            "all_tags": sorted(all_tags),
            "tag_filter": tag_filter,
            "total": len(state.memory_store.community_kb),
        },
    )
