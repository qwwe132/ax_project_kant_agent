from fastapi import APIRouter

from kant_agent.answer_generation.generator import (
    answer_chat,
    answer_from_chunks,
    classify_intent,
)
from kant_agent.answer_generation.schemas import AskRequest
from kant_agent.search import search
from kant_agent.shared.core.schemas import APIResponse

router = APIRouter(prefix="/v1/chatbot", tags=["KANT 규정 챗봇"])


@router.post("/ask", response_model=APIResponse[dict])
def ask_chatbot_endpoint(req: AskRequest):
    """질문을 분류해 규정 질문은 근거 기반 답변, 일반 대화는 대화 답변을 생성합니다."""
    if classify_intent(req.question) == "chat":
        data = answer_chat(req.question)
    else:
        # 검색기는 앱 시작 시 main.py의 lifespan에서 setup_search()로 준비된다.
        chunks = search(req.question)
        data = answer_from_chunks(req.question, chunks)
    return APIResponse.ok(
        data=data, message="질의응답 생성이 완료되었습니다."
    )
