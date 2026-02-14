from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

class Question(BaseModel):
    """
    국제무역사 1급 CBT 문제 모델
    Pydantic v2 적용
    """
    id: int = Field(
        ...,
        description="문제 번호 (고유 식별자)"
    )
    subject: str = Field(
        ...,
        min_length=1,
        description="과목명 (예: 무역규범, 무역결제 등)"
    )
    context: Optional[str] = Field(
        None,
        description="지문 내용 (지문이 없는 경우 None)"
    )
    question_text: str = Field(
        ...,
        min_length=1,
        description="발문/문제 내용"
    )
    options: List[str] = Field(
        ...,
        description="보기 리스트 (객관식 선지)"
    )
    answer: str = Field(
        ...,
        description="정답 (텍스트에 정답이 있으면 options에 포함, 없으면 빈 문자열)"
    )
    explanation: str = Field(
        ...,
        description="해설"
    )
    page_number: int = Field(
        ...,
        description="원본 PDF 페이지 번호 (1-based). 파서가 직접 주입."
    )

    @field_validator('options')
    @classmethod
    def validate_options_length(cls, v: List[str]) -> List[str]:
        """
        검증 로직 1: 보기는 최소 2개 이상이어야 한다.
        """
        if len(v) < 2:
            raise ValueError("보기(options)는 최소 2개 이상의 항목이 필요합니다.")
        return v

    @model_validator(mode='after')
    def validate_answer_in_options(self) -> 'Question':
        """
        검증 로직 2: 정답이 존재하는 경우, 반드시 보기 리스트 안에 있어야 한다.
        정답이 빈 문자열("")인 경우는 허용한다 (PDF에 정답 미기재).
        """
        if self.answer and self.answer not in self.options:
            raise ValueError(f"정답('{self.answer}')이 보기 리스트({self.options})에 존재하지 않습니다.")
        return self
