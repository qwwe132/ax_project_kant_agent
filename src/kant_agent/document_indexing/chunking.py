"""
원문 Markdown 문서를 검색 담당에게 넘길 청크로 나눈다.
청크 필드: chunk_id, document_id, text, source_path, source_location
"""

import json
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from kant_agent.document_indexing.preprocess import clean_notion_markdown

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50

# 원문 상단의 "문서 ID: X" 줄에서 읽어 메타데이터로 옮길 항목
_HEADER_KEYS = {
    "문서 ID": "document_id",
    "자료 구분": "data_type",
    "수집일": "collected_at",
}


def load_markdown_document(file_path: str) -> Document:
    """Markdown 파일을 읽어 본문과 메타데이터를 가진 Document로 만든다."""
    path = Path(file_path)
    # 원문에 한글·이모지가 있어 OS 기본 인코딩(cp949) 대신 UTF-8로 읽는다.
    text = path.read_text(encoding="utf-8")
    # 머리말·본문을 나누기 전에 먼저 정제한다.
    # 정제 전에는 <h2>공가 신청</h2> 같은 HTML 제목이 "## "로 시작하지
    # 않아서, 그 아래 본문까지 머리말로 잘못 취급되기 때문이다.
    lines = clean_notion_markdown(text).splitlines()

    # source_path는 OS와 관계없이 "/" 구분자로 저장한다.
    # Windows의 "\" 경로가 섞이면 팀원 간 출처 대조가 어긋나기 때문이다.
    metadata = {"source_path": path.as_posix(), "title": ""}
    body_lines = []

    # 첫 "##"·"###" 제목 전까지를 머리말로 본다.
    # 본문 속 "수집일: ..." 같은 문장을 메타데이터로 잘못 읽지 않게 한다.
    in_header = True
    for line in lines:
        if line.startswith(("## ", "### ")):
            in_header = False
        # Notion 사본은 "- 문서 ID: ..." 형식이라 목록 기호를 떼고 비교한다.
        stripped = line.strip().removeprefix("- ")
        # partition은 첫 ":"에서만 나눈다.
        # "Notion 원문: https://..."처럼 값에 ":"가 있어도 값이 잘리지 않는다.
        key, _, value = stripped.partition(":")
        if in_header and key in _HEADER_KEYS and value:
            # 머리말 항목은 메타데이터로만 옮기고 본문에서는 뺀다.
            # 본문에 남으면 "문서 ID: SAMPLE-001"이 검색 청크가 되어 버린다.
            metadata[_HEADER_KEYS[key]] = value.strip()
        elif line.startswith("# ") and not metadata["title"]:
            # 첫 "#" 줄만 문서 제목으로 쓴다.
            metadata["title"] = line[2:].strip()
        else:
            body_lines.append(line)

    # 문서 ID는 chunk_id와 평가셋 근거 대조의 기준이다.
    # 없으면 나중에 조용히 틀리지 않도록 여기서 바로 실패시킨다.
    if "document_id" not in metadata:
        raise ValueError(f"문서 ID가 없습니다: {file_path}")

    return Document(page_content="\n".join(body_lines), metadata=metadata)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """'##'·'###' 제목 단위로 본문을 나눠 (제목, 내용) 목록을 만든다."""
    sections = []
    # 첫 제목이 나오기 전 내용은 제목 없는 구간("")으로 모은다.
    section_title = ""
    section_lines = []
    for line in text.splitlines():
        if line.startswith(("## ", "### ")):
            # 새 제목을 만나면 지금까지 모은 구간을 닫고 새 구간을 연다.
            sections.append((section_title, "\n".join(section_lines)))
            # "## 입실 기준" → "입실 기준". 이 값이 source_location이 된다.
            section_title = line.lstrip("#").strip()
            section_lines = []
        else:
            section_lines.append(line)
    # 반복이 끝나도 마지막 구간은 아직 닫히지 않았으므로 따로 추가한다.
    sections.append((section_title, "\n".join(section_lines)))

    # 메타데이터 줄만 있던 머리말처럼 내용이 빈 구간은 버린다.
    return [
        (title, content.strip())
        for title, content in sections
        if content.strip()
    ]


def build_chunks(
    document: Document,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Document를 섹션별로 나눈 뒤 길면 한 번 더 잘라 청크 목록을 만든다."""
    # 교안 2장 2강의 재귀적 분할기.
    # 문단(\n\n) → 줄(\n) → 공백 순으로 나눌 곳을 찾아
    # chunk_size를 넘지 않게 자르므로 문장이 중간에 덜 끊긴다.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,  # 청크 하나의 최대 글자 수
        chunk_overlap=chunk_overlap,  # 앞뒤 청크가 겹치는 글자 수
        length_function=len,  # 토큰이 아닌 글자 수로 길이를 잰다.
        is_separator_regex=False,
    )

    document_id = document.metadata["document_id"]
    chunks = []
    # 섹션을 먼저 나누는 이유: 크기만으로 자르면 "09:10 이후 지각"처럼
    # 규정과 조건이 다른 청크로 갈라져 원문 위치를 찾기 어려워진다.
    for section_title, section_text in _split_sections(
        document.page_content
    ):
        # 섹션이 chunk_size보다 짧으면 조각 1개, 길면 여러 개가 나온다.
        # 같은 섹션에서 나온 조각은 source_location이 모두 같다.
        for piece in text_splitter.split_text(section_text):
            chunks.append(
                {
                    # 순번 기반 ID라 같은 원문·설정이면 다시 만들어도 같다.
                    # 문서 전체에서 이어지는 순번이다(섹션마다 1부터 X).
                    # 원문이나 chunk_size가 바뀌면 순번이 밀리므로
                    # 평가셋의 근거 chunk_id도 다시 매핑해야 한다.
                    "chunk_id": f"{document_id}-{len(chunks) + 1:03d}",
                    "document_id": document_id,
                    "text": piece,
                    "source_path": document.metadata["source_path"],
                    # 첫 제목 전 구간은 제목이 없어 "본문"으로 표시한다.
                    "source_location": section_title or "본문",
                }
            )
    return chunks


def main() -> None:
    """명령행으로 받은 Markdown 파일들의 청크를 JSON으로 출력한다."""
    all_chunks = []
    for file_path in sys.argv[1:]:
        all_chunks.extend(build_chunks(load_markdown_document(file_path)))
    # Windows 콘솔 기본값(cp949)은 이모지·일부 한글을 못 써서 UTF-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(all_chunks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
