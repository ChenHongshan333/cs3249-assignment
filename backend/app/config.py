"""Runtime configuration, read once from environment variables (backend/.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Non-empty values in backend/.env win over system environment variables of the same name;
# empty ones (e.g. an unfilled OPENROUTER_API_KEY=) fall back to the system value.
_DOTENV = dotenv_values(BACKEND_DIR / ".env")
for _key, _value in _DOTENV.items():
    if _value:
        os.environ[_key] = _value

# Where the API key came from, so /api/health can show it without revealing the key.
if (_DOTENV.get("OPENROUTER_API_KEY") or "").strip():
    API_KEY_SOURCE = "backend/.env"
elif os.getenv("OPENROUTER_API_KEY", "").strip():
    API_KEY_SOURCE = "system environment variable"
else:
    API_KEY_SOURCE = "missing"

# Bump this whenever any file in app/prompts/ changes, so logs show which prompts produced a reply.
PROMPT_VERSION = "p4"  # p2: carried-over passages; p3: verbatim evidence_quotes; p4: in-chat language requests


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    chat_model: str
    chat_temperature: float
    embedding_model: str
    pipeline_version: str
    top_k: int
    chunk_size: int
    chunk_overlap: int
    data_dir: Path

    def public(self) -> dict:
        """Configuration that is safe to write into logs (no API key)."""
        data = asdict(self)
        data.pop("api_key")
        data["data_dir"] = str(self.data_dir)
        data["prompt_version"] = PROMPT_VERSION
        return data


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = BACKEND_DIR / data_dir
    version = os.getenv("PIPELINE_VERSION", "v1").strip()
    if version not in {"v0", "v1"}:
        raise ValueError(f"PIPELINE_VERSION must be v0 or v1, got {version!r}")
    return Settings(
        api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip(),
        chat_model=os.getenv("CHAT_MODEL", "anthropic/claude-haiku-5.5").strip(),
        chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
        embedding_model=os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small").strip(),
        pipeline_version=version,
        top_k=int(os.getenv("TOP_K", "6")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1200")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        data_dir=data_dir,
    )


settings = load_settings()
