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
    assert "**Not suitable for my study**" in mine and "My own reason here" in mine and "Model reason" not in mine
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


def _rewrite_with(monkeypatch, language_request, session_language="中文（简体）", override=""):
    from app import graph
    from app.schemas import QueryRewrite
    monkeypatch.setattr(graph, "structured_call", lambda *a, **k: QueryRewrite(
        standalone_query="q", scope="local", current_concept="c", language_request=language_request))
    state = {"pipeline_version": "v1", "mode": "chat", "user_message": "m", "history": [],
             "session": {"language": session_language, "language_override": override},
             "language": override or session_language, "language_override": override, "timings_ms": {}}
    return graph.rewrite_query(state)


def test_in_chat_request_for_supported_language_switches_setting(monkeypatch):
    out = _rewrite_with(monkeypatch, "English")
    assert out["language_setting"] == "English" and out["language"] == "English" and out["language_override"] == ""
    assert _rewrite_with(monkeypatch, "traditional Chinese")["language_setting"] == "中文（繁體）"
    assert _rewrite_with(monkeypatch, "日语", session_language="English")["language_setting"] == "日本語"


def test_in_chat_request_for_unsupported_language_only_changes_answers(monkeypatch):
    out = _rewrite_with(monkeypatch, "Français")
    assert out["language"] == "Français" and out["language_override"] == "Français" and "language_setting" not in out
    back = _rewrite_with(monkeypatch, "default", override="Français")
    assert back["language"] == "中文（简体）" and back["language_override"] == ""
    none = _rewrite_with(monkeypatch, "")
    assert "language" not in none and "language_override" not in none   # writing in a language is not a request


def test_changing_language_setting_clears_chat_override(temp_store):
    from app import core
    session = core.create_session("p1", "Get a general overview of this paper", language="English")
    session["language_override"] = "日本語"
    temp_store.save_session(session)
    updated = core.update_session(session["session_id"], language="中文（简体）")
    assert updated["language"] == "中文（简体）" and updated["language_override"] == ""


def test_note_markdown_uses_interface_language_but_keeps_stored_values(temp_store):
    from app import core
    session = core.create_session("p1", "Explore potential use in my research", language="中文（简体）")
    session["note"] = {"selected_idea": "想法", "research_use": "", "adaptations_and_uncertainties": "", "next_actions": [],
                       "evidence": [{"point": "要点", "sources": [{"kind": "paper", "page": 3, "page_label": "3"}]}],
                       "learner_judgment": {"verdict": "Do not use", "rationale": "我的理由文字"},
                       "system_suggestion": None, "generated_at": "t", "edited_by_learner": False}
    temp_store.save_session(session)
    md = core.note_markdown(session["session_id"])
    assert md.startswith("# 研究应用笔记") and "**不适合我的研究**" in md and "探索在我研究中的潜在用途" in md
    assert "[PDF 第 3 页]" in md
    assert temp_store.load_session(session["session_id"])["note"]["learner_judgment"]["verdict"] == "Do not use"


def test_find_captions_takes_real_captions_only():
    from app.figures import find_captions
    raw = [{"page": 5, "page_label": "5", "text": "\n".join([
        "As shown in Figure 1, the tool has two panes.",          # running text: not a caption
        "Figure 1: BotDesigner main user interface. Right pane:",  # caption with separator: continues to a line end that is a full stop
        "the prompt template authoring area.",
        "Figure 2 shows the error browser.",                       # starts a line but continues in lower case
        "TABLE 2.4 Example words illustrating the vowels",         # title-style caption: one line only
        "Vowel height Vowel Description",                          # table header, not caption
        "Figure 1: duplicate label later in the paper.",
    ])}]
    caps = find_captions(raw)
    assert [(c["label"], c["caption"]) for c in caps] == [
        ("Figure 1", "Figure 1: BotDesigner main user interface. Right pane: the prompt template authoring area."),
        ("Table 2.4", "TABLE 2.4 Example words illustrating the vowels"),
    ]


def test_figure_quotes_count_only_from_the_caption():
    state = _state("v1", ["p1-fig3"])
    state["retrieved"] = [{"chunk_id": "p1-fig3", "kind": "figure", "page": 4, "page_label": "4", "similarity": 0.7,
                           "label": "Figure 3", "caption": "Figure 3: Participants' prompt edits over time.",
                           "text": "Figure 3 (PaperLens description of the image): a line chart rising steeply.\n"
                                   "Caption (authors' words): Figure 3: Participants' prompt edits over time."}]
    state["raw_answer"]["sections"] = []
    state["raw_answer"]["evidence_quotes"] = [
        {"chunk_id": "p1-fig3", "quote": "a line chart rising steeply"},            # generated description: rejected
        {"chunk_id": "p1-fig3", "quote": "Participants' prompt edits over time."},  # caption: accepted
    ]
    out = validate_citations(state)
    src = out["assistant_message"]["sources"][0]
    assert (src["kind"], src["label"]) == ("figure", "Figure 3")
    assert src["quotes"] == ["Participants' prompt edits over time."]
    assert [c["ok"] for c in out["quote_checks"]] == [False, True]
    assert out["assistant_message"]["has_verified_paper_source"] is False   # a description is not original text


def test_figures_are_marked_as_generated_for_the_model():
    from app.graph import format_passages
    text = format_passages([{"chunk_id": "x-fig1", "kind": "figure", "label": "Figure 1", "page": 2, "page_label": "2",
                             "text": "Figure 1 (PaperLens description of the image): a diagram."}])
    assert text.startswith('<figure id="x-fig1"') and "PaperLens-generated description" in text and "</figure>" in text


def test_note_markdown_labels_figure_sources(temp_store):
    from app import core
    session = core.create_session("p1", "Get a general overview of this paper")
    session["note"] = {"selected_idea": "i", "research_use": "", "adaptations_and_uncertainties": "", "next_actions": [],
                       "evidence": [{"point": "p", "sources": [{"kind": "figure", "label": "Figure 2", "page": 6}]}],
                       "learner_judgment": None, "system_suggestion": None, "generated_at": "t", "edited_by_learner": False}
    temp_store.save_session(session)
    assert "[Figure 2, PDF p. 6, PaperLens description of the image]" in core.note_markdown(session["session_id"])


def test_safe_text_repairs_windows_1252_quotes():
    from app.ingest import safe_text
    assert safe_text("a \x93lens\x94 or a \x93view\x94 \x96 separate") == "a “lens” or a “view” – separate"


def test_figures_named_by_page_or_number(monkeypatch):
    from app import retrieval

    class Fake:
        def get(self, **_):
            return {"ids": ["a-fig1", "a-figp"], "documents": ["d1", "d2"],
                    "metadatas": [{"page": 5, "label": "Figure 1", "kind": "figure", "caption": "c"},
                                  {"page": 3, "label": "Figure on p. 3", "kind": "figure", "caption": ""}]}
    monkeypatch.setattr(retrieval, "_collection", lambda: Fake())
    ids = lambda *t: [h["chunk_id"] for h in retrieval.figures_named_in("p", *t)]  # noqa: E731
    assert ids("What does Figure 1 show?") == ["a-fig1"]
    assert ids("What does the chart on page 3 show?") == ["a-figp"]
    assert ids("第3页的图表示什么？") == ["a-figp"]
    assert ids("What does page 3 say about dynamics?") == []        # page without a figure word: normal retrieval


# ---------------------------------------------------------------- hidden text (red-team fix, p7)

RED_TEAM_PAPERS = Path(__file__).resolve().parents[2] / "red_team" / "papers"


def test_hidden_text_is_found_and_removed_but_visible_text_is_kept():
    from app.hidden_text import find_hidden_text, strip_hidden
    from app.ingest import extract_pages
    pdf = (RED_TEAM_PAPERS / "promptscaffold-b1-hidden-claim.pdf").read_bytes()
    hidden = find_hidden_text(pdf)
    assert len(hidden) == 1 and "412 participants" in hidden[0]["text"]
    pages, report = strip_hidden(extract_pages(pdf)[0], hidden)
    text = " ".join(p["text"] for p in pages)
    assert report[0]["removed"] and "412 participants" not in text
    # the paper's own (visible) limitations stay
    assert "16 university" in text and "70-minute lab session" in text


def test_no_hidden_text_in_the_control_paper():
    from app.hidden_text import find_hidden_text
    assert find_hidden_text((RED_TEAM_PAPERS / "promptscaffold-control.pdf").read_bytes()) == []
