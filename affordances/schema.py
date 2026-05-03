"""
Action and precondition schema for the affordance system.

Design invariant: every action lives in the registry (data/actions.yaml).
New action schemas are an authoring activity, not a runtime one.
The LLM may propose novel parameter *values* for parametric actions but
never invents new action schemas wholesale.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class ActionCategory(StrEnum):
    GATHERING = "gathering"
    CRAFTING = "crafting"
    SOCIAL = "social"
    MOVEMENT = "movement"


# ── Preconditions ──────────────────────────────────────────────────────────────
# Leaf types first, compound types after (they reference the Precondition union).


class NearbyTagPrecondition(BaseModel):
    """Tag must be present in zone or within `hops` CONNECTS steps."""
    type: Literal["nearby_tag"] = "nearby_tag"
    tag: str
    hops: int = 1


class ZoneHasTagPrecondition(BaseModel):
    """Tag must be present in exactly the actor's current zone (no radius)."""
    type: Literal["zone_has_tag"] = "zone_has_tag"
    tag: str


class ActorHasItemPrecondition(BaseModel):
    """Actor's inventory must contain at least `quantity` of `item_type`."""
    type: Literal["actor_has_item"] = "actor_has_item"
    item_type: str
    quantity: int = 1


class ZoneHasItemPrecondition(BaseModel):
    """Zone must contain at least `quantity` items of `item_type`."""
    type: Literal["zone_has_item"] = "zone_has_item"
    item_type: str
    quantity: int = 1


class ActorSkillPrecondition(BaseModel):
    """Actor's named skill must be >= `min_value` (0.0–1.0 scale)."""
    type: Literal["actor_skill"] = "actor_skill"
    skill: str
    min_value: float


class ActorKnowsRecipePrecondition(BaseModel):
    """Actor must hold `recipe_id` in their known_recipes set."""
    type: Literal["actor_knows_recipe"] = "actor_knows_recipe"
    recipe_id: str


class NpcPresentPrecondition(BaseModel):
    """
    At least one NPC other than the actor must be present in the zone.
    If `role` is set, the NPC must carry that role tag (checked once NPC
    schema is wired in step 4; until then, any NPC satisfies this).
    """
    type: Literal["npc_present"] = "npc_present"
    role: Optional[str] = None


class ZoneIsAccessiblePrecondition(BaseModel):
    """Zone must not carry the `locked` tag."""
    type: Literal["zone_accessible"] = "zone_accessible"


# Compound (recursive) — use string annotation for Precondition forward ref.

class AndPrecondition(BaseModel):
    """All child conditions must hold."""
    type: Literal["and"] = "and"
    conditions: list["Precondition"]


class OrPrecondition(BaseModel):
    """At least one child condition must hold."""
    type: Literal["or"] = "or"
    conditions: list["Precondition"]


class NotPrecondition(BaseModel):
    """Child condition must be false."""
    type: Literal["not"] = "not"
    condition: "Precondition"


Precondition = Annotated[
    Union[
        NearbyTagPrecondition,
        ZoneHasTagPrecondition,
        ActorHasItemPrecondition,
        ZoneHasItemPrecondition,
        ActorSkillPrecondition,
        ActorKnowsRecipePrecondition,
        NpcPresentPrecondition,
        ZoneIsAccessiblePrecondition,
        AndPrecondition,
        OrPrecondition,
        NotPrecondition,
    ],
    Field(discriminator="type"),
]

# Resolve forward references
AndPrecondition.model_rebuild()
OrPrecondition.model_rebuild()
NotPrecondition.model_rebuild()


# ── Effects ────────────────────────────────────────────────────────────────────
# Effects are pure data. The sim layer interprets and applies them.
# A string starting with "$param:" refers to a runtime parameter value,
# e.g., "$param:recipe_id" means "the recipe_id parameter passed to this action".


class ProducesEffect(BaseModel):
    """Creates one or more items of `item_type` at the actor's location."""
    type: Literal["produces"] = "produces"
    item_type: str
    quantity: int = 1
    quality_fn: str = "default"  # crafting quality policy key


class ConsumesEffect(BaseModel):
    """Removes items from the actor's inventory (from_actor=True) or zone (False)."""
    type: Literal["consumes"] = "consumes"
    item_type: str
    quantity: int = 1
    from_actor: bool = True


class AdvancesSkillEffect(BaseModel):
    """Increments actor's named skill by `amount` (subject to cap)."""
    type: Literal["advances_skill"] = "advances_skill"
    skill: str
    amount: float


class TimeCostEffect(BaseModel):
    """
    Consumes `game_hours` of simulation time.
    Used for atomic actions (no step_list). When step_list is present,
    time cost is the sum of step time costs.
    """
    type: Literal["time_cost"] = "time_cost"
    game_hours: float


class NoiseEffect(BaseModel):
    """Emits noise that nearby NPCs may perceive."""
    type: Literal["noise"] = "noise"
    level: str  # "quiet" | "moderate" | "loud"


class TeachesRecipeEffect(BaseModel):
    """Adds `recipe_id` to the target's known_recipes."""
    type: Literal["teaches_recipe"] = "teaches_recipe"
    recipe_id: str  # may be "$param:recipe_id" for parametric actions


class MovesActorEffect(BaseModel):
    """Moves actor to `to_zone`. Use "$param:to_zone_id" for parametric."""
    type: Literal["moves_actor"] = "moves_actor"
    to_zone: str


class RelationshipEffect(BaseModel):
    """Adjusts relationship value between actor and `target` by `delta`."""
    type: Literal["relationship"] = "relationship"
    target: str = "target"  # NPC ID or "$param:target_npc_id"
    delta: float


Effect = Annotated[
    Union[
        ProducesEffect,
        ConsumesEffect,
        AdvancesSkillEffect,
        TimeCostEffect,
        NoiseEffect,
        TeachesRecipeEffect,
        MovesActorEffect,
        RelationshipEffect,
    ],
    Field(discriminator="type"),
]


# ── Crafting sub-structures ────────────────────────────────────────────────────


class PlayerSkillGate(BaseModel):
    """
    Declares that this step (or action) requires a player skill check.
    The framework provides the interface; the game implementation supplies
    the minigame. If no minigame is registered for `type_id`, falls back
    to auto-resolve using character skill.
    """
    type_id: str   # e.g. "hammer_rhythm", "forge_timing", "fish_pull"
    difficulty: float  # 0.0–1.0


class ConfusionEntry(BaseModel):
    """One possible erroneous output from a gathering action."""
    output_item_type: str
    base_probability: float          # probability when skill = 0
    skill_elimination_threshold: float  # skill level at which probability → 0
    tag_similarity_hint: Optional[str] = None  # e.g. "plants_same_biome"


class ConfusionTable(BaseModel):
    """
    Governs gathering accuracy. At low skill, the actor may retrieve the wrong
    item. Entries are ordered: first match at runtime wins if multiple would apply.
    Hand-authored entries take priority over tag-similarity inference (future).
    """
    intended_output: str   # the item_type the actor intends to harvest
    skill: str             # skill governing accuracy
    entries: list[ConfusionEntry]


class ActionStep(BaseModel):
    """One sub-step in a step_list. Steps decompose crafting into observable phases."""
    name: str
    description: str = ""
    time_cost_hours: float = 0.0
    tool_tag: Optional[str] = None        # tag the required tool must carry
    consumes: Optional[ConsumesEffect] = None
    player_skill_gate: Optional[PlayerSkillGate] = None


# ── Parameter definition ──────────────────────────────────────────────────────


class ParameterDef(BaseModel):
    """Declares a runtime parameter for parametric actions."""
    name: str
    description: str = ""
    type: str  # "zone_id" | "item_type" | "recipe_id" | "npc_id" | "str"


# ── Action ────────────────────────────────────────────────────────────────────


class Action(BaseModel):
    id: str
    name: str
    description: str = ""
    category: ActionCategory

    # Preconditions evaluated against actor + zone state
    preconditions: Precondition

    # Effects applied on successful completion
    effects: list[Effect]

    # Tags on the action itself (drive social/narrative consequences)
    tags: set[str] = Field(default_factory=set)

    # For parametric actions (e.g. teach_recipe, travel_to)
    parameters: list[ParameterDef] = Field(default_factory=list)

    # If non-empty: action decomposes into observable sub-steps.
    # Total time cost = sum of step time_cost_hours. NoTimeCostEffect needed.
    step_list: list[ActionStep] = Field(default_factory=list)

    # Optional top-level player skill gate (for atomic actions without steps)
    player_skill_gate: Optional[PlayerSkillGate] = None

    # Optional gathering confusion table (gathering category only)
    confusion_table: Optional[ConfusionTable] = None

    @property
    def total_time_hours(self) -> float:
        """Total action time in game-hours."""
        if self.step_list:
            return sum(s.time_cost_hours for s in self.step_list)
        for e in self.effects:
            if isinstance(e, TimeCostEffect):
                return e.game_hours
        return 0.0

    @property
    def is_parametric(self) -> bool:
        return len(self.parameters) > 0
