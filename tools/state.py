"""Shared app state — loaded world graph, NPC registry, and action registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from affordances.registry import ActionRegistry
from crafting.bootstrap import BootstrapResult, validate_world
from crafting.dag import build_item_dag
from knowledge.loader import load_memory_store
from knowledge.store import MemoryStore
from npc.loader import load_npcs
from npc.registry import NPCRegistry
from world.graph import WorldGraph
from world.loader import load_world

DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_SEED = DATA_DIR / "village_seed.yaml"
ACTIONS_PATH = DATA_DIR / "actions.yaml"


@dataclass
class AppState:
    graph: WorldGraph
    npc_registry: NPCRegistry
    action_registry: ActionRegistry
    item_dag: nx.DiGraph
    bootstrap_result: BootstrapResult
    memory_store: MemoryStore
    seed_path: Path

    @classmethod
    def load(cls, seed_path: Path = DEFAULT_SEED) -> "AppState":
        graph = load_world(seed_path)
        npc_registry, _ = load_npcs(seed_path, graph=graph)
        action_registry = ActionRegistry.from_yaml(ACTIONS_PATH)
        item_dag = build_item_dag(action_registry)
        bootstrap_result = validate_world(action_registry, graph)
        memory_store = load_memory_store(seed_path, npc_registry)
        return cls(
            graph=graph,
            npc_registry=npc_registry,
            action_registry=action_registry,
            item_dag=item_dag,
            bootstrap_result=bootstrap_result,
            memory_store=memory_store,
            seed_path=seed_path,
        )

    def available_seeds(self) -> list[Path]:
        seeds = sorted(DATA_DIR.glob("*.yaml"))
        scenarios = sorted((DATA_DIR / "scenarios").glob("*.yaml"))
        return seeds + scenarios


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState.load()
    return _state


def reload_state(seed_path: Path | None = None) -> AppState:
    global _state
    _state = AppState.load(seed_path or DEFAULT_SEED)
    return _state
