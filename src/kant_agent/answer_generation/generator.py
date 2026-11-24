from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from kant_agent.answer_generation.schemas import CitedAnswerOutput

load_dotenv()

NO_EVIDENCE_MESSAGE = (
    "제공된 규정에서 관련 내용을 찾을 수 없습니다. 운영 담당자에게 확인해 주세요."
)

SYSTEM_PROMPT = """
    당신은 KANT 교육과정 규정을 안내하는 AI 어시스턴트입니다.
    반드시 아래 제공된 [참고 규정 문맥]에 포함된 사실만을 근거로 답변하세요.

    [작성 규칙]
    1. 문맥에 근거가 전혀 없다면 추측하지 말고 answer에 "제공된 규정에서 관련 내용을 찾을 수 없습니다. 운영 담당자에게 확인해 주세요." 라고 작성하고 cited_numbers는 빈 리스트 ([])로 반환하세요.
    2. 답변 문장 끝에는 반드시 근거가 된 문맥 번호(예: [1], [2])를 표기하세요.
    3. 실제 인용한 문맥 번호만 cited_numbers에 정수로 포함하세요.

    [참고 규정 문맥]
    {context}
"""


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
        model="gpt-6-luna",
        model_provider="openai",
        reasoning_effort="low",
    )
    structured_llm = model.with_structured_output(CitedAnswerOutput)
    chain = prompt | structured_llm

    return chain.invoke(
        {
            "context": _format_numbered_context(docs),
            "question": question,
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
            citations.append(
                {
                    "ref_number": num,
                    "document_id": meta.get("document_id"),
                    "chunk_id": meta.get("chunk_id"),
                    "source_path": meta.get("source_path"),
                    "source_location": meta.get("source_location"),
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
        "citations": citations,
        "retrieved_count": len(docs),
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
