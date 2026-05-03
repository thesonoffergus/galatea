"""Derives speech-style descriptors from Big Five traits, trait tags, and values."""
from __future__ import annotations

from npc.schema import BigFive

# ── Big Five → prose descriptors ──────────────────────────────────────────────

_EXTRAVERSION = [
    (0.30, "Speaks very little; prefers action to words."),
    (0.55, "Speaks briefly. Does not elaborate unless pressed."),
    (0.75, "Speaks in measured amounts; neither talkative nor taciturn."),
    (1.01, "Speaks readily and at length; comfortable filling silence."),
]

_AGREEABLENESS = [
    (0.30, "Blunt and sometimes harsh. Does not soften their words."),
    (0.55, "Civil without being especially warm."),
    (0.75, "Reasonably considerate; chooses words to avoid offence."),
    (1.01, "Warm and accommodating. Naturally polite."),
]

_CONSCIENTIOUSNESS = [
    (0.30, "Speaks carelessly; little concern for precision or formality."),
    (0.55, "Casual in speech; comfortable with approximations."),
    (0.75, "Reasonably organized in thought; stays on topic."),
    (1.01, "Precise and measured; chooses words deliberately."),
]

_NEUROTICISM = [
    (0.30, "Emotionally steady; very difficult to rattle."),
    (0.55, "Composed; keeps feelings mostly to themselves."),
    (0.75, "Normal emotional range; occasional worry shows."),
    (1.01, "Prone to worry or defensiveness; emotional undercurrents show through."),
]

_OPENNESS = [
    (0.30, "Deeply conventional; suspicious of unfamiliar ideas."),
    (0.55, "Practical and grounded; prefers proven approaches."),
    (0.75, "Balanced between tradition and curiosity."),
    (1.01, "Curious and imaginative; drawn to ideas and possibilities."),
]


# ── Big Five combination effects ──────────────────────────────────────────────
# Checked AFTER the individual dimension descriptors.

def _combination_hints(bf: BigFive) -> list[str]:
    hints: list[str] = []

    # High extraversion + high agreeableness → warm, socially engaging
    if bf.extraversion >= 0.70 and bf.agreeableness >= 0.70:
        hints.append("Puts people at ease; conversation comes naturally.")

    # High conscientiousness + low neuroticism → calm authority
    if bf.conscientiousness >= 0.75 and bf.neuroticism < 0.35:
        hints.append("Speaks with quiet confidence; rarely second-guesses themselves in conversation.")

    # High neuroticism + low agreeableness → prickly, defensive
    if bf.neuroticism >= 0.70 and bf.agreeableness < 0.45:
        hints.append("Responds poorly to perceived criticism; quick to read slights into neutral words.")

    # Low extraversion + high conscientiousness → deliberate, careful
    if bf.extraversion < 0.40 and bf.conscientiousness >= 0.70:
        hints.append("When they do speak, the words are considered and to the point.")

    # High openness + high extraversion → enthusiastic, idea-driven
    if bf.openness >= 0.70 and bf.extraversion >= 0.70:
        hints.append("Easily excited by new ideas or unusual news; follows tangents.")

    return hints


# ── Trait tag modifiers ───────────────────────────────────────────────────────

_TRAIT_HINTS: dict[str, str] = {
    # Already present
    "gossipy":        "Enjoys sharing news and dropping names.",
    "pious":          "References their faith naturally in conversation.",
    "greedy":         "Often steers conversation toward profit or material gain.",
    "curious":        "Asks questions; shows genuine interest in novelty.",
    "proud":          "Speaks with confidence, sometimes bordering on arrogance.",
    "secretive":      "Guards information; deflects personal questions smoothly.",
    "generous":       "Offers help or information readily.",
    "vengeful":       "Remembers slights. Holds grudges quietly.",
    "stoic":          "Rarely shows emotion; keeps reactions close.",
    "meticulous":     "Notices details others miss; remarks on quality and precision.",
    "flirtatious":    "Friendly banter comes easily; reads the room well.",
    "altruistic":     "Puts others' needs before their own, even in small talk.",
    "courageous":     "Speaks plainly about danger; not easily rattled.",
    # New entries covering village NPC tags
    "methodical":     "Walks through things step by step; dislikes being rushed.",
    "proud_of_craft": "Takes visible pride in their work; will defend its quality.",
    "taciturn":       "Keeps answers short. Volunteers nothing.",
    "fair":           "Weighs both sides before speaking; dislikes exaggeration.",
    "observant":      "Notices things others overlook; references specific details.",
    "skeptical":      "Questions claims before accepting them; pushes back gently.",
    "precise":        "Corrects imprecise language; prefers exact terms.",
    "private":        "Deflects questions about personal matters.",
    "charming":       "Naturally agreeable; makes conversation feel easy and warm.",
    "perceptive":     "Reads people quickly; responds to what is left unsaid.",
    "practical":      "Cuts to what matters; not interested in abstractions.",
    "suspicious":     "Slow to trust; probes motives behind requests.",
    "stubborn":       "Holds their position even under pressure.",
    "reliable":       "Their word means something; emphasizes commitment and follow-through.",
    "quiet":          "Long pauses are comfortable. Speaks only when it adds something.",
    "patient":        "Lets others finish. Does not interrupt or rush.",
    "mediator":       "Frames disagreements as solvable; looks for common ground.",
    "wise":           "Draws on experience; speaks in terms of what has worked before.",
    "resilient":      "Has seen hard times and does not dramatize difficulty.",
    "blunt":          "Says what they mean without cushioning.",
    "weathered":      "Speaks plainly about hardship; no self-pity.",
    "opportunistic":  "Alert to advantage; phrases things in terms of mutual benefit.",
    "well_traveled":  "References places and people from beyond the village.",
    "hardworking":    "Frames things in terms of effort and outcome; little patience for idleness.",
    "shy":            "Speaks more freely on familiar topics; grows quieter around strangers.",
}


# ── Values → speech hints ─────────────────────────────────────────────────────

_VALUES_HINTS: dict[str, str] = {
    "craft":           "Returns naturally to talk of craft and quality.",
    "community":       "Frames things in terms of what is good for the village.",
    "self_sufficiency":"Values independence; dislikes dependency or charity.",
    "knowledge":       "Drawn to explanation; values understanding over quick answers.",
    "health":          "Mentions wellbeing, diet, and rest unprompted.",
    "independence":    "Chafes at obligations; values doing things their own way.",
    "wealth":          "Mentions money or trade naturally.",
    "entertainment":   "Lightens the mood; finds humor in most situations.",
    "family":          "References kin and home; protective of loved ones.",
    "stability":       "Uneasy about change; prefers things to stay predictable.",
    "hard_work":       "Respects effort; loses patience with laziness.",
    "faith":           "Faith colours their worldview; cites the gods or tradition.",
    "peace":           "Steers away from conflict; prefers reconciliation.",
    "fair_dealing":    "Cares about fairness; will call out injustice.",
    "simple_life":     "Prefers plain speech; distrusts complexity.",
    "nature":          "Notices the natural world; references seasons, weather, animals.",
    "tradition":       "Suspicious of novelty; invokes how things have always been done.",
    "freedom":         "Resents being told what to do; values autonomy.",
    "novelty":         "Gets bored of routine topics; perks up at new information.",
}


# ── Public API ────────────────────────────────────────────────────────────────

def _pick(table: list[tuple[float, str]], value: float) -> str:
    for threshold, descriptor in table:
        if value < threshold:
            return descriptor
    return table[-1][1]


def speech_style_block(big_five: BigFive, trait_tags: list[str], values: list[str] | None = None) -> str:
    """
    Produce a concise prose block describing how this NPC speaks.
    Injected into the system prompt under ## SPEECH STYLE.
    """
    lines = [
        _pick(_EXTRAVERSION, big_five.extraversion),
        _pick(_AGREEABLENESS, big_five.agreeableness),
        _pick(_CONSCIENTIOUSNESS, big_five.conscientiousness),
        _pick(_NEUROTICISM, big_five.neuroticism),
        _pick(_OPENNESS, big_five.openness),
    ]

    lines.extend(_combination_hints(big_five))

    for tag in trait_tags:
        if hint := _TRAIT_HINTS.get(tag.lower()):
            lines.append(hint)

    for value in (values or []):
        if hint := _VALUES_HINTS.get(value.lower()):
            lines.append(hint)

    return " ".join(lines)
