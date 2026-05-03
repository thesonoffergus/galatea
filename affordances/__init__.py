from affordances.schema import (
    Action, ActionCategory, ActionStep, ParameterDef,
    PlayerSkillGate, ConfusionTable, ConfusionEntry,
    Precondition, Effect,
    NearbyTagPrecondition, ZoneHasTagPrecondition,
    ActorHasItemPrecondition, ZoneHasItemPrecondition,
    ActorSkillPrecondition, ActorKnowsRecipePrecondition,
    NpcPresentPrecondition, ZoneIsAccessiblePrecondition,
    AndPrecondition, OrPrecondition, NotPrecondition,
    ProducesEffect, ConsumesEffect, AdvancesSkillEffect,
    TimeCostEffect, NoiseEffect, TeachesRecipeEffect,
    MovesActorEffect, RelationshipEffect,
)
from affordances.registry import ActionRegistry
from affordances.query import (
    ActorContext, EvalContext,
    evaluate_precondition,
    what_can_actor_do,
    where_can_action_be_done,
    actions_available_in_zone,
)

__all__ = [
    "Action", "ActionCategory", "ActionStep", "ParameterDef",
    "PlayerSkillGate", "ConfusionTable", "ConfusionEntry",
    "Precondition", "Effect",
    "NearbyTagPrecondition", "ZoneHasTagPrecondition",
    "ActorHasItemPrecondition", "ZoneHasItemPrecondition",
    "ActorSkillPrecondition", "ActorKnowsRecipePrecondition",
    "NpcPresentPrecondition", "ZoneIsAccessiblePrecondition",
    "AndPrecondition", "OrPrecondition", "NotPrecondition",
    "ProducesEffect", "ConsumesEffect", "AdvancesSkillEffect",
    "TimeCostEffect", "NoiseEffect", "TeachesRecipeEffect",
    "MovesActorEffect", "RelationshipEffect",
    "ActionRegistry",
    "ActorContext", "EvalContext",
    "evaluate_precondition",
    "what_can_actor_do",
    "where_can_action_be_done",
    "actions_available_in_zone",
]
