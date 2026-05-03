"""Dialogue engine — processes player turns and generates NPC responses."""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import settings
from dialogue.prompt_builder import DialogueContext, build_system_prompt
from dialogue.session import DialogueSession, DialogueTurn
from llm.runner import LLMRunner
from llm.types import LLMOptions, Message

# Fallback menu options when the LLM returns unparseable output
_FALLBACK_OPTIONS = [
    "Ask what they're working on.",
    "Ask about the village.",
    "Say farewell.",
]

_MENU_PARSE_RE = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)


@dataclass
class DialogueEngine:
    runner: LLMRunner

    def player_turn(
        self,
        session: DialogueSession,
        player_input: str,
        ctx: DialogueContext,
    ) -> DialogueTurn:
        """
        Process one player turn: call the LLM for an NPC response, then
        generate new menu options.  Appends the turn to the session.
        """
        system_prompt = build_system_prompt(ctx)
        history = session.to_messages()

        messages = [
            Message("system", system_prompt),
            *history,
            Message("user", player_input),
        ]

        npc_response = self.runner.logged_chat(
            messages,
            LLMOptions(
                temperature=settings.llm.temperature,
                max_tokens=settings.llm.dialogue_max_tokens,
            ),
            tags={"type:dialogue", f"npc:{ctx.npc.id}"},
        ).content.strip()

        menu_options = self._generate_menu(session, ctx, npc_response, system_prompt)

        turn = DialogueTurn(
            player_input=player_input,
            npc_response=npc_response,
            menu_options=menu_options,
        )
        session.add_turn(turn)
        return turn

    def _generate_menu(
        self,
        session: DialogueSession,
        ctx: DialogueContext,
        last_npc_response: str,
        system_prompt: str,
    ) -> list[str]:
        """Generate menu options for the next player turn."""
        n = settings.llm.menu_options_count
        history = session.to_messages()  # history before current turn was added

        menu_request = (
            f"{ctx.npc.name} just said: \"{last_npc_response}\"\n\n"
            f"Write exactly {n} short things the player could say next. "
            f"Each should be a brief, natural reply. "
            f"Numbered list, one per line. No quotation marks."
        )

        messages = [
            Message("system", system_prompt),
            *history,
            Message("user", menu_request),
        ]

        raw = self.runner.logged_chat(
            messages,
            LLMOptions(temperature=0.9, max_tokens=100),
            tags={"type:menu", f"npc:{ctx.npc.id}"},
        ).content

        return self._parse_menu(raw, n)

    @staticmethod
    def _parse_menu(raw: str, n: int) -> list[str]:
        options = [m.strip() for m in _MENU_PARSE_RE.findall(raw)]
        # Strip surrounding quotes if the LLM added them anyway
        options = [o.strip('"\'') for o in options if o]
        if len(options) >= 2:
            return options[:n]
        return _FALLBACK_OPTIONS[:n]
