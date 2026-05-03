# Galatea — Architecture Reference

_Living document. Rewritten from source whenever the codebase changes. Last synced: build-order step 15 (complete)._

---

## 1. Module Layout

```
galatea/
├── config.py               # Pydantic Config singleton — all tunable constants
├── world/                  # WorldGraph, Zone, Item, Feature, terrain types, YAML loader
├── affordances/            # Action schema, ActionRegistry, precondition evaluator, query helpers
├── crafting/               # Quality model, recipe store, product DAG, bootstrap validator, confusion table, skill hook
├── npc/                    # NPC/Goal/Relationship schemas, NPCRegistry, tier promotion/demotion, YAML loader
├── llm/                    # LLMRunner abstract interface, Ollama adapter, StubRunner, PromptLog, factory
├── dialogue/               # System-prompt builder, speech-style generator, DialogueEngine, DialogueSession
├── knowledge/              # IndividualMemory, CommunityKB, MemoryStore, RAG retrieval, YAML loader
├── events/                 # EventLog ring buffer, EventType/EventSeverity enums, NPCRole
├── director/               # Director stub (passive), amplification primitives
├── sim/                    # GOAP-lite action selection, action executor, tick system
├── time/                   # Stub package — tick scheduling utilities (not yet implemented)
├── tools/                  # FastAPI + HTMX developer UI: AppState singleton, all route handlers
├── server/                 # WebSocket server (asyncio + websockets): protocol handlers, serializers
└── client/                 # Godot 4 project (not a Python module — see §1 note below)
```

> **`client/`** is a Godot 4.3 project (GDScript). It lives alongside the Python packages for repository convenience but is not imported by any Python code. See section 1 (module descriptions) and section 4 (dependency graph) for its relationship to `server/`.

### One-sentence descriptions

| Package | Responsibility |
|---------|----------------|
| `config` | Single Pydantic `Config` object (`settings` singleton) — all numeric thresholds and defaults live here; nothing else hardcodes these values |
| `world` | `WorldGraph` (NetworkX MultiDiGraph) holds zones, items, NPC locations, containment and passage edges; `Zone`/`Item`/`Feature` are the core spatial objects |
| `affordances` | `Action` schema with preconditions and effects; `ActionRegistry` loads and serves actions; `query.py` evaluates which actions are available to an actor in a zone |
| `crafting` | Quality formula, `RecipeStore` per-NPC, product dependency DAG, bootstrap validator, confusion-table support, player-skill-gate hook registry |
| `npc` | `NPC` Pydantic model (identity, traits, skills, goals, relationships); `NPCRegistry`; tier promotion/demotion logic with LLM-based history compression |
| `llm` | Abstract `LLMRunner` with `chat()` / `logged_chat()`; Ollama and stub adapters; `PromptLog` ring buffer; `get_runner()` factory |
| `dialogue` | Assembles the per-NPC system prompt from modular blocks; `speech_style_block()` derives voice from Big Five; `DialogueEngine` runs turn-by-turn LLM dialogue with menu generation |
| `knowledge` | Per-NPC `IndividualMemory` (salience-based eviction); `CommunityKB` (gossip KB); `MemoryStore` registry; RAG-lite retrieval scored by tag overlap, recency, salience |
| `events` | `EventLog` deque (max 2 000 entries); structured `EventEntry` with type, severity, NPC roles, payload, and director `amplification` hook field |
| `director` | Passive `Director` stub called each tick; `amplify.py` provides primitives — memory salience, KB gossip weight, goal nudging — used by dev-tool routes |
| `sim` | `select_action()` (GOAP-lite scoring); `execute_action()` applies effects to world graph; `tick()` runs one simulation step for all NPCs |
| `time` | Empty stub package; reserved for tick-scheduling utilities |
| `tools` | FastAPI dev server with HTMX UI; `AppState` loads and holds all singletons; route modules for world, NPC, DAG, dialogue, KB, events, tier, amplify, tick stepper |
| `server` | asyncio WebSocket server (websockets library); single-client mode; `handlers.py` dispatches each message type; `serializers.py` converts Python objects to JSON; `__main__.py` is the entry point (`python -m server`) |
| `client` | Godot 4.3 project — GDScript autoloads (`GameBridge`, `GameState`), scene files (main, world, player, NPC, dialogue UI, HUD), and input action definitions. Connects to `server` via WebSocket. Not a Python package. |

---

## 2. Key Data Structures

### `Zone` (`world/zone.py`)
```python
class Zone(BaseModel):
    id: str                                      # UUID default
    name: str
    description: str = ""
    terrain_type: TerrainType = TerrainType.GROUND
    tags: set[str]                               # author-assigned affordance tags
    properties: dict[str, PropertyValue]
    features: list[Feature]                      # embedded sub-objects (forge, counter, etc.)
    item_ids: list[str]                          # IDs of Items currently in this zone
    npc_ids: list[str]                           # IDs of NPCs currently in this zone
    owner_ids: list[str]
    appearance: str | None                       # prose injected into dialogue scene block

    def effective_tags(item_registry, npc_tag_map) -> set[str]
    # own tags + feature tags + item tags (from registry) + NPC tags (from map)
```

### `Item` (`world/zone.py`)
```python
class Item(BaseModel):
    id: str
    name: str
    item_type: str                   # e.g. "iron_blade", "iron_ore"
    tags: set[str]
    properties: dict[str, PropertyValue]
    quality: float = 1.0             # 0.0–1.0
    quantity: int = 1
    owner_id: str | None
    # NOTE: no zone_id field — placement tracked via Zone.item_ids + WorldGraph
```

### `Feature` (`world/zone.py`)
```python
class Feature(BaseModel):
    id: str
    name: str
    description: str = ""
    tags: set[str]                   # contribute to zone's effective_tags
    properties: dict[str, PropertyValue]
    quality: float = 1.0
```

### `Action` (`affordances/schema.py`)
```python
class Action(BaseModel):
    id: str
    name: str
    description: str = ""
    category: ActionCategory         # GATHERING | CRAFTING | SOCIAL | MOVEMENT
    preconditions: Precondition      # single root node; use AndPrecondition([]) for always-true
    effects: list[Effect]
    tags: set[str]
    parameters: list[ParameterDef]
    step_list: list[ActionStep]      # ordered sub-steps; empty = atomic action
    player_skill_gate: PlayerSkillGate | None
    confusion_table: ConfusionTable | None

    @property total_time_hours -> float
    @property is_parametric -> bool
```

Precondition union (discriminated on `type`):
- `NearbyTagPrecondition(tag, hops=1)`
- `ZoneHasTagPrecondition(tag)`
- `ActorHasItemPrecondition(item_type, quantity)`
- `ZoneHasItemPrecondition(item_type, quantity)`
- `ActorSkillPrecondition(skill, min_value)`
- `ActorKnowsRecipePrecondition(recipe_id)`
- `NpcPresentPrecondition(role?)`
- `ZoneIsAccessiblePrecondition()`
- `AndPrecondition(conditions: list[Precondition])`
- `OrPrecondition(conditions: list[Precondition])`
- `NotPrecondition(condition: Precondition)`

Effect union (discriminated on `type`):
- `ProducesEffect(item_type, quantity, quality_fn)`
- `ConsumesEffect(item_type, quantity, from_actor)`
- `AdvancesSkillEffect(skill, amount)`
- `TimeCostEffect(game_hours)`
- `NoiseEffect(level)`
- `TeachesRecipeEffect(recipe_id)`
- `MovesActorEffect(to_zone)`
- `RelationshipEffect(target, delta)`

### `NPC` (`npc/schema.py`)
```python
class NPC(BaseModel):
    id: str
    name: str
    role: str
    description: str = ""
    is_player: bool = False
    tier: NPCTier                    # T0=0 … T3=3; governs simulation fidelity
    big_five: BigFive                # openness/conscientiousness/extraversion/agreeableness/neuroticism (0–1)
    trait_tags: list[str]            # e.g. ["gruff", "pious", "ambitious"]
    skills: dict[str, float]         # skill_name → 0.0–1.0
    known_recipes: RecipeStore
    values: list[str]                # e.g. ["family", "craft", "loyalty"]
    goals: list[Goal]
    relationships: dict[str, Relationship]   # keyed by other NPC id
    physical: PhysicalTraits
    current_zone_id: str | None
    mood: float                      # -1.0–1.0
    carried_item_ids: list[str]
    reach_score: float = 0.0         # last computed score; drives auto promotion/demotion
    narrative_summary: str = ""      # LLM-compressed history; injected into prompt after demotion

    def active_goals() -> list[Goal]
    def add_goal(description, priority) -> Goal
    def effective_tags() -> set[str]    # role + trait_tags + tier tag
    def as_actor_context(graph?) -> ActorContext
```

### `Goal` (`npc/schema.py`)
```python
class Goal(BaseModel):
    id: str
    description: str
    priority: GoalPriority           # HIGH | MEDIUM | LOW
    status: GoalStatus               # ACTIVE | COMPLETED | ABANDONED
    planned_actions: list[str]       # ordered action IDs for GOAP execution chain
```

### `Relationship` (`npc/schema.py`)
```python
class Relationship(BaseModel):
    other_id: str
    affinity: float      # -1.0–1.0; drifts ±0.02/tick off-screen
    trust: float         # 0.0–1.0
    familiarity: float   # 0.0–1.0
    tags: set[str]       # e.g. {"rival", "mentor"}
```

### `MemoryEntry` (`knowledge/memory.py`)
```python
@dataclass
class MemoryEntry:
    npc_id: str
    content: str                         # prose description of the memory
    id: str                              # 10-char hex
    timestamp: datetime
    salience: float = 1.0                # higher = more important; drives retrieval scoring + eviction
    topic_tags: set[str]
    involved_npc_ids: set[str]
    involved_zone_id: str | None
    source: str = "observed"
```

### `KBEntry` (`knowledge/community_kb.py`)
```python
@dataclass
class KBEntry:
    content: str
    id: str
    timestamp: datetime
    topic_tags: set[str]
    involved_npc_ids: set[str]
    involved_zone_id: str | None
    source_npc_id: str | None
    gossip_weight: float = 1.0      # director hook; higher = retrieved more often + gossip priority
```

### `EventEntry` (`events/log.py`)
```python
@dataclass
class EventEntry:
    event_type: EventType            # DIALOGUE | RELATIONSHIP | MOVE | TIER_CHANGE | GOAL_SET |
                                     # GOAL_COMPLETED | GOAL_ABANDONED | CRAFT_SUCCESS |
                                     # CRAFT_FAILURE | RECIPE_LEARNED | RECIPE_LOST |
                                     # GATHER | TRADE | GENERIC
    description: str
    id: str                          # 12-char hex
    timestamp: datetime
    npc_roles: list[NPCRole]         # NPCRole(npc_id, role) — e.g. role="actor", "subject"
    zone_id: str | None
    severity: EventSeverity          # TRIVIAL | MINOR | MODERATE | MAJOR | CRITICAL
    tags: set[str]
    payload: dict
    amplification: float = 1.0       # director hook; reserved for scoring weight
```

### `PromptLogEntry` (`llm/types.py`)
```python
@dataclass
class PromptLogEntry:
    runner_id: str
    model: str
    messages: list[Message]
    response: str
    id: str
    timestamp: datetime
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float
    tags: set[str]
    error: str | None
```

---

## 3. Public API Surface by Module

### `world`
```python
# world/graph.py
WorldGraph()
  .add_zone(zone)  .get_zone(zone_id) -> Zone  .zones() -> Iterator[Zone]
  .add_item(item)  .get_item(item_id) -> Item | None  .remove_item(item_id)
  .items_in_zone(zone_id) -> list[Item]
  .set_parent(child_id, parent_id)  .parent(zone_id) -> Zone | None
  .children(zone_id) -> list[Zone]  .all_descendants(zone_id) -> list[Zone]
  .add_connection(a_id, b_id, label="")
  .connections(zone_id) -> list[Zone]
  .neighbors_within(zone_id, hops=1) -> set[str]
  .effective_tags(zone_id, npc_tag_map?) -> set[str]
  .effective_tags_in_radius(zone_id, hops, npc_tag_map?) -> set[str]
  .zones_with_tag(tag, npc_tag_map?) -> list[Zone]
  .place_npc(npc_id, zone_id)  .move_npc(npc_id, to_zone_id)  .npc_location(npc_id) -> Zone | None
  .place_item(item_id, zone_id)  .move_item(item_id, to_zone_id)  .item_location(item_id) -> Zone | None
  .shortest_path(from_id, to_id) -> list[str] | None
  .summary(zone_id) -> dict

# world/loader.py
load_world(seed_path: Path | str) -> WorldGraph
```

### `affordances`
```python
# affordances/registry.py
ActionRegistry.from_yaml(path) -> ActionRegistry
  .get(action_id) -> Action   .get_or_none(action_id) -> Action | None
  .all_actions() -> list[Action]
  .by_category(category) -> list[Action]
  .by_tag(tag) -> list[Action]
  .produces_item_type(item_type) -> list[Action]
  .consumes_item_type(item_type) -> list[Action]
  .all_produced_item_types() -> set[str]
  .required_tags(action_id) -> set[str]
  ._register(action)    # programmatic registration (tests only)

# affordances/query.py
evaluate_precondition(precond, ctx: EvalContext) -> bool
what_can_actor_do(actor, zone_id, graph, registry, nearby_hops, npc_tag_map?) -> list[Action]
actions_available_in_zone(zone_id, graph, registry, nearby_hops) -> list[Action]
where_can_action_be_done(action, graph, nearby_hops) -> list[Zone]
```

### `crafting`
```python
# crafting/quality.py
compute_quality(inputs: QualityInputs, policy: QualityPolicy = DEFAULT_POLICY) -> float
policy_registry = QualityPolicyRegistry()

# crafting/dag.py
build_item_dag(registry) -> nx.DiGraph
dependency_chain(item_type, dag) -> list[str]
raw_materials_for(item_type, dag) -> set[str]
dependency_tree(item_type, dag, registry) -> dict
detect_cycles(dag) -> list[list[str]]
validate_dag(registry) -> list[DAGIssue]

# crafting/bootstrap.py
validate_world(registry, graph) -> BootstrapResult

# crafting/skill_hook.py
skill_hook_registry = PlayerSkillHookRegistry()
  .register(type_id, fn?)
  .resolve(type_id, difficulty, character_skill) -> float

# crafting/confusion.py
resolve_confusion(table, character_skill, rng?) -> str   # returns chosen output item_type
```

### `npc`
```python
# npc/registry.py
NPCRegistry()
  .register(npc)
  .get(npc_id) -> NPC   .get_or_none(npc_id) -> NPC | None
  .all_npcs() -> list[NPC]
  .by_tier(tier) -> list[NPC]   .by_tier_min(min_tier) -> list[NPC]
  .by_role(role) -> list[NPC]
  .player() -> NPC | None
  .npcs_in_zone(zone_id, graph) -> list[NPC]
  .build_npc_tag_map() -> dict[str, set[str]]
  .place_all_in_world(graph, placements: dict[npc_id, zone_id])

# npc/loader.py
load_npcs(seed_path, graph?) -> tuple[NPCRegistry, dict[str, str]]

# npc/tier.py
compute_reach_score(npc, memory: IndividualMemory) -> float
promote(npc, store) -> TierChangeResult | None
demote(npc, store, runner?) -> TierChangeResult | None
force_tier(npc, store, new_tier, runner?) -> TierChangeResult
PROMOTE_THRESHOLD: dict[int, float]   # populated from config.settings.tier
DEMOTE_THRESHOLD: dict[int, float]    # populated from config.settings.tier
```

### `llm`
```python
# llm/runner.py
class LLMRunner(ABC):
    .chat(messages, options?) -> LLMResponse          # must override
    .logged_chat(messages, options?, tags?) -> LLMResponse   # calls chat + logs
    async .async_logged_chat(...)  -> LLMResponse

# llm/factory.py
get_runner() -> LLMRunner    # returns cached runner; creates from config on first call
set_runner(runner)           # override (tests, dev)
reset_runner()               # clear cached runner

# llm/prompt_log.py
prompt_log = PromptLog(max_entries=500)
  .record(entry)
  .recent(n=100, tag?) -> list[PromptLogEntry]
  .get(entry_id) -> PromptLogEntry | None
```

### `dialogue`
```python
# dialogue/prompt_builder.py
build_system_prompt(ctx: DialogueContext) -> str
affordance_digest(actions: list[Action]) -> str

# dialogue/speech_style.py
speech_style_block(big_five, trait_tags, values?) -> str

# dialogue/engine.py
DialogueEngine(runner: LLMRunner)
  .player_turn(session, player_input, ctx) -> DialogueTurn
```

### `knowledge`
```python
# knowledge/store.py
MemoryStore()
  .register_npc(npc_id, tier) -> IndividualMemory  # sets capacity per TIER_MAX_ENTRIES
  .get(npc_id) -> IndividualMemory                 # lazy-creates with max=0 if unknown
  .community_kb: CommunityKB

# knowledge/retrieval.py
retrieve_for_prompt(store, npc_id, query: RetrievalQuery,
                    max_individual=8, max_community=6) -> MemoryExcerpts

# knowledge/loader.py
load_memory_store(seed_path, npc_registry) -> MemoryStore

# knowledge/memory.py
TIER_MAX_ENTRIES = {0: 0, 1: 5, 2: 25, 3: 200}
```

### `events`
```python
# events/log.py
event_log = EventLog(max_entries=2000)    # module-level singleton
  .emit(event_type, description, *, npc_roles?, zone_id?, severity?, tags?, payload?, amplification?) -> EventEntry
  .recent(n=50) -> list[EventEntry]
  .by_type(event_type) / .by_npc(npc_id) / .by_zone(zone_id) / .by_tag(tag) / .by_severity(min) / .since(ts)
```

### `director`
```python
# director/director.py
director = Director()   # module-level singleton; called by tick
  .tick(log: EventLog) -> None   # currently a no-op stub

# director/amplify.py
set_memory_salience(store, npc_id, memory_id, salience) -> bool
boost_kb_entry(kb, entry_id, gossip_weight) -> bool
nudge_goal(npc, description, priority=HIGH) -> Goal
clear_nudged_goals(npc) -> int    # abandons HIGH-priority, no-planned-actions, ACTIVE goals
```

### `sim`
```python
# sim/goap.py
select_action(npc, zone_id, graph, registry, npc_tag_map?) -> Action | None

# sim/action_executor.py
execute_action(npc, action, graph) -> ExecutionResult

# sim/tick.py
tick(registry, graph, action_registry, memory_store) -> TickResult
current_tick() -> int
reset_tick_count()    # test helper

T1_ACTION_PROBABILITY   # from config.settings.sim
GOSSIP_PROBABILITY      # from config.settings.sim
REL_DRIFT_MAGNITUDE     # from config.settings.sim
```

### `tools`
```python
# tools/state.py
get_state() -> AppState         # returns or creates module-level singleton
reload_state(seed_path?) -> AppState  # also calls event_log.clear() and reset_tick_count()

@dataclass AppState:
    graph: WorldGraph
    npc_registry: NPCRegistry
    action_registry: ActionRegistry
    item_dag: nx.DiGraph
    bootstrap_result: BootstrapResult
    memory_store: MemoryStore
    seed_path: Path
    .load(seed_path?) -> AppState   # classmethod; loads world + NPCs + memories
```

### `server`
```python
# server/__main__.py  (entry point: python -m server)
# CLI args: --port 8765  --seed PATH  --stub / --no-stub  --auto-tick  --tick-interval SECONDS
# Starts a single-client asyncio WebSocket server; blocks until interrupted.

# server/handlers.py  (one coroutine per client→server message type)
handle_connect(payload, state) -> dict
handle_player_move(payload, state) -> dict
handle_player_interact(payload, state) -> dict
handle_dialogue_input(payload, state, sessions) -> dict
handle_dialogue_end(payload, sessions) -> dict
handle_get_affordances(payload, state) -> dict
handle_execute_action(payload, state) -> dict
handle_tick(payload, state) -> dict

# server/serializers.py
serialize_full_state(state) -> dict
serialize_zone(zone, graph) -> dict
serialize_npc(npc) -> dict
serialize_player(npc) -> dict
serialize_tick_result(result) -> dict
_game_time() -> dict   # {"day": int, "hour": int, "period": str}
```

---

## 4. Module Dependency Graph

```
config          (no internal deps)
world           → config (none currently; terrain types self-contained)
affordances     → world
crafting        → affordances, world, config
npc             → crafting (RecipeStore), config
llm             → config
knowledge       → npc (registry, for loader)
events          (no internal deps)
director        → knowledge, npc
dialogue        → affordances, npc, llm, config
sim             → affordances, npc, knowledge, events, director, world, config
npc/tier        → config, knowledge, llm, npc
tools/state     → world, affordances, crafting, npc, knowledge, events, sim
tools/routes/*  → tools/state, plus relevant domain modules
server          → tools.state, llm.factory, dialogue.engine, dialogue.prompt_builder,
                  knowledge.retrieval, sim.tick, events.log, npc.schema,
                  affordances.query, sim.action_executor
client          → server (WebSocket over network — no Python import relationship)
```

Cycle-free. `config` and `events` are leaves with no internal imports. `client` is a Godot project and has no Python import relationship; its only coupling to the Python codebase is the WebSocket protocol spoken by `server`.

---

## 5. Design Decisions That Deviate from or Extend the Spec

### D1 — `config.py` is the single source for all tunable numbers
**Spec implication:** Thresholds scattered across modules.
**Implemented:** `npc/tier.py` reads `PROMOTE_THRESHOLD`/`DEMOTE_THRESHOLD` from `config.settings.tier` at import time. `sim/tick.py` reads `T1_ACTION_PROBABILITY`, `GOSSIP_PROBABILITY`, `REL_DRIFT_MAGNITUDE` from `config.settings.sim`. All numeric defaults live in one place.

### D2 — `Action.preconditions` is a single `Precondition` node, not a list
**Spec:** Ambiguous.
**Implemented:** One root node; use `AndPrecondition(conditions=[])` for unconditional.

### D3 — Item placement tracked by `Zone.item_ids`, not by an `Item.zone_id` field
**Spec:** Unspecified.
**Implemented:** `Item` has no `zone_id`. Placement is via `graph.place_item(item_id, zone_id)` which appends to `zone.item_ids`. `graph.item_location()` scans all zones. This keeps the graph as the authoritative location store.

### D4 — Community KB is loaded from seed YAML and frozen at runtime
**Spec §9:** "Community knowledge base" without specifying mutability.
**Implemented:** KB entries can only enter at seed-load time or via the gossip mechanism (salient NPC memory propagating during tick). There is no runtime API to add arbitrary KB entries except through `director/amplify.py`'s `boost_kb_entry()` (which modifies weight, not creates entries). This was a deliberate simplification.
**Correction:** Actually the tick's `_maybe_gossip()` and the amplify route can inject entries. The KB is not fully frozen — new entries can arrive via gossip. But there is no player-visible "KB write" API.

### D5 — GOAP-lite uses keyword token scoring, not a proper STRIPS planner
**Spec §14:** "GOAP-lite."
**Implemented:** `_score_action()` tokenizes action id/name and adds category-specific tokens (e.g. "craft" for CRAFTING), then intersects with goal description tokens. Priority multiplier: HIGH=3, MEDIUM=2, LOW=1. `planned_actions` chain on a goal is respected first (pop front). No backward-chaining or cost minimization.

### D6 — `AdvancesSkillEffect` and `MovesActorEffect` are handled off-screen; social/noise effects are ignored
**Spec §14:** All effects listed.
**Implemented:** `execute_action()` handles Produces, Consumes, AdvancesSkill, MovesActor. `TeachesRecipeEffect`, `RelationshipEffect`, `NoiseEffect`, `TimeCostEffect` are silently skipped for off-screen ticks. Comment in source says "skipped at MVP."

### D7 — `WorldGraph` uses `nx.MultiDiGraph`, not `DiGraph`
**Spec:** Unspecified.
**Rationale:** A zone can have both a `CONTAINS` edge and a `CONNECTS` edge to the same neighbor (e.g. a smithy is inside a village and also passable from it). `DiGraph` would silently overwrite one edge type.

### D8 — Tier thresholds: implemented values differ from spec examples
**Spec §10:** Examples used high round numbers.
**Implemented:** `promote_t0=2.0, promote_t1=5.0, promote_t2=12.0` / `demote_t1=1.0, demote_t2=3.0, demote_t3=8.0`. These are lower than any spec examples but are what the test suite was designed around. Can be overridden via `config.settings`.

### D9 — `dialogue/routes` holds session state in a module-level dict
**Spec:** No guidance on session management.
**Implemented:** `_sessions: dict[str, DialogueSession]` in `tools/routes/dialogue.py`. One session per NPC ID. Resets are manual (dev-tool button). Not suitable for multi-user or persistent sessions.

### D10 — No SQLite persistence
**Spec §18 (persistence):** SQLModel + SQLite mentioned.
**Implemented:** Everything is in-memory. `AppState.load()` reconstructs from YAML on every server start. Persistence is not started.

### D11 — WebSocket server is single-client, not multi-user
**Rationale:** Galatea's `AppState` is a single shared Python object with no locking. Allowing concurrent WebSocket clients would cause race conditions on world state. The server accepts one connection at a time and closes it cleanly before accepting the next. Multi-user support would require per-session state isolation, which is out of scope for the current build.

### D12 — Godot client uses zone-based screen transitions, not a continuous tilemap
**Rationale:** The world model is a graph of named zones, not a 2-D coordinate grid. Rendering it as a continuous scrolling tilemap would require faking spatial coordinates that don't exist in the data model. Instead each zone is a discrete screen (rendered by `ZoneRenderer`); moving between zones triggers a full scene swap. This keeps the client's view of the world consistent with the server's.

### D13 — `StubRunner` is the default in `python -m server`; `--no-stub` opts into Ollama
**Rationale:** Requiring a running Ollama instance blocks iteration on the client and protocol. The server defaults to `StubRunner` so the Godot client can complete the full round-trip (connect → move → interact → dialogue → tick) without any LLM infrastructure. Pass `--no-stub` (or set `--no-stub` in `run_dev.sh`) to enable live LLM responses.
