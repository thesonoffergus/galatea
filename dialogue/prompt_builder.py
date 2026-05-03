"""Assembles the per-NPC system prompt from modular blocks."""
from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import dedent

from affordances.schema import Action, ActionCategory
from dialogue.speech_style import speech_style_block
from npc.schema import NPC
from world.zone import Zone

# ── Constants ─────────────────────────────────────────────────────────────────

_WORLD_PRIMER = dedent("""\
    This is a pre-industrial medieval world of iron and wood. No gunpowder, no \
    electricity, no modern institutions. Titles, craft, trade, and faith govern \
    daily life. The people are grounded and pragmatic, shaped by the constraints \
    of their era. Never reference anything outside this world.\
""")

_HARD_CONSTRAINTS = dedent("""\
    - Stay in character at all times. Never acknowledge being an AI or a game NPC.
    - If the player says something incoherent or anachronistic, respond in-character \
    (confusion, suspicion, brief deflection) — do not break the fiction.
    - Keep your response to 1–3 sentences. No speeches or monologues.
    - Do not prefix your reply with your name or quotation marks.\
""")


# ── Context ───────────────────────────────────────────────────────────────────

@dataclass
class DialogueContext:
    """Everything the prompt builder needs for one dialogue scene."""
    npc: NPC
    player: NPC
    zone: Zone
    zone_npcs: list[NPC]             # other NPCs present (besides npc and player)
    available_actions: list[Action]  # npc's actions in current zone
    memory_excerpts: list[str] = field(default_factory=list)  # populated via knowledge.retrieval


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mood_description(mood: float) -> str:
    if mood < -0.6:  return "visibly unhappy"
    if mood < -0.2:  return "somewhat sour"
    if mood <  0.2:  return "neutral"
    if mood <  0.6:  return "in decent spirits"
    return "noticeably good-humored"


def affordance_digest(actions: list[Action]) -> str:
    """
    Human-readable summary of available actions for injection into the scene block.
    Groups by category; empty string if nothing is available.
    """
    crafting = [a for a in actions if a.category == ActionCategory.CRAFTING]
    gathering = [a for a in actions if a.category == ActionCategory.GATHERING]
    social = [a for a in actions if a.category == ActionCategory.SOCIAL]

    parts: list[str] = []
    if crafting:
        names = ", ".join(a.name for a in crafting)
        parts.append(f"Craft: {names}.")
    if gathering:
        names = ", ".join(a.name for a in gathering)
        parts.append(f"Gather: {names}.")
    if social:
        names = ", ".join(a.name for a in social)
        parts.append(f"Social: {names}.")
    return " ".join(parts)


# ── Main composer ─────────────────────────────────────────────────────────────

def build_system_prompt(ctx: DialogueContext) -> str:
    """
    Assemble the full system prompt from all modular blocks.

    Block order matches the spec:
      1. World primer
      2. NPC identity (name, role, description, traits, values, active goals)
      3. Speech style (derived from Big Five + trait tags)
      4. Memory excerpts (narrative summary + RAG-retrieved individual/community)
      5. Scene context (zone, present characters, affordances)
      6. Hard constraints
    """
    npc = ctx.npc
    player = ctx.player

    # ── 1. World primer ───────────────────────────────────────────────────────
    blocks: list[str] = [f"## WORLD\n{_WORLD_PRIMER}"]

    # ── 2. Identity ───────────────────────────────────────────────────────────
    identity_lines = [f"You are {npc.name}, a {npc.role}."]
    if npc.description:
        identity_lines.append(npc.description)
    if npc.trait_tags:
        identity_lines.append(f"Known traits: {', '.join(npc.trait_tags)}.")
    if npc.values:
        identity_lines.append(f"Values: {', '.join(npc.values)}.")
    identity_lines.append(f"Current mood: {_mood_description(npc.mood)}.")

    rel = npc.relationships.get(player.id)
    if rel is not None:
        if rel.affinity > 0.5:
            identity_lines.append(f"You know {player.name} and think well of them.")
        elif rel.affinity < -0.2:
            identity_lines.append(f"You have a poor opinion of {player.name}.")
        elif rel.familiarity > 0.3:
            identity_lines.append(f"You know {player.name} in passing.")

    active_goals = npc.active_goals()
    if active_goals:
        goal_strs = "; ".join(g.description for g in active_goals)
        identity_lines.append(f"Current goals: {goal_strs}.")

    blocks.append("## IDENTITY\n" + "\n".join(identity_lines))

    # ── 3. Speech style ───────────────────────────────────────────────────────
    style = speech_style_block(npc.big_five, npc.trait_tags, values=npc.values)
    blocks.append(f"## SPEECH STYLE\n{style}")

    # ── 4. Memory ─────────────────────────────────────────────────────────────
    mem_parts: list[str] = []
    if npc.narrative_summary:
        mem_parts.append(f"[Past history] {npc.narrative_summary}")
    if ctx.memory_excerpts:
        mem_parts.extend(f"- {e}" for e in ctx.memory_excerpts)
    if mem_parts:
        blocks.append("## MEMORY\n" + "\n".join(mem_parts))
    else:
        blocks.append("## MEMORY\nNo specific memories to recall at this moment.")

    # ── 5. Scene context ──────────────────────────────────────────────────────
    scene_lines = [f"You are currently in {ctx.zone.name}."]
    if ctx.zone.appearance:
        scene_lines.append(ctx.zone.appearance)

    others = [n for n in ctx.zone_npcs if n.id != npc.id and n.id != player.id]
    if others:
        names = ", ".join(n.name for n in others)
        scene_lines.append(f"Others present: {names}.")
    else:
        scene_lines.append(f"{player.name} has just approached you.")

    digest = affordance_digest(ctx.available_actions)
    if digest:
        scene_lines.append(f"What you could do here — {digest}")

    blocks.append("## SCENE\n" + "\n".join(scene_lines))

    # ── 6. Hard constraints ───────────────────────────────────────────────────
    blocks.append(f"## CONSTRAINTS\n{_HARD_CONSTRAINTS}")

    return "\n\n".join(blocks)
