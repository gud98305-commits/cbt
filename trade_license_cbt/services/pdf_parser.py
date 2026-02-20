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

from config import MODEL_NAME, MAX_PDF_PAGES, MAX_SECTION_CHARS
from trade_license_cbt.models.question_model import Question

# ── 로거 설정 ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ── OpenAI 클라이언트 (지연 초기화) ──────────────────────────────────────────
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
        logger.info(f"OpenAI 클라이언트 초기화 완료: {MODEL_NAME}")
        return _client
    except Exception as e:
        logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        return None


def reset_client() -> None:
    """API 키 변경 시 클라이언트를 리셋하여 다음 호출에서 재초기화."""
    global _client
    _client = None


# ── 상수 ─────────────────────────────────────────────────────────────────────
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
        raise ValueError("PDF 파일이 비어 있습니다.")
    if not _get_client():
        raise RuntimeError("OpenAI API 키가 올바르지 않거나 클라이언트 초기화에 실패했습니다.")

    doc = None
    try:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"parse_pdf: PDF 열기 실패 - {e}")
            return []

        # 페이지 수 제한 검사
        if len(doc) > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF 페이지가 너무 많습니다 ({len(doc)}페이지). 최대 {MAX_PDF_PAGES}페이지까지 지원합니다."
            )

        # 모든 텍스트 추출 (밑줄 감지 포함)
        full_text_with_meta = ""
        empty_pages = 0
        for i in range(len(doc)):
            page = doc.load_page(i)
            page_text = _extract_text_with_underlines(page)
            if not page_text.strip():
                empty_pages += 1
            full_text_with_meta += f"\n[PAGE {i+1}]\n{page_text}\n"

        # 스캔 이미지 PDF 감지 (텍스트가 거의 없는 경우)
        non_ws = len(re.sub(r"\s", "", full_text_with_meta.replace("[PAGE", "")))
        if non_ws < 100:
            raise ValueError(
                "이 PDF는 스캔 이미지로 구성되어 텍스트를 추출할 수 없습니다. "
                "텍스트가 포함된 PDF를 업로드해 주세요."
            )
        if len(doc) > 0 and empty_pages / len(doc) > 0.5:
            logger.warning(
                f"parse_pdf: {len(doc)}페이지 중 {empty_pages}페이지가 비어 있음 (스캔 이미지 가능성)"
            )

        # 과목 구역 감지 및 분할
        # 예: "제 1 과목", "무역규범", "1과목" 등
        sections = _split_text_by_subject(full_text_with_meta)

        # 복잡한 레이아웃 대비: 단일 섹션이 너무 크면 청크로 분할
        sections = _chunk_large_sections(sections)

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
    답지 PDF 파싱. 결정적 테이블 파싱을 우선 시도하고, 실패 시 OpenAI 폴백.

    국제무역사 답지 형식:
      - 4개 과목 헤더 (무역규범, 무역결제, 무역계약, 무역영어)
      - 각 과목 30문제, 5문제씩 그룹 (숫자 5개 + 원문자 정답 5개)
      - 4과목이 순서대로 반복
    """
    if not file_bytes:
        return []

    doc = None
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for i in range(len(doc)):
            full_text += doc.load_page(i).get_text() + "\n"

        # 1차: 결정적 테이블 파싱 시도
        answers = _parse_answer_table_deterministic(full_text)
        if answers:
            logger.info(f"parse_answer_pdf: 결정적 파싱 성공 — {len(answers)}개 답안")
            return answers

        # 2차: OpenAI 폴백
        logger.info("parse_answer_pdf: 결정적 파싱 실패, OpenAI 폴백")
        if not _get_client():
            logger.error("parse_answer_pdf: OpenAI 클라이언트 미초기화.")
            return []

        tagged_text = ""
        for i in range(len(doc)):
            tagged_text += f"\n[PAGE {i+1}]\n{doc.load_page(i).get_text()}\n"

        sections = _split_text_by_subject(tagged_text)
        all_answers = []
        for subject_hint, section_text in sections:
            ans = _extract_answers_from_text(section_text, subject_hint)
            all_answers.extend(ans)
        return all_answers
    finally:
        if doc is not None:
            doc.close()


def _parse_answer_table_deterministic(text: str) -> List[dict]:
    """
    답지 테이블을 결정적으로 파싱.
    PyMuPDF가 추출하는 순서: 4과목 헤더 → 문제번호/정답 라벨 →
    [5개 숫자, 5개 원문자] × 4과목 반복 (5문제 단위 행 그룹)
    """
    # 과목 헤더 감지
    subject_names = ["무역규범", "무역결제", "무역계약", "무역영어"]
    found_subjects = []
    for name in subject_names:
        # 공백 허용 패턴
        spaced = r"\s*".join(name)
        if re.search(spaced, text):
            found_subjects.append(name)

    if len(found_subjects) < 2:
        return []  # 과목이 2개 미만이면 이 형식이 아님

    num_subjects = len(found_subjects)

    # 원문자 정답 패턴
    circled = {"①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"}

    # 헤더 영역 끝 찾기: "문제번호"와 "정답" 라벨이 반복되는 열 헤더 이후부터 데이터
    # "정답" 라벨의 마지막 출현 위치를 찾아 그 이후부터 파싱
    lines = text.split("\n")
    data_start_idx = 0
    last_label_idx = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("문제번호", "정답"):
            last_label_idx = idx

    if last_label_idx > 0:
        data_start_idx = last_label_idx + 1

    # 데이터 영역에서 숫자와 원문자만 추출
    tokens = []
    for idx in range(data_start_idx, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if stripped.isdigit() or stripped in circled:
            tokens.append(stripped)

    if not tokens:
        return []

    # 토큰 파싱: [5숫자, 5원문자] × num_subjects 과목, 반복
    # 한 "행 그룹"은 num_subjects 과목 × 10 토큰 (5번호 + 5정답)
    group_size = 5  # 한 과목당 5문제씩 그룹
    block_size = group_size * 2  # 숫자5 + 정답5 = 10 토큰
    row_block = block_size * num_subjects  # 4과목 × 10 = 40 토큰

    answers = []
    pos = 0
    while pos + row_block <= len(tokens):
        for subj_idx in range(num_subjects):
            block_start = pos + subj_idx * block_size
            numbers = tokens[block_start:block_start + group_size]
            ans_tokens = tokens[block_start + group_size:block_start + block_size]

            for j in range(group_size):
                try:
                    qnum = int(numbers[j])
                except (ValueError, IndexError):
                    continue
                answer_val = ans_tokens[j] if j < len(ans_tokens) else ""
                answers.append({
                    "id": qnum,
                    "subject": found_subjects[subj_idx],
                    "answer": answer_val,
                    "explanation": "",
                })
        pos += row_block

    # 나머지 토큰 처리 (마지막 불완전 행 그룹)
    remaining = tokens[pos:]
    if remaining:
        rem_pos = 0
        subj_idx = 0
        while rem_pos + block_size <= len(remaining) and subj_idx < num_subjects:
            numbers = remaining[rem_pos:rem_pos + group_size]
            ans_tokens = remaining[rem_pos + group_size:rem_pos + block_size]
            for j in range(group_size):
                try:
                    qnum = int(numbers[j])
                except (ValueError, IndexError):
                    continue
                answer_val = ans_tokens[j] if j < len(ans_tokens) else ""
                answers.append({
                    "id": qnum,
                    "subject": found_subjects[subj_idx],
                    "answer": answer_val,
                    "explanation": "",
                })
            rem_pos += block_size
            subj_idx += 1

    # 검증 1: 최소 과목당 10개 이상이면 유효
    if len(answers) < num_subjects * 10:
        logger.warning(f"결정적 파싱: {len(answers)}개만 추출 (기대: {num_subjects * 30})")
        return []

    # 검증 2: 과목별 문제 번호가 1부터 시작하고 중복 없이 순차적인지 확인
    from collections import defaultdict
    subject_ids: dict[str, list[int]] = defaultdict(list)
    for a in answers:
        subject_ids[a["subject"]].append(a["id"])
    for subj, ids in subject_ids.items():
        if ids != sorted(set(ids)):
            logger.warning(f"결정적 파싱: {subj} 문제 번호 불일치 — {ids[:10]}...")
            return []

    logger.info(f"결정적 파싱: {len(answers)}개 답안 추출 ({num_subjects}과목)")
    return answers

def _split_text_by_subject(text: str) -> List[tuple[str, str]]:
    """
    텍스트에서 과목 경계를 찾아 (과목명, 내용) 쌍으로 분할.
    실제 PDF에서 과목 헤더가 글자 사이에 공백이 있는 형태로 추출됨:
      "무 역 규 범", "무 역 결 제", "무 역 계 약", "무 역 영 어"
    """
    # 국제무역사 시험 과목 헤더 패턴
    # PDF에서 과목 헤더는 글자 사이에 수평 공백이 있음: "무 역 규 범"
    # [^\S\n]+ = 줄바꿈 제외 공백 1개 이상 (본문 내 줄바꿈으로 분리된 단어 오매칭 방지)
    _SP = r"[^\S\n]+"
    pattern = (
        rf"("
        rf"무{_SP}역{_SP}규{_SP}범|"
        rf"무{_SP}역{_SP}결{_SP}제|"
        rf"무{_SP}역{_SP}계{_SP}약|"
        rf"무{_SP}역{_SP}영{_SP}어|"
        rf"무{_SP}역{_SP}물{_SP}류|"
        r"제\s?\d\s?과목|"
        r"제\s?\d\s?교시"
        r")"
    )
    splits = re.split(pattern, text)

    if not splits:
        return [("일반", text)]

    sections = []
    pre_header_text = splits[0].strip() if splits[0].strip() else ""

    for i in range(1, len(splits), 2):
        # 공백 제거하여 과목명 정규화: "무 역 결 제" → "무역결제"
        raw_subject = splits[i].strip()
        normalized = re.sub(r"\s+", "", raw_subject)
        content = splits[i+1].strip() if i+1 < len(splits) else ""

        # 첫 과목 헤더 이전의 텍스트는 첫 과목에 병합
        # (예: "무 역 규 범" 헤더가 페이지 하단에 있어 첫 문제들이 헤더 앞에 위치)
        if pre_header_text:
            content = pre_header_text + "\n" + content
            pre_header_text = ""

        if content:
            sections.append((normalized, content))

    # 과목 헤더가 하나도 없으면 전체를 하나의 섹션으로
    if not sections:
        return [("일반", text)]

    return sections

def _chunk_large_sections(
    sections: List[tuple[str, str]],
) -> List[tuple[str, str]]:
    """
    단일 섹션이 MAX_SECTION_CHARS를 초과하면 [PAGE N] 마커 기준으로 5페이지 단위 청크로 분할.
    복잡한 레이아웃이나 과목 헤더가 없는 긴 PDF에 대비.
    """
    result = []
    for subject, text in sections:
        if len(text) <= MAX_SECTION_CHARS:
            result.append((subject, text))
            continue

        # [PAGE N] 기준으로 페이지 분리
        pages = re.split(r"(?=\[PAGE \d+\])", text)
        pages = [p for p in pages if p.strip()]

        if len(pages) <= 5:
            result.append((subject, text))
            continue

        logger.info(f"섹션 '{subject}' ({len(text)}자, {len(pages)}페이지) → 5페이지 단위 청크 분할")
        for i in range(0, len(pages), 5):
            chunk = "".join(pages[i : i + 5])
            chunk_label = f"{subject}" if subject != "일반" else f"일반_{i // 5 + 1}"
            result.append((chunk_label, chunk))

    return result


def _extract_questions_from_text(text: str, subject_context: str = "") -> List[Question]:
    """배치 텍스트 → OpenAI → Question 리스트 (과목 컨텍스트 포함)."""
    system_prompt = _build_system_prompt()
    user_input = f"현재 분석 중인 구역/과목: {subject_context}\n\n텍스트 내용:\n{text}"

    raw = _call_openai_with_retry(system_prompt, user_input)
    if raw is None:
        return []

    questions = _parse_response_to_questions(raw)
    if questions is not None:
        return questions

    # JSON 파싱 실패 → 재시도
    raw = _call_openai_with_retry(
        system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.", user_input,
    )
    if raw:
        questions = _parse_response_to_questions(raw)
        if questions is not None:
            return questions

    logger.error("_extract_questions_from_text: 2회 모두 실패")
    return []

def _extract_answers_from_text(text: str, subject_context: str = "") -> List[dict]:
    """답지 텍스트 → OpenAI (과목 컨텍스트 포함)."""
    system_prompt = _build_answer_system_prompt()
    user_input = f"현재 분석 중인 답안 구역: {subject_context}\n\n텍스트 내용:\n{text}"

    raw = _call_openai_with_retry(system_prompt, user_input)
    if raw is None:
        return []

    cleaned = _clean_json_response(raw)
    if not cleaned:
        # 재시도
        raw = _call_openai_with_retry(
            system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.", user_input,
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
            # 각 답안에 과목 힌트 주입
            if not item.get("subject"):
                item["subject"] = subject_context
            results.append(item)
    return results


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


# ── 밑줄 감지 ────────────────────────────────────────────────────────────────

def _extract_text_with_underlines(page) -> str:
    """
    페이지 텍스트를 추출하면서 밑줄이 그어진 텍스트를 [[u]]..[[/u]] 마커로 감쌈.
    PDF 그래픽 레이어의 수평선을 텍스트 스팬과 매칭하여 밑줄을 감지.
    실패 시 일반 get_text()로 폴백.
    """
    plain_text = page.get_text()

    try:
        drawings = page.get_drawings()
    except Exception:
        return plain_text

    # 수평선(밑줄 후보) 수집
    h_lines = []
    for path in drawings:
        for item in path.get("items", []):
            if item[0] == "l":  # 선분
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 2 and abs(p1.x - p2.x) > 5:
                    h_lines.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2))
            elif item[0] == "re":  # 얇은 사각형 (밑줄로 그려진 경우)
                rect = item[1]
                if hasattr(rect, "height") and rect.height < 2 and rect.width > 5:
                    h_lines.append((rect.x0, rect.x1, rect.y1))

    if not h_lines:
        return plain_text

    # 텍스트 스팬 위치 정보 획득
    text_dict = page.get_text("dict")

    # 밑줄이 그어진 텍스트 문자열 수집
    underlined_texts = []
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text or len(text) < 2:
                    continue
                bbox = span.get("bbox", (0, 0, 0, 0))
                x0, y0, x1, y1 = bbox
                span_width = x1 - x0
                if span_width < 1:
                    continue

                for lx0, lx1, ly in h_lines:
                    # 선이 텍스트 하단 근처에 있어야 함 (5pt 이내)
                    if abs(ly - y1) <= 5:
                        overlap = min(x1, lx1) - max(x0, lx0)
                        if overlap > span_width * 0.5:
                            underlined_texts.append(text)
                            break

    if not underlined_texts:
        return plain_text

    # 긴 것부터 치환 (부분 매칭 방지), 중복 제거
    underlined_texts = sorted(set(underlined_texts), key=len, reverse=True)

    result = plain_text
    for ul_text in underlined_texts:
        if ul_text in result:
            result = result.replace(ul_text, f"[[u]]{ul_text}[[/u]]", 1)

    return result


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

        # ── 연결된 options 자동 분리 (LLM이 "① A ② B ③ C ④ D" 형태로 반환한 경우) ──
        if isinstance(item.get("options"), list) and len(item["options"]) == 1:
            single = item["options"][0]
            if re.search(r"[①②③④⑤]", single):
                parts = re.split(r"(?=[①②③④⑤])", single)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    item["options"] = parts
                    logger.info(f"item[{idx}]: 연결된 options 분리 → {len(parts)}개")

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
        "7. answer에는 반드시 options 리스트 안의 전체 텍스트를 넣어라. 정답을 모르면 빈 문자열.\n"
        "8. subject 필드에는 과목명을 공백 없이 넣어라 (예: '무역규범', '무역결제', '무역계약', '무역영어').\n"
        "9. id는 과목 내 문제 번호를 사용하라 (과목별 1번부터).\n"
        "10. 텍스트 내에 [[u]]...[[/u]] 마커가 있으면 context와 question_text에 해당 마커를 그대로 보존하라."
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

_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BACKOFF_BASE = 2.0


def _call_openai_with_retry(
    system_prompt: str,
    user_text: str,
    max_retries: int = _MAX_API_RETRIES,
) -> Optional[str]:
    """OpenAI Chat API 호출 + 지수 백오프 재시도."""
    client = _get_client()
    if client is None:
        return None

    # 토큰 추정 경고 (한국어 ~4자/토큰)
    estimated_tokens = len(user_text) // 4
    if estimated_tokens > 25000:
        logger.warning(f"입력 토큰 추정: ~{estimated_tokens} (텍스트 {len(user_text)}자)")

    last_exception: Optional[Exception] = None

    # RateLimitError는 더 많은 재시도 허용
    effective_retries = max_retries

    for attempt in range(1, effective_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=16384,
            )
            return response.choices[0].message.content
        except RateLimitError as e:
            last_exception = e
            # RateLimitError는 더 긴 백오프 + 더 많은 재시도
            effective_retries = _RATE_LIMIT_MAX_RETRIES
            if attempt < effective_retries:
                wait = _RATE_LIMIT_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"Rate Limit, {wait:.1f}초 후 재시도 ({attempt}/{effective_retries})"
                )
                time.sleep(wait)
            else:
                logger.error("Rate Limit 최대 재시도 초과.")
                break
        except APIError as e:
            last_exception = e
            error_str = str(e).lower()
            is_transient = any(
                k in error_str
                for k in ("timeout", "connection", "unavailable", "context_length", "token")
            )
            if hasattr(e, "status_code") and e.status_code in (500, 502, 503, 504):
                is_transient = True
            if attempt < effective_retries and is_transient:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"API 오류, {wait:.1f}초 후 재시도 ({attempt}/{effective_retries})"
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
