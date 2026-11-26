"""평가셋 JSON 읽기.

문항 형식: query_type, question, answer, context
- query_type: 단순 사실 확인 / 복합 추론 질문 / 문서 외 함정 질문
- answer: 정답 문장
- context: 정답 근거 원문. 문서 외 함정 질문은 관련은 있지만 답은 없는 원문

문항 ID는 파일 안 순서로 붙인다(dev.json → DEV-001, test.json → TEST-001).
문항 순서를 바꾸면 기존 실행 결과의 question_id와 어긋나므로 순서는 고정한다.
예전 형식(id, type, expected_answer, allowed_evidence)인 cache.json, sample.json도 그대로 읽는다.
"""
import json
from pathlib import Path

NO_EVIDENCE_TYPE = "문서 외 함정 질문"


def load_testset(path: Path) -> dict[str, dict]:
    """{문항 ID: 문항} 순서대로 반환한다."""
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    prefix = Path(path).stem.upper()
    return {
        item.get("id") or f"{prefix}-{n:03d}": item
        for n, item in enumerate(items, start=1)
    }


def question_type(item: dict) -> str:
    return item.get("query_type") or item.get("type", "")


def is_no_evidence(item: dict) -> bool:
    """정답 근거가 없는 문항(정보 부족 안내가 정답)인지."""
    if "query_type" in item:
        return item["query_type"] == NO_EVIDENCE_TYPE
    return not item.get("allowed_evidence")


def reference_answer(item: dict) -> str:
    if "answer" in item:
        return item["answer"]
    return " ".join(item.get("expected_answer", []))


def _norm(text: str) -> str:
    return " ".join(text.split())


def is_evidence(item: dict, candidate: dict) -> bool:
    """검색된 청크 하나가 정답 근거인지."""
    if is_no_evidence(item):
        return False
    if "context" in item:
        text = _norm(candidate.get("text") or "")
        return bool(text) and text in _norm(item["context"])
    for ev in item.get("allowed_evidence", []):
        if ev.get("chunk_id") is not None:
            if candidate["chunk_id"] == ev["chunk_id"]:
                return True
        elif (
            candidate["document_id"] == ev["document_id"]
            and candidate["source_location"] == ev["source_location"]
        ):
            return True
    return False


def evidence_recall(item: dict, candidates: list[dict]) -> float:
    """정답 근거 중 검색 결과로 찾은 비율.

    context 형식은 근거 원문 글자 수 중 검색된 근거 청크가 덮는 비율로 계산한다.
    """
    if "context" in item:
        found = {
            c["chunk_id"]: len(_norm(c["text"]))
            for c in candidates
            if is_evidence(item, c)
        }
        return min(1.0, sum(found.values()) / len(_norm(item["context"])))
    allowed = item.get("allowed_evidence", [])
    found = sum(
        1
        for ev in allowed
        if any(is_evidence({"allowed_evidence": [ev]}, c) for c in candidates)
    )
    return found / len(allowed)
