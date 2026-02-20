"""
services/pdf_parser.py

PDF 시험지 파싱 서비스.
Public API:
  - parse_pdf(file_bytes) -> List[Question]      : 문제 PDF 파싱
  - parse_answer_pdf(file_bytes) -> List[dict]    : 답지 PDF 파싱
  - merge_answers(questions, answers) -> List[Question] : 문제 + 답지 병합
  - reset_client() -> None                        : API 키 변경 시 클라이언트 리셋

설계 원칙:
- 페이지 배치 처리 (5페이지 단위) + 병렬 API 호출로 속도 최적화
- OpenAI JSON mode로 안정적 JSON 출력
- 답 텍스트 자동 매칭 (prefix, 번호 변환)
- 실패는 해당 배치만 스킵, 전체 중단 없음
- Streamlit 코드 절대 미포함
"""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from openai import OpenAI, RateLimitError, APIError
from pydantic import ValidationError

from models.question_model import Question

# ── 로거 설정 ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ── OpenAI 클라이언트 (지연 초기화) ──────────────────────────────────────────
_MODEL_NAME = "gpt-4o-mini"
_client: Optional[OpenAI] = None


def _get_client() -> Optional[OpenAI]:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY가 설정되지 않았습니다.")
        return None
    try:
        _client = OpenAI(api_key=api_key)
        logger.info(f"OpenAI 클라이언트 초기화 완료: {_MODEL_NAME}")
        return _client
    except Exception as e:
        logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        return None


def reset_client() -> None:
    """API 키 변경 시 클라이언트를 리셋하여 다음 호출에서 재초기화."""
    global _client
    _client = None


# ── 상수 ─────────────────────────────────────────────────────────────────────
_MIN_TEXT_LENGTH = 50
_PAGES_PER_BATCH = 5        # 한 번에 처리할 페이지 수
_MAX_WORKERS = 5             # 병렬 API 호출 수
_MAX_API_RETRIES = 3
_BACKOFF_BASE = 1.0

_CIRCLED_NUMBERS = {
    "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤",
    "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨", "10": "⑩",
}


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(file_bytes: bytes) -> List[Question]:
    """
    PDF 바이트 → Question 리스트.
    과목 헤더를 감지하여 구역별로 나누어 파싱함으로써 정확도를 높임.
    """
    if not file_bytes:
        logger.error("parse_pdf: file_bytes가 비어 있습니다.")
        return []
    if not _get_client():
        logger.error("parse_pdf: OpenAI 클라이언트 미초기화.")
        return []

    doc = None
    try:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"parse_pdf: PDF 열기 실패 - {e}")
            return []

        # 모든 텍스트 추출
        full_text_with_meta = ""
        for i in range(len(doc)):
            page_text = doc.load_page(i).get_text()
            full_text_with_meta += f"\n[PAGE {i+1}]\n{page_text}\n"

        # 과목 구역 감지 및 분할
        # 예: "제 1 과목", "무역규범", "1과목" 등
        sections = _split_text_by_subject(full_text_with_meta)
        
        all_questions: List[Question] = []
        
        # 각 구역별로 파싱 (병렬 처리)
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_map = {
                executor.submit(_extract_questions_from_text, section_text, subject_hint): idx
                for idx, (subject_hint, section_text) in enumerate(sections)
            }
            results = {}
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"구역 {idx} 처리 실패: {e}")
                    results[idx] = []

            for idx in sorted(results.keys()):
                all_questions.extend(results[idx])

        # 중복 ID 방지 및 정렬 (전체 순서 보장)
        # 만약 과목별로 1번부터 시작한다면, 내부적으로 고유 ID를 부여하거나 순서를 유지해야 함.
        logger.info(f"parse_pdf: 총 {len(all_questions)}개 문제 추출 완료")
        return all_questions

    finally:
        if doc is not None:
            doc.close()


def parse_answer_pdf(file_bytes: bytes) -> List[dict]:
    """
    답지 PDF 파싱. 과목 구역을 나누어 파싱하여 오매칭 방지.
    """
    if not file_bytes:
        return []
    
    doc = None
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for i in range(len(doc)):
            full_text += f"\n[PAGE {i+1}]\n{doc.load_page(i).get_text()}\n"
        
        sections = _split_text_by_subject(full_text)
        all_answers = []
        
        for subject_hint, section_text in sections:
            answers = _extract_answers_from_text(section_text, subject_hint)
            all_answers.extend(answers)
            
        return all_answers
    finally:
        if doc is not None:
            doc.close()

def _split_text_by_subject(text: str) -> List[tuple[str, str]]:
    """
    텍스트에서 과목 경계(예: 제1과목, 2교시 등)를 찾아 (과목명, 내용) 쌍으로 분할.
    """
    # 일반적인 과목 패턴: 제 N 과목, [과목명], [제N교시]
    # 실제 시험지 형식에 맞춰 정규식 조정 가능
    pattern = r"(제\s?\d\s?과목|제\s?\d\s?교시|[가-힣]{2,10}규범|[가-힣]{2,10}결제|[가-힣]{2,10}영어|[가-힣]{2,10}물류)"
    splits = re.split(pattern, text)
    
    sections = []
    current_subject = "일반"
    
    # 첫 번째 요소는 헤더 이전의 텍스트
    if splits[0].strip():
        sections.append((current_subject, splits[0].strip()))
        
    for i in range(1, len(splits), 2):
        current_subject = splits[i].strip()
        content = splits[i+1].strip() if i+1 < len(splits) else ""
        sections.append((current_subject, content))
        
    return sections

def _extract_questions_from_text(text: str, subject_context: str = "") -> List[Question]:
    """배치 텍스트 → OpenAI → Question 리스트 (과목 컨텍스트 포함)."""
    system_prompt = _build_system_prompt()
    user_input = f"현재 분석 중인 구역/과목: {subject_context}\n\n텍스트 내용:\n{text}"

    raw = _call_openai_with_retry(system_prompt, user_input)
    if raw is None: return []

    return _parse_response_to_questions(raw) or []

def _extract_answers_from_text(text: str, subject_context: str = "") -> List[dict]:
    """답지 텍스트 → OpenAI (과목 컨텍스트 포함)."""
    system_prompt = _build_answer_system_prompt()
    user_input = f"현재 분석 중인 답안 구역: {subject_context}\n\n텍스트 내용:\n{text}"

    raw = _call_openai_with_retry(system_prompt, user_input)
    if raw is None: return []

    cleaned = _clean_json_response(raw)
    try:
        data = json.loads(cleaned)
        answers = data.get("answers", data.get("items", []))
        # 각 답안에 과목 힌트 주입
        for a in answers:
            if not a.get("subject"):
                a["subject"] = subject_context
        return answers
    except:
        return []


def merge_answers(questions: List[Question], answers: List[dict]) -> List[Question]:
    """
    문제 리스트에 답지 데이터를 병합.
    (subject, id) 복합키로 매칭 → subject 없으면 id만으로 폴백.
    """
    # 1차: (subject_normalized, id) 매핑
    subject_map: Dict[tuple, dict] = {}
    id_only_map: Dict[int, dict] = {}
    for a in answers:
        if "id" not in a:
            continue
        aid = a["id"]
        subj = _normalize_subject(a.get("subject", ""))
        if subj:
            subject_map[(subj, aid)] = a
        id_only_map[aid] = a

    merged: List[Question] = []
    matched_count = 0

    for q in questions:
        q_subj = _normalize_subject(q.subject)
        info = subject_map.get((q_subj, q.id)) or id_only_map.get(q.id)

        if info:
            raw_answer = info.get("answer", "")
            explanation = info.get("explanation", "") or q.explanation
            matched = _match_answer_to_option(raw_answer, q.options)

            try:
                new_q = q.model_copy(update={
                    "answer": matched,
                    "explanation": explanation,
                })
                merged.append(new_q)
                if matched:
                    matched_count += 1
            except Exception as e:
                logger.warning(f"Q{q.id}: 답 병합 실패 — {e}")
                merged.append(q)
        else:
            merged.append(q)

    logger.info(f"merge_answers: {matched_count}/{len(questions)}개 답 매칭 성공")
    return merged


def _normalize_subject(s: str) -> str:
    """과목명 정규화 (공백·특수문자 제거, 소문자)."""
    if not s:
        return ""
    return re.sub(r"[\s·‧\-_]", "", s).lower()


# ── 내부 함수 ─────────────────────────────────────────────────────────────────

def _match_answer_to_option(answer_text: str, options: List[str]) -> str:
    """답지의 답 텍스트를 문제의 보기와 매칭."""
    if not answer_text:
        return ""
    answer_text = answer_text.strip()

    # 1. Exact match
    if answer_text in options:
        return answer_text

    # 2. Prefix match (e.g., "④" → "④ DDP")
    for opt in options:
        if opt.strip().startswith(answer_text):
            return opt

    # 3. Number → 원문자 변환 (e.g., "4" → "④" → prefix match)
    num_match = re.search(r"(\d+)", answer_text)
    if num_match:
        symbol = _CIRCLED_NUMBERS.get(num_match.group(1), "")
        if symbol:
            if symbol in options:
                return symbol
            for opt in options:
                if opt.strip().startswith(symbol):
                    return opt

    logger.debug(f"매칭 실패: answer={answer_text!r}")
    return ""


def _extract_questions_from_text(text: str) -> List[Question]:
    """배치 텍스트 → OpenAI → Question 리스트."""
    system_prompt = _build_system_prompt()

    raw = _call_openai_with_retry(system_prompt, text)
    if raw is None:
        return []

    questions = _parse_response_to_questions(raw)
    if questions is not None:
        return questions

    # JSON 파싱 실패 → 재시도
    raw = _call_openai_with_retry(
        system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.", text,
    )
    if raw:
        questions = _parse_response_to_questions(raw)
        if questions is not None:
            return questions

    logger.error("_extract_questions_from_text: 2회 모두 실패")
    return []


def _parse_response_to_questions(raw_response: str) -> Optional[List[Question]]:
    """LLM JSON → Question 리스트. 파싱 실패 시 None."""
    cleaned = _clean_json_response(raw_response)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    # {"questions": [...]} 또는 [...] 둘 다 처리
    if isinstance(data, dict):
        data = data.get("questions", data.get("items", []))
    if not isinstance(data, list):
        return None

    questions: List[Question] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue

        # ── 필수 필드 누락 시 스킵 (출력 토큰 부족으로 빈 값 발생 대비) ──
        if not item.get("question_text", "").strip():
            continue
        if not item.get("options"):
            continue

        # ── answer가 options에 없으면 자동 매칭 시도 ──
        if item.get("answer") and item.get("options") and isinstance(item["options"], list):
            raw_answer = str(item["answer"]).strip()
            if raw_answer not in item["options"]:
                item["answer"] = _match_answer_to_option(raw_answer, item["options"])

        # page_number 기본값
        if not item.get("page_number"):
            item["page_number"] = 0

        try:
            q = Question(**item)
            questions.append(q)
        except (ValidationError, TypeError) as e:
            logger.warning(f"item[{idx}]: Question 생성 실패 — {e}")
            continue

    return questions


def _extract_answers_from_text(text: str) -> List[dict]:
    """답지 텍스트 → OpenAI → 답안 dict 리스트."""
    system_prompt = _build_answer_system_prompt()

    raw = _call_openai_with_retry(system_prompt, text)
    if raw is None:
        return []

    cleaned = _clean_json_response(raw)
    if not cleaned:
        # 재시도
        raw = _call_openai_with_retry(
            system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.", text,
        )
        if raw:
            cleaned = _clean_json_response(raw)
        if not cleaned:
            return []

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    # {"answers": [...]} 또는 [...] 처리
    if isinstance(data, dict):
        data = data.get("answers", data.get("items", []))
    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        if isinstance(item, dict) and "id" in item and "answer" in item:
            item["id"] = int(item["id"]) if not isinstance(item["id"], int) else item["id"]
            results.append(item)
    return results


# ── 프롬프트 ─────────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    """문제 파싱용 시스템 프롬프트."""
    return (
        "너는 한국 자격증 시험 PDF 문제지 텍스트 파서다.\n"
        "\n"
        "[임무]\n"
        "제공된 텍스트에서 객관식 문제를 모두 찾아 JSON으로 반환하라.\n"
        "\n"
        "[출력 형식]\n"
        '반드시 {"questions": [...]} 형태의 JSON 객체로만 응답하라.\n'
        "마크다운, 설명, 인사말 금지.\n"
        "\n"
        "[각 문제 객체의 필드]\n"
        "{\n"
        '  "id": (int) 문제 번호,\n'
        '  "subject": (str) 과목명. 없으면 "General",\n'
        '  "context": (str|null) 지문. 없으면 null,\n'
        '  "question_text": (str) 문제 본문,\n'
        '  "options": (list[str]) 보기 목록. 원문 그대로,\n'
        '  "answer": (str) 정답. 텍스트에 정답이 명시되어 있을 때만 해당 보기의 전체 텍스트. 없으면 "",\n'
        '  "explanation": (str) 해설. 없으면 "",\n'
        '  "page_number": (int) [PAGE X] 마커의 X값\n'
        "}\n"
        "\n"
        "[규칙]\n"
        '1. 문제가 없으면 {"questions": []}을 반환하라.\n'
        "2. 보기 번호 형식은 원문을 따르라 (①②③④ 등).\n"
        "3. 하나의 지문에 여러 문제가 딸린 경우, 각 문제마다 context에 동일 지문을 넣어라.\n"
        "4. options 배열 원소 수는 원문 보기 개수와 정확히 일치해야 한다.\n"
        "5. question_text에는 보기를 포함하지 마라.\n"
        "6. 텍스트에 [PAGE X] 마커가 있으면 X를 page_number로 사용하라.\n"
        "7. answer에는 반드시 options 리스트 안의 전체 텍스트를 넣어라. 정답을 모르면 빈 문자열."
    )


def _build_answer_system_prompt() -> str:
    """답지 파싱용 시스템 프롬프트."""
    return (
        "너는 한국 자격증 시험 답지(정답표/해설지) 텍스트 파서다.\n"
        "\n"
        "[임무]\n"
        "제공된 텍스트에서 각 문제의 과목, 정답, 해설을 추출하여 JSON으로 반환하라.\n"
        "\n"
        "[출력 형식]\n"
        '반드시 {"answers": [...]} 형태의 JSON 객체로만 응답하라.\n'
        "마크다운, 설명, 인사말 금지.\n"
        "\n"
        "[각 객체의 필드]\n"
        "{\n"
        '  "id": (int) 문제 번호 (과목 내 번호, 예: 1~30),\n'
        '  "subject": (str) 과목명 (예: "무역규범", "무역결제" 등). 반드시 포함,\n'
        '  "answer": (str) 정답 번호/기호. 원문 그대로 (예: "④", "①"),\n'
        '  "explanation": (str) 해설. 있으면 포함, 없으면 ""\n'
        "}\n"
        "\n"
        "[규칙]\n"
        "1. 답이 과목별로 나뉘어 있으면 각 답에 해당 과목명(subject)을 반드시 포함하라.\n"
        "2. 답만 나열된 표라도 모두 추출하라.\n"
        "3. 해설이 있으면 반드시 포함하라.\n"
        "4. 문제 번호는 과목 내 번호를 사용하라 (과목별 1번부터)."
    )


# ── OpenAI API 호출 ──────────────────────────────────────────────────────────

def _call_openai_with_retry(
    system_prompt: str,
    user_text: str,
    max_retries: int = _MAX_API_RETRIES,
) -> Optional[str]:
    """OpenAI Chat API 호출 + 지수 백오프 재시도."""
    client = _get_client()
    if client is None:
        return None

    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except RateLimitError as e:
            last_exception = e
            if attempt < max_retries:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"Rate Limit, {wait:.1f}초 후 재시도 ({attempt}/{max_retries})"
                )
                time.sleep(wait)
            else:
                logger.error("Rate Limit 최대 재시도 초과.")
                break
        except APIError as e:
            last_exception = e
            error_str = str(e).lower()
            is_transient = any(
                k in error_str for k in ("timeout", "connection", "unavailable")
            )
            if hasattr(e, "status_code") and e.status_code in (500, 502, 503, 504):
                is_transient = True
            if attempt < max_retries and is_transient:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"API 오류, {wait:.1f}초 후 재시도 ({attempt}/{max_retries})"
                )
                time.sleep(wait)
            else:
                logger.error(f"API 오류: {e}")
                break
        except Exception as e:
            last_exception = e
            logger.error(f"예상치 못한 오류: {type(e).__name__}: {e}")
            break

    logger.error(f"최종 실패: {last_exception}")
    return None


def _clean_json_response(response_text: str) -> str:
    """LLM 응답에서 순수 JSON을 추출."""
    if not response_text:
        return ""

    # 마크다운 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", response_text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # JSON 객체 또는 배열이면 그대로 반환
    if text.startswith("{") or text.startswith("["):
        return text

    # 중괄호/대괄호 찾기
    match = re.search(r"[{[].*[}\]]", text, re.DOTALL)
    if match:
        return match.group(0).strip()

    return ""
