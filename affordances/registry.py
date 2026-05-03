"""
ActionRegistry — single source of truth for all actions.

Load from YAML once at startup. All other systems read from this object.
Adding a new action is an authoring activity: add it to data/actions.yaml,
and every zone/NPC that qualifies becomes eligible automatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import yaml

from affordances.schema import Action, ActionCategory


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ActionRegistry":
        registry = cls()
        data = yaml.safe_load(Path(path).read_text())
        for record in data.get("actions", []):
            action = Action.model_validate(record)
            registry._register(action)
        return registry

    def _register(self, action: Action) -> None:
        if action.id in self._actions:
            raise ValueError(f"Duplicate action id '{action.id}'")
        self._actions[action.id] = action

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, action_id: str) -> Action:
        try:
            return self._actions[action_id]
        except KeyError:
            raise KeyError(f"Action '{action_id}' not found in registry")

    def get_or_none(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    def all_actions(self) -> list[Action]:
        return list(self._actions.values())

    def __iter__(self) -> Iterator[Action]:
        return iter(self._actions.values())

    def __len__(self) -> int:
        return len(self._actions)

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------

    def by_category(self, category: ActionCategory) -> list[Action]:
        return [a for a in self._actions.values() if a.category == category]

    def by_tag(self, tag: str) -> list[Action]:
        return [a for a in self._actions.values() if tag in a.tags]

    def crafting_actions(self) -> list[Action]:
        return self.by_category(ActionCategory.CRAFTING)

    def gathering_actions(self) -> list[Action]:
        return self.by_category(ActionCategory.GATHERING)

    # ------------------------------------------------------------------
    # Product DAG helpers (used by crafting/ and tools/)
    # ------------------------------------------------------------------

    def produces_item_type(self, item_type: str) -> list[Action]:
        """All actions that produce the given item type."""
        from affordances.schema import ProducesEffect
        result = []
        for action in self._actions.values():
            for effect in action.effects:
                if isinstance(effect, ProducesEffect) and effect.item_type == item_type:
                    result.append(action)
                    break
        return result

    def consumes_item_type(self, item_type: str) -> list[Action]:
        """All actions that consume the given item type."""
        from affordances.schema import ConsumesEffect
        result = []
        for action in self._actions.values():
            for effect in action.effects:
                if isinstance(effect, ConsumesEffect) and effect.item_type == item_type:
                    result.append(action)
                    break
        return result

    def all_produced_item_types(self) -> set[str]:
        from affordances.schema import ProducesEffect
        return {
            e.item_type
            for a in self._actions.values()
            for e in a.effects
            if isinstance(e, ProducesEffect)
        }

    def all_consumed_item_types(self) -> set[str]:
        from affordances.schema import ConsumesEffect
        return {
            e.item_type
            for a in self._actions.values()
            for e in a.effects
            if isinstance(e, ConsumesEffect)
        }

    def required_tags(self, action_id: str) -> set[str]:
        """All NearbyTag and ZoneHasTag values referenced in an action's preconditions."""
        from affordances.schema import (
            NearbyTagPrecondition, ZoneHasTagPrecondition,
            AndPrecondition, OrPrecondition, NotPrecondition,
        )
        action = self.get(action_id)
        tags: set[str] = set()

        def collect(p):
            if isinstance(p, (NearbyTagPrecondition, ZoneHasTagPrecondition)):
                tags.add(p.tag)
            elif isinstance(p, (AndPrecondition, OrPrecondition)):
                for c in p.conditions:
                    collect(c)
            elif isinstance(p, NotPrecondition):
                collect(p.condition)

        collect(action.preconditions)
        return tags
