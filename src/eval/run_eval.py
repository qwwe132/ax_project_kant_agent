import argparse
import json
import time
from pathlib import Path

from kant_agent.answer_generation import generator
from kant_agent.answer_generation.generator import answer_from_chunks
from kant_agent.cache.answer_cache import AnswerCache, make_key
from kant_agent.search import service as search_service

ROOT = Path(__file__).resolve().parents[2]
SEARCH_CONFIGS = ("A", "B", "C")
CACHED_FIELDS = ("candidates", "answer", "citations", "status")  # 캐시에 넣는 항목


def summarize_trace(trace: dict) -> dict:
    """Keep each search stage's candidates (id, rank, score). No text."""

    def pick(rows, rank_key, score_key):
        return [
            {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "rank": r.get(rank_key),
                "score": r.get(score_key),
            }
            for r in rows
        ]

    return {
        "vector": pick(trace["vector_candidates"], "vector_rank", "vector_distance"),
        "bm25": pick(trace["bm25_candidates"], "bm25_rank", "bm25_score"),
        "pre_rerank": pick(trace["pre_rerank"], "pre_rerank_rank", "rrf_score"),
        "post_rerank": pick(trace["post_rerank"], "rank", "rerank_score"),
        "search_latency_sec": round(trace["latency_sec"], 3),
    }


def retrieve(question: str, config: str):
    """Search step. Returns (chunks best first, search trace or None).
    A/B/C use the real search. "stub" returns the 3 sample chunks."""
    # raise RuntimeError("test") #오류테스트용
    if config in SEARCH_CONFIGS:
        trace = search_service.search_with_trace(question, mode=config)
        return trace["results"], summarize_trace(trace)
    path = ROOT / "data" / "fixtures" / "sample-chunks.json"
    return json.loads(path.read_text(encoding="utf-8")), None


def answer(question: str, chunks: list[dict]) -> dict:
    """Answer step. Returns the answer text, citations, and a status."""
    return answer_from_chunks(question, chunks)


def prepare_search(config: str, collection: str, index_version: str):
    """Connect to the DB once before the run. Returns the settings to record."""
    if config not in SEARCH_CONFIGS:
        return None
    search_service.setup_search(
        collection, index_version, load_reranker=(config == "C")
    )
    return {
        "collection": collection,
        "index_version": index_version,
        "top_k": search_service.TOP_K,
        "candidate_k": search_service.CANDIDATE_K,
        "bm25_weight": search_service.BM25_WEIGHT,
        "vector_weight": search_service.VECTOR_WEIGHT,
        "rrf_c": search_service.RRF_C,
        "embedding_model": search_service.EMBEDDING_MODEL,
        "reranker_model": search_service.RERANKER_MODEL if config == "C" else None,
    }


def run(
    run_id: str,
    config: str,
    eval_file: str,
    kind: str,
    collection: str,
    index_version: str,
    use_cache: bool = False,
) -> Path:
    questions = json.loads((ROOT / eval_file).read_text(encoding="utf-8"))

    out_dir = ROOT / "results" / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl"

    if out_path.exists():
        raise SystemExit(
            f"Already exists: {out_path}\nUse a new run_id. Old records are never overwritten."
        )

    settings = prepare_search(config, collection, index_version)
    answer_settings = {
        "model": generator.MODEL_NAME,
        "prompt_version": generator.PROMPT_VERSION,
    }
    cache = AnswerCache() if use_cache else None

    with out_path.open("x", encoding="utf-8") as f:
        for index, item in enumerate(questions, start=1):
            record = {
                "run_id": run_id,
                "question_id": item.get("id", f"UNKNOWN-{index}"),
                "config": config,
                "search_settings": settings,
                "answer_settings": answer_settings,
                "cache": None,
                "search_trace": None,
                "candidates": [],
                "answer": "",
                "citations": [],
                "status": "error",
            }

            start = time.perf_counter()
            key, saved = None, None
            if cache is not None:
                key = make_key(
                    item["question"],
                    config,
                    {"search": settings, "answer": answer_settings},
                )
                saved = cache.get(key)
                record["cache"] = "hit" if saved else "miss"

            if saved:
                record.update(saved)
            else:
                try:
                    chunks, record["search_trace"] = retrieve(item["question"], config)
                    record["candidates"] = [
                        {
                            "rank": rank,
                            "document_id": c["document_id"],
                            "chunk_id": c["chunk_id"],
                            "source_location": c["source_location"],
                            "score": c.get("score"),
                            "pre_rerank_rank": c.get("pre_rerank_rank"),
                            "text": c.get("text"),
                        }
                        for rank, c in enumerate(chunks, start=1)
                    ]
                except Exception as e:
                    record["retrieve_error"] = repr(e)
                else:
                    try:
                        result = answer(item["question"], chunks)
                        record["answer"] = result["answer"]
                        record["citations"] = result["citations"]
                        record["status"] = result["status"]
                    except Exception as e:
                        record["answer_error"] = repr(e)
                if cache is not None:
                    cache.put(
                        key,
                        {k: record[k] for k in CACHED_FIELDS},
                        {
                            "question": item["question"],
                            "config": config,
                            "search": settings,
                            "answer": answer_settings,
                        },
                    )

            record["latency_sec"] = round(time.perf_counter() - start, 3)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            cache_note = f" cache={record['cache']}" if record["cache"] else ""
            print(
                f"{record['question_id']}: {record['status']} ({record['latency_sec']}s){cache_note}"
            )

    print("saved:", out_path)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("config", choices=["stub", *SEARCH_CONFIGS])
    parser.add_argument("eval_file")
    parser.add_argument("--kind", default="smoke", choices=["smoke", "dev", "final"])
    parser.add_argument("--collection", default=search_service.COLLECTION_NAME)
    parser.add_argument("--index-version")
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Use the answer cache (off for A/B/C evaluation).",
    )
    args = parser.parse_args()
    if args.config in SEARCH_CONFIGS and not args.index_version:
        raise SystemExit(
            "--index-version is required for A/B/C (it is saved with every record)."
        )
    run(
        args.run_id,
        args.config,
        args.eval_file,
        args.kind,
        args.collection,
        args.index_version,
        args.cache,
    )
