import argparse
import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METRICS = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
PASS_METRICS = ["context_precision", "context_recall"]  # 팀 합의: 둘 다 올라가야 통과


def load(run_dir: Path, run_id: str) -> dict:
    path = run_dir / f"{run_id}_ragas.csv"
    if not path.exists():
        raise SystemExit(f"Not found: {path}\nRun ragas_eval.py first.")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["question_id"]: r for r in csv.DictReader(f)}


def delta(b: str, i: str):
    return round(float(i) - float(b), 3) if b != "" and i != "" else ""

def find_unscored(base: dict, imp: dict) -> list[str]:
    """Answerable questions whose CP or CR is missing on either side."""
    problems = []
    for q in sorted(set(base) | set(imp)):
        rows = [r for r in (base.get(q), imp.get(q)) if r is not None]
        if any("no-evidence question" in r["note"] for r in rows):
            continue
        if len(rows) < 2 or any(r[m] == "" for r in rows for m in PASS_METRICS):
            problems.append(q)
    return problems

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("improved")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    args = parser.parse_args()

    run_dir = ROOT / "results" / args.kind
    base = load(run_dir, args.baseline)
    imp = load(run_dir, args.improved)

    common = [q for q in base if q in imp]
    missing = sorted(set(base) ^ set(imp))
    if missing:
        print(f"WARNING: only common questions compared. Missing on one side: {', '.join(missing)}")

    print(f"{'metric':<18}{'baseline':>10}{'improved':>10}{'delta':>10}  n")
    deltas = {}
    for m in METRICS:
        pairs = [(float(base[q][m]), float(imp[q][m]))
                 for q in common if base[q][m] != "" and imp[q][m] != ""]
        if not pairs:
            print(f"{m:<18}{'-':>10}{'-':>10}{'-':>10}  0")
            continue
        b = statistics.mean(p[0] for p in pairs)
        i = statistics.mean(p[1] for p in pairs)
        deltas[m] = i - b
        print(f"{m:<18}{b:>10.3f}{i:>10.3f}{i - b:>+10.3f}  {len(pairs)}")

    unscored = find_unscored(base, imp)
    if unscored:
        verdict = "pending"
        print(f"PENDING: CP/CR missing or failed on: {', '.join(unscored)}. "
              "Re-score these questions, then compare again.")
    else:
        verdict = str(all(deltas.get(m, 0) > 0 for m in PASS_METRICS)).lower()
    print(f"regression_passed: {verdict}  (rule: {' and '.join(PASS_METRICS)} must go up)")
    dropped = [m for m in METRICS if m not in PASS_METRICS and deltas.get(m, 0) < 0]
    if dropped:
        print(f"NOTE: went down: {', '.join(dropped)}")

    rows = []
    worse = []
    for q in common:
        row = {"question_id": q}
        for m in METRICS:
            row[f"{m}_baseline"] = base[q][m]
            row[f"{m}_improved"] = imp[q][m]
            row[f"{m}_delta"] = delta(base[q][m], imp[q][m])
        if any(isinstance(row[f"{m}_delta"], float) and row[f"{m}_delta"] < 0 for m in PASS_METRICS):
            worse.append(q)
        rows.append(row)
    if worse:
        print(f"worse in improved (CP or CR): {', '.join(worse)}")

    out_path = run_dir / f"compare_{args.baseline}_vs_{args.improved}.csv"
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["question_id"])
        writer.writeheader()
        writer.writerows(rows)
    print("saved:", out_path)


if __name__ == "__main__":
    main()