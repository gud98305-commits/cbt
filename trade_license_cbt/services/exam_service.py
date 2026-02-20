"""
services/exam_service.py

시험 채점 및 결과 분석 비즈니스 로직.
순수 Python 함수로 구성 — UI 코드, 전역 상태 변경 없음.
"""

from collections import defaultdict
from typing import Dict, List

from trade_license_cbt.models.question_model import Question


def calculate_score(
    questions: List[Question],
    user_answers: Dict[int, str],
) -> float:
    """
    사용자 답안을 채점하여 100점 만점 환산 점수를 반환한다.

    정답 판정 기준: question.answer == user_answers.get(question.id)
    응답하지 않은 문제(키 없음)는 오답으로 처리.

    Args:
        questions:    채점 대상 Question 리스트.
        user_answers: 사용자 답안지. {question.id: 선택한 보기 문자열}

    Returns:
        0.0 ~ 100.0 범위의 점수 (소수점 둘째 자리 반올림).
        questions가 빈 리스트이면 0.0 반환.
    """
    if not questions:
        return 0.0

    correct_count = sum(
        1
        for q in questions
        if q.answer and user_answers.get(q.id) == q.answer
    )

    return round(correct_count / len(questions) * 100, 2)


def get_incorrect_questions(
    questions: List[Question],
    user_answers: Dict[int, str],
) -> List[Question]:
    """
    오답 문제 리스트를 반환한다 (오답 노트용).

    오답 판정 기준:
    - 사용자가 선택한 답이 정답과 다른 경우
    - 사용자가 아예 응답하지 않은 경우 (미응답 포함)
    - question.answer가 빈 문자열("")인 문제는 정답 정보가 없으므로 제외

    Args:
        questions:    전체 Question 리스트.
        user_answers: 사용자 답안지. {question.id: 선택한 보기 문자열}

    Returns:
        오답 Question 리스트. 원본 순서 유지.
    """
    incorrect: List[Question] = []

    for q in questions:
        if not q.answer:
            # 정답 정보 자체가 없는 문제는 채점 불가 → 제외
            continue
        if user_answers.get(q.id) != q.answer:
            incorrect.append(q)

    return incorrect


def calculate_subject_scores(
    questions: List[Question],
    user_answers: Dict[int, str],
) -> List[Dict[str, object]]:
    """
    과목별 점수를 계산하여 반환한다.

    Returns:
        [{"subject": str, "total": int, "correct": int,
          "incorrect": int, "unanswered": int, "score": float}, ...]
        과목명 기준 정렬.
    """
    buckets: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "correct": 0, "incorrect": 0, "unanswered": 0}
    )

    for q in questions:
        subj = q.subject or "기타"
        buckets[subj]["total"] += 1

        user_ans = user_answers.get(q.id)
        if not q.answer:
            # 정답 정보 없는 문제는 채점 제외
            continue
        if user_ans is None:
            buckets[subj]["unanswered"] += 1
        elif user_ans == q.answer:
            buckets[subj]["correct"] += 1
        else:
            buckets[subj]["incorrect"] += 1

    result = []
    for subj in sorted(buckets):
        b = buckets[subj]
        scorable = b["correct"] + b["incorrect"] + b["unanswered"]
        score = round(b["correct"] / scorable * 100, 1) if scorable else 0.0
        result.append({"subject": subj, **b, "score": score})
    return result


def is_passed(score: float, pass_score: float = 60.0) -> bool:
    """
    합격 여부를 반환한다.

    Args:
        score:      calculate_score()가 반환한 점수 (0.0 ~ 100.0).
        pass_score: 합격 기준 점수 (기본값 60.0점).

    Returns:
        score >= pass_score 이면 True, 아니면 False.
    """
    return score >= pass_score
