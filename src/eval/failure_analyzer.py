import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THRESHOLD = 0.7  # 팀 합의 임계치. scoring_criteria.md와 같은 값으로 유지
METRICS = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
FIELDS = (
    ["run_id", "question_id", "status"] + METRICS + ["diagnosis", "owner", "advice"]
)


def to_float(value: str):
    return float(value) if value != "" else None


def diagnose(row: dict) -> list[tuple[str, str, str]]:
    """Return (code, owner, advice) for each problem found in one question."""
    cp, cr, f, ar = (to_float(row[m]) for m in METRICS)
    found = []

    if row["status"] == "error":
        found.append(("CALL_ERROR", "평가", "호출 오류: 하네스 기록의 오류 내용 확인"))
    if "error:" in row["note"]:
        found.append(("JUDGE_ERROR", "평가", "Ragas 채점 실패: note 확인 후 다시 채점"))
    if "no-evidence question" in row["note"]:
        found.append(
            ("NOT_SCORED", "평가", "근거 없는 문항: 정보 부족 안내를 직접 확인")
        )
        return found

    # 검색 진단
    if cr is not None and cr < THRESHOLD:
        found.append(
            (
                "RETRIEVAL_FAILURE",
                "검색",
                "필요한 자료를 못 찾음: 하이브리드·BM25·청킹 점검",
            )
        )
    elif cp is not None and cp < THRESHOLD:
        found.append(
            (
                "RANKING_ISSUE",
                "검색",
                "자료는 찾았지만 순위가 낮음: 리랭크·후보 수 점검",
            )
        )
    elif cr is not None and row["status"] == "no_evidence":
        found.append(
            ("MISSED_ANSWER", "답변", "근거를 찾았는데 모른다고 답함: 답변 조건 점검")
        )

    # 답변 진단
    if f is not None and f < THRESHOLD:
        found.append(
            (
                "GENERATION_FAILURE",
                "답변",
                "자료에 없는 내용을 만듦: '문맥만 사용' 규칙 강화",
            )
        )
    if ar is not None and ar < THRESHOLD:  # AR은 참고용: 담당자 목록에 올리지 않음
        found.append(("AR_LOW", "", "참고용: AR 낮음. 답변을 직접 읽고 판단"))

    if not any(owner for _, owner, _ in found):
        found.insert(0, ("PASS", "", "문제 없음"))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    args = parser.parse_args()

    run_dir = ROOT / "results" / args.kind
    src_path = run_dir / f"{args.run_id}_ragas.csv"
    if not src_path.exists():
        raise SystemExit(f"Not found: {src_path}\nRun ragas_eval.py first.")
    with src_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    counts = Counter()
    by_owner = defaultdict(list)
    for row in rows:
        found = diagnose(row)
        codes = [code for code, _, _ in found]
        owners = list(dict.fromkeys(owner for _, owner, _ in found if owner))
        counts.update(codes)
        for owner in owners:
            by_owner[owner].append(row["question_id"])

        out = {k: row[k] for k in ["run_id", "question_id", "status"] + METRICS}
        out["diagnosis"] = " | ".join(codes)
        out["owner"] = " | ".join(owners)
        out["advice"] = " | ".join(advice for _, _, advice in found)
        out_rows.append(out)
        print(f"{row['question_id']}: {out['diagnosis']}")

    out_path = run_dir / f"{args.run_id}_diagnosis.csv"
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"--- summary (threshold {THRESHOLD}) ---")
    for code, n in counts.most_common():
        print(f"{code}: {n}")
    print("--- to fix, by owner ---")
    for owner, qids in by_owner.items():
        print(f"{owner}: {', '.join(qids)}")
    print("saved:", out_path)


if __name__ == "__main__":
    main()
