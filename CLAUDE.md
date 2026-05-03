# Galatea — Claude Code context

Medieval life simulator with LLM-driven NPCs. Source of truth for the design is `galatea_spec.md`.

## Running things

```bash
# Install deps and run dev server
~/.local/bin/uv run uvicorn tools.app:app --reload

# Run tests
~/.local/bin/uv run pytest tests/ -q
```

The developer UI lives at `http://localhost:8000` and exposes world inspection, NPC dashboards, dialogue sandboxing, knowledge base, event log, and tick stepper.

## Package layout

| Package | Purpose |
|---------|---------|
| `world/` | `WorldGraph` (NetworkX MultiDiGraph), `Zone`, `Item`, YAML loader |
| `affordances/` | `Action` schema, `ActionRegistry`, precondition evaluator |
| `crafting/` | Quality formula, recipe DAG, bootstrap validator |
| `npc/` | `NPC`/`BigFive`/`Goal` schemas, `NPCRegistry`, tier promotion/demotion |
| `llm/` | `LLMRunner` abstract interface, Ollama + stub adapters, `PromptLog` |
| `dialogue/` | `build_system_prompt()`, `speech_style_block()`, dialogue endpoint |
| `knowledge/` | `IndividualMemory`, `CommunityKB`, `MemoryStore`, RAG retrieval, YAML loader |
| `events/` | `EventLog` ring buffer, `EventType`/`EventSeverity` enums |
| `director/` | `Director` stub (wired, passive), amplification primitives |
| `sim/` | GOAP-lite action selection, `execute_action()`, tick system |
| `time/` | Tick scheduling utilities (stub) |
| `tools/` | FastAPI + HTMX + Jinja2 developer UI; `AppState` singleton |
| `config.py` | Pydantic `Config` with `settings` singleton — all tunable constants live here |

## Key invariants

- **`config.settings` is the single source of truth** for all tunable numbers. `npc/tier.py` and `sim/tick.py` both read from it at import time; do not hardcode thresholds elsewhere.
- **`Action.preconditions`** is a single `Precondition` object (not a list). Use `AndPrecondition(conditions=[])` for an always-true precondition in tests.
- **`Item` has no `zone_id` field** — placement is tracked by `Zone.item_ids` via `graph.place_item(item.id, zone_id)`.
- **`ActionRegistry._register(action)`** (private) adds actions programmatically; the public API is YAML-driven.
- **Starlette 1.0 API**: `TemplateResponse(request, name, context)` — the old `(name, {"request": ..., ...})` form is rejected.
- **Community KB is loaded from seed and frozen at runtime** — no runtime KB promotion logic.

## Tier system

Reach score drives automatic promotion/demotion:
- `compute_reach_score(npc, memory)` → `rel_score + goal_score + mem_score (capped at 5.0)`
- Thresholds live in `config.settings.tier` (`promote_t0/t1/t2`, `demote_t1/t2/t3`)
- Demotion triggers LLM history compression into `npc.narrative_summary`; compression failure falls back to last 3 entries joined by `"; "`

## Tick system

`sim/tick.tick(registry, graph, action_registry, memory_store)`:
- T0: skipped entirely
- T1: acts with `t1_action_probability` (default 25%)
- T2+: always attempts GOAP-lite action selection
- Gossip phase: most salient memory (salience ≥ 1.5) propagates to community KB with `gossip_probability` (default 10%)
- Relationship drift: ±`rel_drift_magnitude` (default 0.02) per tick per relationship

## Module-level singletons

```python
from config import settings          # Config
from events.log import event_log     # EventLog
from director.director import director  # Director
from llm.runner import prompt_log    # PromptLog
from tools.state import get_state    # AppState (call as function)
```

## Tests

318 tests across `tests/`. All pure unit/integration — no external services required. The `StubRunner` in `llm/stub_runner.py` fakes LLM responses for tier compression tests.
