"""
Recipe knowledge store — per-character tracking of known crafting recipes.

A recipe is identified by its action ID. The store tracks how each recipe
was acquired so that provenance (taught-by, observed, etc.) is preserved
for memory injection and social mechanics.

Recipe loss: if every living character who knows a recipe has no record of
it, the recipe is functionally lost. The action remains in the registry —
the product is still *possible* — but no actor can perform it until
rediscovered. This module tracks the living side of that invariant.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class RecipeSource(StrEnum):
    INNATE = "innate"          # started with it (world/character creation)
    TAUGHT = "taught"          # an NPC taught it directly via dialogue
    OBSERVED = "observed"      # watched a complete crafting animation
    READ = "read"              # read from a written object (hook only — no literate NPCs yet)
    DISCOVERED = "discovered"  # experimentation system (deferred)


class RecipeEntry(BaseModel):
    recipe_id: str
    source: RecipeSource
    taught_by_id: Optional[str] = None  # NPC actor_id, if source == TAUGHT


class RecipeStore(BaseModel):
    """
    Ordered dict of recipe_id → RecipeEntry.
    Ordered so that the most recently acquired recipes appear last —
    useful for memory summarisation prompts.
    """
    entries: dict[str, RecipeEntry] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def knows(self, recipe_id: str) -> bool:
        return recipe_id in self.entries

    def known_ids(self) -> set[str]:
        return set(self.entries.keys())

    def count(self) -> int:
        return len(self.entries)

    def by_source(self, source: RecipeSource) -> list[RecipeEntry]:
        return [e for e in self.entries.values() if e.source == source]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def learn(
        self,
        recipe_id: str,
        source: RecipeSource = RecipeSource.INNATE,
        taught_by_id: Optional[str] = None,
    ) -> bool:
        """
        Add a recipe to the store. Returns True if the recipe was new,
        False if the actor already knew it (no duplicate entry created).
        """
        if recipe_id in self.entries:
            return False
        self.entries[recipe_id] = RecipeEntry(
            recipe_id=recipe_id,
            source=source,
            taught_by_id=taught_by_id,
        )
        return True

    def forget(self, recipe_id: str) -> bool:
        """Remove a recipe. Returns True if it was present."""
        return self.entries.pop(recipe_id, None) is not None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_id_list(
        cls,
        recipe_ids: list[str],
        source: RecipeSource = RecipeSource.INNATE,
    ) -> "RecipeStore":
        """
        Build a RecipeStore from a plain list of recipe IDs — used when
        loading NPC data from the seed YAML where provenance is not specified.
        """
        store = cls()
        for rid in recipe_ids:
            store.learn(rid, source=source)
        return store
