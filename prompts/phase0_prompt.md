# Phase 0 — Godot Project + Python Bridge

## Context

Galatea is a Python simulation library for a medieval life simulator with LLM-driven NPCs. The simulation layer is built and working (318 passing tests). It includes: world graph with zones/items/features, action/affordance system, NPC schema with Big Five personality and tier system, GOAP-lite off-screen simulation, memory architecture with RAG retrieval, dialogue engine with prompt composition, event log with director hooks, crafting system, and a FastAPI developer tools UI.

The simulation has no visual frontend. This task builds the Godot 4 game client and the WebSocket bridge that connects it to the Python backend.

Reference these files for API details:
- `docs/ARCHITECTURE.md` — module layout, data structures, public APIs
- `docs/INTERFACES.md` — how to start the sim, query state, advance ticks, run dialogue
- `docs/STATE_OF_BUILD.md` — current status and known issues

---

## Part 1: Python WebSocket Server

Create a new module `galatea/server/` that wraps the simulation in a WebSocket server. This is the bridge the Godot client connects to.

### Architecture

- Use `websockets` library (pip install websockets).
- The server loads `AppState` from `tools/state.py` on startup — reuse the existing loader, don't duplicate it.
- The server initializes the LLM runner from config (support both Ollama and StubRunner via config flag so we can develop without a running LLM).
- One WebSocket connection at a time is fine for now. No multi-client support needed.
- All messages are JSON. Every message has a `"type"` field for dispatch.

### Message Protocol

Design and implement these message types. The server is authoritative for all game state — the client is a renderer and input collector, never a source of truth.

**Client → Server:**

```
connect          → {} 
                 ← full_state (entire world snapshot for initial render)

player_move      → { zone_id: str }
                 ← move_result { success: bool, zone_id: str, zone_data: {...} }

player_interact  → { npc_id: str }
                 ← dialogue_start { npc_id: str, npc_name: str, greeting: str, menu_options: [str] }

dialogue_input   → { npc_id: str, input: str }
                 ← dialogue_response { npc_response: str, menu_options: [str] }

dialogue_end     → { npc_id: str }
                 ← dialogue_ended { npc_id: str }

get_affordances  → {}
                 ← affordance_list { actions: [{id, name, description, category}] }

execute_action   → { action_id: str }
                 ← action_result { success: bool, produced: [str], consumed: [str], description: str }

tick             → { count: int }  (optional, defaults to 1)
                 ← tick_result { tick_number: int, actions_taken: int, events: [{type, description}] }
```

**Server → Client (push, after ticks or events):**

```
npc_moved        → { npc_id: str, from_zone: str, to_zone: str }
world_event      → { event_type: str, description: str, zone_id: str? }
time_update      → { tick: int, game_hour: float, day: int, period: str }
```

### `full_state` payload shape

This is the big one — sent on connect and contains everything the client needs to render the initial scene.

```json
{
  "type": "full_state",
  "world": {
    "zones": [
      {
        "id": "...",
        "name": "...",
        "description": "...",
        "terrain_type": "...",
        "tags": ["..."],
        "connections": ["zone_id", ...],
        "parent_id": "..." or null,
        "children": ["zone_id", ...],
        "items": [{ "id": "...", "name": "...", "item_type": "..." }],
        "npcs": ["npc_id", ...],
        "features": [{ "name": "...", "description": "..." }]
      }
    ]
  },
  "npcs": [
    {
      "id": "...",
      "name": "...",
      "role": "...",
      "description": "...",
      "tier": 0,
      "current_zone_id": "...",
      "is_player": false,
      "mood": 0.0,
      "physical": { "age_bracket": "...", "build": "...", ... }
    }
  ],
  "player": {
    "id": "...",
    "name": "...",
    "current_zone_id": "...",
    "carried_items": [{ "id": "...", "name": "...", "item_type": "..." }]
  },
  "time": {
    "tick": 0,
    "game_hour": 6.0,
    "day": 1,
    "period": "morning"
  }
}
```

### Server entry point

Create `galatea/server/__main__.py` so the server can be run with `python -m galatea.server`. It should:
1. Load AppState from the seed YAML.
2. Initialize the LLM runner (StubRunner by default, Ollama if configured).
3. Start the WebSocket server on a configurable port (default 8765).
4. Log all incoming/outgoing messages at DEBUG level.
5. Handle disconnects gracefully.

Also create `galatea/server/handlers.py` for the message dispatch logic — one handler function per message type. Keep the handler functions thin: they should call into existing Galatea APIs (the ones documented in INTERFACES.md) and serialize the results. Don't reimplement simulation logic in the server layer.

### Auto-tick mode

Add an optional auto-tick mode where the server advances the simulation at a configurable interval (default: every 2 seconds = roughly one in-game hour at the 15-min-per-day rate). When auto-tick is on, the server pushes `npc_moved`, `world_event`, and `time_update` messages to the client after each tick. When off, ticks only happen when the client explicitly sends a `tick` message. Start with auto-tick off by default.

---

## Part 2: Godot 4 Project

Create a Godot 4 project in a `client/` directory at the project root (sibling to `galatea/`).

### Project structure

```
client/
├── project.godot
├── assets/
│   ├── tilesets/          # placeholder tileset images go here
│   ├── sprites/           # NPC and player sprite sheets
│   ├── ui/                # UI theme resources
│   └── audio/             # placeholder audio (empty for now)
├── scenes/
│   ├── main.tscn          # root scene — loads world scene
│   ├── world.tscn         # the gameplay scene with tilemap + entities
│   ├── player.tscn        # player character scene (sprite + collision + camera)
│   ├── npc.tscn           # NPC scene (sprite + collision + interaction area)
│   ├── dialogue_ui.tscn   # dialogue box with text + menu options + freeform input
│   └── hud.tscn           # time, location name, minimap placeholder
├── scripts/
│   ├── autoload/
│   │   ├── game_bridge.gd     # WebSocket client — singleton, manages connection
│   │   └── game_state.gd      # client-side state cache — populated from server messages
│   ├── world/
│   │   ├── world_manager.gd   # builds/updates the visual world from game_state
│   │   ├── zone_renderer.gd   # renders a single zone (tilemap region)
│   │   └── npc_controller.gd  # moves NPC sprites, handles interaction triggers
│   ├── player/
│   │   ├── player_controller.gd  # movement, input, interaction initiation
│   │   └── player_camera.gd      # camera follow, zone transitions
│   ├── ui/
│   │   ├── dialogue_ui.gd       # dialogue box logic
│   │   ├── hud.gd               # HUD updates
│   │   └── action_menu.gd       # affordance/action selection UI
│   └── util/
│       └── message_types.gd     # constants for message type strings
```

### WebSocket client (`game_bridge.gd`)

This is the most important script. It:
- Connects to the Python server on startup (configurable URL, default `ws://localhost:8765`).
- Sends JSON messages and receives JSON responses.
- Emits Godot signals for each message type received, so other scripts can subscribe:
  - `full_state_received(data: Dictionary)`
  - `move_result_received(data: Dictionary)`
  - `dialogue_started(data: Dictionary)`
  - `dialogue_response_received(data: Dictionary)`
  - `npc_moved(data: Dictionary)`
  - `world_event(data: Dictionary)`
  - `affordances_received(data: Dictionary)`
  - `action_result_received(data: Dictionary)`
  - `tick_result_received(data: Dictionary)`
  - `time_updated(data: Dictionary)`
- Provides typed send methods: `send_player_move(zone_id)`, `send_interact(npc_id)`, `send_dialogue(npc_id, input)`, etc.
- Handles reconnection attempts if the connection drops.
- Register as an autoload in project.godot.

### Game state cache (`game_state.gd`)

Client-side mirror of the relevant game state. Populated from `full_state` on connect, updated incrementally from push messages. Other scripts read from this, never from raw messages.

- `zones: Dictionary` — zone_id → zone data dict
- `npcs: Dictionary` — npc_id → npc data dict  
- `player: Dictionary` — player state
- `time: Dictionary` — current game time
- `get_current_zone() → Dictionary`
- `get_npcs_in_zone(zone_id) → Array`
- `get_zone_connections(zone_id) → Array`

Register as an autoload.

### World rendering

For MVP, the world is NOT a seamless tilemap. Each zone is a distinct screen or area. When the player moves to a new zone, the scene transitions. This is simpler than a continuous map and matches the graph-based world model. Think of it like rooms in a Zelda dungeon or buildings in Stardew Valley.

Each zone renders as:
- A background appropriate to the terrain type (a colored rectangle with a label is the absolute minimum; a simple tilemap layout per terrain type is better).
- NPC sprites positioned within the zone.
- Item indicators (simple icons or markers for notable items).
- Exit indicators showing which directions lead to connected zones.

NPC sprites need:
- A simple idle animation (even just a bobbing motion).
- A name label above their head.
- An interaction area (Area2D) that triggers when the player walks near.

### Player controller

- 8-directional movement with arrow keys and WASD.
- Walking up to an NPC and pressing interact (E key or Enter) sends `player_interact` to the server.
- Walking to a zone exit sends `player_move` to the server.
- An action key (Tab or Q) opens the affordance menu — sends `get_affordances`, displays results, player selects one, sends `execute_action`.

### Dialogue UI

When dialogue starts:
- A panel appears at the bottom of the screen (classic JRPG style).
- NPC name displayed.
- NPC response text appears, ideally with a typewriter effect.
- Below the response: 2–4 menu option buttons (from the server's `menu_options`).
- Below those: a freeform text input field.
- Clicking a menu option or pressing Enter on freeform input sends `dialogue_input`.
- ESC or a close button sends `dialogue_end`.

### HUD

Minimal for now:
- Current zone name (top left).
- Time of day / day number (top right).
- A placeholder area for future minimap.

### Input mapping

Set up input actions in project.godot:
- `move_up`, `move_down`, `move_left`, `move_right` — WASD + arrows
- `interact` — E, Enter, gamepad A/Cross
- `cancel` — Escape, gamepad B/Circle
- `open_actions` — Tab, Q, gamepad Y/Triangle
- `menu_select_1` through `menu_select_4` — 1/2/3/4 keys (quick-select dialogue options)

Map gamepad inputs from the start even if we can't test them yet. Retrofitting is harder than including them.

### Placeholder art

Download or create minimal placeholder art. Priorities:

1. **Player sprite.** A simple 16x16 or 32x32 character with at least idle and 4-direction walk frames. The LPC (Liberated Pixel Cup) character base from OpenGameArt is ideal — it's free, CC-BY-SA, and has hundreds of equipment overlays for later. URL: https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles
2. **NPC sprites.** Recolor or variation of the player sprite. Different NPCs should be visually distinguishable even if crudely. At minimum, 3–4 color variants.
3. **Terrain tiles.** Simple ground, grass, stone floor, wood floor, water, path tiles. 16x16 or 32x32. The LPC tileset includes these. Kenney.nl's 1-Bit pack (https://kenney.nl/assets/1-bit-pack) is another option — it's public domain and has a consistent medieval set.
4. **Zone backgrounds.** If full tilemaps feel like too much for Phase 0, generate simple background images per terrain type — a green field, a stone interior, a forest clearing, a river bank. Even solid colors with a text label work.
5. **UI elements.** A dialogue box frame, button styles, font. Godot's default theme is fine for now; just pick a readable pixel font. Suggestion: "Press Start 2P" from Google Fonts (free, OFL license) or any clean pixel font.

If any asset source is inaccessible, fall back to colored rectangles with labels. The bridge and the interaction flow matter more than the art at this stage.

### No audio yet

Don't spend time on audio in Phase 0. Create the directory structure for it but leave it empty.

---

## Part 3: Running It Together

### Startup sequence

Create a shell script `run_dev.sh` (and `run_dev.bat` for Windows) at the project root that:
1. Starts the Python WebSocket server in the background: `python -m galatea.server &`
2. Waits 2 seconds for it to initialize.
3. Prints "Server running on ws://localhost:8765 — launch Godot project in client/"
4. Does NOT auto-launch Godot (the developer opens it manually in the Godot editor).

Also create `run_server.sh` that just starts the Python server standalone (useful for testing with the dev tools UI simultaneously).

### Testing the bridge without Godot

Create `galatea/server/test_client.py` — a simple Python WebSocket client that:
1. Connects to the server.
2. Sends `connect`, prints the `full_state` response summary (zone count, NPC count).
3. Sends `player_move` to an adjacent zone, prints result.
4. Sends `player_interact` with a T1+ NPC, prints the greeting.
5. Sends `dialogue_input` with "What do you sell?", prints response.
6. Sends `tick` with count=3, prints results.
7. Disconnects.

This validates the bridge works before Godot is involved.

---

## Part 4: Fix the inventory bug

Before building the bridge, fix the bug documented in STATE_OF_BUILD §2, bug #4:

> `NPC.as_actor_context()` ignores `graph` parameter — the method signature accepts `graph` but the implementation doesn't use it to derive inventory from `carried_item_ids`. Inventory in `ActorContext` is always an empty dict.

The fix: when `graph` is provided, iterate `npc.carried_item_ids`, look up each item via `graph.get_item(item_id)`, and populate `ActorContext.inventory` as `{item_type: quantity}` by aggregating items of the same type. When `graph` is not provided, fall back to empty dict (for backward compatibility with existing tests).

Also fix bug #7: `reload_state()` should reset the event log and tick counter.

---

## Implementation order

1. Fix bugs #4 and #7.
2. Build `galatea/server/` — WebSocket server, message protocol, handlers.
3. Build `galatea/server/test_client.py` and verify the bridge works.
4. Create the Godot project skeleton — project.godot, directory structure, autoloads, input map.
5. Implement `game_bridge.gd` and `game_state.gd`.
6. Build the world renderer — zone backgrounds, NPC placement, exits.
7. Build player controller — movement within zone, zone transitions, NPC interaction.
8. Build dialogue UI.
9. Build HUD.
10. Download and integrate placeholder art assets.
11. End-to-end test: start server, launch Godot, walk to the smithy, talk to the smith.

After each step, run existing tests (`pytest`) to make sure nothing in the simulation layer is broken.

---

## What NOT to do

- Don't modify Galatea's simulation logic except for the two bug fixes specified. The server is a thin wrapper around existing APIs.
- Don't build a continuous scrolling tilemap. Zone-based screen transitions are the right abstraction for Phase 0.
- Don't implement NPC pathfinding or wandering in Godot. NPCs stand in their zones. Movement happens server-side via ticks, and the client gets `npc_moved` messages.
- Don't build audio support yet.
- Don't build a save/load system yet.
- Don't build an auto-tick real-time loop yet — ticks are manual or on-demand for Phase 0.

When complete, update `docs/ARCHITECTURE.md`, `docs/STATE_OF_BUILD.md`, and `docs/INTERFACES.md` to reflect the new server module and client project.
