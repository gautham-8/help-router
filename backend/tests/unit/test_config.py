"""Unit tests for settings loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import BACKEND_ROOT, ENV_FILES, REPO_ROOT, Settings


def test_repo_root_env_is_honored() -> None:
    # The README says `cp .env.example .env` at the repo root, so the backend must read it.
    assert REPO_ROOT / ".env" in ENV_FILES
    assert (REPO_ROOT / ".env.example").exists()
    assert BACKEND_ROOT / ".env" in ENV_FILES


def test_env_file_values_are_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CARRY_DECAY", raising=False)
    env = tmp_path / ".env"
    env.write_text("CARRY_DECAY=0.5\nOPENAI_API_KEY=abc\n", encoding="utf-8")
    settings = Settings(_env_file=env)  # type: ignore[call-arg]
    assert settings.carry_decay == 0.5
    assert settings.openai_api_key == "abc"


def test_defaults_need_no_keys() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.analyzer_backend == "browser"
    assert settings.num_chunks == 6
    assert settings.openai_api_key == ""


def test_invalid_values_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIN_SERVICE_CONF", "3")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_cors_origin_list_parsing() -> None:
    settings = Settings(_env_file=None, cors_origins=" http://a.test , ,https://b.test")  # type: ignore[call-arg]
    assert settings.cors_origin_list == ["http://a.test", "https://b.test"]
