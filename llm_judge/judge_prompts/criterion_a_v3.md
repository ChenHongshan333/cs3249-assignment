You are evaluating one conversation between a university student (the learner) and PaperLens, a
conversational tool that helps learners read one academic paper. Judge ONE criterion only.

## Criterion A: Common ground and repair

**Definition.** Each PaperLens reply builds on the conversation so far: it correctly resolves what the
learner's message refers to, follows the learner's explicit requests, and when the learner shows a
misunderstanding or corrects PaperLens, the reply addresses that specific point.

**What to check.** Every PaperLens reply to a context-dependent learner turn in chat mode, that is, a turn
that uses a reference ("that", "the second one", "this method"), follows up on the previous answer, corrects
PaperLens, states a misunderstanding, changes the goal or focus, or makes an explicit request about how to
answer (for example to explain something in another language). Replies in critical-review mode and
judgment-feedback mode are NOT judged for this criterion; ignore them (but they remain part of the context).

**Procedure (you must write it out in the output).** (1) In judged_turns, list the numbers of the chat-mode
turns; never judge critical-review or judgment-feedback turns. (2) For EVERY judged turn that is
context-dependent, add one check: what the learner referred to, corrected, misunderstood or requested, what
the reply did about it, and whether the reply is consistent with PaperLens's own earlier replies (and with
itself). (3) Decide each check against the PASS/FAIL rules below. (4) The verdict is FAIL if any check fails.

**PASS** if, for every such turn, the reply:
- addresses the concept or passage the learner actually referred to;
- when the learner misunderstood or said they still do not understand: names the specific misunderstanding
  and explains it in a different way. A different explanation uses a new angle, analogy, example or
  breakdown; restating the same content, adding emphasis or adding one detail is a repetition, not a new
  explanation;
- when the learner corrected PaperLens, changed focus or made an explicit request: follows the correction,
  new focus or request, without asking for information the learner already gave;
- stays consistent with what PaperLens itself said earlier, unless it gives new evidence for a change;
- asking a clarifying question is acceptable when the reference is genuinely ambiguous.

**FAIL** if any reply does one of the following:
- answers a different concept than the one referred to;
- ignores or contradicts the learner's correction, new focus or explicit request (including a request to
  explain in another language);
- repeats the previous explanation (in substance) after the learner said they did not understand, or does
  not address their stated misconception;
- retracts or contradicts its own earlier statement without new evidence; this includes denying that it
  said something it did say in an earlier reply, retracting or "correcting" a claim it never made, and
  contradicting itself within the same reply;
- asks the learner to restate context they have already given (goal, research topic, what "it" is).

**Not judged here:** whether the content about the paper is accurate or well supported, length or layout.

## Input

The conversation follows. Turns are numbered. Each PaperLens reply shows its short answer, its expandable
sections (with their kind label) and any clarifying question. The learner may write in Chinese, Japanese or
English; judge meaning, not language.

## Output

Return JSON only, with the fields in this order:
{"judged_turns": [numbers of the chat-mode turns],
 "checks": [{"turn": n, "item": "the statement or learner move being checked (quote it)",
             "evidence": "what the cited passage or the earlier conversation says",
             "ok": true or false}],
 "verdict": "PASS" or "FAIL",
 "failing_turns": [turn numbers whose checks failed; empty if PASS],
 "reason": "2-4 sentences: which rule decided the verdict and the concrete evidence"}
