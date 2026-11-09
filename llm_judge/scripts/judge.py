"""Run the LLM judge for one criterion and one judge-prompt version on every conversation in conversations/index.csv.

Results go to results/judge_<criterion>_<version>.jsonl (one line per conversation). They are NOT written into
labels.csv here, so the student can label blind; agreement.py --merge copies them in afterwards.

Usage (from the repo root, with the backend venv; the OpenRouter key is read from backend/.env by app.config):
    backend/.venv/Scripts/python llm_judge/scripts/judge.py --criterion A --version v1
    [--model google/gemini-3-flash-preview] [--only C03,C07] [--force]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
LLM_JUDGE = HERE.parent
REPO = LLM_JUDGE.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(HERE))

from transcript import load, render  # noqa: E402

DEFAULT_JUDGE_MODEL = "google/gemini-3-flash-preview"


class JudgeVerdict(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    failing_turns: list[int] = Field(default_factory=list)
    reason: str


class Check(BaseModel):
    turn: int
    item: str = Field(description="The statement or learner move being checked (quoted).")
    evidence: str = Field(description="What the cited passage or the earlier conversation says.")
    ok: bool


class JudgeVerdictWithChecks(BaseModel):
    """From judge prompt v3 on: the judge writes out the turns it judged and every check before the verdict."""
    judged_turns: list[int]
    checks: list[Check]
    verdict: Literal["PASS", "FAIL"]
    failing_turns: list[int] = Field(default_factory=list)
    reason: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--criterion", required=True, choices=["A", "B"])
    parser.add_argument("--version", required=True, help="judge prompt version, e.g. v1 -> judge_prompts/criterion_a_v1.md")
    parser.add_argument("--model", default=os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    parser.add_argument("--only", default="", help="comma-separated conversation IDs (e.g. to retry errors)")
    parser.add_argument("--force", action="store_true", help="re-judge; the old results file is kept with a timestamp suffix")
    parser.add_argument("--reasoning", choices=["none", "low", "medium", "high"], default="none",
                        help="OpenRouter reasoning effort for the judge model (default: none)")
    args = parser.parse_args()

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    from app.config import settings
    from app.llm import _decode_json_strings

    prompt_file = LLM_JUDGE / "judge_prompts" / f"criterion_{args.criterion.lower()}_{args.version}.md"
    system = prompt_file.read_text(encoding="utf-8")
    prompt_sha = hashlib.sha256(system.encode("utf-8")).hexdigest()[:12]
    out = LLM_JUDGE / "results" / f"judge_{args.criterion}_{args.version}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if out.exists():
        if not (args.force or args.only):
            print(f"{out} exists; use --force (all) or --only (some) to re-judge; the old file is kept.")
            return 1
        if args.only:  # re-judge some conversations, keep the others' results
            existing = {json.loads(l)["conv_id"]: json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l}
        out.rename(out.with_name(f"{out.stem}__{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"))

    with (LLM_JUDGE / "conversations" / "index.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["included"] == "yes"]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        rows = [r for r in rows if r["conv_id"] in wanted]

    extra = {"reasoning": {"effort": args.reasoning}} if args.reasoning != "none" else None
    model = ChatOpenAI(model=args.model, api_key=settings.api_key, base_url=settings.base_url,
                       temperature=0, timeout=300, max_retries=2, extra_body=extra)
    schema = JudgeVerdictWithChecks if int(args.version.lstrip("v")) >= 3 else JudgeVerdict
    runnable = model.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)

    def judge(row: dict) -> dict:
        export = load(LLM_JUDGE / row["file"])
        started = time.perf_counter()
        record = {"conv_id": row["conv_id"], "file": row["file"], "criterion": args.criterion,
                  "judge_prompt": prompt_file.name, "judge_prompt_sha": prompt_sha, "judge_model": args.model,
                  "reasoning": args.reasoning,
                  "judged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            result = runnable.invoke([SystemMessage(content=system),
                                      HumanMessage(content=render(export, args.criterion))])
            parsed = result.get("parsed")
            if parsed is None:
                parsed = schema.model_validate(_decode_json_strings(json.loads(result["raw"].content)))
            usage = getattr(result.get("raw"), "usage_metadata", None) or {}
            record.update(parsed.model_dump(), usage=dict(usage), error=None)
        except Exception as exc:
            record.update(verdict=None, failing_turns=[], reason="", usage={}, error=f"{type(exc).__name__}: {exc}")
        record["latency_s"] = round(time.perf_counter() - started, 1)
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(judge, rows))
    merged = {**existing, **{r["conv_id"]: r for r in records}}
    with out.open("w", encoding="utf-8") as f:
        for r in sorted(merged.values(), key=lambda r: r["conv_id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    errors = [r["conv_id"] for r in records if r["error"]]
    tokens_in = sum(r["usage"].get("input_tokens", 0) for r in records)
    tokens_out = sum(r["usage"].get("output_tokens", 0) for r in records)
    print(f"Judged {len(records)} conversations on criterion {args.criterion} with {prompt_file.name} "
          f"({args.model}); tokens in/out {tokens_in}/{tokens_out}. Saved {out}")
    if errors:
        print(f"Errors (re-run with --only): {', '.join(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
