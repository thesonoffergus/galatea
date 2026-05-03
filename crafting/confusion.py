"""
Confusion table resolution for gathering actions.

At low skill, a character attempting to gather a specific resource may
accidentally collect similar-looking items. As skill increases, the
probability of each confusion entry decreases linearly to zero at
`skill_elimination_threshold`.

All probabilities are evaluated independently in declaration order;
the first entry whose roll fires determines the actual output.
This means the ordering of entries in the table matters — more dangerous
confusions should be listed first so they are checked before benign ones.
"""

from __future__ import annotations

import random as stdlib_random
from typing import Optional

from affordances.schema import ConfusionTable


def resolve_confusion(
    table: ConfusionTable,
    character_skill: float,
    rng: Optional[stdlib_random.Random] = None,
) -> str:
    """
    Determine the actual item type produced by a gathering action.

    Returns the intended output if no confusion entry fires, or one of
    the confusion outputs if the actor's skill was insufficient to avoid
    the mistake.

    Args:
        table: The confusion table attached to the gathering action.
        character_skill: Actor's proficiency in `table.skill` (0.0–1.0).
        rng: Optional Random instance for deterministic testing.
            Defaults to stdlib random when None.

    Returns:
        item_type string — either `table.intended_output` or a confusion output.
    """
    if rng is None:
        rng = stdlib_random.Random()

    for entry in table.entries:
        if character_skill >= entry.skill_elimination_threshold:
            continue  # skill has fully eliminated this confusion

        # Linear falloff: probability at this skill level
        effective_prob = entry.base_probability * (
            (entry.skill_elimination_threshold - character_skill)
            / entry.skill_elimination_threshold
        )
        if rng.random() < effective_prob:
            return entry.output_item_type

    return table.intended_output


def confusion_probability_at_skill(
    table: ConfusionTable,
    character_skill: float,
) -> dict[str, float]:
    """
    Return the probability of each outcome (including intended) at a given
    skill level. Useful for the developer inspector and prompt composition.

    Note: these probabilities don't sum to 1.0 because entries are evaluated
    independently (first-match); this returns per-entry roll probabilities,
    not a proper distribution.
    """
    result: dict[str, float] = {}
    remaining_probability = 1.0

    for entry in table.entries:
        if character_skill >= entry.skill_elimination_threshold:
            result[entry.output_item_type] = 0.0
            continue

        effective_prob = entry.base_probability * (
            (entry.skill_elimination_threshold - character_skill)
            / entry.skill_elimination_threshold
        )
        # Scale by remaining probability (entries are first-match sequential)
        actual_prob = effective_prob * remaining_probability
        result[entry.output_item_type] = actual_prob
        remaining_probability *= (1.0 - effective_prob)

    result[table.intended_output] = remaining_probability
    return result
