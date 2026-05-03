"""Tick stepper — manually advance simulation by N ticks."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from events.log import event_log
from sim.tick import TickResult, current_tick, tick
from tools.state import get_state

router = APIRouter(prefix="/tick")
templates = Jinja2Templates(directory="tools/templates")

_last_results: list[TickResult] = []
_MAX_RESULTS = 20


@router.get("/", response_class=HTMLResponse)
async def tick_index(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request, "tick/index.html",
        {
            "tick_number": current_tick(),
            "last_results": list(reversed(_last_results)),
            "recent_events": event_log.recent(30),
        },
    )


@router.post("/step", response_class=HTMLResponse)
async def tick_step(request: Request, n: int = Form(default=1)):
    state = get_state()
    n = max(1, min(n, 50))  # cap at 50 ticks per request

    new_results: list[TickResult] = []
    for _ in range(n):
        result = tick(
            registry=state.npc_registry,
            graph=state.graph,
            action_registry=state.action_registry,
            memory_store=state.memory_store,
        )
        new_results.append(result)
        _last_results.append(result)
        while len(_last_results) > _MAX_RESULTS:
            _last_results.pop(0)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request, "tick/_results.html",
            {
                "tick_number": current_tick(),
                "new_results": new_results,
                "recent_events": event_log.recent(30),
            },
        )

    return templates.TemplateResponse(
        request, "tick/index.html",
        {
            "tick_number": current_tick(),
            "last_results": list(reversed(_last_results)),
            "recent_events": event_log.recent(30),
        },
    )
