"""Deterministic stub runner for tests and development without a live LLM."""
from __future__ import annotations

from typing import Callable

from llm.runner import LLMRunner
from llm.types import LLMOptions, LLMResponse, Message


class StubRunner(LLMRunner):
    """
    Returns a fixed or computed string without hitting any network.

    Pass a string for a constant reply, or a callable
    (list[Message]) -> str for dynamic responses.
    """

    def __init__(
        self,
        response: str | Callable[[list[Message]], str] = "Aye.",
        model: str = "stub",
        latency_ms: float = 0.0,
    ):
        self._response = response
        self._model = model
        self._latency_ms = latency_ms
        self._call_count = 0

    @property
    def runner_id(self) -> str:
        return "stub"

    def chat(
        self,
        messages: list[Message],
        options: LLMOptions | None = None,
    ) -> LLMResponse:
        import time
        if self._latency_ms:
            time.sleep(self._latency_ms / 1000)

        self._call_count += 1
        if callable(self._response):
            content = self._response(messages)
        else:
            content = self._response

        return LLMResponse(
            content=content,
            model=self._model,
            prompt_tokens=sum(len(m.content.split()) for m in messages),
            completion_tokens=len(content.split()),
            duration_ms=self._latency_ms,
        )

    @property
    def call_count(self) -> int:
        return self._call_count
