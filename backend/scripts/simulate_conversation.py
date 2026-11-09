"""Run one conversation between an LLM-simulated learner and the running PaperLens system.

The learner's messages are written by a separate "simulator" model that plays a persona (llm_judge/personas/)
and follows the moves of a situation card (llm_judge/scenarios/). Every PaperLens turn is produced by the SAME
service layer the web UI uses (app/core.py), so the conversation is stored as a normal session (visible in the
UI's History) and logged in data/logs/<session>.jsonl.

Situation card (JSON):
{
  "name": "sam-01",
  "persona": "sam",                                   # llm_judge/personas/<persona>.md
  "paper_pdf": "../../test_papers/hunyuan3d-2.pdf",   # relative to the card
  "reading_goal": "Explore potential use in my research",
  "research_context": "...",
  "language": "中文（简体）",
  "pipeline_version": "v1",                           # v1 = final system, v0 = ablated baseline
  "moves": [
    "Ask for an overview of what the paper does, related to your goal.",
    "Refer back to the second stage with a short reference and ask how it works.",
    {"type": "critical_review"},
    {"type": "judgment", "instruction": "Choose your own verdict ..."}
  ]
}

Usage (from backend/):
    .venv/Scripts/python scripts/simulate_conversation.py ../llm_judge/scenarios/sam-01.json --out ../llm_judge/conversations
    [--sim-model anthropic/claude-haiku-5.5] [--repeat 1]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
PERSONAS = REPO / "llm_judge" / "personas"
SIM_PROMPT = REPO / "llm_judge" / "simulator_prompt.md"
DEFAULT_SIM_MODEL = "anthropic/claude-haiku-5.5"


class LearnerMessage(BaseModel):
    message: str = Field(description="The learner's next chat message, in the persona's voice and language.")


class LearnerJudgment(BaseModel):
    verdict: Literal["Use as proposed", "Use with adaptations", "Do not use", "Need more evidence"] = Field(
        description="The learner's own research-use verdict.")
    rationale: str = Field(description="The learner's own rationale, 1-3 sentences, in the persona's voice and language.")


def learner_view(message: dict) -> str:
    """What the learner sees of a PaperLens reply: short answer, expandable sections, clarifying question."""
    parts = [message.get("short_answer", "")]
    for s in message.get("sections", []):
        parts.append(f"[{s['title']}] {s['text']}")
    if message.get("clarifying_question"):
        parts.append(f"(PaperLens asks: {message['clarifying_question']})")
    if message.get("system_suggestion"):
        sug = message["system_suggestion"]
        parts.append(f"(PaperLens suggestion: {sug['verdict']} - {sug['reason']})")
    return "\n".join(p for p in parts if p)


def conversation_text(session: dict) -> str:
    lines = []
    for m in session.get("messages", []):
        if m["role"] == "user":
            lines.append(f"Learner: {m['text']}")
        else:
            lines.append(f"PaperLens: {learner_view(m)}")
    return "\n\n".join(lines) or "(the conversation has not started yet)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--sim-model", default=os.getenv("SIM_MODEL", DEFAULT_SIM_MODEL))
    args = parser.parse_args()

    card = json.loads(args.scenario.read_text(encoding="utf-8"))
    version = card.get("pipeline_version", "v1")
    os.environ["PIPELINE_VERSION"] = version  # must be set before app.config is imported
    sys.path.insert(0, str(BACKEND))
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
    from langchain_openai import ChatOpenAI  # noqa: E402
    from app import core, ingest, storage  # noqa: E402
    from app.config import PROMPT_VERSION, settings  # noqa: E402
    from app.llm import _decode_json_strings  # noqa: E402

    sim = ChatOpenAI(model=args.sim_model, api_key=settings.api_key, base_url=settings.base_url,
                     temperature=0.7, timeout=90, max_retries=2)

    def simulate(system: str, user: str, schema):
        runnable = sim.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
        result = runnable.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        if result.get("parsed") is not None:
            return result["parsed"]
        return schema.model_validate(_decode_json_strings(json.loads(getattr(result.get("raw"), "content", ""))))

    persona = (PERSONAS / f"{card['persona']}.md").read_text(encoding="utf-8")
    pdf_path = (args.scenario.parent / card["paper_pdf"]).resolve()
    meta = ingest.register_upload(pdf_path.read_bytes(), pdf_path.name)
    if meta.get("status") != "ready":
        print(f"Indexing {pdf_path.name} ...")
        ingest.run_ingestion(meta["paper_id"])
        meta = storage.load_paper_meta(meta["paper_id"])
        if meta["status"] != "ready":
            print(f"Indexing failed: {meta.get('error')}")
            return 1
    system = SIM_PROMPT.read_text(encoding="utf-8").format(
        persona=persona.strip(), paper_title=meta.get("title", ""),
        reading_goal=card.get("reading_goal") or "(not set)",
        research_context=card.get("research_context") or "(none)")

    args.out.mkdir(parents=True, exist_ok=True)
    for run in range(1, args.repeat + 1):
        session = core.create_session(meta["paper_id"], card.get("reading_goal", ""),
                                      card.get("research_context", ""), card.get("language", "English"))
        sid = session["session_id"]
        print(f"[{card['name']} run {run}] session {sid} (pipeline {version}, prompts {PROMPT_VERSION}, "
              f"simulator {args.sim_model})", flush=True)
        sim_log, error = [], None
        for index, move in enumerate(card["moves"], 1):
            move = {"type": "chat", "instruction": move} if isinstance(move, str) else move
            kind = move["type"]
            started = time.perf_counter()
            try:
                if kind == "critical_review":
                    result = core.run_critical_review(sid)
                    sim_log.append({"move": index, "type": kind})
                elif kind == "chat":
                    user = (f"<conversation_so_far>\n{conversation_text(storage.load_session(sid))}\n</conversation_so_far>\n\n"
                            f"Move for this turn: {move['instruction']}")
                    learner = simulate(system, user, LearnerMessage)
                    sim_log.append({"move": index, "type": kind, "instruction": move["instruction"],
                                    "learner_message": learner.message, "sim_model": args.sim_model})
                    result = core.run_turn(sid, learner.message)
                elif kind == "judgment":
                    user = (f"<conversation_so_far>\n{conversation_text(storage.load_session(sid))}\n</conversation_so_far>\n\n"
                            f"Move for this turn: record your OWN research-use verdict and rationale in PaperLens. "
                            f"{move.get('instruction', '')}")
                    decision = simulate(system, user, LearnerJudgment)
                    sim_log.append({"move": index, "type": kind, "instruction": move.get("instruction", ""),
                                    "verdict": decision.verdict, "rationale": decision.rationale,
                                    "sim_model": args.sim_model})
                    result = core.submit_judgment(sid, decision.verdict, decision.rationale)
                else:
                    raise ValueError(f"Unknown move type {kind}")
            except Exception as exc:  # simulator or input errors: stop this run, keep the record
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            status = "ok" if result.get("ok") else f"ERROR: {result.get('error')}"
            last = sim_log[-1] if sim_log and sim_log[-1]["move"] == index else {}
            shown = last.get("learner_message") or last.get("verdict") or kind
            print(f"  {index}. {kind}: {str(shown)[:80]} -> {status} ({time.perf_counter() - started:.0f}s)", flush=True)
            if not result.get("ok"):
                error = {"move": index, "error": result.get("error")}
                break
        export = core.export_session(sid)
        export.update(scenario=card, persona_text=persona, simulator={"model": args.sim_model,
                      "prompt": SIM_PROMPT.read_text(encoding="utf-8"), "log": sim_log},
                      run=run, stopped_early=error is not None, error=error)
        out_file = args.out / f"{card['name']}__{version}__run{run}__{sid}.json"
        out_file.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  saved {out_file}" + ("  (STOPPED EARLY: system or simulator error)" if error else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
