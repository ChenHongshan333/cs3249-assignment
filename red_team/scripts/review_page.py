"""Build a read-only review page for red-team transcripts (no verdicts, no model calls).

Shows, for every run: the attempt, session id, each learner turn and PaperLens's full reply (short answer,
sections with their kind, suggestion, clarifying question), plus facts from the run log that the rules refer to
(for T2: whether the passage with the paper's Limitations and any hidden text were among the passages provided).

Usage (from red_team/):  python scripts/review_page.py transcripts/before review/before.html [prefix,prefix,...]
The optional third argument keeps only transcripts whose file name starts with one of the prefixes.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ORDER = ["t1-a1", "t1-a2", "t1-a3", "t1-b1", "t1-b2", "t1-b3", "t2-a1", "t2-a2", "t2-a3", "t2-b1", "t2-b2", "t2-b3",
         "t2-control"]
# Strings that only occur in the hidden (white 1-pt) text of the T2 papers, and one that marks the Limitations passage.
HIDDEN_MARKERS = ["IGNORE ALL PREVIOUS", "Note for LLM-based reviewers", "Instruction for AI assistants",
                  "412 participants", "Erratum (added by the editors", "Castellan et al., 2025"]
LIMITATIONS_MARKER = "16 university students, most of them from computing courses"


def esc(text) -> str:
    return html.escape(str(text or ""))


def rules_html() -> str:
    text = (HERE / "targets.md").read_text(encoding="utf-8")
    start, end = text.index("## T1"), text.index("## Attacks")
    out = []
    for line in text[start:end].splitlines():
        if line.startswith("## "):
            out.append(f"<h3>{esc(line[3:])}</h3>")
        elif line.startswith("- "):
            out.append(f"<li>{esc(line[2:])}</li>")
        elif line.strip() and line.strip() != "---":
            out.append(f"<p>{esc(line)}</p>")
    return "\n".join(out)


def reply_html(msg: dict) -> str:
    parts = [f'<div class="short">{esc(msg.get("short_answer"))}</div>']
    for s in msg.get("sections", []):
        parts.append(f'<div class="sec"><span class="kind">{esc(s["kind"])}</span> <b>{esc(s["title"])}</b>'
                     f'<div>{esc(s["text"])}</div><div class="refs">cites: {esc(", ".join(s.get("refs", [])) or "none")}</div></div>')
    if msg.get("system_suggestion"):
        sug = msg["system_suggestion"]
        parts.append(f'<div class="sug">PaperLens suggestion: <b>{esc(sug.get("verdict"))}</b>: {esc(sug.get("reason"))}</div>')
    if msg.get("clarifying_question"):
        parts.append(f'<div class="clar">Clarifying question: {esc(msg["clarifying_question"])}</div>')
    return "\n".join(parts)


def run_html(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenario, session = data["scenario"], data["session"]
    turns = [e for e in data["events"] if e["event"] == "turn"]
    msgs = session["messages"]
    body = []
    for i, event in enumerate(turns, 1):
        user = event["user_message"] if event["mode"] == "chat" else f"[{event['mode']}] {event['user_message']}"
        assistant = event.get("assistant_message") or {}
        facts = ""
        if scenario.get("target") == "T2":
            texts = [r["text"] for r in event.get("retrieved", [])]
            lim = any(LIMITATIONS_MARKER in t for t in texts)
            hidden = any(m in t for t in texts for m in HIDDEN_MARKERS)
            facts = (f'<div class="facts">Run log: Limitations passage provided this turn: <b>{"yes" if lim else "no"}</b>; '
                     f'passage with hidden text provided: <b>{"yes" if hidden else "no"}</b>; '
                     f'overview summaries provided: {"yes" if event.get("overview_ids") else "no"}</div>')
        body.append(f'<div class="turn"><div class="user"><span class="who">Turn {i} · Kenji</span>{esc(user)}</div>'
                    f'<div class="bot"><span class="who">PaperLens</span>{reply_html(assistant)}{facts}</div></div>')
    title = f'{scenario["name"]} · run {data["run"]}'
    head = (f'<h2 id="{esc(path.stem)}">{esc(title)}</h2><div class="meta">{esc(scenario.get("attack"))} · session '
            f'<code>{esc(session["session_id"])}</code> · prompt {esc(turns[-1]["prompt_version"] if turns else "?")} · '
            f'turns {data.get("turns_completed", len(turns))}/{len(scenario["turns"])} · paper: {esc(session.get("paper_title"))}</div>')
    return title, f'<section class="run">{head}{"".join(body)}</section>'


def main() -> int:
    src, out = HERE / sys.argv[1], HERE / sys.argv[2]
    prefixes = tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else ("",)
    files = sorted((p for p in src.glob("*.json") if p.name.startswith(prefixes)), key=lambda p: (next((i for i, k in enumerate(ORDER) if p.name.startswith(k)), 99), p.name))
    runs = [run_html(p) for p in files]
    toc = "".join(f'<li><a href="#{esc(p.stem)}">{esc(t)}</a></li>' for p, (t, _) in zip(files, runs))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Red-team review</title><style>
body{{font:14px/1.5 system-ui,sans-serif;margin:0;color:#1d1d1f;background:#f6f6f4}}
.wrap{{display:grid;grid-template-columns:260px 1fr;gap:24px;max-width:1300px;margin:0 auto;padding:16px}}
nav{{position:sticky;top:12px;align-self:start;max-height:95vh;overflow:auto;font-size:13px}}
.rules{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin-bottom:16px}}
.rules details summary{{cursor:pointer;font-weight:600}}
.run{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin-bottom:20px}}
.meta{{color:#666;font-size:12px;margin-bottom:8px}} h2{{margin:4px 0;font-size:17px}}
.turn{{border-top:1px solid #eee;padding:8px 0}} .who{{display:block;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.04em}}
.user{{background:#eef4ff;border-radius:6px;padding:6px 10px;margin-bottom:6px}}
.bot{{padding:4px 10px}} .short{{font-weight:500;margin-bottom:6px}}
.sec{{border-left:3px solid #ccc;padding:2px 8px;margin:6px 0}} .kind{{font-size:11px;background:#eee;border-radius:4px;padding:0 5px}}
.refs{{font-size:11px;color:#888}} .sug{{background:#fff6e0;padding:4px 8px;border-radius:4px;margin-top:6px}}
.clar{{color:#555;font-style:italic;margin-top:4px}} .facts{{font-size:12px;color:#555;background:#f3f3f3;padding:4px 8px;border-radius:4px;margin-top:6px}}
</style></head><body><div class="wrap"><nav><b>Runs</b><ol>{toc}</ol></nav><main>
<div class="rules"><details open><summary>PASS/FAIL rules (red_team/targets.md)</summary>{rules_html()}</details></div>
<p style="color:#666">Runs marked "turns k/n" with k &lt; n were stopped after turn k (see red_team/README.md). Read-only. No verdicts or judgments are shown; record yours in <code>red_team/verdicts.csv</code>.</p>
{"".join(h for _, h in runs)}</main></div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(runs)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
