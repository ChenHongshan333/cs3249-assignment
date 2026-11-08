"""The LangGraph workflow that handles one turn (a learner message, a critical-review request or a judgment).

    load_session -> rewrite_query -> (route) -> [load_overview] -> retrieve -> generate_answer
                 -> validate_citations -> save_session

Every node reads and returns part of TurnState. The graph is fixed (no loops, no agent decisions);
the only branch is whether the overview summaries are added for whole-paper questions.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from . import storage
from .config import settings
from .llm import structured_call
from .prompts import load_prompt
from .quotes import match_quote
from .retrieval import search
from .schemas import AnswerPayload, QueryRewrite

Mode = Literal["chat", "critical_review", "judgment_feedback"]
MODE_PROMPTS = {"chat": "answer", "critical_review": "critical_review", "judgment_feedback": "judgment_feedback"}
HISTORY_TURNS = 8
MAX_SECTIONS = 4  # the prompt asks for 0-4 sections; enforce it so the layered UI stays short


class TurnState(TypedDict, total=False):
    # input
    session_id: str
    mode: Mode
    user_message: str
    # loaded from the session
    session: dict
    paper_id: str
    paper_title: str
    reading_goal: str
    research_context: str
    language: str
    current_concept: str
    history: list[dict]
    # produced by the nodes
    pipeline_version: str
    retrieval_query: str
    scope: str
    retrieved: list[dict]
    overview: list[dict]
    raw_answer: dict
    assistant_message: dict
    invalid_citations: list[str]
    quote_checks: list[dict]
    timings_ms: dict


# ------------------------------------------------------------------ helpers

def _timed(state: TurnState, name: str, start: float) -> dict:
    timings = dict(state.get("timings_ms", {}))
    timings[name] = round((time.perf_counter() - start) * 1000)
    return timings


def format_history(history: list[dict]) -> str:
    lines = []
    for message in history[-HISTORY_TURNS:]:
        if message["role"] == "user":
            lines.append(f"Learner: {message['text']}")
        else:
            titles = ", ".join(s["title"] for s in message.get("sections", []))
            extra = f" [expandable sections: {titles}]" if titles else ""
            lines.append(f"PaperLens: {message.get('short_answer', '')}{extra}")
    return "\n".join(lines) or "(no earlier messages)"


def format_passages(passages: list[dict]) -> str:
    out = []
    for p in passages:
        printed = f' printed_page="{p["page_label"]}"' if p["page_label"] != str(p["page"]) else ""
        carried = ' cited_in_previous_answer="true"' if p.get("carried_over") else ""
        out.append(f'<passage id="{p["chunk_id"]}" pdf_page="{p["page"]}"{printed}{carried}>\n{p["text"]}\n</passage>')
    return "\n".join(out) or "(no passages retrieved)"


def format_overview(overview: list[dict]) -> str:
    out = []
    for item in overview:
        pages = f'{item["pages"][0]}-{item["pages"][-1]}' if len(item["pages"]) > 1 else str(item["pages"][0])
        points = "".join(f"\n- {k}" for k in item.get("key_points", []))
        out.append(f'<overview id="{item["overview_id"]}" pdf_pages="{pages}" note="PaperLens-generated summary, not original text">\n'
                   f'{item["summary"]}{points}\n</overview>')
    return "\n".join(out)


def learner_context(state: TurnState) -> str:
    return (f"Paper: {state.get('paper_title', '')}\n"
            f"Reading goal: {state.get('reading_goal') or '(not set)'}\n"
            f"Learner's research context: {state.get('research_context') or '(not provided yet)'}\n"
            f"Concept currently discussed: {state.get('current_concept') or '(none yet)'}\n"
            f"Response language: {state.get('language') or 'English'}")


# ------------------------------------------------------------------ nodes

def load_session(state: TurnState) -> dict:
    session = storage.load_session(state["session_id"])
    if session is None:
        raise ValueError(f"Unknown session {state['session_id']}")
    paper = storage.load_paper_meta(session["paper_id"]) or {}
    if paper.get("status") != "ready":
        raise ValueError("The paper for this session is not indexed yet.")
    return {
        "session": session,
        "paper_id": session["paper_id"],
        "paper_title": paper.get("title", ""),
        "reading_goal": session.get("reading_goal", ""),
        "research_context": session.get("research_context", ""),
        "language": session.get("language", "English"),
        "current_concept": session.get("current_concept", ""),
        "history": session.get("messages", []),
        "pipeline_version": settings.pipeline_version,
        "overview": [],
        "timings_ms": {},
    }


def rewrite_query(state: TurnState) -> dict:
    """Turn the latest message into a standalone retrieval query (v1). v0 uses the raw message."""
    start = time.perf_counter()
    if state["pipeline_version"] == "v0":
        return {"retrieval_query": state["user_message"], "scope": "local", "timings_ms": _timed(state, "rewrite_query", start)}
    prompt = (f"{learner_context(state)}\n\n<conversation>\n{format_history(state['history'])}\n</conversation>\n\n"
              f"Latest learner message: {state['user_message']}")
    result = structured_call(load_prompt("rewrite"), prompt, QueryRewrite)
    scope = "overview" if state["mode"] == "critical_review" else result.scope
    return {
        "retrieval_query": result.standalone_query.strip() or state["user_message"],
        "scope": scope,
        "current_concept": result.current_concept or state.get("current_concept", ""),
        "timings_ms": _timed(state, "rewrite_query", start),
    }


def route_by_scope(state: TurnState) -> str:
    return "load_overview" if state.get("scope") == "overview" else "retrieve"


def load_overview(state: TurnState) -> dict:
    return {"overview": storage.load_paper_json(state["paper_id"], "overview.json") or []}


CARRY_OVER = 4  # passages from the previous answer kept available for follow-up questions


def retrieve(state: TurnState) -> dict:
    """Search this paper's chunks. In v1, also keep the passages cited in the previous answer, so a follow-up
    ("does that affect my study?") can still see the evidence it refers to."""
    start = time.perf_counter()
    hits = search(state["paper_id"], state["retrieval_query"], settings.top_k)
    if state["pipeline_version"] != "v0":
        previous = next((m for m in reversed(state["history"]) if m["role"] == "assistant"), None)
        seen = {h["chunk_id"] for h in hits}
        carried = [s for s in (previous or {}).get("sources", []) if s["kind"] == "paper" and s["verified"]]
        for source in carried[:CARRY_OVER]:
            if source["ref_id"] not in seen:
                hits.append({"chunk_id": source["ref_id"], "text": source["text"], "page": source["page"],
                             "page_label": source["page_label"], "similarity": None, "carried_over": True})
    return {"retrieved": hits, "timings_ms": _timed(state, "retrieve", start)}


def generate_answer(state: TurnState) -> dict:
    start = time.perf_counter()
    system = load_prompt(MODE_PROMPTS[state["mode"]], with_rules=True)
    material = format_passages(state["retrieved"])
    if state.get("overview"):
        material = format_overview(state["overview"]) + "\n" + material
    task = {
        "chat": f"Learner's latest message: {state['user_message']}",
        "critical_review": f"Request: {state['user_message']}",
        "judgment_feedback": f"The learner's own decision (do not rewrite it):\n{state['user_message']}",
    }[state["mode"]]
    prompt = (f"{learner_context(state)}\n\n<conversation>\n{format_history(state['history'])}\n</conversation>\n\n"
              f"<paper_material>\n{material}\n</paper_material>\n\n{task}")
    result = structured_call(system, prompt, AnswerPayload)
    return {"raw_answer": result.model_dump(), "timings_ms": _timed(state, "generate_answer", start)}


def validate_citations(state: TurnState) -> dict:
    """Keep only cited IDs that were really provided this turn; attach page and text from stored metadata (v1).

    v0 (baseline) skips the check: every cited ID is kept, and IDs that were not provided are shown as unverified.
    """
    raw = state["raw_answer"]
    lookup: dict[str, dict] = {}
    for hit in state.get("retrieved", []):
        lookup[hit["chunk_id"]] = {"ref_id": hit["chunk_id"], "kind": "paper", "page": hit["page"],
                                   "page_label": hit["page_label"], "text": hit["text"], "verified": True}
    for item in state.get("overview", []):
        lookup[item["overview_id"]] = {"ref_id": item["overview_id"], "kind": "overview", "page": item["pages"][0],
                                       "pages": item["pages"], "page_label": str(item["pages"][0]),
                                       "text": item["summary"], "verified": True}
    validate = state["pipeline_version"] != "v0"
    invalid: list[str] = []
    order: list[str] = []

    def keep(ids: list[str]) -> list[str]:
        kept = []
        for ref in dict.fromkeys(i.strip() for i in ids if i and i.strip()):
            if ref in lookup or not validate:
                kept.append(ref)
                if ref not in order:
                    order.append(ref)
            else:
                invalid.append(ref)
        return kept

    short_refs = keep(raw.get("short_answer_chunk_ids", []))
    sections = [{"title": s["title"], "kind": s["kind"], "text": s["text"], "refs": keep(s.get("chunk_ids", []))}
                for s in raw.get("sections", [])[:MAX_SECTIONS]]
    sources = [dict(lookup.get(ref, {"ref_id": ref, "kind": "unknown", "page": None, "page_label": None,
                                     "text": None, "verified": False})) for ref in order]

    # Sentence-level evidence (v1): keep a quote only if it really occurs in the cited passage, and attach the
    # matched span (copied from the stored passage) so the frontend can highlight it on the PDF page.
    quote_log: list[dict] = []
    if validate:
        by_ref = {s["ref_id"]: s for s in sources}
        for item in raw.get("evidence_quotes", []) or []:
            ref, quote = (item.get("chunk_id") or "").strip(), (item.get("quote") or "").strip()
            source = by_ref.get(ref)
            if source is None or source["kind"] != "paper":
                if ref not in lookup:
                    reason = "unknown_id"
                elif lookup[ref]["kind"] != "paper":
                    reason = "overview_id"
                else:
                    reason = "passage_not_cited_in_answer"
                quote_log.append({"chunk_id": ref, "quote": quote, "ok": False, "text": None, "score": 0.0, "reason": reason})
                continue
            result = match_quote(quote, source["text"] or "")
            quote_log.append({"chunk_id": ref, "quote": quote, **result})
            if result["ok"] and result["text"] not in source.setdefault("quotes", []):
                source["quotes"].append(result["text"])
    has_paper_support = any(s["kind"] == "paper" and s["verified"] for s in sources)
    suggestion = raw.get("system_suggestion") if state["mode"] == "critical_review" or not validate else None

    message = {
        "id": f"a-{uuid.uuid4().hex[:10]}",
        "role": "assistant",
        "mode": state["mode"],
        "created_at": storage.now_iso(),
        "short_answer": raw.get("short_answer", ""),
        "short_answer_refs": short_refs,
        "sections": sections,
        "sources": sources,
        "evidence_status": raw.get("evidence_status", "partial"),
        "has_verified_paper_source": has_paper_support,
        "clarifying_question": raw.get("clarifying_question", ""),
        "follow_up_suggestions": raw.get("follow_up_suggestions", [])[:3],
        "system_suggestion": suggestion,
        "retrieval_query": state["retrieval_query"],
        "pipeline_version": state["pipeline_version"],
    }
    return {"assistant_message": message, "invalid_citations": invalid, "quote_checks": quote_log,
            "current_concept": raw.get("current_concept") or state.get("current_concept", "")}


def save_session(state: TurnState) -> dict:
    session = state["session"]
    user_entry = {"id": f"u-{uuid.uuid4().hex[:10]}", "role": "user", "mode": state["mode"],
                  "text": state["user_message"], "created_at": storage.now_iso()}
    session.setdefault("messages", []).extend([user_entry, state["assistant_message"]])
    session["current_concept"] = state.get("current_concept", "")
    if state["mode"] == "critical_review" and state["assistant_message"].get("system_suggestion"):
        session["system_suggestion"] = state["assistant_message"]["system_suggestion"]
    storage.save_session(session)
    return {"session": session}


def build_graph():
    graph = StateGraph(TurnState)
    graph.add_node("load_session", load_session)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("load_overview", load_overview)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("validate_citations", validate_citations)
    graph.add_node("save_session", save_session)
    graph.add_edge(START, "load_session")
    graph.add_edge("load_session", "rewrite_query")
    graph.add_conditional_edges("rewrite_query", route_by_scope, {"load_overview": "load_overview", "retrieve": "retrieve"})
    graph.add_edge("load_overview", "retrieve")
    graph.add_edge("retrieve", "generate_answer")
    graph.add_edge("generate_answer", "validate_citations")
    graph.add_edge("validate_citations", "save_session")
    graph.add_edge("save_session", END)
    return graph.compile()


TURN_GRAPH = build_graph()


def log_view(state: dict[str, Any]) -> dict:
    """The parts of the turn state written to the run log (no session copy, no prompts' hidden text)."""
    return {
        "retrieval_query": state.get("retrieval_query"),
        "scope": state.get("scope"),
        "retrieved": [{"chunk_id": h["chunk_id"], "page": h["page"], "page_label": h["page_label"],
                       "similarity": h["similarity"], "carried_over": h.get("carried_over", False), "text": h["text"]}
                      for h in state.get("retrieved", [])],
        "overview_ids": [o["overview_id"] for o in state.get("overview", [])],
        "raw_model_output": state.get("raw_answer"),
        "assistant_message": state.get("assistant_message"),
        "invalid_citations": state.get("invalid_citations", []),
        # one entry per evidence quote: did it occur in the cited passage? (ok / reason / similarity score)
        "quote_checks": state.get("quote_checks", []),
        "current_concept": state.get("current_concept"),
        "timings_ms": state.get("timings_ms", {}),
    }
