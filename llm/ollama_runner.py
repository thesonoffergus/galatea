"""Ollama runner — wraps the ollama Python SDK."""
from __future__ import annotations

from config import settings
from llm.runner import LLMRunner, LLMRunnerError
from llm.types import LLMOptions, LLMResponse, Message


class OllamaRunner(LLMRunner):
    """
    Calls a local Ollama instance via its Python SDK.

    Raises LLMRunnerError if Ollama is unreachable or returns an error.
    """

    def __init__(self, model: str | None = None, base_url: str = "http://localhost:11434"):
        self._model = model or settings.llm.default_model
        self._base_url = base_url

    @property
    def runner_id(self) -> str:
        return "ollama"

    def chat(
        self,
        messages: list[Message],
        options: LLMOptions | None = None,
    ) -> LLMResponse:
        try:
            import ollama
        except ImportError as exc:
            raise LLMRunnerError("ollama package is not installed") from exc

        opts = self._build_options(options)
        raw_messages = [m.to_dict() for m in messages]

        try:
            response = ollama.chat(
                model=self._model,
                messages=raw_messages,
                options=opts if opts else None,
            )
        except Exception as exc:
            raise LLMRunnerError(
                f"Ollama request failed ({self._base_url}): {exc}"
            ) from exc

        content = response.message.content or ""
        duration_ms = 0.0
        if hasattr(response, "total_duration") and response.total_duration:
            duration_ms = response.total_duration / 1_000_000  # ns → ms

        return LLMResponse(
            content=content,
            model=response.model or self._model,
            prompt_tokens=getattr(response, "prompt_eval_count", 0) or 0,
            completion_tokens=getattr(response, "eval_count", 0) or 0,
            duration_ms=duration_ms,
            raw=response,
        )

    def _build_options(self, options: LLMOptions | None) -> dict:
        opts: dict = {}
        llm_cfg = settings.llm

        temp = options.temperature if (options and options.temperature is not None) else llm_cfg.temperature
        opts["temperature"] = temp

        max_tok = options.max_tokens if (options and options.max_tokens is not None) else llm_cfg.dialogue_max_tokens
        opts["num_predict"] = max_tok

        if options and options.stop:
            opts["stop"] = options.stop

        return opts

    def list_models(self) -> list[str]:
        """Return names of locally available models (or empty list on error)."""
        try:
            import ollama
            resp = ollama.list()
            return [m.model for m in resp.models]
        except Exception:
            return []
