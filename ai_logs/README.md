# ai_logs: records of AI tool use for this assignment

This folder holds the full records of every AI tool used for Assignment 2.

| Tool | What it was used for | Record |
|---|---|---|
| Claude Code (VS Code extension), session 01 | Part 1: planning and building the A2 system (backend, frontend, docs, figures), and drafting the Part 1 report section | [claude-code-session-01.md](claude-code-session-01.md) is the English account, with every user message translated. [claude-code-session-01-transcript.md](claude-code-session-01-transcript.md) is the verbatim export. |
| Claude Code (VS Code extension), session 02 | Part 2A: LLM-as-judge (personas, situation cards, simulated conversations, judge prompts v1–v3, agreement with my labels), and drafting the Part 2 report section and appendix | [claude-code-session-02.md](claude-code-session-02.md) is the English account, with every user message translated. [claude-code-session-02-transcript.md](claude-code-session-02-transcript.md) is the verbatim export. |
| Claude Code (VS Code extension), session 03 | Part 2B: red-teaming (targets, PASS/FAIL rules, two rounds of attacks on the running system, the hidden-text fix and prompt p7, the T2 retest), and drafting Sections 2.1 and 2.3 and Appendix B of the report | [claude-code-session-03.md](claude-code-session-03.md) is the English account, with every user message translated. [claude-code-session-03-transcript.md](claude-code-session-03-transcript.md) is the verbatim export. |
| _add later sessions and other tools_ | | |

`export_transcript.py` turns a Claude Code session file (`~/.claude/projects/<project>/<session>.jsonl`) into Markdown:

```
python export_transcript.py <session.jsonl> <out.md>
```

Tools without chat history (for example inline code completion) must be named in the main README instead.
