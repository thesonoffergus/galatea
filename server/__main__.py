"""
WebSocket bridge server.

Run with:
    python -m server [--port 8765] [--seed data/village_seed.yaml] [--stub]

Flags:
    --port   WebSocket port (default 8765)
    --seed   Path to seed YAML (default data/village_seed.yaml)
    --stub   Use StubRunner instead of Ollama (no LLM required)
    --auto-tick   Enable automatic ticking every N seconds (default off)
    --tick-interval  Seconds between auto-ticks (default 2.0)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import websockets
from websockets.server import WebSocketServerProtocol

from llm.factory import set_runner
from llm.stub_runner import StubRunner
from server.handlers import (
    handle_connect,
    handle_dialogue_end,
    handle_dialogue_input,
    handle_execute_action,
    handle_get_affordances,
    handle_player_interact,
    handle_player_move,
    handle_tick,
)
from tools.state import reload_state

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("galatea.server")


# ── Server ────────────────────────────────────────────────────────────────────

class GalateaServer:
    def __init__(
        self,
        seed_path: Path,
        use_stub: bool = True,
        auto_tick: bool = False,
        tick_interval: float = 2.0,
    ) -> None:
        self.state = reload_state(seed_path)
        if use_stub:
            set_runner(StubRunner(response="Aye, what is it you need?"))
            log.info("Using StubRunner (no LLM calls).")
        else:
            from llm.factory import get_runner
            get_runner()   # initialise Ollama runner from config
            log.info("Using Ollama runner.")

        self.auto_tick = auto_tick
        self.tick_interval = tick_interval
        self._sessions: dict = {}     # npc_id → DialogueSession
        self._connection: WebSocketServerProtocol | None = None

    async def handler(self, websocket: WebSocketServerProtocol) -> None:
        if self._connection is not None:
            log.warning("Second connection attempt — rejecting (single-client mode).")
            await websocket.close(1008, "Server already has a client")
            return

        self._connection = websocket
        log.info("Client connected from %s.", websocket.remote_address)

        auto_task = None
        if self.auto_tick:
            auto_task = asyncio.create_task(self._auto_tick_loop(websocket))

        try:
            async for raw in websocket:
                await self._dispatch(websocket, raw)
        except websockets.exceptions.ConnectionClosedOK:
            log.info("Client disconnected cleanly.")
        except websockets.exceptions.ConnectionClosedError as e:
            log.warning("Client disconnected with error: %s", e)
        finally:
            if auto_task:
                auto_task.cancel()
            self._connection = None
            self._sessions.clear()

    async def _dispatch(self, ws: WebSocketServerProtocol, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Received non-JSON message: %r", raw[:200])
            await ws.send(json.dumps({"type": "error", "reason": "invalid JSON"}))
            return

        msg_type: str = msg.get("type", "")
        log.debug("→ %s %s", msg_type, {k: v for k, v in msg.items() if k != "type"})

        from llm.factory import get_runner

        responses: list[dict] = []
        push: list[dict] = []

        if msg_type == "connect":
            responses.append(handle_connect(self.state))

        elif msg_type == "player_move":
            responses.append(handle_player_move(self.state, msg))

        elif msg_type == "player_interact":
            responses.append(handle_player_interact(self.state, msg, self._sessions, get_runner()))

        elif msg_type == "dialogue_input":
            responses.append(handle_dialogue_input(self.state, msg, self._sessions, get_runner()))

        elif msg_type == "dialogue_end":
            responses.append(handle_dialogue_end(self.state, msg, self._sessions))

        elif msg_type == "get_affordances":
            responses.append(handle_get_affordances(self.state))

        elif msg_type == "execute_action":
            responses.append(handle_execute_action(self.state, msg))

        elif msg_type == "tick":
            tick_msg, push = handle_tick(self.state, msg)
            responses.append(tick_msg)

        else:
            responses.append({"type": "error", "reason": f"unknown message type {msg_type!r}"})

        for resp in responses + push:
            log.debug("← %s", resp.get("type", "?"))
            await ws.send(json.dumps(resp))

    async def _auto_tick_loop(self, ws: WebSocketServerProtocol) -> None:
        while True:
            await asyncio.sleep(self.tick_interval)
            tick_msg, push = handle_tick(self.state, {"count": 1})
            for msg in [tick_msg] + push:
                try:
                    await ws.send(json.dumps(msg))
                except websockets.exceptions.ConnectionClosed:
                    return


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Galatea WebSocket server")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--seed", type=Path, default=None)
    p.add_argument("--stub", action="store_true", default=True,
                   help="Use StubRunner (default). Pass --no-stub for Ollama.")
    p.add_argument("--no-stub", dest="stub", action="store_false")
    p.add_argument("--auto-tick", action="store_true", default=False)
    p.add_argument("--tick-interval", type=float, default=2.0)
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    seed = args.seed or (Path(__file__).parent.parent / "data" / "village_seed.yaml")
    server = GalateaServer(
        seed_path=seed,
        use_stub=args.stub,
        auto_tick=args.auto_tick,
        tick_interval=args.tick_interval,
    )
    host, port = "localhost", args.port
    log.info("Starting Galatea WebSocket server on ws://%s:%d", host, port)
    async with websockets.serve(server.handler, host, port):
        log.info("Server ready. Waiting for Godot client...")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
