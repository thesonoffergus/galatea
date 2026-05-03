"""
NPC data schema.

Every NPC — including the player character — uses this schema. Tier governs
which simulation components are active, not what fields exist. A T0 NPC and
a T3 NPC share identical schema; the difference is which fields are populated
and how much compute runs against them.

Field notes:
  - big_five / trait_tags  → feed both rule-based sim and prompt composition
  - skills                 → consumed by affordance preconditions and quality model
  - known_recipes          → RecipeStore wrapping a set[str] of action IDs
  - goals                  → empty for T0/T1; populated by GOAP planner at T2+
  - relationships          → asymmetric per-NPC view; built up by sim
  - carried_item_ids       → items physically on the NPC's person (used for
                             ActorContext inventory; distinct from zone-stored items)
  - narrative_summary      → LLM-generated on demotion; injected in prompts on re-promotion
  - current_zone_id        → tracked here AND in WorldGraph; must stay in sync
"""

from __future__ import annotations

import uuid
from enum import IntEnum, StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from crafting.recipes import RecipeSource, RecipeStore


# ── Tier ──────────────────────────────────────────────────────────────────────


class NPCTier(IntEnum):
    T0 = 0  # Background — name, role, stat sheet; may not tick
    T1 = 1  # Familiar face — personality, basic schedule, constrained LLM
    T2 = 2  # Acquaintance — full traits, relationship graph, GOAP-lite
    T3 = 3  # Key figure — full LLM dialogue, episodic memory, scene-level sim


# ── Sub-models ────────────────────────────────────────────────────────────────


class BigFive(BaseModel):
    """Continuous Big Five personality dimensions (0.0–1.0 each)."""
    openness: float = Field(default=0.5, ge=0.0, le=1.0)
    conscientiousness: float = Field(default=0.5, ge=0.0, le=1.0)
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0)
    agreeableness: float = Field(default=0.5, ge=0.0, le=1.0)
    neuroticism: float = Field(default=0.5, ge=0.0, le=1.0)

    def as_dict(self) -> dict[str, float]:
        return {
            "openness": self.openness,
            "conscientiousness": self.conscientiousness,
            "extraversion": self.extraversion,
            "agreeableness": self.agreeableness,
            "neuroticism": self.neuroticism,
        }


class PhysicalTraits(BaseModel):
    """Appearance notes. Age is a placeholder — NPCs don't age at MVP."""
    build: str = ""
    hair: str = ""
    notable: str = ""
    # Age in perpetual-now mode is frozen. String description only for now.
    age_appearance: Optional[str] = None  # e.g. "middle-aged", "elderly"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class GoalPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Goal(BaseModel):
    """
    An NPC's active ambition. At T2+, `planned_actions` is populated by the
    GOAP planner (step 14) with a chain of action IDs to pursue this goal.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.ACTIVE
    # Populated by GOAP planner at T2+
    planned_actions: list[str] = Field(default_factory=list)


class Relationship(BaseModel):
    """
    One NPC's view of another. Asymmetric: A may love B who is indifferent.
    Familiarity gates how much detail is known; trust gates information sharing.
    """
    other_id: str

    # Emotional valence: -1.0 (deep hostility) → 0.0 (neutral) → 1.0 (deep affection)
    affinity: float = Field(default=0.0, ge=-1.0, le=1.0)

    # 0.0 (strangers) → 1.0 (complete trust)
    trust: float = Field(default=0.3, ge=0.0, le=1.0)

    # 0.0 (just met) → 1.0 (known for years / intimate knowledge)
    familiarity: float = Field(default=0.0, ge=0.0, le=1.0)

    # Qualitative relationship modifiers
    tags: set[str] = Field(default_factory=set)
    # e.g. "kin", "mentor", "rival", "employer", "friend", "romantic_interest"


# ── NPC ───────────────────────────────────────────────────────────────────────


class NPC(BaseModel):
    # Identity
    id: str
    name: str
    role: str
    description: str = ""
    is_player: bool = False

    # Simulation tier
    tier: NPCTier = NPCTier.T1

    # Personality (drives prompt composition and GOAP weights)
    big_five: BigFive = Field(default_factory=BigFive)
    trait_tags: list[str] = Field(default_factory=list)

    # Competency
    skills: dict[str, float] = Field(default_factory=dict)
    known_recipes: RecipeStore = Field(default_factory=RecipeStore)

    # Identity / motivation
    values: list[str] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)

    # Social graph — keyed by other NPC's ID
    relationships: dict[str, Relationship] = Field(default_factory=dict)

    # Physical description
    physical: PhysicalTraits = Field(default_factory=PhysicalTraits)

    # Runtime state (mutable; kept in sync with WorldGraph)
    current_zone_id: Optional[str] = None
    mood: float = Field(default=0.0, ge=-1.0, le=1.0)

    # Items this NPC carries on their person (distinct from zone-stored owned items)
    carried_item_ids: list[str] = Field(default_factory=list)

    # Tier system hooks (populated in step 10)
    reach_score: float = 0.0
    # Compressed history written on demotion; injected into prompts on re-promotion
    narrative_summary: str = ""

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def effective_tags(self) -> set[str]:
        """
        Tags this NPC contributes to a zone's effective tag set when present.
        Used by NpcPresentPrecondition role matching and zone affordance digests.
        """
        role_tag = self.role.lower().replace(" ", "_").replace("-", "_")
        tags = {"npc", role_tag}
        if self.is_player:
            tags.add("player")
        return tags

    # ------------------------------------------------------------------
    # Affordance integration
    # ------------------------------------------------------------------

    def as_actor_context(self, graph=None) -> "ActorContext":
        """
        Produce a lightweight ActorContext snapshot for precondition evaluation.
        If graph is provided, carried item types are resolved from the item registry.
        """
        from affordances.query import ActorContext

        inventory: dict[str, int] = {}
        if graph is not None:
            for item_id in self.carried_item_ids:
                item = graph.get_item(item_id)
                if item:
                    inventory[item.item_type] = (
                        inventory.get(item.item_type, 0) + item.quantity
                    )

        return ActorContext(
            actor_id=self.id,
            skills=dict(self.skills),
            known_recipes=self.known_recipes.known_ids(),
            inventory=inventory,
            role_tags=self.effective_tags(),
        )

    # ------------------------------------------------------------------
    # Relationship helpers
    # ------------------------------------------------------------------

    def get_relationship(self, other_id: str) -> Optional[Relationship]:
        return self.relationships.get(other_id)

    def set_relationship(self, rel: Relationship) -> None:
        self.relationships[rel.other_id] = rel

    def adjust_relationship(
        self,
        other_id: str,
        affinity_delta: float = 0.0,
        trust_delta: float = 0.0,
        familiarity_delta: float = 0.0,
    ) -> Relationship:
        """
        Adjust an existing relationship or initialise a neutral one.
        Returns the updated Relationship.
        """
        if other_id not in self.relationships:
            self.relationships[other_id] = Relationship(other_id=other_id)
        rel = self.relationships[other_id]
        rel.affinity = max(-1.0, min(1.0, rel.affinity + affinity_delta))
        rel.trust = max(0.0, min(1.0, rel.trust + trust_delta))
        rel.familiarity = max(0.0, min(1.0, rel.familiarity + familiarity_delta))
        return rel

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def has_recipe(self, recipe_id: str) -> bool:
        return self.known_recipes.knows(recipe_id)

    def skill_level(self, skill: str) -> float:
        return self.skills.get(skill, 0.0)

    def active_goals(self) -> list[Goal]:
        return [g for g in self.goals if g.status == GoalStatus.ACTIVE]

    def add_goal(self, description: str, priority: GoalPriority = GoalPriority.MEDIUM) -> Goal:
        goal = Goal(description=description, priority=priority)
        self.goals.append(goal)
        return goal


# Import guard: ActorContext is in affordances, imported lazily above
# to avoid a circular import at module load time.
