"""Dialogue session and turn data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from llm.types import Message


@dataclass
class DialogueTurn:
    player_input: str
    npc_response: str
    menu_options: list[str] = field(default_factory=list)


@dataclass
class DialogueSession:
    """
    In-memory record of one player↔NPC conversation.

    `menu_options` is the set offered to the player for the *next* turn —
    updated after each NPC response.
    """
    npc_id: str
    player_id: str
    zone_id: str
    turns: list[DialogueTurn] = field(default_factory=list)
    menu_options: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_turn(self, turn: DialogueTurn) -> None:
        self.turns.append(turn)
        self.menu_options = turn.menu_options

    def to_messages(self) -> list[Message]:
        """Convert turn history to alternating user/assistant messages."""
        msgs: list[Message] = []
        for turn in self.turns:
            msgs.append(Message("user", turn.player_input))
            msgs.append(Message("assistant", turn.npc_response))
        return msgs

    @property
    def is_empty(self) -> bool:
        return len(self.turns) == 0
