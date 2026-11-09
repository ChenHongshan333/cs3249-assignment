"""Build llm_judge/labeling/review.html: a reading aid for the student's own PASS/FAIL labels.

It shows only the turns both criteria judge (chat turns), and for each one:
  * for criterion A: the previous PaperLens reply, the learner's message and the move the situation card gave
    the simulated learner (what the learner meant to do);
  * for criterion B: each part of the reply with its UI label and ONLY the passages it cites, with the evidence
    quotes that really occur in those passages highlighted;
  * objective signals recomputed the same way for every conversation (so the page does not reveal the pipeline
    version): cited IDs that were not provided this turn, evidence quotes not found in their passage,
    "From the paper" parts that cite no original passage, and the evidence status PaperLens reported.
It contains no verdicts and no judge output. Signals are facts from the logs, not labels: a signal does not
mean FAIL and no signal does not mean PASS.

Labels can be entered on the page (kept in the browser) and downloaded as labels.csv.

Usage (from the repo root): backend/.venv/Scripts/python llm_judge/scripts/review_pages.py
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_JUDGE = HERE.parent
REPO = LLM_JUDGE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "backend"))
from transcript import _overview, load, turns  # noqa: E402
from app.quotes import match_quote  # noqa: E402

KIND = {"paper": "From the paper", "explanation": "Explanation", "example": "Illustrative example · not from the paper",
        "inference": "PaperLens inference", "research_use": "For your research", "limitation": "Limitation / uncertainty"}
esc = html.escape


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def highlight(text: str, spans: list[str]) -> str:
    text = nfkc(text)
    marks = []
    for span in spans:
        i = text.find(span)
        if i >= 0:
            marks.append((i, i + len(span)))
    out, pos = [], 0
    for a, b in sorted(marks):
        if a < pos:
            continue
        out += [esc(text[pos:a]), f"<mark>{esc(text[a:b])}</mark>"]
        pos = b
    out.append(esc(text[pos:]))
    return "".join(out)


def turn_data(event: dict, overview: dict) -> dict:
    """Material provided this turn, quote checks and signals, computed uniformly from the logged event."""
    provided: dict[str, dict] = {}
    for o_id in event.get("overview_ids", []):
        if o_id in overview:
            o = overview[o_id]
            provided[o_id] = {"kind": "overview", "page": f"{o['pages'][0]}-{o['pages'][-1]}", "text": o["summary"]}
    for h in event.get("retrieved", []):
        provided[h["chunk_id"]] = {"kind": h.get("kind", "paper"), "page": h["page"], "text": h["text"]}
    raw = event.get("raw_model_output") or {}
    msg = event["assistant_message"]
    raw_ids = list(raw.get("short_answer_chunk_ids", []))
    for s in raw.get("sections", []):
        raw_ids += s.get("chunk_ids", [])
    not_provided = sorted({i for i in raw_ids if i and i not in provided})

    quotes: dict[str, list[str]] = {}
    bad_quotes = []
    for q in raw.get("evidence_quotes", []) or []:
        ref, quote = (q.get("chunk_id") or "").strip(), (q.get("quote") or "").strip()
        src = provided.get(ref)
        if src is None or src["kind"] == "overview":
            bad_quotes.append((ref, quote, "cited ID is not an original passage provided this turn"))
            continue
        target = src["text"]
        if src["kind"] == "figure":  # only the caption is the authors' words
            target = src["text"].split("Caption (authors' words):", 1)[1] if "Caption (authors' words):" in src["text"] else ""
        result = match_quote(quote, target)
        if result["ok"]:
            quotes.setdefault(ref, []).append(result["text"])
        else:
            bad_quotes.append((ref, quote, f"not found in the cited {'caption' if src['kind'] == 'figure' else 'passage'}"))

    signals = []
    if not_provided:
        signals.append("Cited IDs that were not among the material provided this turn: " + ", ".join(not_provided))
    for ref, quote, why in bad_quotes:
        signals.append(f"Evidence quote for {ref} {why}: “{quote[:160]}”")
    for s in msg.get("sections", []):
        if s["kind"] == "paper":
            kinds = {provided.get(r, {}).get("kind") for r in s.get("refs", [])}
            if not s.get("refs"):
                signals.append(f"“From the paper” part “{s['title']}” cites no passage")
            elif "paper" not in kinds:
                signals.append(f"“From the paper” part “{s['title']}” cites only PaperLens-generated material "
                               f"({', '.join(sorted(k for k in kinds if k))})")
    if not msg.get("short_answer_refs"):
        signals.append("The short answer cites no passage")
    if msg.get("evidence_status") in ("partial", "insufficient"):
        signals.append(f"PaperLens reported evidence status: {msg['evidence_status']}")
    return {"provided": provided, "quotes": quotes, "signals": signals}


def sources_html(refs: list[str], data: dict) -> str:
    if not refs:
        return "<div class='nosrc'>No cited passage</div>"
    out = []
    for r in refs:
        src = data["provided"].get(r)
        if src is None:
            out.append(f"<div class='src missing'><b>{esc(r)}</b> — not among the material provided this turn</div>")
            continue
        label = {"paper": "Original passage", "figure": "Figure: PaperLens description + authors' caption",
                 "overview": "PaperLens-generated overview summary (not the authors' words)"}.get(src["kind"], src["kind"])
        out.append(f"<details class='src {src['kind']}'><summary><b>{esc(r)}</b> · PDF p. {esc(str(src['page']))} · {label}</summary>"
                   f"<div class='srctext'>{highlight(src['text'], data['quotes'].get(r, []))}</div></details>")
    return "".join(out)


def reply_html(msg: dict, data: dict) -> str:
    out = [f"<div class='part'><div class='kind short'>Short answer</div><div class='txt'>{esc(msg.get('short_answer', ''))}</div>"
           f"{sources_html(msg.get('short_answer_refs', []), data)}</div>"]
    for s in msg.get("sections", []):
        out.append(f"<div class='part'><div class='kind k-{s['kind']}'>{KIND.get(s['kind'], s['kind'])}</div>"
                   f"<div class='title'>{esc(s['title'])}</div><div class='txt'>{esc(s['text'])}</div>"
                   f"{sources_html(s.get('refs', []), data)}</div>")
    if msg.get("clarifying_question"):
        out.append(f"<div class='part'><div class='kind'>Clarifying question</div><div class='txt'>{esc(msg['clarifying_question'])}</div></div>")
    if msg.get("system_suggestion"):
        sug = msg["system_suggestion"]
        out.append(f"<div class='part'><div class='kind'>PaperLens suggestion</div><div class='txt'>{esc(sug['verdict'])}: {esc(sug['reason'])}</div></div>")
    return "".join(out)


def prev_html(msg: dict | None) -> str:
    if not msg:
        return "<i>(first message of the conversation)</i>"
    titles = "".join(f"<li>[{KIND.get(s['kind'], s['kind'])}] <b>{esc(s['title'])}</b>: {esc(s['text'])}</li>" for s in msg.get("sections", []))
    return f"<div>{esc(msg.get('short_answer', ''))}</div><ul>{titles}</ul>"


def conversation_html(conv_id: str, export: dict) -> str:
    s = export["session"]
    overview = _overview(s["paper_id"])
    moves = {}
    chat_log = [m for m in export.get("simulator", {}).get("log", []) if m.get("type") == "chat"]
    for m in chat_log:
        moves[m.get("learner_message", "")] = m.get("instruction", "")
    out = [f"<section id='{conv_id}'><h2>{conv_id}</h2>",
           f"<p class='meta'><b>Paper:</b> {esc(s.get('paper_title', ''))}<br><b>Reading goal:</b> {esc(s.get('reading_goal') or '(not set)')}"
           f"<br><b>Research context:</b> {esc(s.get('research_context') or '(not provided)')}<br><b>Language setting:</b> {esc(s.get('language', ''))}</p>"]
    prev = None
    for n, e in enumerate(turns(export), 1):
        msg = e["assistant_message"]
        if e.get("mode") != "chat":
            out.append(f"<div class='skipped'>Turn {n} ({esc(e.get('mode'))}): not judged by either criterion</div>")
            prev = msg
            continue
        data = turn_data(e, overview)
        sig = "".join(f"<li>{esc(x)}</li>" for x in data["signals"]) or "<li class='none'>none</li>"
        out.append(f"<div class='turn'><h3>Turn {n}</h3>"
                   f"<div class='grid'><div class='col'><div class='lbl'>For A · previous PaperLens reply</div>{prev_html(prev)}</div>"
                   f"<div class='col'><div class='lbl'>Learner message</div><div class='learner'>{esc(e['user_message'])}</div>"
                   f"<div class='lbl'>Move the simulated learner was given</div><div class='move'>{esc(moves.get(e['user_message'], '(not recorded)'))}</div></div></div>"
                   f"<div class='lbl'>PaperLens reply (expand a source to see the cited text; highlighted = evidence quote that occurs in it)</div>"
                   f"{reply_html(msg, data)}"
                   f"<div class='lbl'>Objective signals from the log (not a verdict)</div><ul class='signals'>{sig}</ul></div>")
        prev = msg
    for crit in ("A", "B"):
        out.append(f"<div class='label' data-id='{conv_id}' data-crit='{crit}'><b>{conv_id} · criterion {crit}</b> "
                   f"<label><input type='radio' name='{conv_id}{crit}' value='PASS'> PASS</label> "
                   f"<label><input type='radio' name='{conv_id}{crit}' value='FAIL'> FAIL</label> "
                   f"<input class='note' placeholder='notes: which turn, which rule'></div>")
    out.append("</section>")
    return "".join(out)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Labeling review</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#d0d4da;--soft:#f5f6f8;--mark:#fff1a8}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI","Microsoft JhengHei","Microsoft YaHei",sans-serif;color:var(--fg);background:var(--bg);font-size:14px;line-height:1.5}
nav{position:fixed;top:0;left:0;bottom:0;width:150px;overflow:auto;border-right:1px solid var(--line);padding:12px;background:var(--soft)}
nav a{display:block;padding:2px 0;color:#0b57d0;text-decoration:none}nav a.done{color:#1a7f37}nav a.done::after{content:" ✓"}
nav button{margin-top:12px;width:100%}main{margin-left:180px;max-width:1100px;padding:16px 24px}
h2{border-bottom:2px solid var(--fg);margin-top:40px}.meta{color:var(--muted)}
.turn{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:14px 0}.turn h3{margin:0 0 6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.col{background:var(--soft);border-radius:6px;padding:8px}
.lbl{font-size:12px;font-weight:600;color:var(--muted);margin:8px 0 3px;text-transform:uppercase;letter-spacing:.03em}
.learner{font-weight:600}.move{font-style:italic;color:#444}
.part{border-left:4px solid var(--line);padding:4px 10px;margin:6px 0}.kind{display:inline-block;font-size:12px;font-weight:700;padding:1px 6px;border-radius:4px;background:#e8eaed}
.k-paper{background:#dbeafe}.k-inference{background:#fde68a}.k-example{background:#fce7f3}.k-research_use{background:#dcfce7}.k-limitation{background:#fee2e2}
.title{font-weight:600}.src{margin:3px 0 3px 10px;font-size:13px}.src summary{cursor:pointer}.srctext{white-space:pre-wrap;background:var(--soft);padding:6px;border-radius:4px}
.src.overview summary,.src.figure summary{color:#8a5a00}.missing{color:#cf222e}.nosrc{color:var(--muted);font-size:12px;margin-left:10px}
mark{background:var(--mark)}.signals li{color:#8a2be2}.signals .none{color:var(--muted)}
.skipped{color:var(--muted);font-style:italic;margin:8px 0}
.label{position:sticky;bottom:0;background:#eef6ff;border:1px solid #9ec5fe;padding:6px 10px;margin:6px 0;border-radius:6px}
.note{width:55%;margin-left:8px}
@media (max-width:700px){nav{display:none}main{margin-left:0}.grid{grid-template-columns:1fr}}
</style></head><body><nav><b>Conversations</b>__NAV__<button onclick="dl()">Download labels.csv</button>
<p style="font-size:12px;color:#666">Labels are kept in this browser until you download them.</p></nav><main>
<h1>Labeling review</h1><p>Both criteria judge chat turns only. Any failing reply makes the conversation FAIL.
Signals are facts recomputed from the logs; they are not verdicts.</p>__BODY__</main><script>
const KEY='paperlens-labels-v1';let store={};try{store=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(store))}catch(e){}mark()}
function mark(){document.querySelectorAll('nav a').forEach(a=>{const id=a.dataset.id;a.classList.toggle('done',!!(store[id+'A']&&store[id+'A'].label&&store[id+'B']&&store[id+'B'].label))})}
document.querySelectorAll('.label').forEach(div=>{const k=div.dataset.id+div.dataset.crit;const v=store[k]||{};
 div.querySelectorAll('input[type=radio]').forEach(r=>{if(r.value===v.label)r.checked=true;r.onchange=()=>{store[k]={...(store[k]||{}),label:r.value};save()}});
 const n=div.querySelector('.note');n.value=v.note||'';n.oninput=()=>{store[k]={...(store[k]||{}),note:n.value};save()}});
function dl(){const ids=[...document.querySelectorAll('section')].map(s=>s.id);let rows=['conv_id,criterion,human_label,judge_label_v1,judge_label_v2,notes'];
 for(const id of ids)for(const c of ['A','B']){const v=store[id+c]||{};rows.push([id,c,v.label||'','','','"'+(v.note||'').replace(/"/g,'""')+'"'].join(','))}
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+rows.join('\\n')],{type:'text/csv'}));a.download='labels.csv';a.click()}
mark();</script></body></html>"""


def main() -> int:
    with (LLM_JUDGE / "conversations" / "index.csv").open(encoding="utf-8") as f:
        rows = sorted((r for r in csv.DictReader(f) if r["included"] == "yes"), key=lambda r: r["conv_id"])
    body = "".join(conversation_html(r["conv_id"], load(LLM_JUDGE / r["file"])) for r in rows)
    nav = "".join(f"<a href='#{r['conv_id']}' data-id='{r['conv_id']}'>{r['conv_id']}</a>" for r in rows)
    out = LLM_JUDGE / "labeling" / "review.html"
    out.write_text(PAGE.replace("__NAV__", nav).replace("__BODY__", body), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
