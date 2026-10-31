import os

from tutor import config


def test_env_file_is_parsed(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nGEN_MODEL=m1\nEMPTY=\nQUOTED=\"v w\"\n  SPACED = x \nnot a line\n")
    assert config.read_env_file(f) == {"GEN_MODEL": "m1", "QUOTED": "v w", "SPACED": "x"}
    assert config.read_env_file(tmp_path / "missing") == {}


def test_env_file_wins_over_the_shell_for_settings(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("GEN_MODEL=from-env-file\n")
    monkeypatch.setenv("GEN_MODEL", "from-shell")
    config.load_env(f)
    assert os.environ["GEN_MODEL"] == "from-env-file"


def test_api_keys_come_only_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("GROQ_API_KEY", "shell-key")
    assert config.api_key("GROQ_API_KEY") is None
    (tmp_path / ".env").write_text("GROQ_API_KEY=file-key\n")
    assert config.api_key("GROQ_API_KEY") == "file-key"


def test_resolve_bank_prefers_the_named_bank_and_explains_a_missing_one():
    assert config.resolve_bank("electricity_gold").name == "electricity_gold"
    try:
        config.resolve_bank("nope")
    except FileNotFoundError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_bank_name_in_the_env_file_pins_the_bank(tmp_path, monkeypatch):
    """Building a newer bank must not silently change which bank the app and database use."""
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("BANK_NAME", raising=False)
    (tmp_path / ".env").write_text("BANK_NAME=electricity_gold\n")
    assert config.resolve_bank().name == "electricity_gold"
    (tmp_path / ".env").write_text("BANK_NAME=does_not_exist\n")
    try:
        config.resolve_bank()
    except FileNotFoundError as e:
        assert "does_not_exist" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")
    monkeypatch.setenv("BANK_NAME", "electricity_gold")           # the environment still wins over .env
    assert config.resolve_bank().name == "electricity_gold"
