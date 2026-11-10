"""File-based storage for papers, sessions and run logs (all under DATA_DIR)."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir(*parts: str) -> Path:
    path = settings.data_dir.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- papers ----------

def paper_dir(paper_id: str) -> Path:
    return _dir("papers", paper_id)


def paper_pdf_path(paper_id: str) -> Path:
    return paper_dir(paper_id) / "paper.pdf"


def save_paper_meta(paper_id: str, meta: dict) -> None:
    with _lock:
        _write_json(paper_dir(paper_id) / "paper.json", meta)


def update_paper_meta(paper_id: str, **fields: Any) -> dict:
    with _lock:
        path = paper_dir(paper_id) / "paper.json"
        meta = _read_json(path) if path.exists() else {"paper_id": paper_id}
        meta.update(fields)
        meta["updated_at"] = now_iso()
        _write_json(path, meta)
        return meta


def load_paper_meta(paper_id: str) -> dict | None:
    path = settings.data_dir / "papers" / paper_id / "paper.json"
    return _read_json(path) if path.exists() else None


def save_paper_json(paper_id: str, name: str, data: Any) -> None:
    _write_json(paper_dir(paper_id) / name, data)


def load_paper_json(paper_id: str, name: str) -> Any | None:
    path = settings.data_dir / "papers" / paper_id / name
    return _read_json(path) if path.exists() else None


# ---------- sessions ----------

def save_session(session: dict) -> None:
    session["updated_at"] = now_iso()
    with _lock:
        _write_json(_dir("sessions") / f"{session['session_id']}.json", session)


def load_session(session_id: str) -> dict | None:
    path = settings.data_dir / "sessions" / f"{session_id}.json"
    return _read_json(path) if path.exists() else None


def list_sessions() -> list[dict]:
    folder = settings.data_dir / "sessions"
    if not folder.exists():
        return []
    sessions = [_read_json(p) for p in folder.glob("*.json")]
    return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)


# ---------- run logs (one JSONL file per session) ----------

def append_log(session_id: str, event: dict) -> None:
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        with (_dir("logs") / f"{session_id}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def read_log(session_id: str) -> list[dict]:
    path = settings.data_dir / "logs" / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
