"""Run a scripted multi-turn conversation through the SAME service layer the web UI uses (app/core.py).

Used to produce real transcripts for llm_judge/ and red_team/. The learner turns come from a scenario file;
every PaperLens turn is generated live by the running pipeline and logged like a UI session.

Scenario file (JSON):
{
  "name": "flow-follow-up-01",
  "paper_pdf": "../test_papers/flow.pdf",          # relative to the scenario file
  "reading_goal": "Explore potential use in my research",
  "research_context": "I study ...",                 # optional
  "language": "English",                              # optional
  "turns": [
    {"type": "chat", "text": "What are the limitations of the flow model?"},
    {"type": "chat", "text": "Does that affect my study?"},
    {"type": "critical_review"},
    {"type": "judgment", "verdict": "Use with adaptations", "rationale": "..."},
    {"type": "note"}
  ]
}

Usage (from backend/):
    .venv/Scripts/python scripts/run_conversation.py path/to/scenario.json --out ../llm_judge/conversations [--repeat 3]
    [--pipeline-version v0]   # run the ablated baseline instead of the configured version
    [--stop-on-error]

Step mode (red-teaming: stop a run as soon as a reply fails, so later turns are never sent):
    scripts/run_conversation.py scenario.json --out DIR --turn 1 --run 2            # new session, first turn only
    scripts/run_conversation.py scenario.json --out DIR --turn 2 --run 2 --session s-...   # next turn, same session
Each step rewrites the run's transcript file; "turns_completed" records how far the run got.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Folder for transcript JSON files")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--pipeline-version", choices=["v0", "v1"])
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--turn", type=int, help="Step mode: run only this turn (1-based) of the scenario")
    parser.add_argument("--session", help="Step mode: continue this session (required for --turn > 1)")
    parser.add_argument("--run", type=int, default=1, help="Step mode: run number used in the file name")
    args = parser.parse_args()

    if args.pipeline_version:
        os.environ["PIPELINE_VERSION"] = args.pipeline_version  # must be set before app.config is imported
    sys.path.insert(0, str(BACKEND))
    from app import core, ingest, storage  # noqa: E402
    from app.config import settings  # noqa: E402

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    pdf_path = (args.scenario.parent / scenario["paper_pdf"]).resolve()
    meta = ingest.register_upload(pdf_path.read_bytes(), pdf_path.name)
    if meta.get("status") != "ready":
        print(f"Indexing {pdf_path.name} ...")
        ingest.run_ingestion(meta["paper_id"])
        meta = storage.load_paper_meta(meta["paper_id"])
        if meta["status"] != "ready":
            print(f"Indexing failed: {meta.get('error')}")
            return 1

    args.out.mkdir(parents=True, exist_ok=True)

    def run_one(sid: str, turn: dict) -> dict:
        kind = turn["type"]
        if kind == "chat":
            result = core.run_turn(sid, turn["text"])
        elif kind == "critical_review":
            result = core.run_critical_review(sid)
        elif kind == "judgment":
            result = core.submit_judgment(sid, turn["verdict"], turn["rationale"])
        elif kind == "note":
            result = core.generate_note(sid)
        else:
            raise ValueError(f"Unknown turn type {kind}")
        status = "ok" if result.get("ok") else f"ERROR: {result.get('error')}"
        print(f"  - {kind}: {turn.get('text', kind)[:70]} -> {status}")
        return result

    def save(sid: str, run: int, stopped_early: bool, turns_completed: int) -> None:
        export = core.export_session(sid)
        export["scenario"] = scenario
        export["run"] = run
        export["stopped_early"] = stopped_early
        export["turns_completed"] = turns_completed
        out_file = args.out / f"{scenario['name']}__{settings.pipeline_version}__run{run}__{sid}.json"
        out_file.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  saved {out_file}")

    if args.turn:
        if not 1 <= args.turn <= len(scenario["turns"]):
            print(f"--turn must be between 1 and {len(scenario['turns'])}")
            return 1
        if args.turn == 1 and not args.session:
            sid = core.create_session(meta["paper_id"], scenario.get("reading_goal", ""),
                                      scenario.get("research_context", ""), scenario.get("language", "English"))["session_id"]
        elif args.session:
            sid = args.session
        else:
            print("--session is required for --turn > 1")
            return 1
        print(f"[{scenario['name']} run {args.run} turn {args.turn}/{len(scenario['turns'])}] session {sid} "
              f"({settings.pipeline_version})")
        result = run_one(sid, scenario["turns"][args.turn - 1])
        save(sid, args.run, stopped_early=not result.get("ok"), turns_completed=args.turn)
        return 0 if result.get("ok") else 2

    for run in range(1, args.repeat + 1):
        session = core.create_session(meta["paper_id"], scenario.get("reading_goal", ""),
                                      scenario.get("research_context", ""), scenario.get("language", "English"))
        sid = session["session_id"]
        print(f"[{scenario['name']} run {run}] session {sid} ({settings.pipeline_version})")
        stopped_early = False
        done = 0
        for turn in scenario["turns"]:
            result = run_one(sid, turn)
            done += 1
            if not result.get("ok") and args.stop_on_error:
                stopped_early = True
                break
        save(sid, run, stopped_early, done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
