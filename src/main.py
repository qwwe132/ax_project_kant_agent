from fastapi import FastAPI

from kant_agent.answer_generation.router import router as chatbot_router
from kant_agent.shared.core.exception_handlers import (
    register_exception_handlers,
)

app = FastAPI(
    title="KANT AGENT API",
    description="부트캠프 교육과정 규정 RAG 질의응답",
    version="0.1.0",
)

register_exception_handlers(app)

# 라우터 등록
app.include_router(chatbot_router)