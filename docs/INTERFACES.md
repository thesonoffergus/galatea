# Galatea — Interface Reference

_Describes the contract between Galatea and any external consumer: a game client, a game loop driver, or another service. Last synced: build-order step 15._

---

## 1. Starting the Simulation

### Current state (dev-tool only)
There is no packaged "start the sim" call. All state lives in the `tools` package's `AppState` singleton, which the FastAPI app creates lazily on the first request.

To embed Galatea programmatically (without the HTTP server):

```python
from tools.state import get_state, reload_state
from pathlib import Path

# Load world + NPCs + memories from seed YAML
state = get_state()                        # uses data/village_seed.yaml by default
# or:
state = reload_state(Path("my_seed.yaml")) # explicit seed

# Singletons available after load:
state.graph           # WorldGraph
state.npc_registry    # NPCRegistry
state.action_registry # ActionRegistry
state.memory_store    # MemoryStore
state.item_dag        # nx.DiGraph (product dependency graph)
state.bootstrap_result # BootstrapResult (validation pass/fail)
```

### Bootstrapping the LLM runner

```python
from llm.factory import set_runner, get_runner
from llm.ollama_runner import OllamaRunner
from llm.stub_runner import StubRunner

# Use Ollama (default if config.settings.llm.default_runner == "ollama")
set_runner(OllamaRunner(model="llama3.2", base_url="http://localhost:11434"))

# Use stub for testing / no-LLM mode
set_runner(StubRunner(response="Aye, what do you need?"))

# Let factory create from config
runner = get_runner()   # auto-creates OllamaRunner from config.settings.llm
```

### Configuring constants

All defaults live in `config.py`. Override before loading state:

```python
from config import settings

settings.tier.promote_t1 = 8.0            # harder promotion
settings.sim.t1_action_probability = 0.5  # more active T1 NPCs
settings.llm.default_model = "mistral"
settings.llm.dialogue_max_tokens = 200
```

`config.settings` is a Pydantic model; fields are validated on assignment.

---

## 11. Starting the WebSocket Server

```bash
python -m server [--port 8765] [--seed PATH] [--stub | --no-stub] [--auto-tick] [--tick-interval SECONDS]
```

| Flag | Default | Effect |
|------|---------|--------|
| `--port` | `8765` | TCP port to listen on |
| `--seed` | `data/village_seed.yaml` | Seed YAML passed to `AppState.load()` |
| `--stub` | on | Use `StubRunner` (no Ollama required) |
| `--no-stub` | — | Use `OllamaRunner` from `config.settings.llm` |
| `--auto-tick` | off | Automatically advance simulation one tick per `--tick-interval` seconds |
| `--tick-interval` | `5.0` | Seconds between auto-ticks (only relevant with `--auto-tick`) |

The server accepts **one WebSocket client at a time**. A second connection attempt is held until the first client disconnects.

### Quick start for development (without Ollama)

```bash
./run_dev.sh          # Linux/macOS: starts server in background, prints instructions
run_dev.bat           # Windows equivalent
# Then open client/project.godot in Godot 4.3 and press Play
```

To run the server standalone without the shell wrapper:

```bash
./run_server.sh
# or:
python -m server --port 8765 --stub
```

---

## 2. Querying World State

All queries below operate on Python objects directly — there is no query language. A WebSocket API for the same data (via the `full_state` message) is also available; see sections 11–13 for the network protocol.

```python
from tools.state import get_state
state = get_state()

# --- Zones ---
zone = state.graph.get_zone("zone_id")          # raises KeyError if not found
zones = list(state.graph.zones())               # all Zone objects
tags = state.graph.effective_tags("zone_id")    # set[str] — own + features + items + NPCs
children = state.graph.children("zone_id")      # list[Zone]
neighbors = state.graph.connections("zone_id")  # list[Zone] — CONNECTS edges only
summary = state.graph.summary("zone_id")        # dict for display

# --- Items ---
item = state.graph.get_item("item_id")          # Item | None
items = state.graph.items_in_zone("zone_id")    # list[Item]
loc = state.graph.item_location("item_id")      # Zone | None

# --- NPCs ---
npc = state.npc_registry.get("npc_id")          # raises KeyError
npcs = state.npc_registry.all_npcs()
tier2 = state.npc_registry.by_tier_min(NPCTier.T2)
loc = state.graph.npc_location("npc_id")         # Zone | None

# --- Actions ---
from affordances.query import what_can_actor_do
available = what_can_actor_do(
    actor=npc.as_actor_context(),
    zone_id=npc.current_zone_id,
    graph=state.graph,
    registry=state.action_registry,
)   # → list[Action]
```

---

## 3. Advancing Time (Tick)

```python
from sim.tick import tick, current_tick, reset_tick_count

result = tick(
    state.npc_registry,
    state.graph,
    state.action_registry,
    state.memory_store,
)

# result: TickResult
result.tick_number          # int — current tick after this advance
result.actions_taken        # int — how many NPCs acted
result.gossip_events        # int — how many gossip propagations
result.npc_results          # list[NpcTickResult]
    # .npc_id               # str
    # .action_result        # ExecutionResult | None
    # .gossiped             # bool
    # .relationships_drifted # int

current_tick()              # int — global tick counter
```

Tick behavior by tier:
- **T0**: skipped entirely
- **T1**: acts with `config.settings.sim.t1_action_probability` (default 25%)
- **T2+**: always attempts GOAP action selection
- All tiers: gossip check (`gossip_probability` default 10%), relationship drift (±`rel_drift_magnitude` default 0.02)

The tick does **not** advance wall-clock time — there is no real-time scheduling yet. Call `tick()` at whatever cadence suits the game loop.

---

## 4. Initiating Dialogue

Dialogue is a stateful turn-by-turn exchange. Sessions are managed by the consumer.

```python
from dialogue.session import DialogueSession, DialogueTurn
from dialogue.engine import DialogueEngine
from dialogue.prompt_builder import DialogueContext
from knowledge.retrieval import RetrievalQuery, retrieve_for_prompt
from affordances.query import what_can_actor_do
from llm.factory import get_runner

# 1. Build the dialogue context
npc = state.npc_registry.get("npc_id")
player = state.npc_registry.player()          # NPC with is_player=True
zone = state.graph.get_zone(npc.current_zone_id)
zone_npcs = state.npc_registry.npcs_in_zone(zone.id, state.graph)

available_actions = what_can_actor_do(
    actor=npc.as_actor_context(),
    zone_id=zone.id,
    graph=state.graph,
    registry=state.action_registry,
)

# 2. Retrieve relevant memories
excerpts = retrieve_for_prompt(
    store=state.memory_store,
    npc_id=npc.id,
    query=RetrievalQuery(
        topic_tags={"trade", "crafting"},     # tune per conversation
        involved_npc_ids={player.id},
        involved_zone_id=zone.id,
    ),
)
memory_strings = [e.content for e in excerpts.individual + excerpts.community]

ctx = DialogueContext(
    npc=npc,
    player=player,
    zone=zone,
    zone_npcs=[n for n in zone_npcs if n.id not in (npc.id, player.id)],
    available_actions=available_actions,
    memory_excerpts=memory_strings,
)

# 3. Create a session and run turns
session = DialogueSession(npc_id=npc.id, player_id=player.id, zone_id=zone.id)
engine = DialogueEngine(runner=get_runner())

turn = engine.player_turn(session, "What do you have for sale?", ctx)
# turn: DialogueTurn
turn.npc_response    # str — the NPC's reply
turn.player_input    # str — echoed back
turn.menu_options    # list[str] — 3 suggested follow-up options
```

The session accumulates `DialogueTurn` objects. Pass the same `session` each turn to maintain conversational history. Each `player_turn()` call makes two LLM requests: one for the NPC response, one to generate the menu options.

---

## 5. Getting Affordances for the Player Character

```python
from affordances.query import what_can_actor_do
from npc.schema import NPCTier

player = state.npc_registry.player()
zone_id = player.current_zone_id  # or any zone ID

# Build ActorContext from player's current state
actor = player.as_actor_context()
# ActorContext fields:
#   actor_id: str
#   skills: dict[str, float]
#   known_recipes: set[str]
#   inventory: dict[str, int]   ← populated from carried_item_ids via graph lookup
#   role_tags: set[str]

actions = what_can_actor_do(
    actor=actor,
    zone_id=zone_id,
    graph=state.graph,
    registry=state.action_registry,
    nearby_hops=1,
    npc_tag_map=state.npc_registry.build_npc_tag_map(),
)
# → list[Action]; only actions whose preconditions are satisfied
```

For display, use `affordance_digest(actions)` to get a concise human-readable string, or iterate `actions` directly.

---

## 6. Sending Player Input / Resolving Player Actions

There is no single "resolve player action" function yet — the action executor is NPC-only in the current build. To apply an action effect for the player:

```python
from sim.action_executor import execute_action

action = state.action_registry.get("smith_blade")
result = execute_action(player_npc, action, state.graph)
# result: ExecutionResult
result.success           # bool
result.produced          # list[str] — item_type strings of created items
result.consumed          # list[str]
result.skill_advanced    # str | None
result.moved_to          # str | None
```

Player skill gates (`PlayerSkillGate` on an `Action` or `ActionStep`) are resolved via:

```python
from crafting.skill_hook import skill_hook_registry

# Register a minigame resolver (game client implements this)
def my_smithing_minigame(difficulty: float, character_skill: float) -> float:
    # returns player performance score 0.0–1.0
    ...

skill_hook_registry.register("smithing_minigame", my_smithing_minigame)

# Resolve a gate
score = skill_hook_registry.resolve(
    type_id="smithing_minigame",
    difficulty=0.7,
    character_skill=player.skill_level("smithing"),
)
```

If no hook is registered for a `type_id`, it falls back to auto-resolve using character skill alone.

---

## 7. Director / Narrative Control

The director primitives are available to any consumer (not just the dev UI):

```python
from director.amplify import (
    set_memory_salience,
    boost_kb_entry,
    nudge_goal,
    clear_nudged_goals,
)

# Boost a specific memory so it persists longer and retrieves higher
set_memory_salience(state.memory_store, "npc_id", "memory_hex_id", 3.5)

# Increase gossip propagation weight of a KB entry
boost_kb_entry(state.memory_store.community_kb, "entry_hex_id", 2.0)

# Inject a goal into an NPC
npc = state.npc_registry.get("npc_id")
goal = nudge_goal(npc, "Find a buyer for the iron stockpile", priority=GoalPriority.HIGH)

# Remove all director-injected goals from an NPC
count = clear_nudged_goals(npc)
```

`nudge_goal()` returns the `Goal` object. The goal immediately affects GOAP action selection on the next tick.

---

## 8. Subscribing to Events

There are no push callbacks. The `EventLog` is a queryable ring buffer (max 2 000 entries). Poll it after each tick:

```python
from events.log import event_log, EventType, EventSeverity
from datetime import datetime, timezone

# All events since a timestamp
since = datetime.now(timezone.utc)
# ... run tick(s) ...
new_events = event_log.since(since)

# Filter by type
craft_events = event_log.by_type(EventType.CRAFT_SUCCESS)

# Filter by NPC
npc_events = event_log.by_npc("npc_id")

# Filter by severity (TRIVIAL | MINOR | MODERATE | MAJOR | CRITICAL)
important = event_log.by_severity(EventSeverity.MODERATE)

# Most recent N
recent = event_log.recent(50)
```

Each `EventEntry` carries:
- `event_type` — from `EventType` StrEnum
- `description` — human-readable string
- `npc_roles` — `list[NPCRole(npc_id, role)]` where role is "actor", "subject", etc.
- `zone_id`
- `severity`
- `tags` — `set[str]`
- `payload` — `dict` with type-specific data (e.g. `{"action": "smith_blade", "produced": ["iron_blade"]}`)
- `amplification` — float director hook field (currently always 1.0)
- `timestamp`, `id`

---

## 9. LLM Configuration and Integration

### Config
```python
# config.py — LLMConfig defaults
settings.llm.default_runner = "ollama"      # only "ollama" is supported; others raise
settings.llm.default_model = "llama3.2"
settings.llm.dialogue_max_tokens = 120
settings.llm.summary_max_tokens = 400
settings.llm.menu_options_count = 3
settings.llm.temperature = 0.8
```

### What uses the LLM

| Use case | Called from | LLM call |
|----------|-------------|----------|
| NPC dialogue response | `DialogueEngine.player_turn()` | 1 call per turn |
| Menu generation | `DialogueEngine._generate_menu()` | 1 call per turn (after NPC response) |
| History compression on demotion | `npc/tier.py::_compress_history()` | 1 call; only when demoting with `runner` arg |

### Inspecting LLM calls

```python
from llm.prompt_log import prompt_log

entries = prompt_log.recent(n=10, tag="type:compression")
for e in entries:
    e.runner_id       # str — e.g. "ollama"
    e.model           # str
    e.messages        # list[Message(role, content)]
    e.response        # str
    e.duration_ms     # float
    e.prompt_tokens   # int
    e.completion_tokens # int
    e.tags            # set[str]
    e.error           # str | None
```

### Message format

```python
from llm.types import Message, LLMOptions, LLMResponse

# Messages are plain dataclasses
Message(role="system", content="You are ...")
Message(role="user", content="What do you sell?")
Message(role="assistant", content="Iron goods, mostly.")

# Options (all optional)
LLMOptions(temperature=0.8, max_tokens=120, stop=["\n\n"])

# Call the runner directly
response: LLMResponse = runner.logged_chat(
    messages=[system_msg, user_msg],
    options=LLMOptions(max_tokens=120),
    tags={"type:dialogue", f"npc:{npc.id}"},
)
response.content         # str — the model's output
response.model           # str
response.prompt_tokens   # int
response.completion_tokens # int
response.duration_ms     # float
```

---

## 10. Data Flow Summary

```
Seed YAML
    ↓ load_world() → WorldGraph
    ↓ load_npcs()  → NPCRegistry + placement dict
    ↓ load_memory_store() → MemoryStore

Game loop tick:
  tick(registry, graph, action_registry, memory_store)
    → select_action() [GOAP-lite]
    → execute_action() [apply effects to WorldGraph]
    → _maybe_gossip() [MemoryEntry → KBEntry]
    → _drift_relationships()
    → event_log.emit()
    → director.tick(event_log)
    → TickResult [Python dataclass, not serialized]

Dialogue turn:
  retrieve_for_prompt() → MemoryExcerpts
  build_system_prompt(DialogueContext) → str
  engine.player_turn(session, input, ctx)
    → runner.logged_chat(messages) → LLMResponse
    → runner.logged_chat(menu_prompt) → LLMResponse
    → DialogueTurn [Python dataclass]

All data in memory as Python objects.
No serialization layer exists (JSON/protobuf/etc.) — not needed until persistence or network transport is added.
```

---

## 12. WebSocket Message Protocol

All messages are JSON objects with a `"type"` field. The server sends a response message for each request; some server messages are pushed without a prior client request.

### Client → Server

| `type` | Required fields | Description |
|--------|-----------------|-------------|
| `connect` | _(none)_ | First message after connection; triggers `full_state` response |
| `player_move` | `zone_id: str` | Move player to the named zone |
| `player_interact` | `npc_id: str` | Begin interaction with an NPC (does not start dialogue) |
| `dialogue_input` | `npc_id: str`, `text: str` | Send a player utterance to an active dialogue session |
| `dialogue_end` | `npc_id: str` | Close the dialogue session for this NPC |
| `get_affordances` | _(none)_ | Request the list of actions available to the player |
| `execute_action` | `action_id: str` | Execute a specific action as the player |
| `tick` | _(none)_ | Advance the simulation by one tick |

### Server → Client (responses)

| `type` | Sent in response to | Key fields |
|--------|---------------------|------------|
| `full_state` | `connect` | `zones`, `npcs`, `player`, `time` (see §13) |
| `move_result` | `player_move` | `success: bool`, `zone_id: str`, `error?: str` |
| `dialogue_start` | `player_interact` | `npc_id: str`, `npc_name: str` |
| `dialogue_response` | `dialogue_input` | `npc_id: str`, `text: str`, `menu_options: list[str]` |
| `dialogue_ended` | `dialogue_end` | `npc_id: str` |
| `affordance_list` | `get_affordances` | `actions: list[{id, name, category}]` |
| `action_result` | `execute_action` | `success: bool`, `action_id: str`, `produced: list[str]`, `consumed: list[str]`, `moved_to?: str` |
| `tick_result` | `tick` | `tick_number: int`, `actions_taken: int`, `npc_results: list[…]` |
| `error` | any | `message: str` |

### Server → Client (push, unsolicited)

| `type` | Trigger | Key fields |
|--------|---------|------------|
| `npc_moved` | NPC changes zone during a tick | `npc_id: str`, `from_zone: str`, `to_zone: str` |
| `world_event` | Significant event emitted to `event_log` | `event_type: str`, `description: str`, `severity: str` |
| `time_update` | Tick advances game time | `day: int`, `hour: int`, `period: str` |

---

## 13. `full_state` Payload Shape

The `full_state` message is the canonical snapshot sent on connect (and can be re-requested). Its `data` object has the following shape:

```json
{
  "type": "full_state",
  "data": {
    "zones": [
      {
        "id": "zone_uuid",
        "name": "The Forge",
        "description": "...",
        "terrain_type": "STRUCTURE",
        "tags": ["forge", "fire"],
        "connections": ["zone_uuid_2"],
        "npc_ids": ["npc_uuid"],
        "item_ids": ["item_uuid"]
      }
    ],
    "npcs": [
      {
        "id": "npc_uuid",
        "name": "Aldric",
        "role": "blacksmith",
        "tier": 2,
        "current_zone_id": "zone_uuid",
        "mood": 0.3,
        "is_player": false
      }
    ],
    "player": {
      "id": "player_uuid",
      "name": "Player",
      "current_zone_id": "zone_uuid",
      "skills": {"smithing": 0.4},
      "carried_item_ids": []
    },
    "time": {
      "day": 1,
      "hour": 9,
      "period": "morning"
    }
  }
}
```

`zones[].connections` lists zone IDs reachable via `CONNECTS` edges (i.e. traversable exits). The `npcs` array excludes the player entry; the player is always under the top-level `player` key.
