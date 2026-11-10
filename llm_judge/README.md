# llm_judge — "what PaperLens must do well"

This folder will hold the LLM-as-judge evaluation for Assignment 2, Step 2. Nothing here is generated
automatically; every file must come from real runs of the system and from your own labelling.

## Planned layout

| Path | Contents |
|---|---|
| `personas/` | Learner personas (who they are, what they want, how they behave). One file per persona. |
| `scenarios/` | Scenario files fed to `backend/scripts/run_conversation.py` (learner turns, paper, goal, context). |
| `conversations/` | Transcripts produced by the running system (`*.json`, exported with full run logs). |
| `conversations/v0/` | Transcripts from the ablated baseline (`--pipeline-version v0`), used as expected-fail cases. |
| `judge_prompts/` | Every version of every judge prompt, e.g. `criterion_a_v1.md`, `criterion_a_v2.md`. Never overwrite an old version. |
| `labels.csv` | One row per conversation × criterion: `conversation_file, criterion, human_label, judge_label_v1, judge_label_v2, notes`. Human labels are filled in by the student. |
| `results/` | Judge outputs per prompt version, agreement (percentage + Cohen's kappa) before/after revision, pass rates. |

## How conversations are produced

```bash
cd backend
.venv/Scripts/python scripts/run_conversation.py ../llm_judge/scenarios/<scenario>.json --out ../llm_judge/conversations
.venv/Scripts/python scripts/run_conversation.py ../llm_judge/scenarios/<scenario>.json --out ../llm_judge/conversations/v0 --pipeline-version v0
```

`run_conversation.py` calls the same functions in `backend/app/core.py` as the web UI, so every PaperLens
turn is produced by the running system. Each transcript contains the session, every learner and system
message, the retrieval query, retrieved chunk IDs/pages/text, model, prompt and pipeline version, timestamps
and errors.

About `v0`: it is a configuration of the same code with three safeguards switched off (history-aware query
rewriting, overview routing, citation validation). Describe it as an *ablated baseline*, not as a historical
build. Real earlier failures from development are also kept in `backend/data/logs/` and can be exported.

## Rules

- Do not edit transcripts by hand. If a run is broken, re-run it and keep both files.
- Keep failed and early runs; they are needed for judge calibration and before/after comparison.
- Human labels are yours; do not let a model fill `human_label`.
