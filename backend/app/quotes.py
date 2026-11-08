"""Check that a quote the model copied from a passage really appears in that passage.

Used for sentence-level source highlighting: only quotes that match the stored passage text are sent to the
frontend, and the frontend highlights the matched span on the PDF page. The check compares word tokens
(case, punctuation, hyphenation and spacing are ignored) and tolerates small differences such as a
ligature the PDF extractor dropped ("felds" vs "fields").
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

MIN_WORDS = 4       # shorter "quotes" are too ambiguous to locate
MAX_WORDS = 90      # longer ones are not a sentence-level quote
FUZZY_THRESHOLD = 0.88

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> list[re.Match[str]]:
    return list(_TOKEN.finditer(unicodedata.normalize("NFKC", text)))


def _words(matches: list[re.Match[str]]) -> list[str]:
    return [m.group(0).casefold() for m in matches]


def match_quote(quote: str, passage: str) -> dict:
    """Return {ok, text, score, reason}. `text` is the matching span copied from the passage itself."""
    q_words = _words(_tokens(quote))
    if len(q_words) < MIN_WORDS:
        return {"ok": False, "text": None, "score": 0.0, "reason": "too_short"}
    if len(q_words) > MAX_WORDS:
        return {"ok": False, "text": None, "score": 0.0, "reason": "too_long"}
    p_matches = _tokens(passage)
    p_words = _words(p_matches)
    n = len(q_words)
    if n > len(p_words):
        return {"ok": False, "text": None, "score": 0.0, "reason": "not_found"}

    best_start, best_len, best_score = -1, n, 0.0
    for start in range(len(p_words) - n + 1):
        if p_words[start:start + n] == q_words:
            best_start, best_len, best_score = start, n, 1.0
            break
    if best_start < 0:
        # Fuzzy: compare the quote with windows of similar length (allowing a word more or less).
        for size in (n, n - 1, n + 1):
            if size < MIN_WORDS or size > len(p_words):
                continue
            for start in range(len(p_words) - size + 1):
                window = p_words[start:start + size]
                if window[0] != q_words[0] and window[-1] != q_words[-1]:
                    continue  # cheap filter: real matches share an edge word
                score = SequenceMatcher(None, " ".join(window), " ".join(q_words), autojunk=False).ratio()
                if score > best_score:
                    best_start, best_len, best_score = start, size, score
    if best_start < 0 or best_score < FUZZY_THRESHOLD:
        return {"ok": False, "text": None, "score": round(best_score, 3), "reason": "not_found"}

    normalized = unicodedata.normalize("NFKC", passage)
    first, last = p_matches[best_start], p_matches[best_start + best_len - 1]
    end = last.end()
    while end < len(normalized) and normalized[end] in ".!?;:)]}\"'”’" and end - last.end() < 3:
        end += 1  # keep closing punctuation/brackets, e.g. "[ahhhhhh]."
    return {"ok": True, "text": normalized[first.start():end], "score": round(best_score, 3), "reason": None}
