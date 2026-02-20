"""
api/routes.py — FastAPI 엔드포인트
"""

import asyncio
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

import config
from api.sample_questions import SAMPLE_QUESTIONS
import api.session as session

# Core Logic Imports (Relative paths handled by package structure)
from trade_license_cbt.models.question_model import Question
from trade_license_cbt.models.session_state import ExamState
from trade_license_cbt.services.exam_service import (
    calculate_score, get_incorrect_questions, 
    calculate_subject_scores, is_passed
)
from trade_license_cbt.services.pdf_parser import (
    parse_pdf, parse_answer_pdf, merge_answers, reset_client
)

router = APIRouter()

# ── Pydantic request bodies ──────────────────────────────────────────────────

class ApiKeyBody(BaseModel):
    api_key: str

class SaveAnswerBody(BaseModel):
    question_id: int
    answer: str

class StartExamBody(BaseModel):
    subjects: list[str] = []

class NavigateBody(BaseModel):
    index: int = 0


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

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/api/set-api-key")
async def set_api_key(body: ApiKeyBody):
    key = body.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API 키가 비어 있습니다.")
    if not key.startswith(("sk-", "sk-proj-")):
        raise HTTPException(status_code=400, detail="올바른 OpenAI API 키 형식이 아닙니다 (sk-... 형식).")
    session.put("api_key", key)
    os.environ["OPENAI_API_KEY"] = key
    reset_client()
    return {"ok": True}


@router.post("/api/parse-pdf")
async def api_parse_pdf(file: UploadFile = File(...)):
    if not session.get("api_key"):
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF 파일이 너무 큽니다 (최대 50MB).")
    try:
        questions = await asyncio.to_thread(parse_pdf, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail="AI 서비스 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )
    if not questions:
        raise HTTPException(status_code=422, detail="문제를 추출하지 못했습니다. PDF 형식을 확인해 주세요.")

    session.put("parsed_questions", questions)
    return {"count": len(questions), "ok": True}


@router.post("/api/parse-answer")
async def api_parse_answer(file: UploadFile = File(...)):
    if not session.get("api_key"):
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF 파일이 너무 큽니다 (최대 50MB).")
    try:
        answers = await asyncio.to_thread(parse_answer_pdf, file_bytes)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not answers:
        raise HTTPException(status_code=422, detail="답안을 추출하지 못했습니다.")

    session.put("parsed_answers", answers)
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
        "api_key_set": bool(session.get("api_key")),
    }


@router.post("/api/start-exam")
async def start_exam(body: StartExamBody):
    parsed_q: list[Question] = session.get("parsed_questions", [])
    parsed_a: list[dict] = session.get("parsed_answers", [])

    if not parsed_q:
        raise HTTPException(status_code=400, detail="파싱된 문제가 없습니다.")

    final_questions = merge_answers(parsed_q, parsed_a) if parsed_a else parsed_q

    if body.subjects:
        final_questions = [q for q in final_questions if q.subject in body.subjects]

    if not final_questions:
        raise HTTPException(status_code=400, detail="선택된 과목의 문제가 없습니다.")

    session.put("questions", final_questions)
    session.put("exam_state", ExamState())
    return {"total": len(final_questions), "ok": True}


@router.post("/api/retry-exam")
async def retry_exam():
    questions: list[Question] = session.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="문제가 없습니다.")
    session.put("exam_state", ExamState())
    return {"total": len(questions), "ok": True}


@router.post("/api/start-sample-exam")
async def start_sample_exam():
    session.put("questions", SAMPLE_QUESTIONS)
    session.put("exam_state", ExamState())
    return {"total": len(SAMPLE_QUESTIONS), "ok": True}


@router.get("/api/question/{index}")
async def get_question(index: int):
    questions: list[Question] = session.get("questions", [])
    if not questions or not (0 <= index < len(questions)):
        raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")
    
    q = questions[index]
    exam_state: ExamState = session.get("exam_state")
    saved_answer = exam_state.user_answers.get(q.id, "") if exam_state else ""
    
    d = _question_to_dict(q)
    d.update({"saved_answer": saved_answer, "index": index, "total": len(questions)})
    return d


@router.get("/api/exam-state")
async def get_exam_state():
    exam_state: ExamState = session.get("exam_state")
    questions = session.get("questions", [])
    if not exam_state:
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
    exam_state: ExamState = session.get("exam_state")
    if not exam_state:
        raise HTTPException(status_code=404, detail="시험 세션이 없습니다.")
    if exam_state.is_submitted:
        raise HTTPException(status_code=400, detail="이미 제출된 시험입니다.")

    if body.answer:
        exam_state.user_answers[body.question_id] = body.answer
    else:
        exam_state.user_answers.pop(body.question_id, None)
    return {"ok": True, "answered_count": len(exam_state.user_answers)}


@router.post("/api/navigate")
async def navigate(body: NavigateBody):
    exam_state: ExamState = session.get("exam_state")
    questions = session.get("questions", [])
    if not exam_state:
        raise HTTPException(status_code=404, detail="시험 세션이 없습니다.")
    if exam_state.is_submitted:
        raise HTTPException(status_code=400, detail="이미 제출된 시험입니다.")

    idx = max(0, min(body.index, len(questions) - 1))
    exam_state.current_quest_index = idx
    return {"index": idx, "ok": True}


@router.post("/api/submit-exam")
async def submit_exam():
    exam_state: ExamState = session.get("exam_state")
    questions = session.get("questions", [])
    if not exam_state or not questions:
        raise HTTPException(status_code=400, detail="시험 세션이 없습니다.")
    
    exam_state.is_submitted = True
    score = calculate_score(questions, exam_state.user_answers)
    incorrect = get_incorrect_questions(questions, exam_state.user_answers)
    
    session.put("final_score", score)
    session.put("incorrect_questions", incorrect)
    return {"score": score, "ok": True}


@router.get("/api/results")
async def get_results():
    score = session.get("final_score", 0.0)
    questions = session.get("questions", [])
    incorrect = session.get("incorrect_questions", [])
    exam_state: ExamState = session.get("exam_state")

    if not questions or not exam_state:
        raise HTTPException(status_code=404, detail="결과 정보가 없습니다.")
    if not exam_state.is_submitted:
        raise HTTPException(status_code=400, detail="시험이 아직 제출되지 않았습니다.")

    incorrect_data = []
    for q in incorrect:
        d = _question_to_dict(q)
        d["user_answer"] = exam_state.user_answers.get(q.id, "")
        incorrect_data.append(d)

    return {
        "score": score,
        "passed": is_passed(score),
        "total": len(questions),
        "correct_count": len(questions) - len(incorrect),
        "incorrect_count": len(incorrect),
        "unanswered_count": len(questions) - len(exam_state.user_answers),
        "subject_scores": calculate_subject_scores(questions, exam_state.user_answers),
        "incorrect_questions": incorrect_data,
    }


@router.post("/api/reset")
async def reset_session():
    session.reset()
    return {"ok": True}
