"""
api/routes.py — FastAPI 엔드포인트
"""

import os
import sys

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# trade_license_cbt 패키지 경로 등록
_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trade_license_cbt")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from models.question_model import Question
from models.session_state import ExamState
from services.exam_service import calculate_score, get_incorrect_questions, calculate_subject_scores, is_passed
from services.pdf_parser import parse_pdf, parse_answer_pdf, merge_answers, reset_client

import api.session as session

router = APIRouter()

# ── 샘플 문제 ────────────────────────────────────────────────────────────────
_SAMPLE_QUESTIONS: list[Question] = [
    Question(id=1, subject="무역규범",
             question_text="무역계약에서 청약(Offer)의 효력이 소멸되는 경우가 아닌 것은?",
             options=["① 청약의 철회", "② 청약의 거절", "③ 반대청약", "④ 청약의 공시"],
             answer="④ 청약의 공시",
             explanation="청약 효력 소멸 사유는 철회, 거절, 반대청약, 기간만료 등이며 '공시'는 해당되지 않습니다.",
             page_number=1),
    Question(id=2, subject="무역규범",
             question_text="인코텀즈(Incoterms) 2020에서 매도인의 위험 부담이 가장 큰 조건은?",
             options=["① EXW", "② FCA", "③ CIF", "④ DDP"],
             answer="④ DDP",
             explanation="DDP(Delivered Duty Paid)는 목적지까지의 모든 비용과 위험을 매도인이 부담하는 조건입니다.",
             page_number=1),
    Question(id=3, subject="무역결제",
             question_text="신용장(L/C)에서 일람출급(Sight) 어음을 사용할 때 대금 지급 시기는?",
             options=["① 선적 후 30일", "② 서류 제시 즉시", "③ 만기일", "④ 선적일"],
             answer="② 서류 제시 즉시",
             explanation="일람출급 어음은 제시와 동시에 지급이 이루어집니다.",
             page_number=2),
    Question(id=4, subject="무역결제",
             question_text="추심결제(Collection) 방식 중 D/P(Documents against Payment)에 대한 설명으로 옳은 것은?",
             options=["① 인수 후 서류 인도", "② 지급 후 서류 인도", "③ 신용장 개설 필요", "④ 은행 지급 보증"],
             answer="② 지급 후 서류 인도",
             explanation="D/P는 수입상이 대금을 지급해야만 선적서류를 인도받을 수 있는 방식입니다.",
             page_number=2),
    Question(id=5, subject="무역물류",
             question_text="해상화물운송장(Sea Waybill)과 선하증권(B/L)의 차이점으로 옳은 것은?",
             options=["① 해상화물운송장은 유통성 있음", "② 선하증권은 권리증권임", "③ 해상화물운송장 원본 3통 발행", "④ 선하증권은 지시식 불가"],
             answer="② 선하증권은 권리증권임",
             explanation="선하증권(B/L)은 유통성 있는 권리증권이며, 해상화물운송장은 비유통성 서류입니다.",
             page_number=3),
    Question(id=6, subject="무역물류",
             question_text="컨테이너 운송에서 FCL(Full Container Load)에 대한 설명으로 옳은 것은?",
             options=["① 혼재화물 운송", "② 단일 화주가 컨테이너 전체 사용", "③ 소량 화물 전용", "④ 항공 전용 용어"],
             answer="② 단일 화주가 컨테이너 전체 사용",
             explanation="FCL은 한 화주가 컨테이너 하나를 전용으로 사용하는 방식입니다.",
             page_number=3),
    Question(id=7, subject="무역규범",
             question_text="WTO 분쟁해결기구(DSB)의 패널 보고서 채택 방식은?",
             options=["① 만장일치", "② 역전컨센서스(Negative Consensus)", "③ 단순다수결", "④ 의장 단독 결정"],
             answer="② 역전컨센서스(Negative Consensus)",
             explanation="WTO DSB는 보고서에 반대하는 전원 합의가 없으면 자동 채택되는 역전컨센서스 방식을 사용합니다.",
             page_number=4),
    Question(id=8, subject="무역영어",
             question_text="무역 서신에서 'We acknowledge receipt of your letter dated ~'의 의미로 옳은 것은?",
             options=["① 서신 발송 확인", "② 서신 수신 확인", "③ 주문 취소 통보", "④ 대금 청구"],
             answer="② 서신 수신 확인",
             explanation="'acknowledge receipt of'는 '~를 수령했음을 확인한다'는 뜻입니다.",
             page_number=4),
    Question(id=9, subject="무역결제",
             question_text="무역금융에서 포페이팅(Forfaiting)의 특징으로 옳은 것은?",
             options=["① 소구권(Recourse) 있음", "② 단기 금융(90일 이내)", "③ 무소구권(Without Recourse)", "④ 국내 거래 전용"],
             answer="③ 무소구권(Without Recourse)",
             explanation="포페이팅은 수출채권을 무소구 방식으로 매입하는 중장기 무역금융입니다.",
             page_number=5),
    Question(id=10, subject="무역물류",
             question_text="항공화물운송장(AWB)의 성격으로 옳은 것은?",
             options=["① 유통증권", "② 권리증권", "③ 비유통성 화물수취증", "④ 보험증권"],
             answer="③ 비유통성 화물수취증",
             explanation="AWB는 선하증권과 달리 유통성이 없으며 단순한 화물수취증 겸 운송계약서입니다.",
             page_number=5),
]


# ── Pydantic request bodies ──────────────────────────────────────────────────

class ApiKeyBody(BaseModel):
    api_key: str

class SaveAnswerBody(BaseModel):
    question_id: int
    answer: str

class StartExamBody(BaseModel):
    subjects: list[str] = []  # 빈 리스트 = 전체 선택


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _question_to_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "subject": q.subject,
        "context": q.context,
        "question_text": q.question_text,
        "options": q.options,
        "answer": q.answer,
        "explanation": q.explanation,
        "page_number": q.page_number,
    }


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.post("/api/set-api-key")
async def set_api_key(body: ApiKeyBody):
    session.set("api_key", body.api_key)
    os.environ["OPENAI_API_KEY"] = body.api_key
    reset_client()
    return {"ok": True}


@router.post("/api/parse-pdf")
async def api_parse_pdf(file: UploadFile = File(...)):
    api_key = session.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다.")
    file_bytes = await file.read()
    questions = parse_pdf(file_bytes)
    if not questions:
        raise HTTPException(status_code=422, detail="문제를 추출하지 못했습니다.")
    session.set("parsed_questions", questions)
    return {"count": len(questions), "ok": True}


@router.post("/api/parse-answer")
async def api_parse_answer(file: UploadFile = File(...)):
    api_key = session.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다.")
    file_bytes = await file.read()
    answers = parse_answer_pdf(file_bytes)
    if not answers:
        raise HTTPException(status_code=422, detail="답안을 추출하지 못했습니다.")
    session.set("parsed_answers", answers)
    return {"count": len(answers), "ok": True}


@router.get("/api/session-status")
async def session_status():
    pq: list[Question] = session.get("parsed_questions", [])
    pa: list[dict] = session.get("parsed_answers", [])
    subjects = sorted(set(q.subject for q in pq if q.subject)) if pq else []
    return {
        "question_count": len(pq),
        "answer_count": len(pa),
        "subjects": subjects,
        "api_key_set": bool(session.get("api_key", "")),
    }


@router.post("/api/start-exam")
async def start_exam(body: StartExamBody):
    parsed_q: list[Question] = session.get("parsed_questions", [])
    parsed_a: list[dict] = session.get("parsed_answers", [])

    if not parsed_q:
        raise HTTPException(status_code=400, detail="파싱된 문제가 없습니다.")

    if parsed_a:
        final_questions = merge_answers(parsed_q, parsed_a)
    else:
        final_questions = parsed_q

    # 과목 필터
    if body.subjects:
        final_questions = [q for q in final_questions if q.subject in body.subjects]

    if not final_questions:
        raise HTTPException(status_code=400, detail="선택된 과목의 문제가 없습니다.")

    session.set("questions", final_questions)
    session.set("exam_state", ExamState())
    session.set("final_score", 0.0)
    session.set("incorrect_questions", [])
    return {"total": len(final_questions), "ok": True}


@router.post("/api/retry-exam")
async def retry_exam():
    """현재 questions로 시험을 다시 시작 (결과 화면에서 '다시 풀기')."""
    questions: list[Question] = session.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="문제가 없습니다.")
    session.set("exam_state", ExamState())
    session.set("final_score", 0.0)
    session.set("incorrect_questions", [])
    return {"total": len(questions), "ok": True}


@router.post("/api/start-sample-exam")
async def start_sample_exam():
    session.set("questions", _SAMPLE_QUESTIONS)
    session.set("exam_state", ExamState())
    session.set("final_score", 0.0)
    session.set("incorrect_questions", [])
    return {"total": len(_SAMPLE_QUESTIONS), "ok": True}


@router.get("/api/question/{index}")
async def get_question(index: int):
    questions: list[Question] = session.get("questions", [])
    if not questions:
        raise HTTPException(status_code=404, detail="시험 문제가 없습니다.")
    if index < 0 or index >= len(questions):
        raise HTTPException(status_code=404, detail="유효하지 않은 인덱스입니다.")
    q = questions[index]
    exam_state: ExamState | None = session.get("exam_state")
    saved_answer = exam_state.user_answers.get(q.id, "") if exam_state else ""
    d = _question_to_dict(q)
    d["saved_answer"] = saved_answer
    d["index"] = index
    d["total"] = len(questions)
    return d


@router.get("/api/exam-state")
async def get_exam_state():
    exam_state: ExamState | None = session.get("exam_state")
    questions: list[Question] = session.get("questions", [])
    if exam_state is None:
        raise HTTPException(status_code=404, detail="시험 세션이 없습니다.")
    return {
        "current_quest_index": exam_state.current_quest_index,
        "user_answers": {str(k): v for k, v in exam_state.user_answers.items()},
        "is_submitted": exam_state.is_submitted,
        "start_time": exam_state.start_time,
        "total": len(questions),
        "answered_count": len(exam_state.user_answers),
        "question_ids": [q.id for q in questions],
    }


@router.post("/api/save-answer")
async def save_answer(body: SaveAnswerBody):
    exam_state: ExamState | None = session.get("exam_state")
    if exam_state is None:
        raise HTTPException(status_code=404, detail="시험 세션이 없습니다.")
    if body.answer:
        exam_state.user_answers[body.question_id] = body.answer
    else:
        exam_state.user_answers.pop(body.question_id, None)
    return {"ok": True, "answered_count": len(exam_state.user_answers)}


@router.post("/api/navigate")
async def navigate(body: dict):
    """현재 문제 인덱스 업데이트."""
    exam_state: ExamState | None = session.get("exam_state")
    questions: list[Question] = session.get("questions", [])
    if exam_state is None:
        raise HTTPException(status_code=404, detail="시험 세션이 없습니다.")
    idx = body.get("index", exam_state.current_quest_index)
    idx = max(0, min(idx, len(questions) - 1))
    exam_state.current_quest_index = idx
    return {"index": idx, "ok": True}


@router.post("/api/submit-exam")
async def submit_exam():
    exam_state: ExamState | None = session.get("exam_state")
    questions: list[Question] = session.get("questions", [])
    if exam_state is None or not questions:
        raise HTTPException(status_code=400, detail="시험 세션이 없습니다.")
    exam_state.is_submitted = True
    score = calculate_score(questions, exam_state.user_answers)
    incorrect = get_incorrect_questions(questions, exam_state.user_answers)
    session.set("final_score", score)
    session.set("incorrect_questions", incorrect)
    return {"score": score, "ok": True}


@router.get("/api/results")
async def get_results():
    score: float = session.get("final_score", 0.0)
    questions: list[Question] = session.get("questions", [])
    incorrect: list[Question] = session.get("incorrect_questions", [])
    exam_state: ExamState | None = session.get("exam_state")

    if not questions or exam_state is None:
        raise HTTPException(status_code=404, detail="결과 정보가 없습니다.")

    total = len(questions)
    answered = len(exam_state.user_answers)
    correct_count = total - len(incorrect)
    unanswered_count = total - answered
    passed = is_passed(score)
    subject_scores = calculate_subject_scores(questions, exam_state.user_answers)

    incorrect_data = []
    for q in incorrect:
        d = _question_to_dict(q)
        d["user_answer"] = exam_state.user_answers.get(q.id, "")
        incorrect_data.append(d)

    return {
        "score": score,
        "passed": passed,
        "total": total,
        "correct_count": correct_count,
        "incorrect_count": len(incorrect),
        "unanswered_count": unanswered_count,
        "subject_scores": subject_scores,
        "incorrect_questions": incorrect_data,
    }


@router.post("/api/reset")
async def reset_session():
    session.reset()
    return {"ok": True}


@router.get("/api/sample-questions")
async def get_sample_questions():
    return [_question_to_dict(q) for q in _SAMPLE_QUESTIONS]
