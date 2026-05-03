from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from llm.prompt_log import prompt_log

router = APIRouter(prefix="/prompts")
templates = Jinja2Templates(directory="tools/templates")

_TAG_OPTIONS = [
    "", "type:dialogue", "type:summary", "type:menu",
]


@router.get("/", response_class=HTMLResponse)
async def prompts_index(request: Request, tag: str = "", n: int = 100):
    entries = prompt_log.recent(n=n, tag=tag or None)
    return templates.TemplateResponse(
        request, "prompts/index.html",
        {"entries": entries, "tag": tag, "selected": None, "tag_options": _TAG_OPTIONS},
    )


@router.get("/{entry_id}", response_class=HTMLResponse)
async def prompt_detail(request: Request, entry_id: str, tag: str = ""):
    entry = prompt_log.get(entry_id)
    if entry is None:
        return HTMLResponse(f"<p>Entry <code>{entry_id}</code> not found.</p>", status_code=404)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request, "prompts/_entry.html",
            {"entry": entry},
        )

    entries = prompt_log.recent(n=100, tag=tag or None)
    return templates.TemplateResponse(
        request, "prompts/index.html",
        {"entries": entries, "tag": tag, "selected": entry, "tag_options": _TAG_OPTIONS},
    )
