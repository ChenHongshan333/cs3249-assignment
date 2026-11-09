"""Run every situation card in llm_judge/scenarios/ through simulate_conversation.py (in parallel).

v1 cards go to conversations/, v0 cards to conversations/v0/. A card that already has a complete transcript is
skipped unless --force; a broken run is never deleted, the card is simply run again (both files are kept).
Console output of each run is kept in conversations/run_logs/.

Usage (from the repo root):
    backend/.venv/Scripts/python llm_judge/scripts/run_batch.py [--only sam-01,mei-03] [--workers 4] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

LLM_JUDGE = Path(__file__).resolve().parent.parent
REPO = LLM_JUDGE.parent
PYTHON = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
SIMULATE = REPO / "backend" / "scripts" / "simulate_conversation.py"


def out_dir(card: dict) -> Path:
    base = LLM_JUDGE / "conversations"
    return base / "v0" if card.get("pipeline_version") == "v0" else base


def complete_exists(card: dict) -> bool:
    for f in out_dir(card).glob(f"{card['name']}__*.json"):
        if not json.loads(f.read_text(encoding="utf-8")).get("stopped_early"):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cards = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((LLM_JUDGE / "scenarios").glob("*.json"))]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cards = [(p, c) for p, c in cards if c["name"] in wanted]
    todo = [(p, c) for p, c in cards if args.force or not complete_exists(c)]
    print(f"{len(todo)} of {len(cards)} cards to run")
    logs = LLM_JUDGE / "conversations" / "run_logs"
    logs.mkdir(parents=True, exist_ok=True)

    def run(item):
        path, card = item
        log = logs / f"{card['name']}__{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        with log.open("w", encoding="utf-8") as f:
            code = subprocess.call([str(PYTHON), str(SIMULATE), str(path), "--out", str(out_dir(card))],
                                   cwd=REPO / "backend", stdout=f, stderr=subprocess.STDOUT, env=env)
        ok = code == 0 and complete_exists(card)
        print(f"{'ok    ' if ok else 'FAILED'} {card['name']} (log: {log.name})", flush=True)
        return ok

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, todo))
    print(f"done: {sum(results)} ok, {len(results) - sum(results)} failed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
