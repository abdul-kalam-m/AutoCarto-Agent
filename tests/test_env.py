"""Tests for the minimal .env loader (src/autocarto/env.py)."""

from __future__ import annotations

import pytest

from autocarto.env import get_key, load_env


def test_load_env_parses_keys_comments_and_quotes(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# a comment\n"
        "PLAIN=value1\n"
        'QUOTED="value2"\n'
        "SINGLE='value3'\n"
        "\n"
        "SPACED = value4 \n"
        "NOT_A_LINE\n",
        encoding="utf-8",
    )
    env = load_env(p)
    assert env == {
        "PLAIN": "value1",
        "QUOTED": "value2",
        "SINGLE": "value3",
        "SPACED": "value4",
    }


def test_load_env_missing_file_returns_empty(tmp_path):
    assert load_env(tmp_path / "does_not_exist.env") == {}


def test_get_key_prefers_real_environment(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("MY_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("MY_KEY", "from_environment")
    assert get_key("MY_KEY", env_path=p) == "from_environment"


def test_get_key_falls_back_to_file(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("MY_KEY=from_file\n", encoding="utf-8")
    monkeypatch.delenv("MY_KEY", raising=False)
    assert get_key("MY_KEY", env_path=p) == "from_file"


def test_get_key_required_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ABSENT_KEY"):
        get_key("ABSENT_KEY", env_path=tmp_path / "empty.env")


def test_get_key_optional_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_KEY", raising=False)
    assert get_key("ABSENT_KEY", env_path=tmp_path / "empty.env", required=False) is None
