"""RAGAS 검색·생성 지표 채점 (RAG 교안 7장 3강·4강 방식).

- 3강 검색 지표: user_input, reference, retrieved_contexts → ContextPrecision, ContextRecall
- 4강 생성 지표: user_input, retrieved_contexts, response → Faithfulness, ResponseRelevancy
- 심사위원: init_chat_model(temperature=0)을 LangchainLLMWrapper로 감싸 evaluate()에 전달

출력:
- <run_id>_ragas_search.csv      3강 검색 평가 리포트 (to_pandas 원본)
- <run_id>_ragas_generation.csv  4강 생성 평가 리포트 (to_pandas 원본)
- <run_id>_ragas.csv             문항별 4지표 요약 (failure_analyzer.py, compare.py가 읽음)

사용: uv run python src/eval/ragas_eval.py dev-C-03 eval/dev.json --kind dev
"""

import argparse
import csv
import json
import math
import os
import warnings
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # 개인정보 보호.
# 교안의 ragas.metrics 경로는 0.4에서 사용 중단 예고 경고가 나오므로 숨긴다(동작은 같음).
warnings.filterwarnings("ignore", category=DeprecationWarning)

import ragas
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    ContextPrecision,
    ContextRecall,
    Faithfulness,
    ResponseRelevancy,
)
from testset import is_no_evidence, load_testset, reference_answer

ROOT = Path(__file__).resolve().parents[2]
# 심사위원 모델. 교안은 gpt-4o-mini + temperature=0이지만, 우리 API 키는 gpt-6-luna만 쓸 수 있다.
JUDGE_MODEL = "gpt-6-luna"
# temperature를 기본값(1) 외에는 받지 않는 추론 모델. 이 모델들은 temperature 고정을 건너뛴다.
NO_TEMPERATURE_PREFIXES = ("gpt-6", "gpt-5", "o1", "o3", "o4")
EMBEDDING_MODEL = "text-embedding-3-small"  # 답변 관련성의 질문 유사도 계산용. 검색과 같은 모델
SEARCH_METRICS = ["context_precision", "context_recall"]
GENERATION_METRICS = ["faithfulness", "answer_relevancy"]
FIELDS = [
    "run_id",
    "question_id",
    "status",
    *SEARCH_METRICS,
    *GENERATION_METRICS,
    "judge_model",
    "embedding_model",
    "ragas_version",
    "note",
]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_datasets(records: list[dict], items: dict, rows: dict) -> tuple:
    """3강·4강 데이터셋 규격으로 변환한다. 채점하지 않는 문항은 note에 이유를 남긴다."""
    search, search_ids = [], []
    generation, generation_ids = [], []
    for r in records:
        qid = r["question_id"]
        item = items[qid]
        question = item["question"]
        contexts = [c["text"] for c in r["candidates"] if c.get("text")]
        notes = rows[qid]["notes"]

        # 3강 검색 지표: 답이 있는 문항이면 답변 결과와 상관없이 채점
        if is_no_evidence(item):
            notes.append("context: no-evidence question")
        elif not contexts:
            rows[qid]["context_precision"] = 0
            rows[qid]["context_recall"] = 0
            notes.append("context: nothing retrieved")
        else:
            search.append(
                {
                    "user_input": question,
                    "reference": reference_answer(item),
                    "retrieved_contexts": contexts,
                }
            )
            search_ids.append(qid)

        # 4강 생성 지표: 정상 답변(ok)만 채점
        if r["status"] != "ok":
            notes.append(f"answer: skipped, status is {r['status']}")
        else:
            generation.append(
                {
                    "user_input": question,
                    "retrieved_contexts": contexts,
                    "response": r["answer"],
                }
            )
            generation_ids.append(qid)
    return (search, search_ids), (generation, generation_ids)


def run_evaluate(samples: list[dict], metrics: list, label: str):
    """evaluate()로 채점하고 to_pandas() 결과를 돌려준다. 문항이 없으면 None."""
    if not samples:
        return None
    print(f"{label}: {len(samples)}문항 채점 중...")
    result = evaluate(
        dataset=EvaluationDataset.from_list(samples),
        metrics=metrics,
        # 한 문항 채점이 실패해도 나머지는 계속 채점한다. 실패한 칸은 note에 남긴다.
        raise_exceptions=False,
    )
    return result.to_pandas()


def fill_scores(df, ids: list[str], names: list[str], rows: dict) -> None:
    for qid, (_, line) in zip(ids, df.iterrows()):
        for name in names:
            value = line.get(name)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                rows[qid]["notes"].append(f"{name}: judge error")
            else:
                rows[qid][name] = round(float(value), 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("eval_file")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    parser.add_argument("--judge-model", default=JUDGE_MODEL)  # 심사위원 모델
    args = parser.parse_args()

    load_dotenv()
    run_dir = ROOT / "results" / args.kind
    records = load_jsonl(run_dir / f"{args.run_id}.jsonl")
    items = load_testset(ROOT / args.eval_file)

    out_path = run_dir / f"{args.run_id}_ragas.csv"
    if out_path.exists():
        raise SystemExit(
            f"Already exists: {out_path}\nLLM scores are kept, not overwritten."
        )

    # 심사위원 모델 연동: 일관된 채점을 위해 temperature=0 (지원하는 모델만)
    fixed_temperature = not args.judge_model.startswith(NO_TEMPERATURE_PREFIXES)
    chat_model = (
        init_chat_model(model=args.judge_model, model_provider="openai", temperature=0)
        if fixed_temperature
        else init_chat_model(model=args.judge_model, model_provider="openai")
    )
    judge_llm = LangchainLLMWrapper(chat_model, bypass_temperature=not fixed_temperature)
    judge_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=EMBEDDING_MODEL)
    )

    rows = {
        r["question_id"]: {
            "run_id": r["run_id"],
            "question_id": r["question_id"],
            "status": r["status"],
            **{m: "" for m in SEARCH_METRICS + GENERATION_METRICS},
            "judge_model": args.judge_model,
            "embedding_model": EMBEDDING_MODEL,
            "ragas_version": ragas.__version__,
            "notes": [],
        }
        for r in records
    }
    (search, search_ids), (generation, generation_ids) = build_datasets(
        records, items, rows
    )

    # 3강: 검색 지표 측정 → 리포트 저장
    search_df = run_evaluate(
        search,
        [ContextPrecision(llm=judge_llm), ContextRecall(llm=judge_llm)],
        "검색 지표(CP·CR)",
    )
    if search_df is not None:
        search_df.insert(0, "question_id", search_ids)
        search_df.to_csv(
            run_dir / f"{args.run_id}_ragas_search.csv",
            index=False,
            encoding="utf-8-sig",
        )
        fill_scores(search_df, search_ids, SEARCH_METRICS, rows)

    # 4강: 생성 지표 측정 → 리포트 저장
    generation_df = run_evaluate(
        generation,
        [
            Faithfulness(llm=judge_llm),
            ResponseRelevancy(llm=judge_llm, embeddings=judge_embeddings),
        ],
        "생성 지표(F·AR)",
    )
    if generation_df is not None:
        generation_df.insert(0, "question_id", generation_ids)
        generation_df.to_csv(
            run_dir / f"{args.run_id}_ragas_generation.csv",
            index=False,
            encoding="utf-8-sig",
        )
        fill_scores(generation_df, generation_ids, GENERATION_METRICS, rows)

    # 문항별 4지표 요약 (failure_analyzer.py, compare.py 입력)
    with out_path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows.values():
            row["note"] = "; ".join(row.pop("notes"))
            writer.writerow(row)
            print(
                f"{row['question_id']}: CP={row['context_precision']} CR={row['context_recall']} "
                f"F={row['faithfulness']} AR={row['answer_relevancy']} {row['note']}"
            )
    print("saved:", out_path)


if __name__ == "__main__":
    main()
