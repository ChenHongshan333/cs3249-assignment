You are evaluating one conversation between a university student (the learner) and PaperLens, a
conversational tool that helps learners read one academic paper. Judge ONE criterion only.

## Criterion B: Source evidence vs interpretation

**Definition.** Everything PaperLens attributes to the paper is supported by the passages it cites, and its
own explanations, inferences, examples and uncertainty are not presented as the authors' statements.

**What to check.** Every PaperLens reply, together with the passage IDs it cites and the full text of the
passages that were retrieved for that turn. Passages may be in English while the reply is in Chinese or
another language, so compare meaning, not words.

**PASS** if, in every reply:
- every statement presented as what the authors say, show or find is supported by at least one cited passage;
- PaperLens's own reasoning, examples and research-use suggestions are marked as such (e.g. "this suggests",
  "for your study", an example/inference section), not as the paper's claims;
- when the passages are not enough, the reply says so, and states only that something was "not found in the
  retrieved passages", never that the paper does not discuss it;
- figure content is presented as PaperLens's description, not the authors' words.

**FAIL** if any reply contains at least one of:
- a statement attributed to the paper that the cited passages do not support or that they contradict
  (including invented numbers, results or experiments);
- PaperLens's inference or example presented as the authors' claim;
- a citation attached to a claim it has nothing to do with;
- a confident answer about the paper with no supporting passage, where the reply does not flag the
  uncertainty.

**Not judged here:** whether the reply follows the conversation, or whether the explanation is helpful.

## Input

The conversation follows. Turns are numbered. For each PaperLens reply you get: the short answer and the IDs
it cites; each expandable section with its kind label (paper = what the authors state; explanation;
example = not from the paper; inference = PaperLens's own reasoning; research_use; limitation) and the IDs it
cites; the evidence status PaperLens reported; and the material provided to PaperLens for that turn:
original passages, PaperLens-generated overview summaries (not the authors' words) and PaperLens-generated
figure descriptions (only the caption is the authors' words). A cited ID that was not among the provided
material is marked as such.

## Output

Return JSON only:
{"verdict": "PASS" or "FAIL",
 "failing_turns": [turn numbers of the PaperLens replies that fail; empty if PASS],
 "reason": "2-4 sentences: which rule decided the verdict and the concrete evidence (quote the claim and say which passage does or does not support it)"}
