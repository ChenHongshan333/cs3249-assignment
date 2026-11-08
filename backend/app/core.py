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
    if session is None:
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
    if changes:
        storage.save_session(session)
        storage.append_log(session_id, {**_base_event("session_updated", session), "changes": changes})
    return session


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
              f"Response language: {session.get('language', 'English')}\n\n"
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

def export_session(session_id: str) -> dict:
    session = _get_session(session_id)
    return {
        "exported_at": storage.now_iso(),
        "paper": storage.load_paper_meta(session["paper_id"]),
        "session": session,
        "events": storage.read_log(session_id),
    }
