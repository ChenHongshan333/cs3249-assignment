"""Give each complete conversation a blind ID (C01, C02, ...) and write the student's labeling sheets.

Writes:
  conversations/index.csv  conv_id -> transcript file, persona, card, pipeline version (do not open before labeling)
  labeling/Cxx.md          one readable sheet per conversation (no pipeline version, no file name)
  labels.csv               one row per conversation x criterion; human_label is left empty for the student

The order of IDs is shuffled with a fixed seed so that v0 conversations are not grouped together. Existing
human labels in labels.csv are never overwritten; the script refuses to re-number once labels exist.

Usage (from the repo root):  backend/.venv/Scripts/python llm_judge/scripts/prepare_labeling.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_JUDGE = HERE.parent
sys.path.insert(0, str(HERE))
from transcript import labeling_markdown, load  # noqa: E402

LABEL_FIELDS = ["conv_id", "criterion", "human_label", "judge_label_v1", "judge_label_v2", "notes"]


def main() -> int:
    labels = LLM_JUDGE / "labels.csv"
    if labels.exists():
        with labels.open(encoding="utf-8") as f:
            if any(r["human_label"].strip() for r in csv.DictReader(f)):
                print("labels.csv already has human labels; not re-numbering.")
                return 1
    base = LLM_JUDGE / "conversations"
    files = sorted(base.glob("*.json")) + sorted((base / "v0").glob("*.json"))
    complete, broken = [], []
    for f in files:
        export = load(f)
        (broken if export.get("stopped_early") else complete).append((f, export))
    # one complete transcript per card (the first one); later duplicates are listed but not included
    seen, included, extra = set(), [], []
    for f, export in complete:
        name = export["scenario"]["name"]
        (extra if name in seen else included).append((f, export))
        seen.add(name)
    random.Random(3249).shuffle(included)

    rows = []
    for i, (f, export) in enumerate(included, 1):
        rows.append({"conv_id": f"C{i:02d}", "file": f.relative_to(LLM_JUDGE).as_posix(), "included": "yes",
                     "card": export["scenario"]["name"], "persona": export["scenario"]["persona"],
                     "pipeline_version": export["scenario"].get("pipeline_version", "v1"),
                     "session_id": export["session"]["session_id"]})
    for f, export in extra + broken:
        rows.append({"conv_id": "", "file": f.relative_to(LLM_JUDGE).as_posix(),
                     "included": "no (broken run)" if export.get("stopped_early") else "no (duplicate run)",
                     "card": export["scenario"]["name"], "persona": export["scenario"]["persona"],
                     "pipeline_version": export["scenario"].get("pipeline_version", "v1"),
                     "session_id": export["session"]["session_id"]})
    with (base / "index.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    sheets = LLM_JUDGE / "labeling"
    sheets.mkdir(exist_ok=True)
    for row in rows:
        if row["included"] == "yes":
            (sheets / f"{row['conv_id']}.md").write_text(labeling_markdown(load(LLM_JUDGE / row["file"]), row["conv_id"]),
                                                         encoding="utf-8")
    with labels.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
        w.writeheader()
        for row in rows:
            if row["included"] == "yes":
                for crit in ("A", "B"):
                    w.writerow({"conv_id": row["conv_id"], "criterion": crit, "human_label": "",
                                "judge_label_v1": "", "judge_label_v2": "", "notes": ""})
    print(f"{len(included)} conversations included, {len(extra)} duplicate and {len(broken)} broken runs listed in index.csv")
    print(f"Labeling sheets in {sheets}; fill human_label (PASS/FAIL) in {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
