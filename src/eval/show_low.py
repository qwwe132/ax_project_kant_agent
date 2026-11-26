"""Ragas 점수가 낮은 문항의 질문, 정답, 답변, 검색 결과를 함께 출력한다 (읽기 전용).

사용: uv run python src/eval/show_low.py final-A-01 --kind final --metric context_precision --below 0.5
"""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--kind", default="final")
    p.add_argument("--testset", default="eval/test.json")
    p.add_argument("--metric", default="context_precision")
    p.add_argument("--below", type=float, default=0.5)
    p.add_argument("--chars", type=int, default=200, help="검색 청크 미리보기 글자 수")
    a = p.parse_args()

    run_dir = ROOT / "results" / a.kind
    items = {i["id"]: i for i in json.loads((ROOT / a.testset).read_text(encoding="utf-8"))}
    recs = {}
    for line in (run_dir / f"{a.run_id}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["question_id"]] = r

    with open(run_dir / f"{a.run_id}_ragas.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        v = row.get(a.metric, "")
        if v == "" or float(v) >= a.below:
            continue
        qid = row["question_id"]
        it, rec = items[qid], recs[qid]
        print("=" * 70)
        print(f"{qid} [{it['type']}] status={rec['status']}  "
              f"CP={row['context_precision']} CR={row['context_recall']} "
              f"F={row['faithfulness'] or '-'} AR={row['answer_relevancy'] or '-'}")
        print("Q:", it["question"])
        print("정답:", it["expected_answer"])
        print("허용 근거:", it["allowed_evidence"])
        print("답변:", rec["answer"])
        print("인용:", rec["citations"])
        print("-- 검색 상위 5 --")
        for c in (rec["candidates"] or [])[:5]:
            print(f"  #{c['rank']} {c['chunk_id']} {c['source_location']}: "
                  f"{c['text'][:a.chars].replace(chr(10), ' ')}")
        print("ragas note:", row["note"])


if __name__ == "__main__":
    main()
