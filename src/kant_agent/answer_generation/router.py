import json
from pathlib import Path

from fastapi import APIRouter

from kant_agent.answer_generation.generator import answer_from_chunks
from kant_agent.answer_generation.schemas import AskRequest
from kant_agent.shared.core.schemas import APIResponse

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_CHUNKS_PATH = ROOT / "data" / "fixtures" / "sample-chunks.json"

router = APIRouter(prefix="/v1/chatbot", tags=["KANT 규정 챗봇"])


def _load_sample_chunks() -> list[dict]:
    """검색 모듈 연결 전까지 샘플 청크를 검색 결과 대신 사용합니다."""
    # TODO: DB 준비 후 kant_agent.search.search(question)로 교체
    return json.loads(SAMPLE_CHUNKS_PATH.read_text(encoding="utf-8"))


@router.post("/ask", response_model=APIResponse[dict])
def ask_chatbot_endpoint(req: AskRequest):
    """질문을 받아 출처가 표기된 답변을 생성합니다."""
    chunks = _load_sample_chunks()
    data = answer_from_chunks(req.question, chunks)
    return APIResponse.ok(
        data=data, message="질의응답 생성이 완료되었습니다."
    )
