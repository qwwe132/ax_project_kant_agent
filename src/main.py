import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from kant_agent.answer_generation.router import router as chatbot_router
from kant_agent.search import service as search_service
from kant_agent.shared.core.exception_handlers import (
    register_exception_handlers,
)
from kant_agent.shared.core.logger import get_logger

# 아래 SEARCH_* 환경변수를 읽기 전에 .env를 먼저 불러온다.
load_dotenv()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 검색기(BM25·벡터 연결·재정렬 모델)는 서버 시작 시 1회만 준비한다.
    # 재정렬 모델 로드 때문에 시작에 수십 초가 걸리지만, 첫 질문은 빨라진다.
    # (SEARCH_LOAD_RERANKER=false면 로드를 미루고 첫 C 모드 검색 때 로드한다.)
    # BM25 청크는 여기서 고정되므로 재색인할 때는
    # API 중지 → build_index 실행 → API 재시작 순서를 지킨다.
    # .env.example을 복사해 빈 값으로 남은 경우도 기본값을 쓴다.
    collection = os.getenv("SEARCH_COLLECTION") or search_service.COLLECTION_NAME
    version = os.getenv("SEARCH_INDEX_VERSION") or "local"
    load_reranker = (os.getenv("SEARCH_LOAD_RERANKER") or "true").lower() != "false"
    try:
        search_service.setup_search(
            collection,
            version,
            load_reranker=load_reranker,
        )
    except Exception:
        logger.exception("[startup] 검색기 준비 실패 (컬렉션: %s)", collection)
        raise
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
app.mount(
    "/library",
    StaticFiles(directory=Path(__file__).parent / "ui" / "library", html=True),
    name="library",
)
