"""Export a Claude Code session .jsonl to Markdown.

usage: python export.py <session.jsonl> <out.md> [--users-only]
Keeps user and assistant text verbatim; tool calls become one-line entries; tool results are truncated.
"""
import json
import re
import sys

src, out = sys.argv[1], sys.argv[2]
users_only = "--users-only" in sys.argv
KEY = re.compile(r"sk-(or-)?[A-Za-z0-9_-]{20,}")
RESULT_MAX = 600


def redact(s: str) -> str:
    return KEY.sub("[REDACTED-KEY]", s)


def tool_line(block: dict) -> str:
    name = block.get("name", "?")
    inp = block.get("input", {}) or {}
    detail = inp.get("description") or inp.get("file_path") or inp.get("pattern") or inp.get("url") or ""
    if not detail:
        for k in ("command", "query", "prompt", "action", "text"):
            if k in inp:
                detail = str(inp[k])
                break
    if not detail:
        detail = json.dumps(inp, ensure_ascii=False)
    detail = " ".join(str(detail).split())
    if len(detail) > 300:
        detail = detail[:300] + " …"
    return f"- **Tool call** `{name}`: {detail}"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts)


lines = []
n_user = 0
with open(src, encoding="utf-8") as f:
    for raw in f:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if ev.get("isSidechain"):
            continue
        t = ev.get("type")
        ts = ev.get("timestamp", "")[:19].replace("T", " ")
        if t == "summary" or ev.get("isCompactSummary"):
            body = text_of(ev.get("message", {}).get("content", "")) or ev.get("summary", "")
            lines.append(f"\n---\n\n### [{ts}] Context compaction (automatic summary inserted by Claude Code)\n\n<details><summary>Summary text</summary>\n\n{redact(body)}\n\n</details>\n")
            continue
        msg = ev.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if t == "user":
            if isinstance(content, list) and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                if users_only:
                    continue
                for b in content:
                    r = b.get("content")
                    r = text_of(r) if not isinstance(r, str) else r
                    r = " ".join(redact(r or "").split())
                    if len(r) > RESULT_MAX:
                        r = r[:RESULT_MAX] + " … [truncated]"
                    lines.append(f"  - *Result*{' (error)' if b.get('is_error') else ''}: {r}")
                continue
            body = text_of(content)
            # drop harness-injected reminders and command wrappers that are not the user's words
            body = re.sub(r"<system-reminder>.*?</system-reminder>", "", body, flags=re.S)
            body = re.sub(r"<ide_(opened_file|selection)>.*?</ide_\1>", "", body, flags=re.S)
            body = body.strip()
            if not body or body.startswith("<local-command") or body.startswith("<command-"):
                continue
            n_user += 1
            lines.append(f"\n---\n\n### [{ts}] User (message {n_user})\n\n{redact(body)}\n")
        elif t == "assistant" and not users_only:
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    lines.append(f"\n**Claude** [{ts}]:\n\n{redact(b['text'].strip())}\n")
                elif b.get("type") == "tool_use":
                    lines.append(redact(tool_line(b)))

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("user messages:", n_user, "lines:", len(lines))
