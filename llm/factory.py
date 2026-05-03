"""Runner factory — returns the globally configured LLM runner."""
from __future__ import annotations

from config import settings
from llm.runner import LLMRunner

_runner: LLMRunner | None = None


def get_runner() -> LLMRunner:
    """Return the active runner, creating it from config on first call."""
    global _runner
    if _runner is None:
        _runner = _make_runner(settings.llm.default_runner)
    return _runner


def set_runner(runner: LLMRunner) -> None:
    """Override the active runner (useful in tests and tooling)."""
    global _runner
    _runner = runner


def reset_runner() -> None:
    """Force next get_runner() call to recreate from config."""
    global _runner
    _runner = None


def _make_runner(runner_type: str) -> LLMRunner:
    match runner_type:
        case "ollama":
            from llm.ollama_runner import OllamaRunner
            return OllamaRunner()
        case "stub":
            from llm.stub_runner import StubRunner
            return StubRunner()
        case _:
            raise ValueError(f"Unknown LLM runner type: {runner_type!r}")
