"""Agreement between the student's labels and the judge, pass rates, and pages for screenshots.

    backend/.venv/Scripts/python llm_judge/scripts/agreement.py --merge   # copy judge verdicts into labels.csv
    backend/.venv/Scripts/python llm_judge/scripts/agreement.py           # compute and write the reports

--merge only fills judge_label_<version> columns from results/judge_<criterion>_<version>.jsonl; it never
touches human_label or notes. The report step writes:
    results/agreement.md, results/agreement.html   percentage agreement, Cohen's kappa, confusion matrices,
                                                   disagreements, pass rates (per criterion, per judge version)
    results/judge_<version>.html                   the judge's verdicts and reasons for every conversation
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from pathlib import Path

LLM_JUDGE = Path(__file__).resolve().parent.parent
RESULTS = LLM_JUDGE / "results"
LABELS = LLM_JUDGE / "labels.csv"
CRITERIA = {"A": "Common ground and repair", "B": "Source evidence vs interpretation"}


def read_labels() -> tuple[list[str], list[dict]]:
    with LABELS.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def judge_files() -> dict[tuple[str, str], Path]:
    out = {}
    for p in RESULTS.glob("judge_*_v*.jsonl"):
        m = re.fullmatch(r"judge_([AB])_(v\d+)", p.stem)  # skips archived files with a timestamp suffix
        if m:
            out[(m.group(1), m.group(2))] = p
    return out


def judge_records(path: Path) -> dict[str, dict]:
    return {r["conv_id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}


def versions() -> list[str]:
    return sorted({v for _, v in judge_files()}, key=lambda v: int(v[1:]))


def merge() -> None:
    fields, rows = read_labels()
    for (crit, ver), path in judge_files().items():
        col = f"judge_label_{ver}"
        if col not in fields:
            fields.insert(fields.index("notes"), col)
        recs = judge_records(path)
        for row in rows:
            if row["criterion"] == crit and row["conv_id"] in recs:
                row[col] = recs[row["conv_id"]].get("verdict") or "ERROR"
    with LABELS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Merged judge verdicts into {LABELS}")


def kappa(pairs: list[tuple[str, str]]) -> tuple[float, float | None]:
    n = len(pairs)
    if n == 0:
        return 0.0, None
    po = sum(h == j for h, j in pairs) / n
    ph = sum(h == "PASS" for h, _ in pairs) / n
    pj = sum(j == "PASS" for _, j in pairs) / n
    pe = ph * pj + (1 - ph) * (1 - pj)
    return po, (None if pe == 1 else (po - pe) / (1 - pe))


def pipeline_of() -> dict[str, str]:
    with (LLM_JUDGE / "conversations" / "index.csv").open(encoding="utf-8") as f:
        return {r["conv_id"]: r["pipeline_version"] for r in csv.DictReader(f) if r["conv_id"]}


def human(r: dict) -> str:
    return r["human_label"].strip().upper()


def human_rev(r: dict) -> str:
    return (r.get("human_label_revised") or r["human_label"]).strip().upper()


def report() -> None:
    _, rows = read_labels()
    pipe = pipeline_of()
    vers = versions()
    recs = {(c, v): judge_records(p) for (c, v), p in judge_files().items()}
    unlabeled = [f"{r['conv_id']}/{r['criterion']}" for r in rows if r["human_label"].strip().upper() not in ("PASS", "FAIL")]
    md = ["# LLM judge: agreement and pass rates", ""]
    if unlabeled:
        md += [f"**Warning:** {len(unlabeled)} rows have no human label yet: {', '.join(unlabeled)}", ""]

    md += ["## Agreement between the student's labels and the judge", "",
           "Human labels: 'original' = as first labelled (blind); 'revised' = after the student revised a label "
           "on reading the judge disagreements (column human_label_revised; unchanged rows keep the original).", "",
           "| Criterion | Judge prompt | Human labels | n | Agreement | Cohen's kappa | Human PASS / judge PASS | Human PASS / judge FAIL | Human FAIL / judge PASS | Human FAIL / judge FAIL |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    disagreements = []
    revised_any = any(r.get("human_label_revised", "").strip() for r in rows)
    label_sets = [("original", human)] + ([("revised", human_rev)] if revised_any else [])
    for crit in CRITERIA:
        for ver in vers:
          for set_name, hfun in label_sets:
            pairs, ids = [], []
            for r in rows:
                h, j = hfun(r), r.get(f"judge_label_{ver}", "").strip().upper()
                if r["criterion"] == crit and h in ("PASS", "FAIL") and j in ("PASS", "FAIL"):
                    pairs.append((h, j))
                    ids.append(r["conv_id"])
                    if h != j and set_name == label_sets[-1][0]:
                        rec = recs.get((crit, ver), {}).get(r["conv_id"], {})
                        disagreements.append((crit, ver, r["conv_id"], h, j, rec.get("failing_turns", []),
                                              rec.get("reason", ""), r.get("notes", "")))
            if not pairs:
                continue
            po, k = kappa(pairs)
            cm = {(a, b): sum(1 for h, j in pairs if (h, j) == (a, b)) for a in ("PASS", "FAIL") for b in ("PASS", "FAIL")}
            md.append(f"| {crit}: {CRITERIA[crit]} | {ver} | {set_name} | {len(pairs)} | {po:.0%} | "
                      f"{'n/a (one class only)' if k is None else f'{k:.2f}'} | {cm['PASS', 'PASS']} | "
                      f"{cm['PASS', 'FAIL']} | {cm['FAIL', 'PASS']} | {cm['FAIL', 'FAIL']} |")

    md += ["", "## Pass rates", "",
           "Final system = pipeline v1 (current prompts); v0 = ablated baseline (expected-fail conversations).", "",
           "| Criterion | Conversations | n | Human (original): PASS | Human (revised): PASS | " + " | ".join(f"Judge {v}: PASS" for v in vers) + " |",
           "|---|---|---|---|---|" + "---|" * len(vers)]
    for crit in CRITERIA:
        for group in ("v1", "v0"):
            sub = [r for r in rows if r["criterion"] == crit and pipe.get(r["conv_id"]) == group]
            if not sub:
                continue

            def rate(col):
                vals = [human(r) if col == "original" else human_rev(r) if col == "revised" else r.get(col, "").strip().upper() for r in sub]
                vals = [v for v in vals if v in ("PASS", "FAIL")]
                return f"{sum(v == 'PASS' for v in vals)}/{len(vals)} ({sum(v == 'PASS' for v in vals) / len(vals):.0%})" if vals else "-"
            label = "final system (v1)" if group == "v1" else "ablated baseline (v0)"
            md.append(f"| {crit} | {label} | {len(sub)} | {rate('original')} | {rate('revised')} | "
                      + " | ".join(rate(f"judge_label_{v}") for v in vers) + " |")

    md += ["", "## Disagreements (with the latest human labels)", "", "| Criterion | Judge prompt | Conversation | Human | Judge | Judge's failing turns | Judge's reason | Student's notes |",
           "|---|---|---|---|---|---|---|---|"]
    for d in disagreements:
        md.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in d) + " |")
    if not disagreements:
        md.append("| - | - | - | - | - | - | - | - |")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "agreement.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (RESULTS / "agreement.html").write_text(md_tables_to_html("LLM judge: agreement and pass rates", md), encoding="utf-8")

    for ver in vers:
        page = [f"# Judge verdicts, judge prompt {ver}", ""]
        meta = next((r for (c, v), rr in recs.items() if v == ver for r in rr.values()), {})
        page += [f"Judge model: {meta.get('judge_model', '?')}. Prompts: "
                 + ", ".join(f"criterion_{c.lower()}_{ver}.md" for c in CRITERIA) + ".", ""]
        page += ["| Conversation | Criterion | Verdict | Failing turns | Reason |", "|---|---|---|---|---|"]
        conv_ids = sorted({cid for (c, v), rr in recs.items() if v == ver for cid in rr})
        for cid in conv_ids:
            for crit in CRITERIA:
                r = recs.get((crit, ver), {}).get(cid)
                if r:
                    page.append(f"| {cid} | {crit} | {r.get('verdict') or 'ERROR'} | {', '.join(map(str, r.get('failing_turns', [])))} | "
                                + (r.get("reason") or r.get("error") or "").replace("|", "/").replace("\n", " ") + " |")
        (RESULTS / f"judge_{ver}.html").write_text(md_tables_to_html(f"Judge verdicts ({ver})", page), encoding="utf-8")
    print("\n".join(md))
    print(f"\nWrote {RESULTS / 'agreement.md'}, agreement.html and judge_<version>.html")


def md_tables_to_html(title: str, lines: list[str]) -> str:
    """Tiny Markdown subset (headings, paragraphs, tables) to a clean page for screenshots."""
    body, table = [], []

    def flush():
        if table:
            head, *rest = table
            cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]  # noqa: E731
            body.append("<table><thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cells(head)) + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(f"<td class='{c.lower() if c in ('PASS', 'FAIL') else ''}'>{html.escape(c)}</td>"
                                                   for c in cells(r)) + "</tr>" for r in rest if not set(r) <= set("|-: "))
                        + "</tbody></table>")
            table.clear()
    for line in lines:
        if line.startswith("|"):
            table.append(line)
            continue
        flush()
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.strip():
            body.append(f"<p>{html.escape(line).replace('**', '')}</p>")
    flush()
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>
body{{font-family:Cambria,Georgia,serif;margin:24px;color:#1d1d1f;background:#fff;max-width:1200px}}
h1{{font-size:20px}}h2{{font-size:16px;margin-top:28px}}p{{font-size:13px}}
table{{border-collapse:collapse;font-size:12.5px;width:100%;margin:8px 0}}
th,td{{border:1px solid #c9ccd1;padding:5px 8px;text-align:left;vertical-align:top}}th{{background:#f1f3f5}}
td.pass{{color:#1a7f37;font-weight:bold}}td.fail{{color:#cf222e;font-weight:bold}}
</style></head><body>{''.join(body)}</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if args.merge:
        merge()
    else:
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
