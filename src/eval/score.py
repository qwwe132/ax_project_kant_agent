import argparse
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCORE_COLUMNS = ["answer_correct", "evidence_fit", "no_evidence_ok"]
MANUAL_COLUMNS = SCORE_COLUMNS + ["note", "scorer", "reviewer"]
FIELDS = [
    "run_id", "question_id", "config", "type", "status",
    "call_ok", "latency_sec", "hit_at_5",
] + MANUAL_COLUMNS


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def hit_at_5(item: dict, record: dict):
    """1 if any allowed evidence is in the top 5 candidates, 0 if not, "" if no evidence is expected."""
    allowed = item.get("allowed_evidence", [])
    if not allowed:
        return ""
    for ev in allowed:
        for c in record["candidates"][:5]:
            if ev.get("chunk_id") is not None:
                if c["chunk_id"] == ev["chunk_id"]:
                    return 1
            elif c["document_id"] == ev["document_id"] and c["source_location"] == ev["source_location"]:
                return 1
    return 0


def build_rows(records: list[dict], items: dict) -> list[dict]:
    rows = []
    for r in records:
        item = items.get(r["question_id"], {})
        call_ok = not r.get("retrieve_error") and not r.get("answer_error")
        row = {
            "run_id": r["run_id"],
            "question_id": r["question_id"],
            "config": r["config"],
            "type": item.get("type", ""),
            "status": r["status"],
            "call_ok": int(call_ok),
            "latency_sec": r["latency_sec"],
            "hit_at_5": hit_at_5(item, r) if item else "",
        }
        row.update({col: "" for col in MANUAL_COLUMNS})

        if not call_ok:
            if row["hit_at_5"] == "":
                row["no_evidence_ok"] = 0
            else:
                row["answer_correct"] = 0
                row["evidence_fit"] = 0
            row["note"] = "호출 오류로 자동 0점"

        rows.append(row)
    return rows


def read_sheet(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def total_of(column: str, group: list[dict]):
    filled = [r for r in group if r[column] != ""]
    score = sum(int(r[column]) for r in filled if r["call_ok"] == "1")
    return score, len(filled), len(group)


def summarize(records: list[dict], rows: list[dict]) -> None:
    answerable = [r for r in rows if r["hit_at_5"] != ""]
    no_evidence = [r for r in rows if r["hit_at_5"] == ""]

    hits = sum(int(r["hit_at_5"]) for r in answerable)
    ok = [r for r in rows if r["call_ok"] == "1"]
    latencies = [float(r["latency_sec"]) for r in ok]
    retrieve_errors = sum(1 for r in records if r.get("retrieve_error"))
    answer_errors = sum(1 for r in records if r.get("answer_error"))

    print("--- automatic ---")
    print(f"Hit@5: {hits}/{len(answerable)}")
    print(f"call success: {len(ok)}/{len(rows)}")
    if latencies:
        print(f"latency: mean {statistics.mean(latencies):.3f}s, median {statistics.median(latencies):.3f}s, n={len(latencies)}")
    print(f"errors: retrieve {retrieve_errors}, answer {answer_errors}")

    print("--- manual (from the scoring sheet) ---")
    for col, label, group in [
        ("answer_correct", "answer correct", answerable),
        ("evidence_fit", "evidence fit", answerable),
        ("no_evidence_ok", "no-evidence handling", no_evidence),
    ]:
        score, filled, total = total_of(col, group)
        print(f"{label}: {score}/{total}  (filled {filled}/{total})")

    reviewed = sum(1 for r in rows if r["reviewer"] != "")
    print(f"cross-reviewed rows: {reviewed}/{len(rows)}")

    wrong = [r["question_id"] for r in rows
             if r["call_ok"] == "0" and any(r[c] == "1" for c in SCORE_COLUMNS)]
    if wrong:
        print(f"WARNING: call errors marked as 1 (counted as 0): {', '.join(wrong)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("eval_file")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    args = parser.parse_args()

    run_dir = ROOT / "results" / args.kind
    records = load_jsonl(run_dir / f"{args.run_id}.jsonl")
    items = {i["id"]: i for i in json.loads((ROOT / args.eval_file).read_text(encoding="utf-8"))}

    sheet_path = run_dir / f"{args.run_id}_scoring.csv"
    if not sheet_path.exists():
        with sheet_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(build_rows(records, items))
        print("created scoring sheet:", sheet_path)
    else:
        print("using existing scoring sheet:", sheet_path)

    summarize(records, read_sheet(sheet_path))


if __name__ == "__main__":
    main()