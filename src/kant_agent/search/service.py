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
    from sqlalchemy.engine import Engine

# 기본값 설정
TOP_K = 5
CANDIDATE_K = 20
RRF_C = 60
BM25_WEIGHT = 0.5
VECTOR_WEIGHT = 0.5
EMBEDDING_MODEL = "text-embedding-3-small"
RERANKER_MODEL = "Dongjin-kr/ko-reranker"

# 색인 담당(document_indexing/build_index.py)이 적재하는 컬렉션 이름
COLLECTION_NAME = "kant_docs"
SAMPLE_COLLECTION_NAME = "kant_docs_sample"

chunks = []
chunk_map = {}
bm25: BM25Retriever | None = None
vectorstore: PGVector | None = None
reranker = None
index_version = ""


def load_chunks(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


# PGVector 기본 스키마에서 컬렉션 이름으로 청크를 읽는다.
# 컬렉션 이름으로 JOIN 필터링해야 다른 컬렉션(다른 색인 버전) 청크가 섞이지 않는다.
_COLLECTION_CHUNKS_SQL = """
SELECT e.id, e.document, e.cmetadata
FROM langchain_pg_embedding AS e
JOIN langchain_pg_collection AS c ON e.collection_id = c.uuid
WHERE c.name = :collection_name
"""


def get_database_url() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    connection = os.getenv("DATABASE_URL")

    if not connection:
        raise ValueError(".env에 DATABASE_URL을 설정하세요.")

    return connection


def load_collection_chunks(collection_name: str, engine: Engine) -> list[dict]:
    """PGVector 컬렉션에 적재된 청크를 prepare_chunks() 입력 형식으로 읽는다.

    본문은 document 컬럼, 나머지 필드는 cmetadata(JSONB)에서 가져온다.
    필드 누락 검사는 prepare_chunks()가 맡는다.
    색인 쪽 index()는 PGVector id에 해시를 쓰므로 chunk_id 순으로 정렬한다.
    """
    from sqlalchemy import JSON, String, text

    query = text(_COLLECTION_CHUNKS_SQL).columns(
        id=String, document=String, cmetadata=JSON
    )

    with engine.connect() as conn:
        rows = conn.execute(query, {"collection_name": collection_name}).all()

    if not rows:
        raise ValueError(f"컬렉션 '{collection_name}'이 없거나 비어 있습니다.")

    chunk_list = []

    for row in rows:
        chunk = dict(row.cmetadata or {})
        chunk["text"] = row.document
        chunk_list.append(chunk)

    chunk_list.sort(key=lambda chunk: str(chunk.get("chunk_id", "")))
    return chunk_list


# BM25에 남길 형태소 품사. 조사(J*)·어미(E*)·문장부호(S*)는 버린다.
# 공백 분리만 하면 "지각이야?"와 "지각"이 다른 단어가 되어 키워드 검색이 실패한다.
# W_*는 09:10, 2026-12-01 같은 시간·날짜·URL을 한 토큰으로 유지한다.
_KEEP_TAG_PREFIXES = ("NN", "NR", "NP", "VV", "VA", "XR", "SL", "SH", "SN", "W_")
_kiwi = None


def _get_kiwi():
    global _kiwi

    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()

    return _kiwi


def split_words(text: str) -> list[str]:
    """BM25용 토큰 목록. 한국어 형태소 분석 후 내용어만 남긴다."""
    words = []

    for token in _get_kiwi().tokenize(text):
        if token.tag.startswith(_KEEP_TAG_PREFIXES):
            words.append(token.form.lower())

    return words


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


def setup_search(
    collection_name: str,
    version: str,
    chunks_path: str | Path | None = None,
    load_reranker: bool = True,
) -> None:
    """검색기를 초기화한다. 앱 시작 시 1회 호출한다.

    기본은 DB의 같은 컬렉션에서 청크를 읽어 BM25를 만든다.
    chunks_path를 주면 JSON 파일을 대신 쓴다(샘플·테스트용).
    load_reranker가 True면 재정렬 모델도 여기서 로드한다.
    첫 C 모드 검색이 모델 로드 시간만큼 느려지고 latency_sec에
    그 시간이 섞이는 것을 막기 위해서다. A·B 모드만 쓸 때는 False로 둔다.
    """
    global vectorstore, reranker, index_version
    from langchain_openai import OpenAIEmbeddings
    from langchain_postgres import PGVector
    from sqlalchemy import create_engine

    engine = create_engine(get_database_url())

    if chunks_path is None:
        chunk_list = load_collection_chunks(collection_name, engine)
    else:
        chunk_list = load_chunks(chunks_path)

    prepare_chunks(chunk_list)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PGVector(
        embeddings=embeddings,
        connection=engine,
        collection_name=collection_name,
        use_jsonb=True,
        create_extension=False,
    )
    index_version = version
    reranker = None

    if load_reranker:
        get_reranker()


def vector_search(question, k):
    if vectorstore is None:
        raise ValueError("setup_search를 먼저 실행하세요.")

    found = vectorstore.similarity_search_with_score(question, k=k)
    results = []
    seen = set()

    for doc, distance in found:
        chunk_id = doc.metadata["chunk_id"]

        if chunk_id not in chunk_map or doc.page_content != chunk_map[chunk_id]["text"]:
            # BM25 청크는 setup_search() 시점에 고정되지만 벡터 검색은 DB 최신 상태를 읽는다.
            # 서버를 켠 채 재색인하면 여기서 어긋나므로 API를 재시작해야 한다.
            raise ValueError(
                "벡터 색인과 BM25 청크가 다릅니다. 재색인 후에는 API를 재시작하세요"
                "(API 중지 → build_index → API 재시작)."
            )

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


def get_reranker():
    global reranker

    if reranker is None:
        from langchain_community.cross_encoders import HuggingFaceCrossEncoder

        reranker = HuggingFaceCrossEncoder(model_name=RERANKER_MODEL)

    return reranker


def rerank_search(question, candidates):
    if not candidates:
        return []

    pairs = []

    for row in candidates:
        pairs.append((question, row["text"]))

    scores = list(get_reranker().score(pairs))

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
