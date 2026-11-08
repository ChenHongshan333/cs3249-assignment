"""Checks that need no API key: text cleaning, chunking, the no-text-layer guard and citation validation."""
from pathlib import Path

import pytest

from app import ingest
from app.graph import validate_citations


def make_pages(n=4):
    pages = []
    for i in range(1, n + 1):
        body = (f"Journal of Testing Studies\nThis is the body of page {i}. It discusses flow chan-\nnels and "
                "player skill in some detail.\nA second line continues the same sentence and adds more words. " * 5)
        pages.append({"page": i, "page_label": str(100 + i), "text": f"{body}\n{100 + i}"})
    return pages


def test_clean_removes_repeated_header_and_page_numbers():
    cleaned = ingest.clean_pages(make_pages())
    for page in cleaned:
        assert not page["text"].startswith("Journal of Testing Studies")
        assert not page["text"].rstrip().endswith(page["page_label"])
        assert "channels" in page["text"]          # hyphenated word re-joined
        assert "\n" not in page["text"]            # broken lines joined


def test_chunks_keep_page_and_stable_ids():
    pages = ingest.clean_pages(make_pages())
    chunks = ingest.chunk_pages("abcdef1234567890", pages)
    assert chunks, "expected chunks"
    for c in chunks:
        assert c["metadata"]["paper_id"] == "abcdef1234567890"
        assert c["chunk_id"].startswith(f"abcdef12-p{c['metadata']['page']:03d}-c")
        assert c["metadata"]["page_label"] == str(100 + c["metadata"]["page"])
    assert chunks == ingest.chunk_pages("abcdef1234567890", pages)  # deterministic


def test_text_layer_guard_rejects_empty_pages():
    with pytest.raises(ingest.IngestError, match="scanned"):
        ingest.check_text_layer([{"page": i, "page_label": str(i), "text": ""} for i in range(1, 6)])


SCANNED = [Path(r"D:\NUS CS\Y3 S1\SC1101E\readings\West&Zimmerman_DoingGender.pdf"),
           Path(r"D:\NUS CS\Y3 S1\NM4260\critique2 readings\Flow in games (and everything else).pdf")]


@pytest.mark.parametrize("path", SCANNED, ids=["doing_gender", "flow_in_games"])
def test_real_scanned_pdfs_are_rejected(path):
    if not path.exists():
        pytest.skip("local scanned PDF not available")
    pages, _ = ingest.extract_pages(path.read_bytes())
    with pytest.raises(ingest.IngestError):
        ingest.check_text_layer(ingest.clean_pages(pages))


def _state(version, cited):
    return {
        "pipeline_version": version, "mode": "chat", "retrieval_query": "q",
        "retrieved": [{"chunk_id": "p1-c0", "page": 3, "page_label": "45", "text": "real text", "similarity": 0.8}],
        "overview": [{"overview_id": "ov-1", "pages": [1, 2], "summary": "generated", "key_points": []}],
        "raw_answer": {"short_answer": "a", "short_answer_chunk_ids": cited, "evidence_status": "sufficient",
                       "sections": [{"title": "t", "kind": "paper", "text": "x", "chunk_ids": ["p1-c0", "fake-9"]}],
                       "system_suggestion": {"verdict": "Use as proposed", "reason": "r"}},
    }


def test_validation_drops_invented_ids_and_uses_real_metadata():
    out = validate_citations(_state("v1", ["p1-c0", "ov-1", "made-up"]))
    msg = out["assistant_message"]
    assert msg["short_answer_refs"] == ["p1-c0", "ov-1"]
    assert msg["sections"][0]["refs"] == ["p1-c0"]
    assert set(out["invalid_citations"]) == {"made-up", "fake-9"}
    paper_src = next(s for s in msg["sources"] if s["ref_id"] == "p1-c0")
    assert (paper_src["page"], paper_src["page_label"], paper_src["text"]) == (3, "45", "real text")
    assert next(s for s in msg["sources"] if s["ref_id"] == "ov-1")["kind"] == "overview"
    assert msg["system_suggestion"] is None          # suggestions only allowed in critical review


def test_v0_baseline_keeps_unverified_ids():
    msg = validate_citations(_state("v0", ["made-up"]))["assistant_message"]
    assert msg["short_answer_refs"] == ["made-up"]
    assert next(s for s in msg["sources"] if s["ref_id"] == "made-up")["verified"] is False


def test_safe_text_handles_surrogates_and_ligatures():
    # Found with a real paper ("Why Johnny Can't Prompt"): pypdf returned a lone surrogate
    # and json.dump failed during indexing.
    from app.ingest import safe_text

    joined = safe_text("x = \ud835\udc65 and lone \ud835 half")
    joined.encode("utf-8")  # must not raise
    assert "x = x and lone  half" == joined
    assert safe_text("\ufb01nd the \ufb02ow") == "find the flow"


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    from dataclasses import replace

    from app import config, storage
    monkeypatch.setattr(storage, "settings", replace(config.settings, data_dir=tmp_path))
    storage.save_paper_meta("p1", {"paper_id": "p1", "title": "Test paper", "status": "ready"})
    return storage


def test_soft_delete_hides_session_but_keeps_file_and_log(temp_store):
    from app import core
    session = core.create_session("p1", "Get a general overview of this paper")
    sid = session["session_id"]
    assert [s["session_id"] for s in core.list_visible_sessions()] == [sid]
    core.delete_session(sid)
    assert core.list_visible_sessions() == []
    assert temp_store.load_session(sid)["deleted_at"]          # file kept
    events = [e["event"] for e in temp_store.read_log(sid)]
    assert events == ["session_created", "session_deleted"]   # log kept, deletion recorded
    with pytest.raises(core.UserInputError):
        core.delete_session(sid)


def test_note_markdown_keeps_learner_decision_separate_from_suggestion(temp_store):
    from app import core
    session = core.create_session("p1", "Explore potential use in my research", "my study")
    session["note"] = {
        "selected_idea": "Idea X", "research_use": "Use", "adaptations_and_uncertainties": "Unsure",
        "next_actions": ["Pilot it", " "],
        "evidence": [{"point": "Claim", "sources": [{"kind": "paper", "page": 3, "page_label": "12"},
                                                     {"kind": "overview", "page": 1, "pages": [1, 2, 3]}]}],
        "learner_judgment": {"verdict": "Do not use", "rationale": "My own reason here"},
        "system_suggestion": {"verdict": "Use with adaptations", "reason": "Model reason"},
        "generated_at": "t", "edited_by_learner": True,
    }
    temp_store.save_session(session)
    md = core.note_markdown(session["session_id"])
    mine, theirs = md.split("## PaperLens suggestion (not my decision)")
    assert "**Do not use**" in mine and "My own reason here" in mine and "Model reason" not in mine
    assert "Use with adaptations: Model reason" in theirs
    assert "[PDF p. 3 (printed p. 12); PDF pp. 1-3, PaperLens summary (not the authors' words)]" in md
    assert "- Pilot it\n" in md and "edited by the learner" in md


PASSAGE = ("Our participant pool, skewed towards professionals and graduate students in STEM-related felds, "
           "is not representative of the population at large. Future work should recruit more broadly.")


def test_quote_match_exact_and_tolerant():
    from app.quotes import match_quote
    exact = match_quote("is not representative of the population at large.", PASSAGE)
    assert exact["ok"] and exact["score"] == 1.0 and exact["text"] == "is not representative of the population at large."
    # case, punctuation and the hyphen differ; the model "fixed" the dropped ligature (felds -> fields)
    tolerant = match_quote("Our participant pool skewed towards professionals and graduate students in STEM related fields",
                           PASSAGE)
    assert tolerant["ok"] and tolerant["text"].startswith("Our participant pool,") and tolerant["text"].endswith("felds")


def test_quote_match_rejects_paraphrase_and_fragments():
    from app.quotes import match_quote
    assert not match_quote("The sample was mostly engineers and was not representative of everyone.", PASSAGE)["ok"]
    assert match_quote("population at large", PASSAGE)["reason"] == "too_short"


def test_validation_attaches_only_verified_quotes():
    state = _state("v1", ["p1-c0"])
    state["retrieved"][0]["text"] = PASSAGE
    state["raw_answer"]["evidence_quotes"] = [
        {"chunk_id": "p1-c0", "quote": "Future work should recruit more broadly."},
        {"chunk_id": "p1-c0", "quote": "The authors recruited only undergraduates from one class."},   # invented
        {"chunk_id": "ov-1", "quote": "generated summary text that is not a passage"},
        {"chunk_id": "made-up", "quote": "some quote from a passage that was never provided"},
    ]
    out = validate_citations(state)
    source = next(s for s in out["assistant_message"]["sources"] if s["ref_id"] == "p1-c0")
    assert source["quotes"] == ["Future work should recruit more broadly."]
    assert [c["reason"] for c in out["quote_checks"]] == [None, "not_found", "overview_id", "unknown_id"]


def test_v0_baseline_has_no_quote_highlighting():
    state = _state("v0", ["p1-c0"])
    state["raw_answer"]["evidence_quotes"] = [{"chunk_id": "p1-c0", "quote": "real text"}]
    out = validate_citations(state)
    assert all("quotes" not in s for s in out["assistant_message"]["sources"]) and out["quote_checks"] == []
