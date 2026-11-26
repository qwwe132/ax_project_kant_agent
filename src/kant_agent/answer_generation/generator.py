import json

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from kant_agent.answer_generation.schemas import CitedAnswerOutput
from kant_agent.answer_generation.sources import SOURCES

load_dotenv()

# 생성 모델과 프롬프트 버전 (평가 기록·보고서에 남긴다)
# SYSTEM_PROMPT, INTENT_PROMPT, CHAT_PROMPT, TONE_RULES 중
# 하나라도 고치면 PROMPT_VERSION을 올린다.
MODEL_NAME = "gpt-6-luna"
PROMPT_VERSION = "v3"
MAX_TOKENS = 1000  # 출력 한도 (추론 토큰 포함, 실측 최대 약 370)

NO_EVIDENCE_MESSAGE = (
    "흐음… 짐의 서고에도 그런 기록은 없구나. 운영 담당자에게 직접 물어보거라."
)

# 규정 답변과 일반 대화가 함께 쓰는 마왕 말투 규칙
TONE_RULES = """
    [말투 규칙]
    - 자신을 "짐"이라 부르고, 질문자를 "인간" 또는 "용사여"라고 부르세요.
    - "~하거라", "~느니라", "~로다", "~구나" 같은 고풍스럽고 위엄 있는 반말을 쓰세요.
    - 여유롭고 약간 오만한 태도를 유지하되, 질문자를 모욕하거나 욕하지 마세요.
    - 웃음("크크큭", "훗", "크하하하!", "후후후…")은 필수가 아닙니다. 세 번에 한 번 정도만 쓰세요.
    - 첫마디는 정해진 감탄사를 반복하지 말고, 질문 내용에 맞춰 마왕다운 한마디를 그때그때 지어내거나 첫마디 없이 바로 본론으로 시작하세요.
      (예를 들어 지각 질문이면 "시간을 우습게 보는구나,", 서류 질문이면 "증표가 필요하단 말이지," 처럼)
"""

SYSTEM_PROMPT = (
    """
    당신은 KANT 교육과정 규정을 안내하는 마왕 "어둠의 에이타니"입니다.
    반드시 아래 제공된 [참고 규정 문맥]에 포함된 사실만을 근거로 답변하세요.
"""
    + TONE_RULES
    + """
    - 말투보다 정보가 우선입니다. 시간·날짜·숫자·서류 이름은 문맥 그대로 정확히 쓰고, 답변은 2~4문장으로 짧게 쓰세요.

    [작성 규칙]
    1. 문맥에 근거가 전혀 없다면 추측하지 말고 answer에 "{no_evidence}" 라고 작성하고 cited_numbers는 빈 리스트 ([])로 반환하세요.
    2. 답변 문장 끝에는 반드시 근거가 된 문맥 번호(예: [1], [2])를 표기하세요.
    3. 실제 인용한 문맥 번호만 cited_numbers에 정수로 포함하세요.

    [참고 규정 문맥]
    {context}
"""
)

# 교안 4장 4강: 의도 분류(Intent Classifier) 프롬프트
INTENT_PROMPT = """
    당신은 KANT 챗봇의 질문 분류기입니다.
    사용자의 입력을 분석하여 아래 2가지 라벨 중 정확히 하나만 출력하세요.
    어떠한 추가 설명이나 공백 없이 오직 라벨 단어만 출력해야 합니다.

    [분류 라벨]
    - rules: 무언가를 알고 싶어 묻는 모든 질문. 출결, 공가, 휴가, 과제, 시간표, 시설, 서류 발급, 지원금, 수료, LMS, 주변 식당 등 KANT 교육과정과 수강 생활에 관한 질문을 포함합니다.
    - chat: 정보를 묻지 않는 인사, 감사, 감탄, 챗봇에게 누구인지 묻기, 챗봇의 말에 대한 반응이나 되묻기(예: 뭐라고?, 왜 그래?, 진짜?) 같은 가벼운 잡담

    [판단 기준]
    - 인사와 질문이 함께 있으면 rules로 분류하세요.
    - 애매하면 rules로 분류하세요.
"""

# 일반 대화(chat) 전용 프롬프트
CHAT_PROMPT = (
    """
    당신은 KANT 교육과정 수강생을 돕는 마왕 "어둠의 에이타니"입니다.
    인사나 가벼운 잡담에 응답하세요.
"""
    + TONE_RULES
    + """
    [대화 규칙]
    - 규정·일정·시간·숫자 같은 정보는 절대 지어내지 마세요.
    - 1~2문장으로 짧게 답하고, KANT 생활이나 규정에 대해 물어보라고 권하세요.
"""
)


def _format_numbered_context(docs: list[Document]) -> str:
    blocks = []
    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata
        header = (
            f"[{idx}] 문서ID: {meta.get('document_id')}"
            f" | 위치: {meta.get('source_location')}"
        )
        blocks.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


def generate_answer(question: str, docs: list[Document]) -> CitedAnswerOutput:
    """번호 문맥 주입 -> LLM 구조화 생성을 수행합니다."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{question}"),
        ]
    )
    model = init_chat_model(
        model=MODEL_NAME,
        model_provider="openai",
        reasoning_effort="low",
        max_tokens=MAX_TOKENS,
    )
    structured_llm = model.with_structured_output(CitedAnswerOutput)
    chain = prompt | structured_llm

    return chain.invoke(
        {
            "context": _format_numbered_context(docs),
            "question": question,
            "no_evidence": NO_EVIDENCE_MESSAGE,
        }
    )


def answer_question(question: str, docs: list[Document]) -> dict:
    """문맥 주입 -> 구조화 생성 -> 인용 검증 -> status 판정을 수행합니다."""
    if not docs:
        return {
            "question": question,
            "status": "no_evidence",
            "answer": NO_EVIDENCE_MESSAGE,
            "citations": [],
            "retrieved_count": 0,
        }

    result = generate_answer(question, docs)

    # 후처리 - 실제 존재하는 문맥 번호만 메타데이터로 역매핑
    citations = []
    for num in result.cited_numbers:
        if 1 <= num <= len(docs):
            meta = docs[num - 1].metadata
            source = SOURCES.get(meta.get("document_id"), {})
            citations.append(
                {
                    "ref_number": num,
                    "document_id": meta.get("document_id"),
                    "chunk_id": meta.get("chunk_id"),
                    "source_path": meta.get("source_path"),
                    "source_location": meta.get("source_location"),
                    "title": source.get("title"),
                    "source_url": source.get("url"),
                }
            )

    if citations:
        status = "ok"
        answer = result.answer
    else:
        status = "no_evidence"
        answer = NO_EVIDENCE_MESSAGE

    return {
        "question": question,
        "status": status,
        "answer": answer,
        "raw_answer": result.answer,
        "citations": citations,
        "retrieved_count": len(docs),
    }


def answer_from_chunks(question: str, chunks: list[dict]) -> dict:
    """dict 형태 청크(샘플, 하네스 입력)를 Document로 바꿔 답변합니다."""
    docs = [Document(page_content=chunk["text"], metadata=chunk) for chunk in chunks]
    return answer_question(question, docs)


def classify_intent(question: str) -> str:
    """질문을 rules(규정 질문) / chat(일반 대화)으로 분류합니다. (교안 4장 4강)"""
    prompt = ChatPromptTemplate.from_messages(
        [("system", INTENT_PROMPT), ("human", "{question}")]
    )
    model = init_chat_model(
        model=MODEL_NAME,
        model_provider="openai",
        reasoning_effort="low",
        max_tokens=MAX_TOKENS,
    )
    chain = prompt | model | StrOutputParser()
    intent = chain.invoke({"question": question}).strip()
    # 애매하면 규정 질문으로 처리한다. (검색 결과가 없으면 근거 없음 안내로 끝난다)
    return "chat" if intent == "chat" else "rules"


def answer_chat(question: str) -> dict:
    """인사 및 잡담에 마왕 말투로 답합니다. 검색과 인용 없이 답합니다."""
    prompt = ChatPromptTemplate.from_messages(
        [("system", CHAT_PROMPT), ("human", "{question}")]
    )
    model = init_chat_model(
        model=MODEL_NAME,
        model_provider="openai",
        reasoning_effort="low",
        max_tokens=MAX_TOKENS,
    )
    chain = prompt | model | StrOutputParser()
    return {
        "question": question,
        "status": "chat",
        "answer": chain.invoke({"question": question}).strip(),
        "citations": [],
        "retrieved_count": 0,
    }


if __name__ == "__main__":
    sample_docs = [
        Document(
            page_content="평일 입실 마감은 09:10입니다. 09:10 이후 입실하면 지각으로 처리합니다.",
            metadata={
                "document_id": "SAMPLE-001",
                "chunk_id": "SAMPLE-001-001",
                "source_path": "data/sample/attendance.md",
                "source_location": "입실 기준",
            },
        ),
        Document(
            page_content="본인의 질병으로 진료받아 공가를 신청할 때는 진료일과 질병코드가 적힌 진료확인서를 제출해야 합니다.",
            metadata={
                "document_id": "SAMPLE-002",
                "chunk_id": "SAMPLE-002-001",
                "source_path": "data/sample/excused-absence.md",
                "source_location": "질병 공가",
            },
        ),
    ]

    # 1) 근거 있음 -> ok
    print(answer_question("지각 기준이 몇 시야?", sample_docs))
    # 2) 검색 결과 없음 -> no_evidence (LLM 호출 안 함)
    print(answer_question("지각 기준이 몇 시야?", []))
    # 3) 문서와 무관한 질문 -> no_evidence
    print(answer_question("회의실 예약은 어떻게 해?", sample_docs))
    # 4) dict 청크 입력 (하네스와 같은 형식)
    chunks = json.loads(
        open("data/fixtures/sample-chunks.json", encoding="utf-8").read()
    )
    print(answer_from_chunks("지각 기준이 몇 시야?", chunks))
