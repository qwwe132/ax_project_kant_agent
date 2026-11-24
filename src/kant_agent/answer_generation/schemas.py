from pydantic import BaseModel, Field


class CitedAnswerOutput(BaseModel):
    """LLM 모델 Structured Output 전용 응답 스키마"""

    answer: str = Field(
        description="제공된 문맥만을 근거로 작성된 답변 (문장 끝에 [1], [2] 인용 표기)"
    )
    cited_numbers: list[int] = Field(
        default_factory=list,
        description="실제 인용된 문맥 번호 배열",
    )
