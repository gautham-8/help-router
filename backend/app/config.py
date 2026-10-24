"""Environment-driven settings for Help Router.

Defaults run the full demo and test suite with no API keys (the deterministic
``mock`` analyzer backend). See ``.env.example`` at the repo root.

Settings are read from process environment variables and from ``.env`` files. The
repo-root ``.env`` (what the README tells you to create) and ``backend/.env`` are both
honored; ``backend/.env`` wins on conflicts.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# browser: speech + sounds analyzed on the caller's device (default, no keys)
# mock:    every report plays a scripted scenario (tests; offline demos)
# live:    server-side models (needs keys; adapters are integration seams)
AnalyzerBackend = Literal["browser", "mock", "live"]

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
# Later files override earlier ones.
ENV_FILES: tuple[Path, ...] = (REPO_ROOT / ".env", BACKEND_ROOT / ".env")


class Settings(BaseSettings):
    """Runtime configuration, populated from environment variables / ``.env``."""

    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    # Which analyzer backend to use. "browser" (default) and "mock" need no API keys.
    # A report created with a demo scenario always uses the scripted mock analyzers.
    analyzer_backend: AnalyzerBackend = "browser"

    # A service is considered "indicated" at or above this confidence.
    min_service_conf: float = Field(default=0.3, ge=0.0, le=1.0)

    # A service at or above this confidence is "committed": refinement may lower it
    # or flag a downgrade, but must not silently drop it.
    high_conf: float = Field(default=0.7, ge=0.0, le=1.0)

    # Each new chunk keeps this fraction of the previous confidence, so a service with
    # no fresh evidence fades instead of staying pinned at its peak.
    carry_decay: float = Field(default=0.85, gt=0.0, le=1.0)

    # A hard-guarantee event (smoke_alarm -> fire) must be at least this confident.
    guarantee_min_event_conf: float = Field(default=0.5, ge=0.0, le=1.0)

    # Capture window and chunking (seconds). Six ~10s chunks over 60s.
    capture_seconds: int = Field(default=60, gt=0)
    chunk_seconds: int = Field(default=10, gt=0)

    # Largest decoded audio chunk the capture stream accepts.
    max_audio_bytes: int = Field(default=2_000_000, gt=0)

    # Optional shared secret protecting the dashboard, queues, and confirm/reject.
    # Empty means open (fine for a local demo; set it before exposing a public URL).
    dashboard_token: str = ""

    # Comma-separated browser origins allowed to call the API directly.
    cors_origins: str = "http://localhost:5173,https://localhost:5173"

    # Only used when ANALYZER_BACKEND=live.
    openai_api_key: str = ""
    audio_event_model_url: str = ""
    audio_event_model_key: str = ""

    @property
    def num_chunks(self) -> int:
        return max(1, self.capture_seconds // self.chunk_seconds)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
