"""
원문 전체를 청크 파일(chunks.json)로 만들고 PGVector에 적재한다.

실행 순서
1) 문서 목록(data/sources.md)에서 색인할 파일과 문서 ID를 읽는다.
2) 파일 형식(md, xlsx)에 맞는 로더로 청크를 만든다.
    문서 목록이나 청크가 비어 있으면 여기서 멈춘다. (기존 색인 보호)
3) 같은 청크를 PGVector 컬렉션에 증분 적재한다. (교안 2장 7강)
4) 적재가 성공한 뒤에 청크 전체를 data/processed/chunks.json에 저장한다.
    → 검색 담당의 setup_search(chunks_path, ...)가 이 파일을 읽는다.
    (--chunks-only는 3을 건너뛰고 4만 한다.)

사용법 (레포 루트에서)
    uv run python -m kant_agent.document_indexing.build_index
    uv run python -m kant_agent.document_indexing.build_index --chunks-only
    uv run python -m kant_agent.document_indexing.build_index --sample
"""

import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from kant_agent.document_indexing.chunking import (
    build_chunks,
    load_markdown_document,
)
from kant_agent.document_indexing.excel_loader import load_excel_chunks
from kant_agent.shared.core.logger import get_logger

logger = get_logger(__name__)

# 이 파일 위치에서 세 단계 위가 레포 루트다.
# src/kant_agent/document_indexing/build_index.py → 레포 루트
ROOT = Path(__file__).resolve().parents[3]

# 검색 담당 코드(search/service.py)의 EMBEDDING_MODEL과 같아야 한다.
# 적재할 때와 검색할 때 다른 모델을 쓰면 벡터끼리 비교할 수 없다.
EMBEDDING_MODEL = "text-embedding-3-small"

# 운영 원문 색인 설정
SOURCES_PATH = Path("data/sources.md")
CHUNKS_PATH = Path("data/processed/chunks.json")
COLLECTION_NAME = "kant_docs"

# 팀 공용 샘플 색인 설정 (README "팀 공용 샘플 데이터")
SAMPLE_DIR = Path("data/sample")
SAMPLE_CHUNKS_PATH = Path("data/processed/sample_chunks.json")
SAMPLE_COLLECTION_NAME = "kant_docs_sample"
# 샘플 xlsx는 머리말이 없어 README 표의 문서 ID를 그대로 쓴다.
SAMPLE_DOCUMENT_IDS = {"data/sample/schedule.xlsx": "SAMPLE-003"}

# 청크마다 반드시 있어야 하는 필드. 검색 코드의 검사 목록과 같다.
REQUIRED_FIELDS = [
    "chunk_id",
    "document_id",
    "text",
    "source_path",
    "source_location",
]

# 문서 목록 표 한 줄에서 문서 ID와 원문 경로를 꺼내는 패턴
# 예) | NOTION-019 | ... | `data/raw/notion/assets/KANT_AX_시간표.xlsx` · ...
# - ^\| (\S+) \|  : 줄 맨 앞 첫 칸의 문서 ID (1번 그룹)
# - `([^`]+\.(md|xlsx))` : 백틱 안의 .md·.xlsx 경로 (2번 그룹)
# MULTILINE을 켜야 ^가 줄마다 적용된다. (정규식 특강 4절)
_SOURCE_ROW = re.compile(
    r"^\| (\S+) \|.*`([^`]+\.(md|xlsx))`", re.MULTILINE
)


def read_source_list(sources_path: Path) -> dict[str, str]:
    """문서 목록 표를 읽어 {원문 경로: 문서 ID} 딕셔너리를 만든다."""
    text = sources_path.read_text(encoding="utf-8")
    sources = {}
    for match in _SOURCE_ROW.finditer(text):
        sources[match.group(2)] = match.group(1)
    return sources


def read_sample_list(sample_dir: Path) -> dict[str, str]:
    """샘플 폴더의 md·xlsx 파일을 {경로: 문서 ID}로 모은다."""
    sources = {}
    for path in sorted(sample_dir.iterdir()):
        file_path = path.as_posix()
        if path.suffix == ".md":
            # md는 파일 안의 "문서 ID:" 머리말을 쓰므로 빈 값으로 둔다.
            sources[file_path] = ""
        elif path.suffix == ".xlsx":
            sources[file_path] = SAMPLE_DOCUMENT_IDS[file_path]
    return sources


def load_chunks(file_path: str, document_id: str) -> list[dict]:
    """파일 형식에 맞는 로더를 골라 청크 목록을 만든다. (진입 함수)"""
    if file_path.endswith(".md"):
        document = load_markdown_document(file_path)
        # 문서 목록의 ID와 원문 머리말의 ID가 다르면 근거 대조가
        # 어긋나므로 바로 알린다. (샘플 md는 목록 ID가 비어 있다)
        file_id = document.metadata["document_id"]
        if document_id and document_id != file_id:
            raise ValueError(
                f"문서 ID가 다릅니다: {file_path} "
                f"(목록 {document_id}, 원문 {file_id})"
            )
        return build_chunks(document)
    if file_path.endswith(".xlsx"):
        return load_excel_chunks(file_path, document_id)
    raise ValueError(f"지원하지 않는 형식입니다: {file_path}")


def build_all_chunks(sources: dict[str, str]) -> list[dict]:
    """목록의 모든 원문을 청크로 만들고 빈 값·중복을 검사한다."""
    # 적재는 cleanup="full"이라 "이번 실행에 없는 청크는 지운다".
    # 문서 목록 표 형식이 바뀌어 목록이 비면, 빈 입력으로 적재해서
    # 기존 컬렉션이 통째로 지워진다. 그래서 시작 전에 막는다.
    if not sources:
        raise ValueError(
            "색인할 문서가 없습니다. 문서 목록 표 형식을 확인하세요."
        )

    all_chunks = []
    seen_ids = set()
    for file_path, document_id in sources.items():
        chunks = load_chunks(file_path, document_id)
        logger.info("[build_index] %s -> 청크 %d개", file_path, len(chunks))
        # 본문 없이 첨부 링크만 있는 문서는 청크가 0개일 수 있다.
        # 이런 문서 하나 때문에 전체 색인을 멈추지는 않고 경고만 남긴다.
        if not chunks:
            logger.warning("[build_index] %s 에서 청크가 없습니다.", file_path)
        for chunk in chunks:
            # 검색 코드(prepare_chunks)와 같은 검사를 미리 해서
            # 검색 담당 쪽에서 오류가 나기 전에 여기서 잡는다.
            for field in REQUIRED_FIELDS:
                if not chunk.get(field):
                    raise ValueError(f"{chunk.get('chunk_id')}: {field} 없음")
            if chunk["chunk_id"] in seen_ids:
                raise ValueError(f"chunk_id 중복: {chunk['chunk_id']}")
            seen_ids.add(chunk["chunk_id"])
            all_chunks.append(chunk)

    # 문서는 있는데 청크가 하나도 안 나오면 로더·정제가 고장난 것이다.
    # 이때도 빈 입력으로 적재되지 않도록 여기서 멈춘다.
    if not all_chunks:
        raise ValueError("만들어진 청크가 없습니다. 로더·정제를 확인하세요.")
    return all_chunks


def save_chunks(chunks: list[dict], chunks_path: Path) -> None:
    """청크 목록을 JSON 파일로 저장한다."""
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False: 한글을 \uXXXX가 아닌 글자 그대로 저장한다.
    chunks_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def index_chunks(chunks: list[dict], collection_name: str) -> dict:
    """청크를 PGVector 컬렉션에 증분 적재하고 결과 개수를 돌려준다.

    반환값 예) {'num_added': 379, 'num_updated': 0,
                'num_skipped': 0, 'num_deleted': 0}
    """
    # DB·OpenAI 패키지는 실제 적재할 때만 필요해서 함수 안에서 불러온다.
    # --chunks-only로 JSON만 만들 때는 DB 없이도 실행되게 하려는 것이다.
    from langchain_classic.indexes import SQLRecordManager, index
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings
    from langchain_postgres.vectorstores import PGVector

    load_dotenv()
    connection_url = os.getenv("DATABASE_URL")
    if not connection_url:
        raise ValueError(".env에 DATABASE_URL을 설정하세요.")

    # 교안 2장 5·6강: 임베딩 모델과 PGVector 저장소를 연결한다.
    # use_jsonb=True: 메타데이터를 JSONB로 저장해 필터 검색이 빠르다.
    # create_extension 기본값(True)으로 vector 확장도 여기서 켠다.
    # 검색 코드는 create_extension=False라서 색인이 먼저 켜 둬야 한다.
    vector_store = PGVector(
        embeddings=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        collection_name=collection_name,
        connection=connection_url,
        use_jsonb=True,
    )

    # 교안 2장 7강: 어떤 청크를 이미 적재했는지 기록하는 "장부"
    # namespace로 컬렉션마다 장부를 따로 쓴다.
    record_manager = SQLRecordManager(
        namespace=f"pgvector/{collection_name}",
        db_url=connection_url,
    )
    record_manager.create_schema()

    # 청크 본문은 page_content로, 5개 필드는 모두 메타데이터로 넣는다.
    # 검색 코드가 page_content와 chunks.json의 text가 같은지,
    # 메타데이터 chunk_id로 청크를 찾기 때문에 그대로 넣어야 한다.
    documents = [
        Document(page_content=chunk["text"], metadata=chunk)
        for chunk in chunks
    ]

    # 내용이 같은 청크는 장부와 비교해 건너뛰고(skip),
    # 새로 생기거나 바뀐 청크만 임베딩해서 넣는다(add).
    #
    # cleanup="full": 전체 실행이 끝난 뒤, 이번 실행에 없던 옛 청크를
    # 한 번에 지운다. 우리는 매번 원문 전체를 넣으므로 이 방식이 맞다.
    # 원문 목록에서 빠진 문서의 청크도 함께 정리된다.
    #
    # 교안 2장 7강의 "incremental"을 쓰지 않은 이유:
    # index()는 청크를 100개씩 묶어 처리하는데, incremental은 묶음마다
    # 정리를 한다. 그래서 청크가 여러 묶음에 걸친 문서(시간표 206개 등)는
    # 앞 묶음에서 뒤 묶음 청크가 지워졌다가 다시 들어간다.
    # (실측: 바뀐 것 없이 2차 실행 시 190개 삭제 후 재추가)
    #
    # source_id_key="document_id": 청크가 어느 문서에서 왔는지 기록한다.
    # (교안은 "source"였지만 우리 청크의 문서 단위 키는 document_id다)
    return index(
        docs_source=documents,
        record_manager=record_manager,
        vector_store=vector_store,
        cleanup="full",
        source_id_key="document_id",
    )


def main() -> None:
    """원문 → chunks.json → PGVector 순서로 색인을 만든다."""
    parser = argparse.ArgumentParser(description="KANT 문서 색인 생성")
    parser.add_argument(
        "--chunks-only",
        action="store_true",
        help="DB 적재 없이 chunks.json만 만든다.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="data/sample/ 원문으로 샘플 색인을 만든다.",
    )
    args = parser.parse_args()

    # source_path를 "data/raw/notion/..."처럼 레포 기준 상대 경로로
    # 남기기 위해 레포 루트에서 실행한다.
    os.chdir(ROOT)

    if args.sample:
        sources = read_sample_list(SAMPLE_DIR)
        chunks_path = SAMPLE_CHUNKS_PATH
        collection_name = SAMPLE_COLLECTION_NAME
    else:
        sources = read_source_list(SOURCES_PATH)
        chunks_path = CHUNKS_PATH
        collection_name = COLLECTION_NAME

    # 문서 목록이나 청크가 비어 있으면 여기서 오류가 나서
    # 아래의 DB 적재와 JSON 저장이 실행되지 않는다.
    chunks = build_all_chunks(sources)

    # DB 적재를 먼저 하고, 성공했을 때만 JSON을 바꾼다.
    # DB 접속이나 임베딩 호출이 실패해도 JSON은 이전 상태로 남아서
    # 검색 코드가 읽는 JSON과 DB의 청크가 어긋나지 않는다.
    # (--chunks-only는 DB를 쓰지 않으므로 바로 JSON만 만든다.)
    if not args.chunks_only:
        result = index_chunks(chunks, collection_name)
        logger.info(
            "[build_index] %s 적재 결과: %s", collection_name, result
        )

    save_chunks(chunks, chunks_path)
    logger.info(
        "[build_index] 문서 %d개, 청크 %d개 -> %s",
        len(sources),
        len(chunks),
        chunks_path.as_posix(),
    )


if __name__ == "__main__":
    main()
