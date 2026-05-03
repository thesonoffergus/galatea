"""
Product DAG utilities.

The dependency structure is implicit in the action registry: if `smelt_iron`
produces `iron_ingot` and `smith_sword` consumes `iron_ingot`, the tree exists
by following those links. This module derives and validates the DAG — it is
never hand-authored separately.

Node = item_type string
Edge A → B = "item A is consumed in the production of item B"
Each edge is annotated with the action_id that performs the transformation.

Convention:
  - Leaf nodes (no incoming edges): raw materials obtainable by gathering
  - Root nodes (no outgoing edges): finished goods consumed by no further action
  - All other nodes: intermediate products
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import networkx as nx

from affordances.registry import ActionRegistry
from affordances.schema import ActionCategory, ConsumesEffect, ProducesEffect


# ── Build ─────────────────────────────────────────────────────────────────────


def build_item_dag(registry: ActionRegistry) -> nx.DiGraph:
    """
    Derive the product dependency graph from the action registry.

    Nodes carry:
        gatherable (bool)  — True if a gathering action produces this item
        craftable  (bool)  — True if a crafting action produces this item
    Edges carry:
        action_id (str)    — ID of the action that performs the transformation
        quantity  (int)    — how many of the ingredient are consumed
    """
    dag: nx.DiGraph = nx.DiGraph()

    for action in registry:
        produced = [e for e in action.effects if isinstance(e, ProducesEffect)]
        consumed = [e for e in action.effects if isinstance(e, ConsumesEffect)]

        is_gathering = action.category == ActionCategory.GATHERING
        is_crafting = action.category == ActionCategory.CRAFTING

        for p_effect in produced:
            item = p_effect.item_type
            if item not in dag:
                dag.add_node(item, gatherable=False, craftable=False)
            if is_gathering:
                dag.nodes[item]["gatherable"] = True
            if is_crafting:
                dag.nodes[item]["craftable"] = True

            for c_effect in consumed:
                ingredient = c_effect.item_type
                if ingredient not in dag:
                    dag.add_node(ingredient, gatherable=False, craftable=False)
                # Multiple actions may consume the same ingredient → multi-edges
                # Use a combined key so nx.DiGraph (no multi-edges) keeps the
                # last-registered action. That's fine — the DAG is for structure
                # queries, not for picking which action to use.
                dag.add_edge(
                    ingredient,
                    item,
                    action_id=action.id,
                    quantity=c_effect.quantity,
                )

    return dag


# ── Queries ───────────────────────────────────────────────────────────────────


def raw_materials_for(item_type: str, dag: nx.DiGraph) -> set[str]:
    """
    Leaf nodes (no incoming edges) in the transitive dependency set of
    `item_type`. These are items that cannot be produced from other items —
    they must be gathered from the world.
    """
    if item_type not in dag:
        return set()
    ancestors = nx.ancestors(dag, item_type)
    return {n for n in ancestors if dag.in_degree(n) == 0}


def dependency_chain(item_type: str, dag: nx.DiGraph) -> list[str]:
    """
    Topologically-ordered list of all item types needed to produce
    `item_type`, from raw materials to the final product.
    Includes `item_type` itself at the end.
    """
    if item_type not in dag:
        return [item_type]
    subgraph = nx.subgraph(dag, nx.ancestors(dag, item_type) | {item_type})
    try:
        return list(nx.topological_sort(subgraph))
    except nx.NetworkXUnfeasible:
        # Cycle exists — return what we have in DFS order
        return list(nx.dfs_preorder_nodes(subgraph, item_type))


def producing_actions(item_type: str, registry: ActionRegistry) -> list[str]:
    """Action IDs that produce `item_type`."""
    return [a.id for a in registry.produces_item_type(item_type)]


def dependency_tree(
    item_type: str,
    dag: nx.DiGraph,
    registry: ActionRegistry,
    _visited: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Recursive dependency tree for a single item type. Used by the product
    DAG viewer in the developer tooling.

    Returns a nested dict:
        {
          "item_type": "sword",
          "produced_by": ["smith_sword"],
          "gatherable": False,
          "craftable": True,
          "requires": [
            {"item_type": "iron_ingot", ...},
            ...
          ]
        }
    """
    if _visited is None:
        _visited = set()

    if item_type in _visited:
        # Cycle — return a sentinel so the caller knows not to recurse
        return {"item_type": item_type, "cycle_ref": True}

    _visited = _visited | {item_type}

    node_data = dag.nodes.get(item_type, {})
    ingredients = list(dag.predecessors(item_type))

    return {
        "item_type": item_type,
        "produced_by": producing_actions(item_type, registry),
        "gatherable": node_data.get("gatherable", False),
        "craftable": node_data.get("craftable", False),
        "requires": [
            dependency_tree(ing, dag, registry, _visited)
            for ing in ingredients
        ],
    }


# ── Validation ────────────────────────────────────────────────────────────────


def detect_cycles(dag: nx.DiGraph) -> list[list[str]]:
    """Return all simple cycles in the DAG (empty list = valid DAG)."""
    return list(nx.simple_cycles(dag))


@dataclass
class DAGIssue:
    severity: str   # "error" | "warning"
    description: str
    item_type: Optional[str] = None
    action_id: Optional[str] = None


def validate_dag(registry: ActionRegistry) -> list[DAGIssue]:
    """
    Structural validation of the product DAG derived from the registry.
    Returns a list of issues (empty = clean).
    """
    dag = build_item_dag(registry)
    issues: list[DAGIssue] = []

    # Cycles are hard errors — they indicate a broken authoring invariant
    for cycle in detect_cycles(dag):
        issues.append(DAGIssue(
            severity="error",
            description=f"Product cycle detected: {' → '.join(cycle + [cycle[0]])}",
        ))

    # Consumed-but-never-produced items are warnings — they may be world-seeded
    consumed = registry.all_consumed_item_types()
    produced = registry.all_produced_item_types()
    for item in consumed - produced:
        issues.append(DAGIssue(
            severity="warning",
            description=(
                f"Item type '{item}' is consumed by actions but never produced "
                f"by any action. It must exist as a starting world item."
            ),
            item_type=item,
        ))

    return issues
