import os

import openai
from fastapi import APIRouter, status

from kant_agent.answer_generation import generator
from kant_agent.answer_generation.generator import (
    answer_chat,
    answer_from_chunks,
    classify_intent,
)
from kant_agent.answer_generation.schemas import AskRequest
from kant_agent.cache.answer_cache import AnswerCache, make_key
from kant_agent.search import search
from kant_agent.search import service as search_service
from kant_agent.shared.core.exception import SharedException
from kant_agent.shared.core.schemas import APIResponse

router = APIRouter(prefix="/v1/chatbot", tags=["KANT 규정 챗봇"])

# 같은 규정 질문은 분류·검색·답변을 건너뛰고 저장된 답을 돌려준다.
# 메모리에만 저장하므로 서버를 재시작하면 비워진다(재색인 후 API 재시작 규칙과 맞물림).
# 잡담(chat)은 저장하지 않는다.
SEARCH_MODE = "C"
answer_cache = AnswerCache(path=None)


def cache_settings() -> dict:
    """Everything that can change a rules answer (same shape as the harness)."""
    return {
        "search": {
            # main.py와 같은 규칙으로 컬렉션 이름을 읽는다.
            "collection": os.getenv("SEARCH_COLLECTION") or search_service.COLLECTION_NAME,
            "index_version": search_service.index_version,
            "top_k": search_service.TOP_K,
            "candidate_k": search_service.CANDIDATE_K,
            "bm25_weight": search_service.BM25_WEIGHT,
            "vector_weight": search_service.VECTOR_WEIGHT,
            "rrf_c": search_service.RRF_C,
            "embedding_model": search_service.EMBEDDING_MODEL,
            "reranker_model": search_service.RERANKER_MODEL,
        },
        "answer": {
            "model": generator.MODEL_NAME,
            "prompt_version": generator.PROMPT_VERSION,
            "max_tokens": generator.MAX_TOKENS,
        },
    }


@router.post("/ask", response_model=APIResponse[dict])
def ask_chatbot_endpoint(req: AskRequest):
    """질문을 분류해 규정 질문은 근거 기반 답변, 일반 대화는 대화 답변을 생성합니다."""
    key = make_key(req.question, SEARCH_MODE, cache_settings())
    data = answer_cache.get(key)
    cached = data is not None
    try:
        if not cached:
            if classify_intent(req.question) == "chat":
                data = answer_chat(req.question)
            else:
                # 검색기는 앱 시작 시 main.py의 lifespan에서 setup_search()로 준비된다.
                chunks = search(req.question, mode=SEARCH_MODE)
                data = answer_from_chunks(req.question, chunks)
                answer_cache.put(key, data, {"question": req.question})
    # 오류 종류별로 나눠서 안내한다.
    except openai.AuthenticationError as e:
        raise SharedException(
            "생성 모델 인증에 실패했습니다. API 키를 확인하세요.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="LLM_AUTH_ERROR",
        ) from e
    except openai.RateLimitError as e:
        raise SharedException(
            "요청이 많습니다. 잠시 후 다시 시도해 주세요.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="LLM_RATE_LIMIT",
        ) from e
    except openai.APITimeoutError as e:
        raise SharedException(
            "생성 모델 응답 시간이 초과되었습니다.",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            error_code="LLM_TIMEOUT",
        ) from e
    except openai.BadRequestError as e:
        raise SharedException(
            "생성 모델 요청 형식이 올바르지 않습니다.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="LLM_BAD_REQUEST",
        ) from e
    except openai.APIError as e:
        raise SharedException(
            "생성 모델 서버 오류가 발생했습니다.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="LLM_API_ERROR",
        ) from e
    return APIResponse.ok(
        data={**data, "question": req.question, "cached": cached},
        message="질의응답 생성이 완료되었습니다.",
    )