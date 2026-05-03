"""
Player skill hook interface.

A step (or an atomic action) can declare a player_skill_gate with a type
identifier and a difficulty value. The framework defines the interface:
"this step requires a player skill check of type X at difficulty Y; return
a performance score 0.0–1.0."

The game implementation supplies the minigame that resolves it. If no
minigame is registered for that type, the framework falls back to
auto-resolve using character skill alone.

The framework never knows what a minigame looks like.
"""

from __future__ import annotations

from typing import Callable, Optional

# The resolver signature: (difficulty, character_skill) → performance_score
# character_skill is 0.0–1.0. difficulty is 0.0–1.0.
# Returns performance_score 0.0–1.0.
SkillResolverFn = Callable[[float, float], float]


def _default_auto_resolve(difficulty: float, character_skill: float) -> float:
    """
    Auto-resolve fallback when no minigame is registered.

    At character_skill == difficulty, performance is ~0.75 (competent but
    not perfect). At double the difficulty the actor performs near-perfectly.
    At zero skill with any difficulty, performance is near zero.
    This produces a smooth, non-binary result the quality model can use.
    """
    if difficulty <= 0.0:
        return 1.0
    # Sigmoid-like mapping
    ratio = character_skill / difficulty
    # Clamp smoothly to [0, 1]
    return max(0.0, min(1.0, ratio * 0.75))


class PlayerSkillHookRegistry:
    """
    Maps player skill gate type IDs to resolver callables.

    Usage:
        registry = PlayerSkillHookRegistry()

        # Game implementation registers a minigame:
        @registry.register("hammer_rhythm")
        def hammer_rhythm_minigame(difficulty, character_skill):
            # ... run the minigame, return 0.0–1.0
            return result

        # Framework calls:
        performance = registry.resolve("hammer_rhythm", difficulty=0.5, character_skill=0.6)
    """

    def __init__(self) -> None:
        self._resolvers: dict[str, SkillResolverFn] = {}

    def register(self, type_id: str, fn: Optional[SkillResolverFn] = None):
        """
        Register a resolver for a skill gate type. Can be used as a decorator
        or called directly.

            registry.register("type_id", my_fn)
            # or
            @registry.register("type_id")
            def my_fn(difficulty, character_skill): ...
        """
        if fn is not None:
            self._resolvers[type_id] = fn
            return fn

        # Decorator form
        def decorator(f: SkillResolverFn) -> SkillResolverFn:
            self._resolvers[type_id] = f
            return f

        return decorator

    def resolve(
        self,
        type_id: str,
        difficulty: float,
        character_skill: float = 0.0,
    ) -> float:
        """
        Resolve a player skill gate to a performance score (0.0–1.0).

        Uses the registered minigame if available; otherwise falls back
        to auto-resolve using character skill.
        """
        resolver = self._resolvers.get(type_id, _default_auto_resolve)
        return max(0.0, min(1.0, resolver(difficulty, character_skill)))

    def is_registered(self, type_id: str) -> bool:
        return type_id in self._resolvers

    def registered_types(self) -> list[str]:
        return list(self._resolvers.keys())


# Module-level singleton — the game implementation registers minigames here.
skill_hook_registry = PlayerSkillHookRegistry()
