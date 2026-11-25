from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    """질의 응답 API 요청 DTO"""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(
        min_length=1,
        max_length=500,
        description="사용자 질문",
        examples=["몇 시부터 지각이야?"],
    )


class CitedAnswerOutput(BaseModel):
    """LLM 모델 Structured Output 전용 응답 스키마"""

    answer: str = Field(
        description="제공된 문맥만을 근거로 작성된 답변 (문장 끝에 [1], [2] 인용 표기)"
    )
    cited_numbers: list[int] = Field(
        default_factory=list,
        description="실제 인용된 문맥 번호 배열",
    )
