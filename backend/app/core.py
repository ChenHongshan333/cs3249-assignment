"""PaperLens service layer: the single entry point used by BOTH the web API (main.py) and test scripts.

Every learner-facing action is a function here and every call writes one event to data/logs/<session_id>.jsonl.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from . import storage
from .config import PROMPT_VERSION, settings
from .graph import TURN_GRAPH, log_view
from .llm import ModelError, structured_call
from .prompts import load_prompt
from .schemas import VERDICTS, NoteDraft

CRITICAL_REVIEW_REQUEST = "Critically review whether the idea or method we have been discussing is applicable to my research."
READING_GOALS = (
    "Get a general overview of this paper",
    "Reproduce the study or method",
    "Explore potential use in my research",
)


class UserInputError(ValueError):
    """Invalid request from the learner (shown to them as-is)."""


def _base_event(event: str, session: dict) -> dict:
    return {
        "event": event,
        "event_id": uuid.uuid4().hex[:12],
        "timestamp": storage.now_iso(),
        "session_id": session["session_id"],
        "paper_id": session["paper_id"],
        "pipeline_version": settings.pipeline_version,
        "prompt_version": PROMPT_VERSION,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "config": settings.public(),
    }


def _get_session(session_id: str) -> dict:
    session = storage.load_session(session_id)
    if session is None or session.get("deleted_at"):
        raise UserInputError(f"Session {session_id} does not exist.")
    return session


# ------------------------------------------------------------------ sessions

def create_session(paper_id: str, reading_goal: str = "", research_context: str = "", language: str = "English") -> dict:
    paper = storage.load_paper_meta(paper_id)
    if not paper or paper.get("status") != "ready":
        raise UserInputError("This paper is not ready yet. Wait for indexing to finish or retry the upload.")
    session = {
        "session_id": f"s-{uuid.uuid4().hex[:12]}",
        "paper_id": paper_id,
        "paper_title": paper.get("title", ""),
        "created_at": storage.now_iso(),
        "reading_goal": reading_goal.strip(),
        "research_context": research_context.strip(),
        "language": language,
        "current_concept": "",
        "messages": [],
        "system_suggestion": None,   # PaperLens's suggestion from the critical review
        "judgment": None,            # the learner's own verdict + rationale (never model-written)
        "note": None,
    }
    storage.save_session(session)
    storage.append_log(session["session_id"], {**_base_event("session_created", session),
                                               "reading_goal": session["reading_goal"],
                                               "research_context": session["research_context"],
                                               "language": language})
    return session


def update_session(session_id: str, reading_goal: str | None = None, research_context: str | None = None,
                   language: str | None = None) -> dict:
    session = _get_session(session_id)
    changes = {}
    for key, value in (("reading_goal", reading_goal), ("research_context", research_context), ("language", language)):
        if value is not None and value.strip() != session.get(key, ""):
            session[key] = value.strip()
            changes[key] = session[key]
    if "language" in changes and session.get("language_override"):
        # choosing a language in the settings replaces an earlier in-chat request
        session["language_override"] = ""
        changes["language_override"] = ""
    if changes:
        storage.save_session(session)
        storage.append_log(session_id, {**_base_event("session_updated", session), "changes": changes})
    return session


def delete_session(session_id: str) -> dict:
    """Soft delete: hide the session from the learner but keep its file and its full run log.

    The JSONL log is evidence for evaluation (ai_logs / llm_judge), so nothing is erased; a
    session_deleted event is appended instead.
    """
    session = _get_session(session_id)
    session["deleted_at"] = storage.now_iso()
    storage.save_session(session)
    storage.append_log(session_id, {**_base_event("session_deleted", session), "deleted_at": session["deleted_at"]})
    return {"ok": True, "session_id": session_id, "deleted_at": session["deleted_at"]}


def list_visible_sessions() -> list[dict]:
    return [s for s in storage.list_sessions() if not s.get("deleted_at")]


# ------------------------------------------------------------------ turns

def run_turn(session_id: str, message: str, mode: str = "chat") -> dict:
    """Run one learner turn through the LangGraph workflow. Returns {ok, message | error}."""
    session = _get_session(session_id)
    message = (message or "").strip()
    if not message:
        raise UserInputError("Message is empty.")
    if len(message) > 4000:
        raise UserInputError("Message is too long (max 4000 characters).")
    started = time.perf_counter()
    last_state: dict[str, Any] = {}
    error = None
    try:
        for state in TURN_GRAPH.stream({"session_id": session_id, "mode": mode, "user_message": message},
                                       stream_mode="values"):
            last_state = state
    except ModelError as exc:
        error = str(exc)
    except ValueError as exc:
        error = str(exc)
    except Exception as exc:  # keep the system usable and record the failure
        error = f"Unexpected error: {exc!r}"
    event = {**_base_event("turn", session), "mode": mode, "user_message": message,
             **log_view(last_state), "latency_ms": round((time.perf_counter() - started) * 1000), "error": error}
    storage.append_log(session_id, event)
    if error:
        return {"ok": False, "error": error, "event_id": event["event_id"]}
    return {"ok": True, "message": last_state["assistant_message"], "event_id": event["event_id"],
            "current_concept": last_state.get("current_concept", "")}


def run_critical_review(session_id: str) -> dict:
    session = _get_session(session_id)
    if not session.get("research_context"):
        raise UserInputError("Add a short description of your research first, so the review can be about your study.")
    return run_turn(session_id, CRITICAL_REVIEW_REQUEST, mode="critical_review")


def submit_judgment(session_id: str, verdict: str, rationale: str) -> dict:
    """Store the learner's own verdict and rationale verbatim, then ask PaperLens to respond to it."""
    if verdict not in VERDICTS:
        raise UserInputError(f"Verdict must be one of: {', '.join(VERDICTS)}.")
    rationale = (rationale or "").strip()
    if len(rationale) < 10:
        raise UserInputError("Please write a short rationale in your own words (at least a few words).")
    session = _get_session(session_id)
    session["judgment"] = {"verdict": verdict, "rationale": rationale, "submitted_at": storage.now_iso(),
                           "system_suggestion_at_time": session.get("system_suggestion")}
    storage.save_session(session)
    storage.append_log(session_id, {**_base_event("judgment_recorded", session), "judgment": session["judgment"]})
    text = f"My verdict: {verdict}\nMy rationale: {rationale}"
    result = run_turn(session_id, text, mode="judgment_feedback")
    result["judgment"] = session["judgment"]
    return result


# ------------------------------------------------------------------ research-use note

def _cited_sources(session: dict) -> dict[str, dict]:
    sources: dict[str, dict] = {}
    for message in session.get("messages", []):
        for src in message.get("sources", []):
            if src.get("verified"):
                sources[src["ref_id"]] = src
    return sources


def generate_note(session_id: str) -> dict:
    session = _get_session(session_id)
    if not any(m["role"] == "assistant" for m in session.get("messages", [])):
        raise UserInputError("Have at least one exchange with PaperLens before creating a note.")
    sources = _cited_sources(session)
    transcript = []
    for m in session["messages"]:
        if m["role"] == "user":
            transcript.append(f"Learner ({m['mode']}): {m['text']}")
        else:
            body = m["short_answer"] + "".join(f"\n  - {s['title']}: {s['text']}" for s in m.get("sections", []))
            transcript.append(f"PaperLens: {body}")
    passages = "\n".join(f'<passage id="{ref}" pdf_page="{s["page"]}">\n{s["text"]}\n</passage>' for ref, s in sources.items())
    prompt = (f"Paper: {session.get('paper_title', '')}\nReading goal: {session.get('reading_goal') or '(not set)'}\n"
              f"Learner's research context: {session.get('research_context') or '(not provided)'}\n"
              f"Response language: {session.get('language_override') or session.get('language', 'English')}\n\n"
              f"<transcript>\n" + "\n".join(transcript) + "\n</transcript>\n\n"
              f"<passages_cited_in_session>\n{passages or '(none)'}\n</passages_cited_in_session>")
    started = time.perf_counter()
    error, note = None, None
    try:
        draft = structured_call(load_prompt("note"), prompt, NoteDraft)
        invalid = []
        evidence = []
        for item in draft.evidence:
            refs = [r for r in item.chunk_ids if r in sources]
            invalid += [r for r in item.chunk_ids if r not in sources]
            evidence.append({"point": item.point, "sources": [sources[r] for r in refs]})
        note = {
            "selected_idea": draft.selected_idea,
            "evidence": evidence,
            "research_use": draft.research_use,
            "adaptations_and_uncertainties": draft.adaptations_and_uncertainties,
            "next_actions": draft.next_actions,
            # Copied verbatim from what the learner submitted; the model never writes these fields.
            "learner_judgment": session.get("judgment"),
            "system_suggestion": session.get("system_suggestion"),
            "generated_at": storage.now_iso(),
            "edited_by_learner": False,
        }
        session["note"] = note
        storage.save_session(session)
    except ModelError as exc:
        error, invalid = str(exc), []
    storage.append_log(session_id, {**_base_event("note_generated", session), "note": note, "error": error,
                                    "invalid_citations": invalid,
                                    "latency_ms": round((time.perf_counter() - started) * 1000)})
    if error:
        return {"ok": False, "error": error}
    return {"ok": True, "note": note}


def save_note(session_id: str, fields: dict) -> dict:
    """Learner edits to the note. Only text fields are editable; sources stay attached."""
    session = _get_session(session_id)
    note = session.get("note")
    if not note:
        raise UserInputError("Generate the note first.")
    for key in ("selected_idea", "research_use", "adaptations_and_uncertainties"):
        if isinstance(fields.get(key), str):
            note[key] = fields[key]
    if isinstance(fields.get("next_actions"), list):
        note["next_actions"] = [str(x) for x in fields["next_actions"] if str(x).strip()]
    if isinstance(fields.get("evidence_points"), list):
        for item, point in zip(note["evidence"], fields["evidence_points"]):
            item["point"] = str(point)
    if isinstance(fields.get("rationale"), str) and note.get("learner_judgment"):
        note["learner_judgment"]["rationale"] = fields["rationale"]
    note["edited_by_learner"] = True
    note["edited_at"] = storage.now_iso()
    storage.save_session(session)
    storage.append_log(session_id, {**_base_event("note_edited", session), "note": note})
    return note


# ------------------------------------------------------------------ export

# Labels of the Markdown note, in the learner's interface language (the language setting). Stored values
# (verdicts, reading goals) stay in English in the session and logs; only their display is translated here.
_EN = {
    "title": "Research-use note", "paper": "Paper", "goal": "Reading goal", "research": "My research",
    "untitled": "Untitled paper", "not_set": "Not set", "not_provided": "Not provided",
    "idea": "Selected idea", "decision": "My decision", "reason": "My reason", "undecided": "Not decided yet.",
    "suggestion": "PaperLens suggestion (not my decision)", "no_review": "No critical review in this session.",
    "evidence": "Evidence from the paper", "no_evidence": "No cited evidence in this session.",
    "use": "Possible use in my research", "adapt": "Required adaptations and uncertainties", "next": "Next actions",
    "page": "PDF p. {n}", "pages": "PDF pp. {a}-{b}", "printed": " (printed p. {n})",
    "summary": "PaperLens summary (not the authors' words)",
    "figure": "{label}, PDF p. {n}, PaperLens description of the image",
    "footer": "Drafted by PaperLens from session {sid} on {at}; {edited}. Page numbers are PDF page indexes.",
    "edited": "edited by the learner", "unedited": "not edited by the learner",
    "verdicts": {"Do not use": "Not suitable for my study"}, "goals": {},
}
_ZH_HANS = {
    "title": "研究应用笔记", "paper": "论文", "goal": "阅读目标", "research": "我的研究",
    "untitled": "未命名论文", "not_set": "未设置", "not_provided": "未提供",
    "idea": "选定的想法", "decision": "我的决定", "reason": "我的理由", "undecided": "尚未决定。",
    "suggestion": "PaperLens 的建议（不是我的决定）", "no_review": "本次会话没有进行批判性评估。",
    "evidence": "论文中的证据", "no_evidence": "本次会话没有引用证据。",
    "use": "在我的研究中的可能用途", "adapt": "需要的调整与不确定之处", "next": "下一步",
    "page": "PDF 第 {n} 页", "pages": "PDF 第 {a}-{b} 页", "printed": "（印刷页码 {n}）",
    "summary": "PaperLens 生成的摘要（不是作者原话）",
    "figure": "{label}，PDF 第 {n} 页，PaperLens 对图的描述",
    "footer": "由 PaperLens 根据会话 {sid} 于 {at} 起草；{edited}。页码为 PDF 页序。",
    "edited": "学习者已编辑", "unedited": "学习者未编辑",
    "verdicts": {"Use as proposed": "按原样使用", "Use with adaptations": "调整后使用", "Do not use": "不适合我的研究",
                 "Need more evidence": "需要更多证据"},
    "goals": {"Get a general overview of this paper": "了解这篇论文的概况", "Reproduce the study or method": "复现研究或方法",
              "Explore potential use in my research": "探索在我研究中的潜在用途"},
}
_ZH_HANT = {
    "title": "研究應用筆記", "paper": "論文", "goal": "閱讀目標", "research": "我的研究",
    "untitled": "未命名論文", "not_set": "未設定", "not_provided": "未提供",
    "idea": "選定的想法", "decision": "我的決定", "reason": "我的理由", "undecided": "尚未決定。",
    "suggestion": "PaperLens 的建議（不是我的決定）", "no_review": "本次對話沒有進行批判性評估。",
    "evidence": "論文中的證據", "no_evidence": "本次對話沒有引用證據。",
    "use": "在我的研究中的可能用途", "adapt": "需要的調整與不確定之處", "next": "下一步",
    "page": "PDF 第 {n} 頁", "pages": "PDF 第 {a}-{b} 頁", "printed": "（印刷頁碼 {n}）",
    "summary": "PaperLens 產生的摘要（不是作者原話）",
    "figure": "{label}，PDF 第 {n} 頁，PaperLens 對圖的描述",
    "footer": "由 PaperLens 根據對話 {sid} 於 {at} 起草；{edited}。頁碼為 PDF 頁序。",
    "edited": "學習者已編輯", "unedited": "學習者未編輯",
    "verdicts": {"Use as proposed": "按原樣使用", "Use with adaptations": "調整後使用", "Do not use": "不適合我的研究",
                 "Need more evidence": "需要更多證據"},
    "goals": {"Get a general overview of this paper": "了解這篇論文的概況", "Reproduce the study or method": "重現研究或方法",
              "Explore potential use in my research": "探索在我研究中的潛在用途"},
}
_JA = {
    "title": "研究活用ノート", "paper": "論文", "goal": "読む目的", "research": "自分の研究",
    "untitled": "無題の論文", "not_set": "未設定", "not_provided": "未入力",
    "idea": "選んだアイデア", "decision": "自分の判断", "reason": "理由", "undecided": "まだ判断していません。",
    "suggestion": "PaperLens の提案（自分の判断ではありません）", "no_review": "このセッションでは批判的レビューを行っていません。",
    "evidence": "論文からの根拠", "no_evidence": "このセッションで引用された根拠はありません。",
    "use": "自分の研究での活用可能性", "adapt": "必要な調整と不確かな点", "next": "次のアクション",
    "page": "PDF {n} ページ", "pages": "PDF {a}–{b} ページ", "printed": "（印刷ページ {n}）",
    "summary": "PaperLens による要約（著者の言葉ではありません）",
    "figure": "{label}、PDF {n} ページ、PaperLens による図の説明",
    "footer": "PaperLens がセッション {sid} から {at} に作成；{edited}。ページ番号は PDF のページ順です。",
    "edited": "学習者が編集済み", "unedited": "学習者は未編集",
    "verdicts": {"Use as proposed": "提案どおり使う", "Use with adaptations": "調整して使う", "Do not use": "自分の研究には合わない",
                 "Need more evidence": "さらに根拠が必要"},
    "goals": {"Get a general overview of this paper": "論文の全体像をつかむ", "Reproduce the study or method": "研究や手法を再現する",
              "Explore potential use in my research": "自分の研究での活用を探る"},
}
NOTE_LABELS = {"English": _EN, "中文（简体）": _ZH_HANS, "中文（繁體）": _ZH_HANT, "日本語": _JA}


def _source_label(src: dict, t: dict = _EN) -> str:
    pages = src.get("pages") or []
    if src.get("kind") == "figure":
        return t["figure"].format(label=src.get("label") or "Figure", n=src.get("page"))
    if src.get("kind") == "overview":
        span = t["pages"].format(a=pages[0], b=pages[-1]) if len(pages) > 1 else t["page"].format(n=src.get("page"))
        return f"{span}, {t['summary']}"
    label = t["page"].format(n=src.get("page"))
    if src.get("page_label") and str(src.get("page_label")) != str(src.get("page")):
        label += t["printed"].format(n=src["page_label"])
    return label


def note_markdown(session_id: str) -> str:
    """The research-use note as a Markdown document for the learner, labelled in their interface language.

    The learner's decision and PaperLens's suggestion are kept in separate sections.
    """
    session = _get_session(session_id)
    note = session.get("note")
    if not note:
        raise UserInputError("There is no research-use note in this session yet. Draft one on the note page first.")
    t = NOTE_LABELS.get(session.get("language", "English"), _EN)

    def verdict(value: str) -> str:
        return t["verdicts"].get(value, value)

    goal = session.get("reading_goal") or ""
    judgment = note.get("learner_judgment")
    suggestion = note.get("system_suggestion")
    lines = [
        f"# {t['title']}",
        "",
        f"**{t['paper']}:** {session.get('paper_title') or t['untitled']}  ",
        f"**{t['goal']}:** {t['goals'].get(goal, goal) or t['not_set']}  ",
        f"**{t['research']}:** {session.get('research_context') or t['not_provided']}",
        "",
        f"## {t['idea']}",
        "",
        note.get("selected_idea") or "-",
        "",
        f"## {t['decision']}",
        "",
    ]
    if judgment:
        lines += [f"**{verdict(judgment['verdict'])}**", "", f"{t['reason']}: {judgment['rationale']}"]
    else:
        lines += [t["undecided"]]
    lines += ["", f"## {t['suggestion']}", ""]
    lines += [f"{verdict(suggestion['verdict'])}: {suggestion['reason']}" if suggestion else t["no_review"]]
    lines += ["", f"## {t['evidence']}", ""]
    if note.get("evidence"):
        for item in note["evidence"]:
            # Several cited passages can sit on the same page; list each page once.
            refs = "; ".join(dict.fromkeys(_source_label(s, t) for s in item.get("sources", [])))
            lines.append(f"- {item['point']}" + (f" [{refs}]" if refs else ""))
    else:
        lines.append(t["no_evidence"])
    lines += ["", f"## {t['use']}", "", note.get("research_use") or "-",
              "", f"## {t['adapt']}", "", note.get("adaptations_and_uncertainties") or "-",
              "", f"## {t['next']}", ""]
    lines += [f"- {a}" for a in note.get("next_actions", []) if a.strip()] or ["-"]
    edited = t["edited"] if note.get("edited_by_learner") else t["unedited"]
    lines += ["", "---", "", t["footer"].format(sid=session_id, at=note.get("generated_at", ""), edited=edited)]
    storage.append_log(session_id, {**_base_event("note_exported", session), "format": "markdown",
                                    "language": session.get("language", "English")})
    return "\n".join(lines) + "\n"


def export_session(session_id: str) -> dict:
    session = _get_session(session_id)
    return {
        "exported_at": storage.now_iso(),
        "paper": storage.load_paper_meta(session["paper_id"]),
        "session": session,
        "events": storage.read_log(session_id),
    }
