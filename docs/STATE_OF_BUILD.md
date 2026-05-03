# Galatea — State of Build

_Status snapshot as of build-order step 15 (complete). 318 passing tests._

---

## 1. What's Built and Working

### Solid (well-tested, no known gaps)

| Component | Notes |
|-----------|-------|
| **World graph** (`world/`) | Zone schema, Item, Feature, terrain types. NetworkX MultiDiGraph with CONTAINS and CONNECTS edges. Loader from YAML. All spatial queries working: containment, adjacency, tag union, shortest path. |
| **Affordance schema** (`affordances/schema.py`) | Complete Action/Effect/Precondition type hierarchy. Pydantic discriminated unions with all 11 precondition types and 8 effect types. |
| **ActionRegistry** (`affordances/registry.py`) | YAML loading, all query methods (by category, by tag, produces/consumes). |
| **Precondition evaluator** (`affordances/query.py`) | `evaluate_precondition()` handles all types including And/Or/Not composites. `what_can_actor_do()` and `actions_available_in_zone()` work correctly. |
| **Quality model** (`crafting/quality.py`) | Weighted formula, per-action policy override via `QualityPolicyRegistry`, `player_performance` hook slot. |
| **Product DAG** (`crafting/dag.py`) | Builds item dependency graph from registry; cycle detection; raw material query; dependency tree. |
| **Bootstrap validator** (`crafting/bootstrap.py`) | Three-pass validation (DAG cycles, gathering tool reachability, crafting ingredient reachability). Returns structured `BootstrapResult`. |
| **NPC schema** (`npc/schema.py`) | Full `NPC` model with Big Five, goals, relationships, skills, recipes, tier. All computed properties work. |
| **NPCRegistry** (`npc/registry.py`) | All query/filter methods. `build_npc_tag_map()` for effective-tag propagation. YAML loader. |
| **LLM layer** (`llm/`) | Abstract `LLMRunner`, Ollama adapter, `StubRunner` for tests, `PromptLog` ring buffer, `get_runner()` factory. |
| **Dialogue system** (`dialogue/`) | `build_system_prompt()` with all 6 blocks (world, identity + goals, speech style, memory, scene, constraints). `speech_style_block()` with full Big Five + 27 trait hints + 19 value hints + 5 combination effects. `DialogueEngine` with menu generation. |
| **Memory store** (`knowledge/`) | `IndividualMemory` with salience-based eviction (heap), tier-governed capacity. `CommunityKB`. `MemoryStore` registry. YAML loader. |
| **RAG retrieval** (`knowledge/retrieval.py`) | Scored retrieval for individual + community entries. Scoring: `tag_overlap + npc_overlap*2 + salience*1.5 + recency_decay + zone_bonus`. |
| **Tier system** (`npc/tier.py`) | `compute_reach_score()`, `promote()`, `demote()`, `force_tier()`, LLM history compression with fallback. All thresholds read from `config.settings.tier`. |
| **Event log** (`events/log.py`) | Ring buffer (max 2 000), all filter methods, `emit()` convenience wrapper, `clear()` method for resets. |
| **Director stub** (`director/`) | Wired into tick, reads recent events, applies nothing — intentional stub. |
| **Amplification primitives** (`director/amplify.py`) | `set_memory_salience`, `boost_kb_entry`, `nudge_goal`, `clear_nudged_goals` — all implemented and exposed via dev-tool routes. |
| **GOAP-lite** (`sim/goap.py`) | Keyword-token scoring against active goals. `planned_actions` chain respected first. Stochastic fallback when no goal match. |
| **Action executor** (`sim/action_executor.py`) | Produces (quality-weighted item creation + zone placement), Consumes (carried or zone), AdvancesSkill (capped 1.0), MovesActor. |
| **Tick system** (`sim/tick.py`) | T0 skip, T1 stochastic (configurable probability), T2+ always. Gossip phase. Relationship drift. Event emission. Director hook. All tick params from `config.settings.sim`. |
| **Developer UI** (`tools/`) | FastAPI + HTMX + Jinja2 + Pico CSS dark theme. All 11 route groups registered and functional. |
| **Config** (`config.py`) | `TierConfig`, `SimConfig`, `LLMConfig`, `TimeConfig`, `CraftingConfig` all wired to consuming modules. |
| **WebSocket server** (`server/`) | asyncio + websockets; single-client mode; full message protocol (connect, move, interact, dialogue, tick, affordances, action). StubRunner on by default. `python -m server` entry point with CLI args. `test_client.py` bridge validator included. |
| **Godot client skeleton** (`client/`) | Godot 4.3 project. Scenes: main, world, player, NPC, dialogue UI, HUD. Scripts: `GameBridge` WebSocket autoload, `GameState` cache, `WorldManager`, `ZoneRenderer`, `NpcController`, `PlayerController`, `DialogueUI`, `HUD`, `ActionMenu`. Input actions wired. Colored-rect rendering (no image assets). |

### Works but fragile or shallow

| Component | Fragility |
|-----------|-----------|
| **Dialogue route** (`tools/routes/dialogue.py`) | Session stored in module-level dict keyed by NPC id. Two simultaneous users hitting the same NPC would corrupt each other's session. Acceptable for single-user dev tool; not for production. |
| **NPC interaction area detection** (`client/scripts/world/zone_renderer.gd`) | NPC body-entered signals can't easily bubble up to `WorldManager` through the instanced scene boundary, so the implementation uses `propagate_call()` as a workaround to invoke handlers on the parent. Functional but brittle — breaks if scene hierarchy changes. |
| **LLM factory** (`llm/factory.py`) | `get_runner()` constructs from `config.settings.llm.default_runner`. Only "ollama" is supported; any other value throws. No retry or circuit-breaker. |
| **Ollama adapter** (`llm/ollama_runner.py`) | Synchronous HTTP calls via the `ollama` Python SDK. Long generation blocks the event loop for async routes. Works in practice for the single-user dev tool. |
| **Gossip propagation** | The `_maybe_gossip()` logic in `sim/tick.py` uses the module-level `event_log` directly (not injected), and the `GOSSIP_PROBABILITY` check happens independently per NPC per tick — there's no global cap on how much gossip floods the KB per tick. |
| **`AppState.load()`** | Loads world, NPCs, then memories sequentially from the same seed YAML file. If the seed file is malformed, it raises unhandled exceptions that crash the server rather than returning a validation error. |

### Stubbed / intentionally incomplete

| Component | Status |
|-----------|--------|
| **Director logic** | `Director.tick()` reads the last 100 events and does nothing. The TODO comment is intentional — real scoring logic will slot in without changing callers. |
| **`time/` package** | Empty stub (`__init__.py` only). Reserved for tick-scheduling utilities (real-time wall-clock advancement, pause/resume). Not started. |
| **`TeachesRecipeEffect`** in off-screen tick | The effect type exists in the schema but `execute_action()` silently skips it. Off-screen recipe learning is not implemented. |
| **`RelationshipEffect`** in off-screen tick | Same — skipped. Relationship drift is the only off-screen social simulation. |
| **Confusion table resolution** in off-screen tick | `crafting/confusion.py` is implemented but never called from `execute_action()`. |
| **`TimeConfig`** | The tick time model (`real_seconds_per_tick`, etc.) is defined in config but nothing consumes it. Real-time advancement is not wired. |

---

## 2. Known Bugs and Limitations

1. **`_maybe_gossip` uses a module-level `event_log`** — `sim/tick.py::_maybe_gossip()` emits via the module-level `event_log` singleton rather than receiving it as a parameter. This makes it hard to test in isolation and creates an implicit global dependency.

2. **Memory retrieval has no deduplication** — `retrieve_for_prompt()` can return the same content from both individual and community memory if a memory was gossiped. The prompt receives duplicated text.

3. **Off-screen skill advancement is unbounded in practice** — `AdvancesSkillEffect` is capped at 1.0 per execution, but nothing prevents an NPC from practicing the same skill every tick until capped. There's no diminishing-returns or time-gate.

4. **`WorldGraph.npc_location()` is O(zones)** — scans every zone's `npc_ids` list. Fine at current scale; will degrade with hundreds of zones.

5. **No validation that NPC's `current_zone_id` matches `WorldGraph` placement** — they can drift out of sync if only one is updated.

6. **`reload_state()` does not reset the event log or tick counter** — FIXED. `reload_state()` now calls `event_log.clear()` and `reset_tick_count()` after loading state, so reloads start with a clean slate.

7. **No actual art assets** — the Godot client uses colored rectangles for all NPC and terrain rendering. Zone terrain colors are defined in `zone_renderer.gd`; no sprite sheets or tilesets exist yet.

8. **Server is single-client only** — `python -m server` accepts one WebSocket connection at a time. A second client connecting will wait until the first disconnects.

9. **Dialogue sessions in the server are in-memory** — `server/handlers.py` holds active `DialogueSession` objects in a dict keyed by NPC id. Sessions are lost on disconnect or server restart. There is no persistence or handoff mechanism.

---

## 3. Judgment Calls Made During Implementation

### J1 — Salience-based eviction for `IndividualMemory`, not FIFO
FIFO would be simpler. Salience-based eviction means the director can keep important memories alive by boosting their salience. This is the semantics the spec implies but doesn't specify explicitly. The implementation uses a min-heap on salience, evicting the lowest-salience entry when at capacity.

### J2 — `action.preconditions` is a single root node, not `list[Precondition]`
The spec's YAML examples were ambiguous. A single root `AndPrecondition` composes cleanly; a list would be implicitly an AND without being explicit. Chose single node with `AndPrecondition(conditions=[])` as the always-true sentinel.

### J3 — `Item` has no `zone_id` field
Keeping location tracking in `WorldGraph` (via `Zone.item_ids`) rather than on the `Item` itself avoids dual-write bugs and keeps the graph as the single authoritative location store. Downside: `item_location()` is O(zones).

### J4 — Community KB is effectively append-only at runtime
New entries come from seed YAML and gossip. There's no "remove stale knowledge" mechanism. This was the simplest correct behavior — the spec doesn't describe KB expiry, and building it wrong seemed worse than leaving it out.

### J5 — `GOAP-lite` does keyword overlap, not backward-chaining
Full backward-chaining GOAP is expensive and would require a complete world-state representation. The keyword approach gets the behavioral intent right (NPC with "smith a blade" goal selects smithing actions) while remaining simple and debuggable.

### J6 — `planned_actions` is consumed front-to-back and cleared when exhausted
When a goal has `planned_actions = ["gather_ore", "smith_blade"]`, the first tick picks `gather_ore` (popping it), the second picks `smith_blade`. When empty, GOAP scoring resumes. This is a simple action-queue model, not re-planning.

### J7 — Compression fallback is last-3 entries joined by `"; "`
When the LLM fails during demotion compression, the fallback is deterministic and produces a usable if unsophisticated summary. The alternative (empty string) would silently lose information.

---

## 4. Spec Section Coverage

| § | Title | Status | Notes |
|---|-------|--------|-------|
| 1 | Vision | — | Design only |
| 2 | Constraints | — | Design only |
| 3 | World graph | ✅ Full | Zone, Item, Feature, containment, adjacency, tags |
| 4 | Terrain types | ✅ Full | `TerrainType` StrEnum, 10 values |
| 5 | Affordances | ✅ Full | Action schema, preconditions, effects, registry |
| 6 | Crafting system | ✅ Full | Quality, recipes, DAG, bootstrap, step list, confusion table, skill hook |
| 7 | NPC schema | ✅ Full | BigFive, tier, goals, relationships, skills, traits |
| 8 | Dialogue | ✅ Full | Prompt builder, speech style, engine, menu generation |
| 9 | Memory | ✅ Full | Individual + community KB, salience eviction, RAG retrieval |
| 10 | Tier system | ✅ Full | Reach score, promote/demote, LLM compression |
| 11 | Speech/traits | ✅ Full | Big Five bands, trait tags, value hints, combination effects |
| 12 | Events | ✅ Full | EventLog, all types/severities, NPCRole, director amplification field |
| 13 | Director / amplification | ✅ Full | Primitives implemented; Director.tick() is intentional stub |
| 14 | Off-screen tick | ✅ Full | GOAP-lite, execute_action, tick system; some effects skipped (see §2) |
| 15 | Player skill gates | ✅ Schema + hook | `PlayerSkillGate` in schema; `skill_hook_registry` implemented; not invoked in off-screen tick |
| 16 | Confusion tables | ✅ Schema + logic | `ConfusionTable`/`resolve_confusion()` implemented; not wired into off-screen executor |
| 17 | Open design questions | — | Design only; answers embedded in implementation |
| 18 | Persistence (SQLite) | ❌ Not started | Everything is in-memory; seed YAML reloads on server restart |
| 19 | Build order | ✅ Steps 1–15 | All build-order steps complete |
| 20 | How to proceed | — | Process guidance only |
| Phase 0 | WebSocket bridge + Godot client | 🔄 Skeleton complete | Full message protocol implemented; scenes and scripts in place; end-to-end test with a running Godot editor instance pending |
