"""Structured outputs the LLM must return. Field descriptions are sent to the model as part of the tool schema."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["Use as proposed", "Use with adaptations", "Do not use", "Need more evidence"]
VERDICTS: tuple[str, ...] = ("Use as proposed", "Use with adaptations", "Do not use", "Need more evidence")


class QueryRewrite(BaseModel):
    """Turns the learner's latest message into a self-contained retrieval query."""
    standalone_query: str = Field(description="A self-contained search query for the paper, resolving pronouns and references "
                                              "('that', 'it', 'my study') using the conversation and the learner's research context.")
    scope: Literal["local", "overview"] = Field(description="'overview' if the learner asks about the whole paper "
                                                            "(main argument, overall summary, structure); otherwise 'local'.")
    current_concept: str = Field(default="", description="The paper concept or method currently being discussed, in a few words. Empty if none.")
    language_request: str = Field(default="", description="Only if the latest message EXPLICITLY asks PaperLens to answer in a "
                                                          "particular language from now on (e.g. 'please reply in English', '请用中文回答'): "
                                                          "that language's name, e.g. 'English', '中文（简体）', '日本語'. 'default' if they ask "
                                                          "to go back to their usual language. Otherwise empty. Merely writing in a "
                                                          "language is NOT a request.")


class AnswerSection(BaseModel):
    title: str = Field(description="Short label for this expandable section, specific to the question (e.g. 'How flow channels are defined').")
    kind: Literal["paper", "explanation", "example", "inference", "research_use", "limitation"] = Field(
        description="paper = what the authors state; explanation = clarifying the paper's idea in simpler terms; "
                    "example = an illustrative example NOT from the paper; inference = PaperLens's own reasoning beyond the text; "
                    "research_use = how it might apply to the learner's research; limitation = limits, assumptions or unknowns.")
    text: str = Field(description="Section content, 1-4 sentences.")
    chunk_ids: list[str] = Field(default_factory=list, description="IDs of the provided passages that support this section. "
                                                                   "Only IDs listed in the provided passages. Empty for pure examples.")


class EvidenceQuote(BaseModel):
    chunk_id: str = Field(description="ID of the provided original passage the quote is copied from (a passage ID, never an overview ID).")
    quote: str = Field(description="One or two consecutive sentences copied word for word from that passage, that best support "
                                   "what you said (about 8-40 words). Copy exactly, including the authors' spelling; do not "
                                   "paraphrase, translate, shorten in the middle or join separate sentences.")


class SystemSuggestion(BaseModel):
    verdict: Verdict = Field(description="PaperLens's own suggestion; the learner makes the final decision.")
    reason: str = Field(description="One or two sentences explaining the suggestion, grounded in the passages.")


class AnswerPayload(BaseModel):
    short_answer: str = Field(description="A short, direct answer (1-3 sentences) to the learner's latest message.")
    short_answer_chunk_ids: list[str] = Field(default_factory=list, description="IDs of the provided passages that support the short answer.")
    sections: list[AnswerSection] = Field(default_factory=list, description="0-4 optional expandable sections relevant to THIS question. "
                                                                            "Do not add sections just to fill a template.")
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list, description="For EACH original passage ID you cited "
                                                 "anywhere in this answer, one verbatim quote from that passage. Not for overview IDs.")
    evidence_status: Literal["sufficient", "partial", "insufficient"] = Field(
        description="Whether the provided passages are enough to support the answer.")
    clarifying_question: str = Field(default="", description="A brief clarifying question for the learner, only if essential information is missing.")
    current_concept: str = Field(default="", description="The paper concept being discussed after this turn, in a few words.")
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Up to 3 short follow-up questions the learner might ask next.")
    system_suggestion: SystemSuggestion | None = Field(default=None, description="Only for critical review: PaperLens's suggested verdict. Otherwise null.")


class OverviewSummary(BaseModel):
    summary: str = Field(description="3-5 sentence summary of what these pages of the paper say.")
    key_points: list[str] = Field(default_factory=list, description="Up to 4 key points from these pages.")


class NoteEvidence(BaseModel):
    point: str = Field(description="One piece of evidence from the paper relevant to the selected idea.")
    chunk_ids: list[str] = Field(default_factory=list, description="IDs of the provided passages that support this point.")


class NoteDraft(BaseModel):
    selected_idea: str = Field(description="The concept or method from the paper the learner is considering, as discussed in this session.")
    evidence: list[NoteEvidence] = Field(default_factory=list, description="2-4 pieces of paper evidence discussed in the session.")
    research_use: str = Field(description="The learner's research context and how the idea could be used there, based on the conversation.")
    adaptations_and_uncertainties: str = Field(description="Adaptations needed, limitations and open uncertainties raised in the session.")
    next_actions: list[str] = Field(default_factory=list, description="2-3 concrete next steps for the learner.")
