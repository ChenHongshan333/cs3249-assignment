"""Turn an exported conversation (simulate_conversation.py output) into readable text.

Used in two places with the SAME content, so the student and the judge see the same evidence:
  * render(export, "A")  -> what the criterion-A judge sees (learner messages and PaperLens replies)
  * render(export, "B")  -> what the criterion-B judge sees (replies + cited IDs + the material provided per turn)
  * labeling_markdown()  -> the student's labeling sheet: everything above, without pipeline version or file name
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERS = REPO / "backend" / "data" / "papers"


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def turns(export: dict) -> list[dict]:
    """Successful turn events in order (learner message + PaperLens reply + the material it was given)."""
    return [e for e in export.get("events", []) if e.get("event") == "turn" and not e.get("error")
            and e.get("assistant_message")]


def _overview(paper_id: str) -> dict[str, dict]:
    path = PAPERS / paper_id / "overview.json"
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {o["overview_id"]: o for o in items}


MODE_LABEL = {"chat": "chat", "critical_review": "critical review", "judgment_feedback": "judgment feedback"}


def _reply(msg: dict, with_refs: bool) -> list[str]:
    refs = lambda ids: f"  [cites: {', '.join(ids)}]" if with_refs and ids else ""  # noqa: E731
    out = [f"Short answer: {msg.get('short_answer', '')}{refs(msg.get('short_answer_refs', []))}"]
    for s in msg.get("sections", []):
        out.append(f"- Section ({s['kind']}) \"{s['title']}\": {s['text']}{refs(s.get('refs', []))}")
    if msg.get("clarifying_question"):
        out.append(f"Clarifying question: {msg['clarifying_question']}")
    if msg.get("system_suggestion"):
        sug = msg["system_suggestion"]
        out.append(f"PaperLens suggestion: {sug['verdict']} - {sug['reason']}")
    if with_refs:
        out.append(f"Evidence status reported by PaperLens: {msg.get('evidence_status', '')}")
    return out


def _material(event: dict, msg: dict, overview: dict[str, dict]) -> list[str]:
    out = ["Material provided to PaperLens for this turn:"]
    provided = set()
    for o_id in event.get("overview_ids", []):
        o = overview.get(o_id)
        if o:
            provided.add(o_id)
            pages = f"{o['pages'][0]}-{o['pages'][-1]}"
            out.append(f'<overview id="{o_id}" pdf_pages="{pages}" note="PaperLens-generated summary, not the authors\' words">\n'
                       f"{o['summary']}\n</overview>")
    for h in event.get("retrieved", []):
        provided.add(h["chunk_id"])
        if h.get("kind") == "figure":
            out.append(f'<figure id="{h["chunk_id"]}" pdf_page="{h["page"]}" note="PaperLens-generated description; '
                       f'only the caption is the authors\' words">\n{h["text"]}\n</figure>')
        else:
            out.append(f'<passage id="{h["chunk_id"]}" pdf_page="{h["page"]}">\n{h["text"]}\n</passage>')
    cited = [s["ref_id"] for s in msg.get("sources", [])]
    missing = [c for c in cited if c not in provided]
    if missing:
        out.append("Cited IDs that were NOT among the provided material: " + ", ".join(missing))
    return out


def render(export: dict, criterion: str) -> str:
    """The conversation as the judge for criterion A or B sees it."""
    with_evidence = criterion.upper() == "B"
    overview = _overview(export["session"]["paper_id"]) if with_evidence else {}
    s = export["session"]
    lines = [f"Paper: {s.get('paper_title', '')}",
             f"Learner's reading goal: {s.get('reading_goal') or '(not set)'}",
             f"Learner's research context: {s.get('research_context') or '(not provided)'}",
             f"Response language setting: {s.get('language', 'English')}", ""]
    for n, e in enumerate(turns(export), 1):
        msg = e["assistant_message"]
        lines.append(f"=== Turn {n} ({MODE_LABEL.get(e.get('mode'), e.get('mode'))}) ===")
        lines.append(f"Learner: {e['user_message']}")
        lines.append("PaperLens:")
        lines += _reply(msg, with_evidence)
        if with_evidence:
            lines += _material(e, msg, overview)
        lines.append("")
    return "\n".join(lines)


def labeling_markdown(export: dict, conv_id: str) -> str:
    """Labeling sheet for the student: same content as the criterion-B judge input, blinded (no pipeline version
    or file name), formatted for reading in a Markdown preview. Provided material is folded under <details>."""
    s = export["session"]
    overview = _overview(s["paper_id"])
    out = [f"# {conv_id}", "",
           f"**Paper:** {s.get('paper_title', '')}  ",
           f"**Reading goal:** {s.get('reading_goal') or '(not set)'}  ",
           f"**Research context:** {s.get('research_context') or '(not provided)'}  ",
           f"**Language setting:** {s.get('language', 'English')}", "",
           "Label PASS/FAIL for criterion A and criterion B in `llm_judge/labels.csv`. "
           "Both criteria ignore critical-review and judgment-feedback turns.", ""]
    for n, e in enumerate(turns(export), 1):
        msg = e["assistant_message"]
        out += [f"## Turn {n} ({MODE_LABEL.get(e.get('mode'), e.get('mode'))})", "",
                f"**Learner:** {e['user_message']}", "", "**PaperLens:**", ""]
        out += [line if line.startswith("- ") else f"- {line}" for line in _reply(msg, True)]
        material = _material(e, msg, overview)
        out += ["", "<details><summary>Material provided to PaperLens for this turn</summary>", "", "```text",
                "\n".join(material[1:]), "```", "</details>", ""]
    return "\n".join(out) + "\n"
