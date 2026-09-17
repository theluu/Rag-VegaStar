from vessel_chat.config import Settings


def test_explicit_values_override_defaults():
    s = Settings(_env_file=None, database_url="postgresql://u:p@h:1/db", memory_window_turns=2)
    assert s.database_url == "postgresql://u:p@h:1/db"
    assert s.memory_window_turns == 2


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("MEMORY_WINDOW_TURNS", "3")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    s = Settings(_env_file=None)
    assert s.memory_window_turns == 3
    assert s.llm_model == "some-model"


def test_cors_origins_parsed_from_comma_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a:1, http://b:2")
    s = Settings(_env_file=None)
    assert s.cors_origin_list == ["http://a:1", "http://b:2"]
