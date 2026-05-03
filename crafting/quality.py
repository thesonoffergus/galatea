"""
Quality model for crafted items.

Every craftable item carries a quality float (0.0–1.0) set at creation time.
The framework defines the input vector and ships a default weighting function,
but exposes it as an overridable policy — per action, per action category,
or globally. The designer controls how much each factor matters.

Gathering actions produce items at quality 1.0 (raw materials have intrinsic
quality; the quality model applies to *crafted* transformations).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from config import settings


class MaterialAggregation(StrEnum):
    AVERAGE = "average"    # mean of all material qualities
    WORST_OF = "worst_of"  # quality is capped by the worst input


class QualityInputs(BaseModel):
    """
    Runtime snapshot of all factors that influence crafted item quality.
    Populated by the sim layer at the moment an action resolves.
    """
    # Qualities of every consumed material (0.0–1.0 each)
    material_qualities: list[float] = Field(default_factory=list)

    # Quality of the primary tool used (1.0 if no tool, or best available)
    tool_quality: float = 1.0

    # Actor's relevant skill level (0.0–1.0)
    character_skill: float = 0.0

    # Score from player minigame (0.0–1.0); defaults to 1.0 when no gate applies
    player_performance: float = 1.0

    # Zone-based modifier (e.g., a particularly well-maintained forge)
    environment_modifier: float = 1.0


class QualityPolicy(BaseModel):
    """
    Weighting policy for quality computation. Weights must sum to 1.0.
    Override this per action or per category via QualityPolicyRegistry.
    """
    material_aggregation: MaterialAggregation = MaterialAggregation.AVERAGE
    weight_material: float = 0.40
    weight_tool: float = 0.15
    weight_character_skill: float = 0.35
    weight_player_performance: float = 0.05
    weight_environment: float = 0.05

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "QualityPolicy":
        total = (
            self.weight_material
            + self.weight_tool
            + self.weight_character_skill
            + self.weight_player_performance
            + self.weight_environment
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"QualityPolicy weights must sum to 1.0, got {total:.4f}")
        return self


# Module-level default, initialised from config
DEFAULT_POLICY = QualityPolicy(
    weight_material=settings.crafting.quality_weight_material,
    weight_tool=settings.crafting.quality_weight_tool,
    weight_character_skill=settings.crafting.quality_weight_character_skill,
    weight_player_performance=settings.crafting.quality_weight_environment,  # shared slot
    weight_environment=0.0,  # environment folded into player_performance slot at default
)


def compute_quality(
    inputs: QualityInputs,
    policy: QualityPolicy = DEFAULT_POLICY,
) -> float:
    """
    Compute a quality float (0.0–1.0) from the input vector and policy.

    If no materials were consumed, material quality defaults to 1.0 so
    that unskilled crafting with no inputs doesn't penalise the output.
    """
    # Aggregate material qualities
    if not inputs.material_qualities:
        mat_score = 1.0
    elif policy.material_aggregation == MaterialAggregation.AVERAGE:
        mat_score = sum(inputs.material_qualities) / len(inputs.material_qualities)
    else:  # WORST_OF
        mat_score = min(inputs.material_qualities)

    score = (
        mat_score * policy.weight_material
        + inputs.tool_quality * policy.weight_tool
        + inputs.character_skill * policy.weight_character_skill
        + inputs.player_performance * policy.weight_player_performance
        + inputs.environment_modifier * policy.weight_environment
    )
    return max(0.0, min(1.0, score))


# ── Per-action / per-category policy registry ─────────────────────────────────


class QualityPolicyRegistry:
    """
    Allows the designer to override quality weighting on a per-action or
    per-category basis. Falls back to DEFAULT_POLICY when no override is set.
    """

    def __init__(self, default: QualityPolicy = DEFAULT_POLICY) -> None:
        self._default = default
        self._by_action: dict[str, QualityPolicy] = {}
        self._by_category: dict[str, QualityPolicy] = {}

    def set_for_action(self, action_id: str, policy: QualityPolicy) -> None:
        self._by_action[action_id] = policy

    def set_for_category(self, category: str, policy: QualityPolicy) -> None:
        self._by_category[category] = policy

    def get(self, action_id: str, category: Optional[str] = None) -> QualityPolicy:
        """Action-level override → category-level override → global default."""
        if action_id in self._by_action:
            return self._by_action[action_id]
        if category and category in self._by_category:
            return self._by_category[category]
        return self._default


# Module-level singleton
policy_registry = QualityPolicyRegistry()
