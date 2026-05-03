"""FastAPI application factory for the Galatea developer tooling."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from tools.routes import amplify, dag, dialogue, eventlog, knowledge, npc, prompts, seed, tickstepper, tier, world


def create_app() -> FastAPI:
    app = FastAPI(title="Galatea Dev Tools", docs_url=None, redoc_url=None)

    app.include_router(world.router)
    app.include_router(npc.router)
    app.include_router(dag.router)
    app.include_router(seed.router)
    app.include_router(prompts.router)
    app.include_router(dialogue.router)
    app.include_router(knowledge.router)
    app.include_router(tier.router)
    app.include_router(eventlog.router)
    app.include_router(amplify.router)
    app.include_router(tickstepper.router)

    @app.get("/")
    async def root():
        return RedirectResponse(url="/world/")

    return app


app = create_app()
