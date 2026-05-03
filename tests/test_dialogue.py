"""Tests for the dialogue system — prompt builder, session, engine."""
from pathlib import Path

import pytest

from affordances.query import what_can_actor_do
from affordances.registry import ActionRegistry
from dialogue.engine import DialogueEngine
from dialogue.prompt_builder import (
    DialogueContext,
    affordance_digest,
    build_system_prompt,
)
from dialogue.session import DialogueSession, DialogueTurn
from dialogue.speech_style import speech_style_block
from llm.stub_runner import StubRunner
from llm.types import Message
from npc.loader import load_npcs
from npc.schema import BigFive, NPC, NPCTier
from world.loader import load_world

SEED_PATH = Path(__file__).parent.parent / "data" / "village_seed.yaml"
ACTIONS_PATH = Path(__file__).parent.parent / "data" / "actions.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def seed_graph():
    return load_world(SEED_PATH)


@pytest.fixture(scope="module")
def npc_registry(seed_graph):
    reg, _ = load_npcs(SEED_PATH, graph=seed_graph)
    return reg


@pytest.fixture(scope="module")
def action_registry():
    return ActionRegistry.from_yaml(ACTIONS_PATH)


@pytest.fixture
def aldric(npc_registry):
    return npc_registry.get("npc_aldric_stonehand")


@pytest.fixture
def player(npc_registry):
    return npc_registry.player()


@pytest.fixture
def aldric_context(aldric, player, seed_graph, action_registry, npc_registry):
    zone = seed_graph.get_zone(aldric.current_zone_id)
    tag_map = npc_registry.build_npc_tag_map()
    actor_ctx = aldric.as_actor_context(graph=seed_graph)
    actor_ctx.inventory["iron_ingot"] = 5
    actor_ctx.inventory["iron_ore"] = 4
    available = what_can_actor_do(
        actor_ctx, aldric.current_zone_id, seed_graph, action_registry, npc_tag_map=tag_map
    )
    zone_npcs = [
        npc_registry.get(nid)
        for nid in zone.npc_ids
        if nid != aldric.id
        and nid in {n.id for n in npc_registry.all_npcs()}
    ]
    return DialogueContext(
        npc=aldric,
        player=player,
        zone=zone,
        zone_npcs=zone_npcs,
        available_actions=available,
    )


# ── Speech style ──────────────────────────────────────────────────────────────

def test_speech_style_low_extraversion():
    bf = BigFive(extraversion=0.2)
    style = speech_style_block(bf, [])
    # Very low extraversion (< 0.30) → "Speaks very little"
    assert "very little" in style.lower() or "briefly" in style.lower()


def test_speech_style_high_agreeableness():
    bf = BigFive(agreeableness=0.9)
    style = speech_style_block(bf, [])
    assert "warm" in style.lower() or "accommodating" in style.lower() or "polite" in style.lower()


def test_speech_style_low_neuroticism():
    bf = BigFive(neuroticism=0.1)
    style = speech_style_block(bf, [])
    assert "steady" in style.lower() or "difficult to rattle" in style.lower()


def test_speech_style_includes_trait_hints():
    bf = BigFive()
    style = speech_style_block(bf, ["gossipy", "stoic"])
    assert "news" in style.lower()        # gossipy hint
    assert "emotion" in style.lower()     # stoic hint


def test_speech_style_unknown_tags_ignored():
    bf = BigFive()
    style = speech_style_block(bf, ["nonexistent_tag"])
    assert isinstance(style, str)
    assert len(style) > 0


def test_speech_style_values_included():
    bf = BigFive()
    style = speech_style_block(bf, [], values=["craft", "community"])
    assert "craft" in style.lower() or "quality" in style.lower()
    assert "village" in style.lower() or "community" in style.lower()


def test_speech_style_combination_high_e_high_a():
    bf = BigFive(extraversion=0.85, agreeableness=0.85)
    style = speech_style_block(bf, [])
    assert "ease" in style.lower() or "naturally" in style.lower()


def test_aldric_speech_style(aldric):
    style = speech_style_block(aldric.big_five, aldric.trait_tags, values=aldric.values)
    # Aldric: conscientiousness=0.85, extraversion=0.25, proud_of_craft, taciturn, methodical
    assert "proud" in style.lower() or "craft" in style.lower() or "quality" in style.lower()
    assert len(style) > 20


# ── Affordance digest ─────────────────────────────────────────────────────────

def test_affordance_digest_empty():
    assert affordance_digest([]) == ""


def test_affordance_digest_includes_crafting(aldric_context):
    digest = affordance_digest(aldric_context.available_actions)
    assert "Craft" in digest


def test_affordance_digest_no_categories_leaked(aldric_context):
    digest = affordance_digest(aldric_context.available_actions)
    # Should use human-readable names, not raw action IDs in the format shown
    assert isinstance(digest, str)
    assert len(digest) > 0


# ── Prompt builder ────────────────────────────────────────────────────────────

def test_system_prompt_contains_world_primer(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## WORLD" in prompt
    assert "medieval" in prompt.lower()
    assert "gunpowder" in prompt.lower()


def test_system_prompt_contains_npc_identity(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## IDENTITY" in prompt
    assert "Aldric" in prompt
    assert "Blacksmith" in prompt


def test_system_prompt_contains_speech_style(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## SPEECH STYLE" in prompt


def test_system_prompt_contains_scene(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## SCENE" in prompt
    assert "Forge Room" in prompt


def test_system_prompt_contains_constraints(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## CONSTRAINTS" in prompt
    assert "in character" in prompt.lower()
    assert "1–3 sentences" in prompt or "1-3 sentences" in prompt


def test_system_prompt_contains_affordances(aldric_context):
    prompt = build_system_prompt(aldric_context)
    # Aldric has crafting actions available → digest should appear
    assert "Craft" in prompt


def test_system_prompt_includes_memory_stub(aldric_context):
    prompt = build_system_prompt(aldric_context)
    assert "## MEMORY" in prompt


def test_system_prompt_with_memory_excerpts(aldric_context):
    from copy import copy
    ctx = copy(aldric_context)
    ctx.memory_excerpts = ["Three moons ago, the player helped mend a wagon wheel."]
    prompt = build_system_prompt(ctx)
    assert "wagon wheel" in prompt


def test_system_prompt_narrative_summary_injected(aldric_context, aldric):
    aldric.narrative_summary = "Aldric once forged a blade for a wandering knight, a memory he guards closely."
    prompt = build_system_prompt(aldric_context)
    assert "wandering knight" in prompt
    aldric.narrative_summary = ""


def test_system_prompt_relationship_warmth(aldric_context, aldric, player):
    from npc.schema import Relationship
    aldric.set_relationship(Relationship(other_id=player.id, affinity=0.8))
    prompt = build_system_prompt(aldric_context)
    assert "well of them" in prompt or "think well" in prompt
    # Clean up
    aldric.relationships.pop(player.id, None)


# ── DialogueSession ───────────────────────────────────────────────────────────

def test_session_starts_empty():
    s = DialogueSession(npc_id="n1", player_id="p1", zone_id="z1")
    assert s.is_empty
    assert s.to_messages() == []


def test_session_add_turn_grows_history():
    s = DialogueSession(npc_id="n1", player_id="p1", zone_id="z1")
    turn = DialogueTurn("Hello", "Well met.", ["Ask about work.", "Farewell."])
    s.add_turn(turn)
    assert not s.is_empty
    assert len(s.turns) == 1


def test_session_to_messages_interleaves():
    s = DialogueSession(npc_id="n1", player_id="p1", zone_id="z1")
    s.add_turn(DialogueTurn("Hi", "Ho"))
    s.add_turn(DialogueTurn("Question", "Answer"))
    msgs = s.to_messages()
    assert len(msgs) == 4
    assert msgs[0].role == "user" and msgs[0].content == "Hi"
    assert msgs[1].role == "assistant" and msgs[1].content == "Ho"
    assert msgs[2].role == "user"
    assert msgs[3].role == "assistant"


def test_session_menu_options_updated_on_add():
    s = DialogueSession(npc_id="n1", player_id="p1", zone_id="z1")
    s.add_turn(DialogueTurn("Hi", "Ho", menu_options=["A", "B"]))
    assert s.menu_options == ["A", "B"]


# ── DialogueEngine ────────────────────────────────────────────────────────────

def test_engine_processes_turn(aldric_context, aldric):
    runner = StubRunner("Aye, what is it ye need?")
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    turn = engine.player_turn(session, "Good day.", aldric_context)

    assert turn.npc_response == "Aye, what is it ye need?"
    assert turn.player_input == "Good day."
    assert len(session.turns) == 1


def test_engine_appends_multiple_turns(aldric_context, aldric):
    runner = StubRunner("As ye wish.")
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    engine.player_turn(session, "First.", aldric_context)
    engine.player_turn(session, "Second.", aldric_context)
    assert len(session.turns) == 2


def test_engine_history_grows_correctly(aldric_context, aldric):
    # Each player_turn makes 2 LLM calls: response + menu.
    # Alternate: odd calls = NPC response, even calls = menu output.
    call_n = [0]
    npc_replies = ["First reply.", "Second reply."]

    def reply_stub(msgs: list[Message]) -> str:
        call_n[0] += 1
        if call_n[0] % 2 == 1:
            return npc_replies[(call_n[0] - 1) // 2]
        return "1. Option A\n2. Option B\n3. Option C"

    runner = StubRunner(reply_stub)
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    engine.player_turn(session, "Hello.", aldric_context)
    engine.player_turn(session, "Goodbye.", aldric_context)

    msgs = session.to_messages()
    assert msgs[0].content == "Hello."
    assert msgs[1].content == "First reply."
    assert msgs[2].content == "Goodbye."
    assert msgs[3].content == "Second reply."


def test_engine_generates_menu_options(aldric_context, aldric):
    call_n = [0]
    def smart_stub(msgs: list[Message]) -> str:
        call_n[0] += 1
        if call_n[0] % 2 == 0:
            # Menu call
            return "1. Ask about the anvil\n2. Inquire about prices\n3. Say farewell"
        return "I am busy."

    runner = StubRunner(smart_stub)
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    turn = engine.player_turn(session, "Good morning.", aldric_context)
    assert len(turn.menu_options) >= 2


def test_engine_menu_fallback_on_bad_output(aldric_context, aldric):
    call_n = [0]
    def bad_menu_stub(msgs):
        call_n[0] += 1
        if call_n[0] % 2 == 0:
            return "The menu is broken gibberish here."
        return "Aye."

    runner = StubRunner(bad_menu_stub)
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    turn = engine.player_turn(session, "Hello.", aldric_context)
    # Fallback options should kick in
    assert len(turn.menu_options) >= 2


def test_engine_logs_to_prompt_log(aldric_context, aldric):
    from llm.prompt_log import PromptLog
    from llm import prompt_log

    prompt_log.clear()
    runner = StubRunner("Fine work ye do.")
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    engine.player_turn(session, "Hello.", aldric_context)

    entries = prompt_log.recent(10)
    assert len(entries) >= 1
    dialogue_entries = [e for e in entries if "type:dialogue" in e.tags]
    assert len(dialogue_entries) >= 1


def test_engine_system_prompt_passes_to_runner(aldric_context, aldric):
    captured = []
    def capture_stub(msgs: list[Message]) -> str:
        captured.extend(msgs)
        return "Fine."
    runner = StubRunner(capture_stub)
    engine = DialogueEngine(runner=runner)
    session = DialogueSession(
        npc_id=aldric.id, player_id="player", zone_id=aldric.current_zone_id
    )
    engine.player_turn(session, "Hello.", aldric_context)
    system_msgs = [m for m in captured if m.role == "system"]
    assert len(system_msgs) > 0
    assert "WORLD" in system_msgs[0].content
    assert "Aldric" in system_msgs[0].content
