"""
Manual bridge validation — connects to the server and exercises the protocol.

Run the server first:
    python -m server --stub

Then run this script:
    python server/test_client.py
"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets


SERVER_URI = "ws://localhost:8765"


async def send_recv(ws, msg: dict) -> dict:
    await ws.send(json.dumps(msg))
    raw = await ws.recv()
    return json.loads(raw)


async def drain(ws, count: int) -> list[dict]:
    """Receive `count` messages (for tick which sends tick_result + push messages)."""
    msgs = []
    for _ in range(count):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            msgs.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
    return msgs


async def main() -> None:
    print(f"Connecting to {SERVER_URI}...")
    async with websockets.connect(SERVER_URI) as ws:
        # 1. connect → full_state
        resp = await send_recv(ws, {"type": "connect"})
        assert resp["type"] == "full_state", f"Expected full_state, got {resp['type']}"
        zones = resp["world"]["zones"]
        npcs = resp["npcs"]
        player = resp["player"]
        print(f"[connect] full_state: {len(zones)} zones, {len(npcs)} NPCs")
        print(f"          Player: {player['name'] if player else 'None'}, zone: {player['current_zone_id'] if player else 'None'}")
        print(f"          Time: {resp['time']}")

        # 2. player_move → pick a connected zone
        if player and zones:
            current_zone = player["current_zone_id"]
            zone_data = next((z for z in zones if z["id"] == current_zone), None)
            if zone_data and zone_data["connections"]:
                target_zone = zone_data["connections"][0]
                resp = await send_recv(ws, {"type": "player_move", "zone_id": target_zone})
                print(f"\n[player_move] → {target_zone}: success={resp.get('success')}, reason={resp.get('reason', '')}")
                if resp.get("success"):
                    moved_zone = resp["zone_data"]
                    print(f"  Now in: {moved_zone['name']} ({moved_zone['terrain_type']}), {len(moved_zone['npcs'])} NPCs present")
            else:
                print("\n[player_move] No adjacent zones to move to, skipping.")

        # 3. player_interact → pick a T1+ NPC in current zone
        all_npcs_by_id = {n["id"]: n for n in resp.get("npcs", npcs)}
        current_zone_id = player["current_zone_id"] if player else None
        # Refresh current zone from move result
        if "zone_data" in resp:
            npc_ids_in_zone = resp["zone_data"]["npcs"]
        else:
            zone_data = next((z for z in zones if z["id"] == current_zone_id), None)
            npc_ids_in_zone = zone_data["npcs"] if zone_data else []

        interactable = [nid for nid in npc_ids_in_zone if not all_npcs_by_id.get(nid, {}).get("is_player")]
        if interactable:
            npc_id = interactable[0]
            npc_name = all_npcs_by_id.get(npc_id, {}).get("name", npc_id)
            resp = await send_recv(ws, {"type": "player_interact", "npc_id": npc_id})
            print(f"\n[player_interact] {npc_name}: type={resp.get('type')}")
            if resp.get("type") == "dialogue_start":
                print(f"  Greeting: {resp['greeting'][:120]}")
                print(f"  Menu: {resp.get('menu_options', [])}")

                # 4. dialogue_input
                resp = await send_recv(ws, {"type": "dialogue_input", "npc_id": npc_id, "input": "What do you sell?"})
                print(f"\n[dialogue_input] 'What do you sell?'")
                print(f"  Response: {resp.get('npc_response', '')[:120]}")
                print(f"  Menu: {resp.get('menu_options', [])}")

                # end dialogue
                resp = await send_recv(ws, {"type": "dialogue_end", "npc_id": npc_id})
                print(f"\n[dialogue_end] {resp}")
        else:
            print("\n[player_interact] No interactable NPCs in zone, skipping.")

        # 5. tick(count=3)
        print("\n[tick] Advancing 3 ticks...")
        await ws.send(json.dumps({"type": "tick", "count": 3}))
        msgs = await drain(ws, 10)
        tick_msgs = [m for m in msgs if m.get("type") == "tick_result"]
        push_msgs = [m for m in msgs if m.get("type") != "tick_result"]
        for tm in tick_msgs:
            print(f"  tick_result: tick={tm['tick_number']}, actions={tm['actions_taken']}, time={tm['time']}")
        print(f"  push messages: {[m['type'] for m in push_msgs]}")

    print("\nDone.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConnectionRefusedError:
        print(f"ERROR: Could not connect to {SERVER_URI}. Is the server running?", file=sys.stderr)
        print("  Start it with: python -m server --stub", file=sys.stderr)
        sys.exit(1)
