# Choosing the judge set-up for v3 (exploratory runs, 2026-11-09)

After judge prompt v2 (rules made explicit) barely changed agreement (A 80% -> 80%, B 35% -> 40%, Gemini 3
Flash), the v2 reasons showed the judge restating a FAIL rule and still passing the conversation (e.g. C06:
"it explicitly states ... that the paper does not discuss it ... adhering to the requirement"), judging a
judgment-feedback turn it should ignore (C14), and missing a reversed paraphrase (C13). Its outputs were
about 100 tokens with no reasoning. Prompt v3 therefore keeps the v2 rules unchanged and only requires the
judge to write out the judged turns and one check per statement before the verdict.

Before the full v3 run, the v3 criterion-B prompt was tried on a few conversations. These outputs were printed
in the Claude Code session only (see ai_logs); they are not in labels.csv.

| # | Judge model | Setting | Conversations | Outcome | Output tokens per call |
|---|---|---|---|---|---|
| 1 | google/gemini-3-flash-preview | v3, reasoning effort "medium" | C06 | FAIL, turn 5 (matches student) | ~64,300 (62,900 reasoning) |
| 2 | google/gemini-3-flash-preview | v3, no reasoning | C06, C13 | PASS, PASS (student: FAIL, FAIL) | 700-1,000 |
| 3 | google/gemini-3-flash-preview | v3, reasoning effort "low" | C06, C13 | PASS, PASS; no reasoning tokens produced | 1,300-1,700 |
| 4 | google/gemini-3-flash-preview | v3, reasoning max_tokens 8000 | C06, C13, C07 | C06 FAIL (budget ignored, ~62,900 reasoning tokens); C13, C07 PASS with 0 reasoning tokens | 1,100-64,300 |
| 5 | anthropic/claude-sonnet-5.5 | v3, no reasoning | C06, C13, C07 | FAIL, FAIL, FAIL (student: FAIL, FAIL, PASS) | 3,200-5,500 |

Decision (student): run v3 for both criteria with anthropic/claude-sonnet-5.5, no reasoning. Note for the
report: v2 -> v3 changes two things at once, the output format (written-out checks) and the judge model.
Gemini with reasoning was rejected because reasoning use was unstable (0 or ~63k tokens on similar inputs)
and the cost unpredictable.
