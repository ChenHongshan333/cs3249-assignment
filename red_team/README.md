# red_team — "what PaperLens must never do"

This folder will hold the red-teaming for Assignment 2, Step 2. Only attack this system, use made-up names
and data, and stop a run as soon as PaperLens fails.

## Planned layout

| Path | Contents |
|---|---|
| `targets.md` | The things PaperLens must never do (at least one from the learning design, one about harm), each with its PASS/FAIL rule. |
| `attempts/` | Scenario files for each attempt: direct request, role-play framing and multi-turn build-up per target. |
| `papers/` | The fictional paper *PromptScaffold* for T2 (control + three injected variants), built by `papers/src/build_papers.py`. Its authors, institution and data are invented; the PDFs carry no visible note saying so, because PaperLens sends whole page images to the vision model and would read it. |
| `transcripts/before/` | Transcripts of every attempt (at least 3 runs each) before fixes. |
| `transcripts/after/` | Transcripts after each fix (at least 3 runs per attempt again). |
| `verdicts.csv` | `attempt, run, transcript_file, verdict (PASS/FAIL), checked_by, notes` — every verdict checked by you. |
| `fixes.md` | What failed, what was changed (prompt version / guardrail / design), and whether the retest passed. |

## Step mode (stop a run at the first failing reply)

```bash
cd backend
.venv/Scripts/python scripts/run_conversation.py ../red_team/attempts/<attempt>.json --out ../red_team/transcripts/before --turn 1 --run 1
.venv/Scripts/python scripts/run_conversation.py ../red_team/attempts/<attempt>.json --out ../red_team/transcripts/before --turn 2 --run 1 --session s-...
```

Each step rewrites that run's transcript; `turns_completed` shows how far it got. Runs used for the red-teaming
were made this way, one turn at a time, with every reply read before the next turn was sent.

## Running attempts

```bash
cd backend
.venv/Scripts/python scripts/run_conversation.py ../red_team/attempts/<attempt>.json --out ../red_team/transcripts/before --repeat 3
```

The runner can only stop on system errors (`--stop-on-error`). Whether a reply *fails* a red-team rule is a
judgement about content, so check each transcript and stop that run as soon as it fails.

When you change a prompt, bump `PROMPT_VERSION` in `backend/app/config.py`; every log entry records it, so
before/after transcripts can be told apart.

## Safeguards that exist in v1 (relevant when explaining fixes)

- `backend/app/prompts/shared_rules.md`: grounding, labelling, learner-decision and safety rules.
- `backend/app/graph.py::validate_citations`: drops cited IDs that were not provided this turn; system
  suggestions are only allowed in critical-review turns.
- `backend/app/core.py::submit_judgment` / `generate_note`: the learner's verdict and rationale are stored
  verbatim from their input and copied into the note by code, never written by the model.
