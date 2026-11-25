import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kant_agent.answer_generation.router import router as chatbot_router
from kant_agent.search import service as search_service
from kant_agent.shared.core.exception_handlers import (
    register_exception_handlers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 검색기(BM25·벡터 연결·재정렬 모델)는 서버 시작 시 1회만 준비한다.
    # 재정렬 모델 로드 때문에 시작에 수십 초가 걸리지만, 첫 질문은 빨라진다.
    search_service.setup_search(
        os.getenv("SEARCH_COLLECTION", search_service.COLLECTION_NAME),
        os.getenv("SEARCH_INDEX_VERSION", "local"),
    )
    yield


app = FastAPI(
    title="KANT AGENT API",
    description="부트캠프 교육과정 규정 RAG 질의응답",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

# 라우터 등록
app.include_router(chatbot_router)
