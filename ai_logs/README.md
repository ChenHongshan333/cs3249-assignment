# ai_logs: records of AI tool use for this assignment

This folder holds the full records of every AI tool used for Assignment 2.

| Tool | What it was used for | Record |
|---|---|---|
| Claude Code (VS Code extension), session 01 | Part 1: planning and building the A2 system (backend, frontend, docs, figures), and drafting the Part 1 report section | [claude-code-session-01.md](claude-code-session-01.md) is the English account, with every user message translated. [claude-code-session-01-transcript.md](claude-code-session-01-transcript.md) is the verbatim export. |
| _add later sessions and other tools_ | | |

`export_transcript.py` turns a Claude Code session file (`~/.claude/projects/<project>/<session>.jsonl`) into Markdown:

```
python export_transcript.py <session.jsonl> <out.md>
```

Tools without chat history (for example inline code completion) must be named in the main README instead.
