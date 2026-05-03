"""
Bootstrap validation pass.

Runs after world generation to verify the hard invariant: every tool
required to harvest raw materials is reachable — either craftable from
tool-free materials OR present as a starting world item.

An item is considered "reachable" if:
  1. It is produced by at least one action whose own ingredient chain is
     also reachable (recursive), OR
  2. It exists as a placed item in the world graph at validation time.

Circular dependencies (e.g., pickaxe needs iron, iron needs pickaxe) are
only valid if a starting world item breaks the cycle. This validator detects
those cases and confirms the world item is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import networkx as nx

from affordances.registry import ActionRegistry
from affordances.schema import (
    ActorHasItemPrecondition,
    AndPrecondition,
    NotPrecondition,
    OrPrecondition,
    Precondition,
)
from crafting.dag import build_item_dag, detect_cycles
from world.graph import WorldGraph


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class BootstrapIssue:
    severity: str   # "error" | "warning"
    description: str
    item_type: Optional[str] = None
    action_id: Optional[str] = None


@dataclass
class BootstrapResult:
    passed: bool
    issues: list[BootstrapIssue] = field(default_factory=list)

    def errors(self) -> list[BootstrapIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[BootstrapIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        e = len(self.errors())
        w = len(self.warnings())
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {e} error(s), {w} warning(s)"


# ── World item index ──────────────────────────────────────────────────────────


def _world_item_types(graph: WorldGraph) -> set[str]:
    """Set of all item_type values present anywhere in the world graph."""
    types: set[str] = set()
    for zone in graph.zones():
        for iid in zone.item_ids:
            item = graph.get_item(iid)
            if item:
                types.add(item.item_type)
    return types


# ── Reachability ──────────────────────────────────────────────────────────────


def _iter_actor_has_item(precond: Precondition):
    """Yield all ActorHasItemPrecondition nodes in a precondition tree."""
    if isinstance(precond, ActorHasItemPrecondition):
        yield precond
    elif isinstance(precond, (AndPrecondition, OrPrecondition)):
        for child in precond.conditions:
            yield from _iter_actor_has_item(child)
    elif isinstance(precond, NotPrecondition):
        yield from _iter_actor_has_item(precond.condition)


def _is_reachable(
    item_type: str,
    registry: ActionRegistry,
    world_items: set[str],
    dag: nx.DiGraph,
    _seen: frozenset[str] = frozenset(),
) -> bool:
    """
    True if an actor can eventually obtain `item_type` through some
    combination of gathering, crafting, and starting world items.

    _seen guards against infinite recursion in circular dependency chains.
    """
    # Present as a starting world item — always reachable
    if item_type in world_items:
        return True

    if item_type in _seen:
        # Cycle back to something we're already checking — not independently reachable
        return False

    producing = registry.produces_item_type(item_type)
    if not producing:
        return False  # nothing produces it and it's not a world item

    _seen = _seen | {item_type}

    for action in producing:
        # Check whether all ingredients for this action are reachable
        ingredients_needed = [
            p.item_type
            for p in _iter_actor_has_item(action.preconditions)
        ]
        if all(
            _is_reachable(ing, registry, world_items, dag, _seen)
            for ing in ingredients_needed
        ):
            return True

    return False


# ── Main validation entry point ───────────────────────────────────────────────


def validate_world(
    registry: ActionRegistry,
    graph: WorldGraph,
) -> BootstrapResult:
    """
    Run the bootstrap validation pass against the current world state.

    Steps:
      1. Build and cycle-check the product DAG.
      2. Verify every tool required by gathering actions is reachable.
      3. Verify every ingredient required by crafting actions is reachable
         (warnings only — crafting gaps don't prevent play, they just limit it).
    """
    issues: list[BootstrapIssue] = []
    dag = build_item_dag(registry)
    world_items = _world_item_types(graph)

    # ── Step 1: DAG cycles ────────────────────────────────────────────────────
    for cycle in detect_cycles(dag):
        issues.append(BootstrapIssue(
            severity="error",
            description=f"Product cycle: {' → '.join(cycle + [cycle[0]])}",
        ))

    # ── Step 2: Gathering tool reachability (hard invariant) ─────────────────
    for action in registry.gathering_actions():
        for precond in _iter_actor_has_item(action.preconditions):
            item_type = precond.item_type
            if not _is_reachable(item_type, registry, world_items, dag):
                issues.append(BootstrapIssue(
                    severity="error",
                    description=(
                        f"Gathering action '{action.id}' requires item '{item_type}', "
                        f"but it is not reachable (not craftable and not present as a world item)."
                    ),
                    item_type=item_type,
                    action_id=action.id,
                ))

    # ── Step 3: Crafting ingredient reachability (soft invariant) ────────────
    for action in registry.crafting_actions():
        for precond in _iter_actor_has_item(action.preconditions):
            item_type = precond.item_type
            if not _is_reachable(item_type, registry, world_items, dag):
                issues.append(BootstrapIssue(
                    severity="warning",
                    description=(
                        f"Crafting action '{action.id}' requires item '{item_type}', "
                        f"which may not be obtainable. Consider adding it as a world item."
                    ),
                    item_type=item_type,
                    action_id=action.id,
                ))

    has_errors = any(i.severity == "error" for i in issues)
    return BootstrapResult(passed=not has_errors, issues=issues)
