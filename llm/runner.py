"""Runner-agnostic LLM interface."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from llm.types import LLMOptions, LLMResponse, Message, PromptLogEntry

if TYPE_CHECKING:
    pass


class LLMRunnerError(RuntimeError):
    """Raised when the LLM backend is unavailable or returns an error."""


class LLMRunner(ABC):
    """
    Abstract base for all LLM runners (Ollama, llama.cpp, stub, …).

    Implementors override `chat`. Callers should prefer `logged_chat` so
    every call is recorded in the prompt log automatically.
    """

    @property
    @abstractmethod
    def runner_id(self) -> str:
        """Short identifier, e.g. 'ollama' or 'stub'."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        options: LLMOptions | None = None,
    ) -> LLMResponse:
        """Send messages and return the response. Must not log."""

    def logged_chat(
        self,
        messages: list[Message],
        options: LLMOptions | None = None,
        tags: set[str] | None = None,
    ) -> LLMResponse:
        """
        chat() with automatic prompt logging.

        Every call — success or failure — is recorded in the global prompt_log.
        Use `tags` to annotate entries for filtering (e.g. {"type:dialogue", "npc:aldric"}).
        """
        from llm.prompt_log import prompt_log  # late import to avoid circularity

        t0 = time.monotonic()
        response: LLMResponse | None = None
        error: str | None = None
        try:
            response = self.chat(messages, options)
            return response
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = (time.monotonic() - t0) * 1000
            prompt_log.record(PromptLogEntry(
                runner_id=self.runner_id,
                model=response.model if response else "unknown",
                messages=messages,
                response=response.content if response else "",
                prompt_tokens=response.prompt_tokens if response else 0,
                completion_tokens=response.completion_tokens if response else 0,
                duration_ms=elapsed,
                tags=set(tags) if tags else set(),
                error=error,
            ))

    async def async_logged_chat(
        self,
        messages: list[Message],
        options: LLMOptions | None = None,
        tags: set[str] | None = None,
    ) -> LLMResponse:
        """Async wrapper — runs logged_chat in a thread executor."""
        import asyncio
        import functools
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(self.logged_chat, messages, options, tags),
        )
