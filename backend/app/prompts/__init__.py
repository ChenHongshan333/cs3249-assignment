"""Prompt files live next to this module as Markdown. Bump config.PROMPT_VERSION when you edit them."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(name: str, with_rules: bool = False) -> str:
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    if with_rules:
        text = text + "\n\n" + (_DIR / "shared_rules.md").read_text(encoding="utf-8").strip()
    return text
