"""Tests for the LLM runner abstraction, prompt log, and factory."""
import time
from unittest.mock import MagicMock, patch

import pytest

from llm.factory import get_runner, reset_runner, set_runner
from llm.ollama_runner import OllamaRunner
from llm.prompt_log import PromptLog
from llm.runner import LLMRunnerError
from llm.stub_runner import StubRunner
from llm.types import LLMOptions, LLMResponse, Message, PromptLogEntry


# ── StubRunner ────────────────────────────────────────────────────────────────

def test_stub_returns_fixed_string():
    runner = StubRunner("Greetings, traveller.")
    resp = runner.chat([Message("user", "Hello")])
    assert resp.content == "Greetings, traveller."
    assert resp.model == "stub"


def test_stub_callable_response():
    def reply(msgs: list[Message]) -> str:
        return f"You said: {msgs[-1].content}"

    runner = StubRunner(reply)
    resp = runner.chat([Message("user", "Bread")])
    assert resp.content == "You said: Bread"


def test_stub_tracks_call_count():
    runner = StubRunner("Aye.")
    runner.chat([Message("user", "One")])
    runner.chat([Message("user", "Two")])
    assert runner.call_count == 2


def test_stub_token_counts_are_nonzero():
    runner = StubRunner("Hello world")
    resp = runner.chat([Message("user", "Say something")])
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0


def test_stub_options_accepted_without_error():
    runner = StubRunner("Fine.")
    opts = LLMOptions(temperature=0.5, max_tokens=50)
    resp = runner.chat([Message("user", "Test")], options=opts)
    assert resp.content == "Fine."


def test_stub_runner_id():
    assert StubRunner().runner_id == "stub"


# ── PromptLog ─────────────────────────────────────────────────────────────────

def _make_entry(**kwargs) -> PromptLogEntry:
    defaults = dict(
        runner_id="stub",
        model="stub",
        messages=[Message("user", "hi")],
        response="hello",
    )
    defaults.update(kwargs)
    return PromptLogEntry(**defaults)


def test_prompt_log_records_and_retrieves():
    log = PromptLog()
    entry = _make_entry()
    log.record(entry)
    assert len(log) == 1
    assert log.recent(10)[0] is entry


def test_prompt_log_most_recent_first():
    log = PromptLog()
    e1 = _make_entry(response="first")
    e2 = _make_entry(response="second")
    log.record(e1)
    log.record(e2)
    assert log.recent(2)[0] is e2
    assert log.recent(2)[1] is e1


def test_prompt_log_maxlen_evicts_oldest():
    log = PromptLog(max_entries=3)
    for i in range(5):
        log.record(_make_entry(response=str(i)))
    assert len(log) == 3
    contents = [e.response for e in log.recent(3)]
    assert "0" not in contents
    assert "4" in contents


def test_prompt_log_filter_by_tag():
    log = PromptLog()
    log.record(_make_entry(tags={"type:dialogue", "npc:aldric"}))
    log.record(_make_entry(tags={"type:summary"}))
    log.record(_make_entry(tags={"type:dialogue", "npc:maren"}))

    dialogue = log.recent(tag="type:dialogue")
    assert len(dialogue) == 2

    summary = log.recent(tag="type:summary")
    assert len(summary) == 1


def test_prompt_log_get_by_id():
    log = PromptLog()
    entry = _make_entry()
    log.record(entry)
    assert log.get(entry.id) is entry
    assert log.get("nonexistent") is None


def test_prompt_log_clear():
    log = PromptLog()
    log.record(_make_entry())
    log.clear()
    assert len(log) == 0


def test_prompt_log_entry_to_dict():
    entry = _make_entry(tags={"type:dialogue"})
    d = entry.to_dict()
    assert d["runner_id"] == "stub"
    assert d["response"] == "hello"
    assert "type:dialogue" in d["tags"]
    assert "timestamp" in d


# ── logged_chat integration ───────────────────────────────────────────────────

def test_logged_chat_records_to_log():
    from llm import prompt_log
    prompt_log.clear()

    runner = StubRunner("I am a stub.")
    runner.logged_chat([Message("user", "Hello")], tags={"type:test"})

    assert len(prompt_log) == 1
    entry = prompt_log.recent(1)[0]
    assert entry.response == "I am a stub."
    assert "type:test" in entry.tags
    assert entry.runner_id == "stub"
    assert entry.error is None


def test_logged_chat_records_error():
    from llm import prompt_log
    prompt_log.clear()

    class BrokenRunner(StubRunner):
        def chat(self, messages, options=None):
            raise RuntimeError("boom")

    runner = BrokenRunner()
    with pytest.raises(RuntimeError):
        runner.logged_chat([Message("user", "Help")])

    assert len(prompt_log) == 1
    entry = prompt_log.recent(1)[0]
    assert entry.error is not None
    assert "boom" in entry.error


# ── OllamaRunner (offline mocked) ─────────────────────────────────────────────

def _mock_chat_response(content: str, model: str = "llama3.2"):
    resp = MagicMock()
    resp.message.content = content
    resp.model = model
    resp.prompt_eval_count = 10
    resp.eval_count = 5
    resp.total_duration = 500_000_000  # 500ms in ns
    return resp


def test_ollama_runner_id():
    assert OllamaRunner().runner_id == "ollama"


def test_ollama_runner_maps_response():
    runner = OllamaRunner(model="llama3.2")
    mock_resp = _mock_chat_response("Well met, traveller.")

    with patch("ollama.chat", return_value=mock_resp):
        resp = runner.chat([Message("user", "Hello")])

    assert resp.content == "Well met, traveller."
    assert resp.model == "llama3.2"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert abs(resp.duration_ms - 500.0) < 1.0


def test_ollama_runner_passes_options():
    runner = OllamaRunner(model="llama3.2")
    mock_resp = _mock_chat_response("Aye.")

    with patch("ollama.chat", return_value=mock_resp) as mock_call:
        runner.chat(
            [Message("user", "Test")],
            LLMOptions(temperature=0.3, max_tokens=30),
        )

    call_kwargs = mock_call.call_args.kwargs
    assert call_kwargs["options"]["temperature"] == 0.3
    assert call_kwargs["options"]["num_predict"] == 30


def test_ollama_runner_wraps_connection_error():
    runner = OllamaRunner()
    with patch("ollama.chat", side_effect=ConnectionError("refused")):
        with pytest.raises(LLMRunnerError, match="Ollama request failed"):
            runner.chat([Message("user", "Hello")])


def test_ollama_runner_wraps_response_error():
    import ollama as _ollama
    runner = OllamaRunner()
    with patch("ollama.chat", side_effect=_ollama.ResponseError("no model")):
        with pytest.raises(LLMRunnerError):
            runner.chat([Message("user", "Hi")])


# ── Factory ────────────────────────────────────────────────────────────────────

def test_factory_set_and_get():
    stub = StubRunner("test")
    set_runner(stub)
    assert get_runner() is stub
    reset_runner()


def test_factory_reset_creates_new():
    stub = StubRunner()
    set_runner(stub)
    reset_runner()
    # After reset, get_runner will try to create from config (ollama by default).
    # We don't want to actually init Ollama here, so just confirm reset_runner
    # cleared the cached instance.
    from llm import factory
    assert factory._runner is None
    # Put a stub back so other tests are not affected
    set_runner(StubRunner())


def test_factory_stub_type():
    reset_runner()
    from config import settings
    original = settings.llm.default_runner
    settings.llm.default_runner = "stub"
    reset_runner()
    runner = get_runner()
    assert runner.runner_id == "stub"
    settings.llm.default_runner = original
    reset_runner()
