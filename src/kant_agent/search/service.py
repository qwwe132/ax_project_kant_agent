from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

if TYPE_CHECKING:
    from langchain_postgres import PGVector

# 기본값 설정
TOP_K = 5
CANDIDATE_K = 20
RRF_C = 60
BM25_WEIGHT = 0.5
VECTOR_WEIGHT = 0.5
EMBEDDING_MODEL = "text-embedding-3-small"
RERANKER_MODEL = "Dongjin-kr/ko-reranker"

chunks = []
chunk_map = {}
bm25: BM25Retriever | None = None
vectorstore: PGVector | None = None
reranker = None
index_version = ""


def load_chunks(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def split_words(text):
    return text.split()


def prepare_chunks(chunk_list):
    global chunks, chunk_map, bm25

    chunk_map = {}
    documents = []

    for chunk in chunk_list:
        for key in [
            "chunk_id",
            "document_id",
            "text",
            "source_path",
            "source_location",
        ]:
            if not chunk.get(key):
                raise ValueError(f"청크에 {key} 값이 없습니다.")

        if chunk["chunk_id"] in chunk_map:
            raise ValueError("chunk_id가 중복됩니다.")

        chunk_map[chunk["chunk_id"]] = chunk.copy()
        documents.append(Document(page_content=chunk["text"], metadata=chunk.copy()))

    chunks = list(chunk_map.values())
    bm25 = None

    if documents:
        bm25 = BM25Retriever.from_documents(documents, preprocess_func=split_words)


def setup_search(chunks_path, collection_name, version):
    global vectorstore, reranker, index_version
    from dotenv import load_dotenv
    from langchain_openai import OpenAIEmbeddings
    from langchain_postgres import PGVector

    load_dotenv()
    connection = os.getenv("DATABASE_URL")

    if not connection:
        raise ValueError(".env에 DATABASE_URL을 설정하세요.")

    prepare_chunks(load_chunks(chunks_path))
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PGVector(
        embeddings=embeddings,
        connection=connection,
        collection_name=collection_name,
        use_jsonb=True,
        create_extension=False,
    )
    index_version = version
    reranker = None


def vector_search(question, k):
    if vectorstore is None:
        raise ValueError("setup_search를 먼저 실행하세요.")

    found = vectorstore.similarity_search_with_score(question, k=k)
    results = []
    seen = set()

    for doc, distance in found:
        chunk_id = doc.metadata["chunk_id"]

        if chunk_id not in chunk_map or doc.page_content != chunk_map[chunk_id]["text"]:
            raise ValueError("벡터 색인과 청크 JSON이 다릅니다.")

        if chunk_id in seen:
            continue

        seen.add(chunk_id)
        row = chunk_map[chunk_id].copy()
        row["vector_distance"] = float(distance)
        row["vector_rank"] = len(results) + 1
        results.append(row)

    return results


def keyword_search(question):
    if bm25 is None:
        return []

    scores = bm25.vectorizer.get_scores(split_words(question))
    results = []
    for i, chunk in enumerate(chunks):
        # 일치하지 않는 청크가 RRF 점수를 받지 않도록 먼저 제외한다.
        if scores[i] <= 0:
            continue
        row = chunk.copy()
        row["bm25_score"] = float(scores[i])
        results.append(row)
    results.sort(key=lambda row: row["bm25_score"], reverse=True)
    results = results[:CANDIDATE_K]
    for rank, row in enumerate(results, 1):
        row["bm25_rank"] = rank
    return results


def hybrid_search(vector_results, keyword_results):
    combined = {}

    for row in keyword_results:
        chunk_id = row["chunk_id"]
        combined[chunk_id] = row.copy()
        combined[chunk_id]["rrf_score"] = BM25_WEIGHT / (RRF_C + row["bm25_rank"])

    for row in vector_results:
        chunk_id = row["chunk_id"]

        if chunk_id not in combined:
            combined[chunk_id] = row.copy()
            combined[chunk_id]["rrf_score"] = 0

        combined[chunk_id].update(row)
        combined[chunk_id]["rrf_score"] += VECTOR_WEIGHT / (RRF_C + row["vector_rank"])

    results = list(combined.values())
    results.sort(key=lambda row: row["rrf_score"], reverse=True)
    results = results[:CANDIDATE_K]

    for rank, row in enumerate(results, 1):
        row["pre_rerank_rank"] = rank
        row["score"] = row["rrf_score"]
        row["score_type"] = "rrf"

    return results


def rerank_search(question, candidates):
    global reranker

    if not candidates:
        return []

    if reranker is None:
        from langchain_community.cross_encoders import HuggingFaceCrossEncoder

        reranker = HuggingFaceCrossEncoder(model_name=RERANKER_MODEL)

    pairs = []

    for row in candidates:
        pairs.append((question, row["text"]))

    scores = list(reranker.score(pairs))

    if len(scores) != len(candidates):
        raise ValueError("재정렬 점수 개수가 후보 개수와 다릅니다.")

    results = []

    for row, score in zip(candidates, scores):
        item = row.copy()
        item["rerank_score"] = float(score)
        item["score"] = float(score)
        item["score_type"] = "cross_encoder"
        results.append(item)

    results.sort(key=lambda row: row["rerank_score"], reverse=True)

    for rank, row in enumerate(results, 1):
        row["rank"] = rank

    return results


def search_with_trace(question, mode="C"):
    if mode not in ["A", "B", "C"]:
        raise ValueError("mode는 A, B, C 중 하나여야 합니다.")

    if not question.strip():
        raise ValueError("질문을 입력하세요.")

    start = perf_counter()
    vector_results = []
    keyword_results = []
    before = []
    after = []
    selected = []

    if chunks:
        if mode == "A":
            vector_results = vector_search(question, TOP_K)
            for row in vector_results:
                item = row.copy()
                item["score"] = item["vector_distance"]
                item["score_type"] = "vector_distance"
                selected.append(item)
        else:
            vector_results = vector_search(question, CANDIDATE_K)
            keyword_results = keyword_search(question)
            before = hybrid_search(vector_results, keyword_results)
            selected = before
            if mode == "C":
                after = rerank_search(question, before)
                selected = after

    results = []

    for rank, row in enumerate(selected[:TOP_K], 1):
        item = row.copy()
        item["rank"] = rank
        results.append(item)

    return {
        "question": question,
        "mode": mode,
        "settings": {
            "top_k": TOP_K,
            "candidate_k": CANDIDATE_K,
            "bm25_weight": BM25_WEIGHT,
            "vector_weight": VECTOR_WEIGHT,
            "rrf_c": RRF_C,
            "embedding_model": EMBEDDING_MODEL,
            "reranker_model": RERANKER_MODEL,
            "index_version": index_version,
        },
        "status": "ok" if results else "no_results",
        "vector_candidates": vector_results,
        "bm25_candidates": keyword_results,
        "pre_rerank": before,
        "post_rerank": after,
        "results": results,
        "latency_sec": perf_counter() - start,
    }


def search(question, mode="C"):
    return search_with_trace(question, mode)["results"]
