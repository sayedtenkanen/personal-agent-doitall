"""
Tests for chat session CRUD and LLM module (provider-mocked).
"""

import pytest

from agent.core.chat import (
    ChatMessage,
    ChatSession,
    add_message,
    create_session,
    delete_session,
    get_messages,
    get_session_by_id,
    list_sessions,
)
from agent.core.llm import LLMError, build_system_prompt, get_reply, is_available
from agent.core.storage import get_session, init_db


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------


def test_create_session_persists():
    with get_session() as db:
        s = create_session(db, title="Work planning")

    assert s.id
    assert s.title == "Work planning"


def test_add_and_retrieve_messages():
    with get_session() as db:
        s = create_session(db, title="Test")
        add_message(db, session_id=s.id, role="user", content="Hello!")
        add_message(db, session_id=s.id, role="assistant", content="Hi there!")
        msgs = get_messages(db, s.id)

    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"


def test_list_sessions_ordered_by_updated_at():
    with get_session() as db:
        s1 = create_session(db, title="First")
        s2 = create_session(db, title="Second")
        sessions = list_sessions(db)

    # Most recent first
    assert sessions[0].id == s2.id
    assert sessions[1].id == s1.id


def test_get_session_by_id_returns_none_for_missing():
    with get_session() as db:
        result = get_session_by_id(db, "nonexistent-id")
    assert result is None


def test_delete_session_removes_messages():
    with get_session() as db:
        s = create_session(db, title="To delete")
        add_message(db, session_id=s.id, role="user", content="bye")
        ok = delete_session(db, s.id)

    assert ok is True

    with get_session() as db:
        assert get_session_by_id(db, s.id) is None
        assert get_messages(db, s.id) == []


def test_delete_nonexistent_session_returns_false():
    with get_session() as db:
        ok = delete_session(db, "ghost-id")
    assert ok is False


# ---------------------------------------------------------------------------
# LLM module — provider config and error branches
# ---------------------------------------------------------------------------


def test_is_available_false_when_provider_none(monkeypatch):
    import agent.core.config as config

    config.settings = config.Settings(llm_provider="none")
    assert is_available() is False


def test_is_available_true_for_ollama(monkeypatch):
    import agent.core.config as config

    config.settings = config.Settings(llm_provider="ollama")
    assert is_available() is True


def test_get_reply_raises_llmerror_when_provider_none(monkeypatch):
    import agent.core.config as config

    config.settings = config.Settings(llm_provider="none")
    with pytest.raises(LLMError, match="AGENT_LLM_PROVIDER"):
        get_reply([{"role": "user", "content": "hi"}])


def test_get_reply_raises_llmerror_for_unknown_provider(monkeypatch):
    import agent.core.config as config

    config.settings = config.Settings(llm_provider="unknown_backend")
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        get_reply([{"role": "user", "content": "hi"}])


def test_get_reply_ollama_uses_mock(monkeypatch):
    import agent.core.config as config
    import agent.core.llm as llm_module

    config.settings = config.Settings(
        llm_provider="ollama",
        llm_model="llama3.2",
        llm_base_url="http://localhost:11434",
    )

    def _fake_ollama(messages, *, model, base_url):
        return f"mocked reply for {messages[-1]['content']}"

    monkeypatch.setattr(llm_module, "_ollama_chat", _fake_ollama)
    reply = get_reply([{"role": "user", "content": "hello"}])
    assert "mocked" in reply


def test_get_reply_openai_uses_mock(monkeypatch):
    import agent.core.config as config
    import agent.core.llm as llm_module

    config.settings = config.Settings(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_base_url="https://api.openai.com/v1",
        llm_api_key="sk-test",
    )

    def _fake_openai(messages, *, model, base_url, api_key):
        assert api_key == "sk-test"
        return "openai mock reply"

    monkeypatch.setattr(llm_module, "_openai_chat", _fake_openai)
    reply = get_reply([{"role": "user", "content": "test"}])
    assert reply == "openai mock reply"


def test_build_system_prompt_includes_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()

    from agent.core.memory import add_memory

    with get_session() as db:
        add_memory(db, text="Project Alpha deadline is Q2 2026")
        prompt = build_system_prompt(db)

    assert "personal work agent" in prompt.lower()
    assert "Project Alpha" in prompt


def test_build_system_prompt_works_without_memory():
    with get_session() as db:
        prompt = build_system_prompt(db)
    assert "personal work agent" in prompt.lower()
