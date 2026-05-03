"""Dialogue REPL — web UI for testing NPC conversations end-to-end."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from affordances.query import what_can_actor_do
from dialogue.engine import DialogueEngine
from dialogue.prompt_builder import DialogueContext
from dialogue.session import DialogueSession, DialogueTurn
from events.log import EventSeverity, EventType, NPCRole, event_log
from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
from llm.factory import get_runner
from npc.schema import NPCTier
from tools.state import get_state

router = APIRouter(prefix="/dialogue")
templates = Jinja2Templates(directory="tools/templates")

# In-memory session store: npc_id → DialogueSession
_sessions: dict[str, DialogueSession] = {}


def _build_context(npc_id: str, state) -> DialogueContext:
    npc = state.npc_registry.get(npc_id)
    player = state.npc_registry.player()
    zone = state.graph.get_zone(npc.current_zone_id)
    tag_map = state.npc_registry.build_npc_tag_map()
    actor_ctx = npc.as_actor_context(graph=state.graph)
    available_actions = what_can_actor_do(
        actor_ctx, npc.current_zone_id, state.graph,
        state.action_registry, npc_tag_map=tag_map,
    )
    zone_npcs = [
        state.npc_registry.get(nid)
        for nid in zone.npc_ids
        if nid != npc.id and nid in {n.id for n in state.npc_registry.all_npcs()}
    ]

    query = RetrievalQuery(
        topic_tags=set(npc.trait_tags) | set(npc.values),
        involved_npc_ids={player.id},
        involved_zone_id=npc.current_zone_id,
    )
    excerpts = retrieve_for_prompt(state.memory_store, npc_id, query)
    memory_excerpts = [e.content for e in excerpts.individual]
    if excerpts.community:
        memory_excerpts += [f"[village knowledge] {e.content}" for e in excerpts.community]

    return DialogueContext(
        npc=npc, player=player, zone=zone,
        zone_npcs=zone_npcs, available_actions=available_actions,
        memory_excerpts=memory_excerpts,
    )


@router.get("/", response_class=HTMLResponse)
async def dialogue_index(request: Request):
    state = get_state()
    npcs = [
        n for n in state.npc_registry.all_npcs()
        if not n.is_player and n.tier >= NPCTier.T1 and n.current_zone_id
    ]
    npcs.sort(key=lambda n: (-n.tier, n.name))
    return templates.TemplateResponse(
        request, "dialogue/index.html", {"npcs": npcs}
    )


@router.get("/{npc_id}", response_class=HTMLResponse)
async def dialogue_chat(request: Request, npc_id: str):
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f"NPC {npc_id!r} not found.", status_code=404)

    session = _sessions.get(npc_id)
    if session is None:
        session = DialogueSession(
            npc_id=npc_id, player_id="player",
            zone_id=npc.current_zone_id or "",
        )
        _sessions[npc_id] = session

    return templates.TemplateResponse(
        request, "dialogue/chat.html",
        {"npc": npc, "session": session},
    )


@router.post("/{npc_id}/send", response_class=HTMLResponse)
async def dialogue_send(
    request: Request,
    npc_id: str,
    player_input: str = Form(...),
):
    state = get_state()
    try:
        npc = state.npc_registry.get(npc_id)
    except KeyError:
        return HTMLResponse(f"NPC {npc_id!r} not found.", status_code=404)

    session = _sessions.setdefault(
        npc_id,
        DialogueSession(npc_id=npc_id, player_id="player", zone_id=npc.current_zone_id or ""),
    )

    ctx = _build_context(npc_id, state)
    engine = DialogueEngine(runner=get_runner())

    try:
        engine.player_turn(session, player_input.strip(), ctx)
        event_log.emit(
            EventType.DIALOGUE,
            f"Player spoke with {npc.name}.",
            npc_roles=[
                NPCRole(npc_id=npc.id, role="actor"),
                NPCRole(npc_id="player", role="target"),
            ],
            zone_id=npc.current_zone_id,
            severity=EventSeverity.TRIVIAL,
            tags={"dialogue", f"npc:{npc.id}"},
            payload={"turn": len(session.turns), "input_len": len(player_input)},
        )
    except Exception as exc:
        session.add_turn(DialogueTurn(
            player_input=player_input,
            npc_response=f"[LLM error: {exc}]",
        ))

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request, "dialogue/_conversation.html",
            {"npc": npc, "session": session},
        )

    return templates.TemplateResponse(
        request, "dialogue/chat.html",
        {"npc": npc, "session": session},
    )


@router.post("/{npc_id}/reset", response_class=HTMLResponse)
async def dialogue_reset(request: Request, npc_id: str):
    _sessions.pop(npc_id, None)
    return RedirectResponse(f"/dialogue/{npc_id}", status_code=303)
