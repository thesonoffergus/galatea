from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from crafting.dag import dependency_tree
from tools.state import get_state

router = APIRouter(prefix="/dag")
templates = Jinja2Templates(directory="tools/templates")


def _all_item_types(state) -> dict[str, dict]:
    dag = state.item_dag
    result = {}
    for node in sorted(dag.nodes):
        data = dag.nodes[node]
        result[node] = {
            "gatherable": data.get("gatherable", False),
            "craftable": data.get("craftable", False),
        }
    return result


@router.get("/", response_class=HTMLResponse)
async def dag_index(request: Request):
    state = get_state()
    items = _all_item_types(state)
    return templates.TemplateResponse(
        request, "dag/index.html",
        {"items": items, "tree": None, "selected_item": None},
    )


@router.get("/{item_type}", response_class=HTMLResponse)
async def dag_tree(request: Request, item_type: str):
    state = get_state()
    tree = dependency_tree(item_type, state.item_dag, state.action_registry)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request, "dag/_tree.html",
            {"tree": tree, "item_type": item_type},
        )

    items = _all_item_types(state)
    return templates.TemplateResponse(
        request, "dag/index.html",
        {"items": items, "tree": tree, "selected_item": item_type},
    )
