from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from crafting.bootstrap import validate_world
from tools.state import DATA_DIR, get_state, reload_state

router = APIRouter(prefix="/seed")
templates = Jinja2Templates(directory="tools/templates")


@router.get("/", response_class=HTMLResponse)
async def seed_index(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request, "seed/index.html",
        {"state": state, "message": None},
    )


@router.post("/reload", response_class=HTMLResponse)
async def seed_reload(request: Request, seed_path: str = Form(...)):
    path = Path(seed_path)
    if not path.is_absolute():
        path = DATA_DIR / path
    try:
        state = reload_state(path)
        br = state.bootstrap_result
        status = "PASS" if br.passed else "FAIL"
        message = (
            f"Loaded: {path.name} — {len(state.npc_registry)} NPCs, "
            f"{state.graph.zone_count()} zones · Bootstrap {status}: "
            f"{len(br.errors())} error(s), {len(br.warnings())} warning(s)"
        )
        ok = True
    except Exception as exc:
        message = f"Error loading {path.name}: {exc}"
        state = get_state()
        ok = False

    if request.headers.get("HX-Request") == "true":
        cls = "success" if ok else "error"
        return HTMLResponse(f'<p class="msg-{cls}">{message}</p>')

    return templates.TemplateResponse(
        request, "seed/index.html",
        {"state": state, "message": message, "ok": ok},
    )


@router.get("/validate", response_class=HTMLResponse)
async def seed_validate(request: Request):
    """Re-run bootstrap validation against the current world state."""
    state = get_state()
    result = validate_world(state.action_registry, state.graph)
    # Update stored result in place so the page reflects the fresh run
    state.bootstrap_result = result

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request, "seed/_bootstrap.html",
            {"result": result},
        )

    return templates.TemplateResponse(
        request, "seed/index.html",
        {"state": state, "message": None},
    )
