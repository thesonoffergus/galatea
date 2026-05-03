"""Core data types for the LLM layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    stop: list[str] = field(default_factory=list)


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    raw: Any = None  # original SDK response, kept for debugging


@dataclass
class PromptLogEntry:
    runner_id: str
    model: str
    messages: list[Message]
    response: str
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    tags: set[str] = field(default_factory=set)  # e.g. {"type:dialogue", "npc:aldric"}
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "runner_id": self.runner_id,
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "response": self.response,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "duration_ms": round(self.duration_ms, 1),
            "tags": sorted(self.tags),
            "error": self.error,
        }
