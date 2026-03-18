"""
Configuration and environment settings.

Data root defaults to ~/.agent; override with AGENT_DATA_DIR.
All paths are pathlib.Path — never os.path.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    data_dir: Path = Path.home() / ".agent"
    embed_model: str = "all-MiniLM-L6-v2"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    # LLM settings — provider is "none" by default (no LLM)
    llm_provider: str = "none"  # none | ollama | openai
    llm_model: str = "llama3.2"
    llm_base_url: str = "http://localhost:11434"  # Ollama default; override for OpenAI
    llm_api_key: str = ""  # only needed for openai provider

    @field_validator("data_dir", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: object) -> Path:
        return Path(str(v)).expanduser().resolve()

    # ------------------------------------------------------------------ #
    # Derived paths — computed as properties so they stay in sync.         #
    # ------------------------------------------------------------------ #

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agent.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backup"

    def ensure_dirs(self) -> None:
        """Create all required data directories, cross-platform safe."""
        for d in (self.data_dir, self.snapshots_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)


# Module-level singleton; import this everywhere instead of re-creating it.
settings = Settings()
