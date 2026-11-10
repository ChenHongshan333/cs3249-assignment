"""Print the latest PaperLens reply of a session (short answer, sections, suggestion, cited pages) for reading
between steps of a red-team run. Usage (from backend/): .venv/Scripts/python ../red_team/scripts/show_turn.py s-..."""
import json
import sys
from pathlib import Path

session = json.loads((Path(__file__).resolve().parents[2] / "backend" / "data" / "sessions" / f"{sys.argv[1]}.json")
                     .read_text(encoding="utf-8"))
msg = [m for m in session["messages"] if m["role"] == "assistant"][-1]
print(f"[{msg['mode']}] evidence={msg['evidence_status']}  SHORT: {msg['short_answer']}")
for s in msg["sections"]:
    print(f"  ({s['kind']}) {s['title']}: {s['text']}  refs={s['refs']}")
if msg.get("system_suggestion"):
    print("  SUGGESTION:", msg["system_suggestion"])
if msg.get("clarifying_question"):
    print("  CLARIFY:", msg["clarifying_question"])
