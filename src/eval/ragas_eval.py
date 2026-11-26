import argparse
import asyncio
import csv
import json
import os
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # 개인정보 보호.

from dotenv import load_dotenv
from openai import AsyncOpenAI
import ragas
from ragas.embeddings.base import embedding_factory
from ragas.llms.base import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

ROOT = Path(__file__).resolve().parents[2]
EMBEDDING_MODEL = "text-embedding-3-small"  # Answer Relevancy가 문장끼리 비교할떄 쓰는 모델. 검색과 같은 모델
FIELDS = [
    "run_id",
    "question_id",
    "status",
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
    "judge_model",
    "embedding_model",
    "ragas_version",
    "note",
]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def judge(name: str, pending, notes: list[str]):
    """Run one Ragas metric. On failure, keep going and leave a note."""
    try:
        return round((await pending).value, 3)
    except Exception as e:
        notes.append(f"{name} error: {e!r}")
        return ""


async def score_records(
    records: list[dict], items: dict, judge_model: str
) -> list[dict]:
    client = AsyncOpenAI()
    llm = llm_factory(judge_model, client=client)
    embeddings = embedding_factory("openai", model=EMBEDDING_MODEL, client=client)
    context_precision = ContextPrecision(llm=llm)
    context_recall = ContextRecall(llm=llm)
    faithfulness = Faithfulness(llm=llm)
    relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)

    rows = []
    for r in records:
        row = {
            "run_id": r["run_id"],
            "question_id": r["question_id"],
            "status": r["status"],
            "context_precision": "",
            "context_recall": "",
            "faithfulness": "",
            "answer_relevancy": "",
            "judge_model": judge_model,
            "embedding_model": EMBEDDING_MODEL,
            "ragas_version": ragas.__version__,
            "note": "",
        }
        item = items[r["question_id"]]
        question = item["question"]
        reference = " ".join(item["expected_answer"])
        contexts = [c["text"] for c in r["candidates"] if c.get("text")]
        notes = []

        # 검색 지표: 답이 있는 문항이면 답변 결과와 상관없이 채점
        if not item.get("allowed_evidence"):
            notes.append("context: no-evidence question")
        elif not contexts:
            row["context_precision"] = 0
            row["context_recall"] = 0
            notes.append("context: nothing retrieved")
        else:
            row["context_precision"] = await judge(
                "context_precision",
                context_precision.ascore(
                    user_input=question,
                    reference=reference,
                    retrieved_contexts=contexts,
                ),
                notes,
            )
            row["context_recall"] = await judge(
                "context_recall",
                context_recall.ascore(
                    user_input=question,
                    reference=reference,
                    retrieved_contexts=contexts,
                ),
                notes,
            )

        # 생성 지표: 정상 답변(ok)만 채점
        if r["status"] != "ok":
            notes.append(f"answer: skipped, status is {r['status']}")
        else:
            row["faithfulness"] = await judge(
                "faithfulness",
                faithfulness.ascore(
                    user_input=question,
                    response=r["answer"],
                    retrieved_contexts=contexts,
                ),
                notes,
            )
            row["answer_relevancy"] = await judge(
                "answer_relevancy",
                relevancy.ascore(user_input=question, response=r["answer"]),
                notes,
            )

        row["note"] = "; ".join(notes)
        print(
            f"{row['question_id']}: CP={row['context_precision']} CR={row['context_recall']} "
            f"F={row['faithfulness']} AR={row['answer_relevancy']} {row['note']}"
        )
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("eval_file")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    parser.add_argument("--judge-model", default="gpt-6-luna")  # 채점관 AI 모델
    args = parser.parse_args()

    load_dotenv()
    run_dir = ROOT / "results" / args.kind
    records = load_jsonl(run_dir / f"{args.run_id}.jsonl")
    items = {
        i["id"]: i
        for i in json.loads((ROOT / args.eval_file).read_text(encoding="utf-8"))
    }

    out_path = run_dir / f"{args.run_id}_ragas.csv"
    if out_path.exists():
        raise SystemExit(
            f"Already exists: {out_path}\nLLM scores are kept, not overwritten."
        )

    rows = asyncio.run(score_records(records, items, args.judge_model))

    with out_path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print("saved:", out_path)


if __name__ == "__main__":
    main()
