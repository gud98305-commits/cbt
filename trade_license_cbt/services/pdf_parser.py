"""
services/pdf_parser.py

PDF 시험지 파싱 서비스 (멀티모달 비전).
Public API:
  - parse_pdf(file_bytes, api_key) -> List[Question]      : 문제 PDF 파싱 (비전)
  - parse_answer_pdf(file_bytes, api_key) -> List[dict]    : 답지 PDF 파싱 (텍스트)
  - merge_answers(questions, answers) -> List[Question] : 문제 + 답지 병합

설계 원칙:
- PDF 페이지를 이미지로 변환 → GPT-4o 비전 API로 파싱
- 3페이지 단위 그룹으로 지문-문제 연결 유지
- 병렬 API 호출로 속도 최적화
- 실패는 해당 배치만 스킵, 전체 중단 없음
"""

import base64
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from openai import OpenAI, RateLimitError, APIError
from pydantic import ValidationError

from config import MODEL_NAME, MAX_PDF_PAGES, VISION_DPI, PAGES_PER_GROUP
from trade_license_cbt.models.question_model import Question

# ── 로거 설정 ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ── OpenAI 클라이언트 (요청별 생성) ──────────────────────────────────────────

def _make_client(api_key: str) -> Optional[OpenAI]:
    """API 키로 OpenAI 클라이언트를 생성."""
    if not api_key:
        logger.warning("API 키가 제공되지 않았습니다.")
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        return None


# ── 상수 ─────────────────────────────────────────────────────────────────────
_MAX_WORKERS = 3             # 병렬 API 호출 수 (비전은 토큰 소모가 크므로 축소)
_MAX_API_RETRIES = 3
_BACKOFF_BASE = 1.0

_CIRCLED_NUMBERS = {
    "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤",
    "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨", "10": "⑩",
}


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def parse_pdf(file_bytes: bytes, api_key: str = "") -> List[Question]:
    """
    PDF 바이트 → Question 리스트 (멀티모달 비전 파싱).
    각 페이지를 이미지로 변환하여 GPT-4o 비전 API로 문제를 추출.
    """
    if not file_bytes:
        raise ValueError("PDF 파일이 비어 있습니다.")
    client = _make_client(api_key)
    if not client:
        raise RuntimeError("OpenAI API 키가 올바르지 않거나 클라이언트 초기화에 실패했습니다.")

    doc = None
    try:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"parse_pdf: PDF 열기 실패 - {e}")
            return []

        if len(doc) > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF 페이지가 너무 많습니다 ({len(doc)}페이지). 최대 {MAX_PDF_PAGES}페이지까지 지원합니다."
            )

        # 각 페이지를 이미지(PNG base64)로 변환
        page_images: List[str] = []
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=VISION_DPI)
            png_bytes = pix.tobytes("png")
            b64 = base64.b64encode(png_bytes).decode("ascii")
            page_images.append(b64)
            logger.info(f"페이지 {i+1}/{len(doc)} 이미지 변환 완료 ({len(png_bytes)//1024}KB)")

        # 페이지 그룹 생성 (PAGES_PER_GROUP 단위)
        groups: List[List[tuple[int, str]]] = []
        for i in range(0, len(page_images), PAGES_PER_GROUP):
            group = [(i + j + 1, page_images[i + j])
                     for j in range(min(PAGES_PER_GROUP, len(page_images) - i))]
            groups.append(group)

        logger.info(f"parse_pdf: {len(doc)}페이지 → {len(groups)}그룹 ({PAGES_PER_GROUP}페이지/그룹)")

        # 각 그룹을 병렬로 비전 API에 전송
        all_questions: List[Question] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_map = {
                executor.submit(_extract_questions_from_images, group, client): idx
                for idx, group in enumerate(groups)
            }
            results = {}
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"그룹 {idx} 처리 실패: {e}")
                    results[idx] = []

            for idx in sorted(results.keys()):
                all_questions.extend(results[idx])

        logger.info(f"parse_pdf: 총 {len(all_questions)}개 문제 추출 완료")
        return all_questions

    finally:
        if doc is not None:
            doc.close()


def parse_answer_pdf(file_bytes: bytes, api_key: str = "") -> List[dict]:
    """
    답지 PDF 파싱. 결정적 테이블 파싱을 우선 시도하고, 실패 시 OpenAI 폴백.
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

        # 2차: OpenAI 텍스트 폴백
        logger.info("parse_answer_pdf: 결정적 파싱 실패, OpenAI 폴백")
        client = _make_client(api_key)
        if not client:
            logger.error("parse_answer_pdf: OpenAI 클라이언트 미초기화.")
            return []

        tagged_text = ""
        for i in range(len(doc)):
            tagged_text += f"\n[PAGE {i+1}]\n{doc.load_page(i).get_text()}\n"

        sections = _split_text_by_subject(tagged_text)
        all_answers = []
        for subject_hint, section_text in sections:
            ans = _extract_answers_from_text(section_text, subject_hint, client)
            all_answers.extend(ans)
        return all_answers
    finally:
        if doc is not None:
            doc.close()


def merge_answers(questions: List[Question], answers: List[dict]) -> List[Question]:
    """
    문제 리스트에 답지 데이터를 병합.
    (subject, id) 복합키로 매칭 → subject 없으면 id만으로 폴백.
    """
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


# ══════════════════════════════════════════════════════════════════════════════
# 비전 파싱 (문제 PDF용)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_questions_from_images(
    page_group: List[tuple[int, str]],
    client: OpenAI,
) -> List[Question]:
    """페이지 이미지 그룹 → GPT-4o 비전 → Question 리스트."""
    system_prompt = _build_vision_system_prompt()

    page_nums = [p[0] for p in page_group]
    logger.info(f"비전 파싱: 페이지 {page_nums}")

    # 유저 메시지: 텍스트 + 이미지들
    user_content: list = [
        {"type": "text", "text": f"다음은 시험지 페이지 {page_nums} 이미지입니다. 모든 문제를 추출하세요."}
    ]
    for page_num, b64_img in page_group:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64_img}",
                "detail": "high",
            }
        })

    raw = _call_openai(system_prompt, user_content, client)
    if raw is None:
        return []

    questions = _parse_response_to_questions(raw, page_nums)
    if questions is not None:
        return questions

    # 재시도
    raw = _call_openai(
        system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.",
        user_content, client,
    )
    if raw:
        questions = _parse_response_to_questions(raw, page_nums)
        if questions is not None:
            return questions

    logger.error(f"비전 파싱 실패: 페이지 {page_nums}")
    return []


def _build_vision_system_prompt() -> str:
    """비전 모델용 시스템 프롬프트."""
    return (
        "너는 한국 자격증 시험 PDF 문제지를 이미지에서 파싱하는 전문가다.\n"
        "\n"
        "[임무]\n"
        "제공된 시험지 페이지 이미지에서 객관식 문제를 모두 찾아 JSON으로 반환하라.\n"
        "\n"
        "[출력 형식]\n"
        '반드시 {"questions": [...]} 형태의 JSON 객체로만 응답하라.\n'
        "마크다운, 설명, 인사말 금지.\n"
        "\n"
        "[각 문제 객체의 필드]\n"
        "{\n"
        '  "id": (int) 문제 번호,\n'
        '  "subject": (str) 과목명. 반드시 다음 4개 중 하나만 사용: "무역규범", "무역결제", "무역계약", "무역영어". '
        '이 외의 과목명을 만들거나 세분화하지 마라.,\n'
        '  "context": (str|null) 지문. 없으면 null,\n'
        '  "question_text": (str) 문제 본문,\n'
        '  "options": (list[str]) 보기 목록. 원문 그대로,\n'
        '  "answer": (str) 정답. 이미지에 정답이 명시되어 있을 때만. 없으면 "",\n'
        '  "explanation": (str) 해설. 없으면 "",\n'
        '  "page_number": (int) 해당 문제가 있는 페이지 번호\n'
        "}\n"
        "\n"
        "[규칙]\n"
        '1. 문제가 없으면 {"questions": []}을 반환하라.\n'
        "2. 보기 번호 형식은 원문을 따르라 (①②③④ 등).\n"
        "3. 하나의 지문에 여러 문제가 딸린 경우, 각 문제마다 context에 동일 지문 전체를 복사해 넣어라. "
        "절대 지문을 첫 번째 문제에만 넣고 나머지는 null로 하지 마라.\n"
        "4. options 배열 원소 수는 원문 보기 개수와 정확히 일치해야 한다.\n"
        "5. question_text에는 보기를 포함하지 마라.\n"
        "6. answer에는 반드시 options 리스트 안의 전체 텍스트를 넣어라. 정답을 모르면 빈 문자열.\n"
        "7. id는 과목 내 문제 번호를 사용하라 (과목별 1번부터).\n"
        "\n"
        "[★ 밑줄 처리 — 매우 중요]\n"
        "이미지에서 밑줄(underline)이 그어진 텍스트를 반드시 감지하라.\n"
        "밑줄이 있는 텍스트는 [[u]]밑줄 텍스트[[/u]] 형태로 마킹하라.\n"
        "context, question_text, options 모두에 적용하라.\n"
        "밑줄은 시험에서 핵심 키워드를 강조하는 용도이므로 절대 누락하지 마라.\n"
        "예: '다음 중 [[u]]옳지 않은 것[[/u]]은?'\n"
        "\n"
        "[★ 표(Table) 처리 — 매우 중요]\n"
        "이미지에 표(table)가 있으면 반드시 HTML <table> 형식으로 보존하라.\n"
        "표를 단순 텍스트로 풀어쓰지 마라. 행/열 구조를 유지해야 한다.\n"
        "예:\n"
        '<table><tr><th>구분</th><th>내용</th></tr>'
        '<tr><td>A</td><td>설명1</td></tr>'
        '<tr><td>B</td><td>설명2</td></tr></table>\n'
        "표가 지문(context) 안에 있으면 context에, 문제 본문에 있으면 question_text에 넣어라.\n"
        "★ 표를 options 안에 넣지 마라. 보기는 항상 순수 텍스트여야 한다.\n"
        "표 안에 빈칸(A, B, C 등)이 있고 보기에서 빈칸 내용을 고르는 문제라면,\n"
        "표 전체를 context에 넣고 보기는 텍스트로만 작성하라.\n"
        "예: options = ['① C group - D group - D group', '② D group - F group - C group']\n"
        "\n"
        "[텍스트 정확성]\n"
        "- 영어 텍스트(무역영어 지문, 계약서 조항, 약어 등)는 이미지에 보이는 그대로 정확히 옮겨라. "
        "임의로 띄어쓰기를 변경하거나 단어를 수정하지 마라.\n"
        "- 한국어 텍스트만 자연스러운 띄어쓰기를 적용하라.\n"
        "- 약어(L/C, B/L, CIF, FOB, DDP 등)는 원문 그대로 유지하라.\n"
        "\n"
        "[★ 지문(context) 추출 — 매우 중요]\n"
        "지문이란 문제 앞에 제시되는 참고 텍스트다:\n"
        "- 영문 지문, 계약서 조항, 사례, 조문, 표, 상황 설명, 보기 전 제시문 등이 해당된다.\n"
        "- '다음을 읽고 물음에 답하시오', '다음 사례를 보고...' 등의 안내문 뒤에 오는 텍스트가 지문이다.\n"
        "- 여러 문제(예: 29번, 30번)가 하나의 지문을 공유하면,\n"
        "  각 문제의 context에 동일한 지문 전체를 복사해 넣어라.\n"
        "  절대로 첫 번째 문제에만 넣고 나머지를 null로 하지 마라.\n"
        "- 지문이 없는 단독 문제는 context를 null로 하라.\n"
        "- 이전 페이지에서 시작된 지문이 이어지는 경우, 보이는 부분만 context에 포함하라."
    )


# ══════════════════════════════════════════════════════════════════════════════
# 답지 파싱용 내부 함수 (텍스트 기반 — 변경 없음)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_answer_table_deterministic(text: str) -> List[dict]:
    """
    답지 테이블을 결정적으로 파싱.
    """
    subject_names = ["무역규범", "무역결제", "무역계약", "무역영어"]
    found_subjects = []
    for name in subject_names:
        spaced = r"\s*".join(name)
        if re.search(spaced, text):
            found_subjects.append(name)

    if len(found_subjects) < 2:
        return []

    num_subjects = len(found_subjects)
    circled = {"①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"}

    lines = text.split("\n")
    data_start_idx = 0
    last_label_idx = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("문제번호", "정답"):
            last_label_idx = idx

    if last_label_idx > 0:
        data_start_idx = last_label_idx + 1

    tokens = []
    for idx in range(data_start_idx, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if stripped.isdigit() or stripped in circled:
            tokens.append(stripped)

    if not tokens:
        return []

    group_size = 5
    block_size = group_size * 2
    row_block = block_size * num_subjects

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

    if len(answers) < num_subjects * 10:
        logger.warning(f"결정적 파싱: {len(answers)}개만 추출 (기대: {num_subjects * 30})")
        return []

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
    """답지 OpenAI 폴백용: 텍스트에서 과목 경계를 찾아 분할."""
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
        raw_subject = splits[i].strip()
        normalized = re.sub(r"\s+", "", raw_subject)
        content = splits[i+1].strip() if i+1 < len(splits) else ""

        if pre_header_text:
            content = pre_header_text + "\n" + content
            pre_header_text = ""

        if content:
            sections.append((normalized, content))

    if not sections:
        return [("일반", text)]

    return sections


def _extract_answers_from_text(text: str, subject_context: str = "", client: Optional[OpenAI] = None) -> List[dict]:
    """답지 텍스트 → OpenAI (과목 컨텍스트 포함)."""
    system_prompt = _build_answer_system_prompt()
    user_input = f"현재 분석 중인 답안 구역: {subject_context}\n\n텍스트 내용:\n{text}"

    raw = _call_openai(system_prompt, user_input, client=client)
    if raw is None:
        return []

    cleaned = _clean_json_response(raw)
    if not cleaned:
        raw = _call_openai(
            system_prompt + "\n\n⚠️ 반드시 유효한 JSON 객체만 반환하세요.", user_input, client=client,
        )
        if raw:
            cleaned = _clean_json_response(raw)
        if not cleaned:
            return []

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = data.get("answers", data.get("items", []))
    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        if isinstance(item, dict) and "id" in item and "answer" in item:
            item["id"] = int(item["id"]) if not isinstance(item["id"], int) else item["id"]
            if not item.get("subject"):
                item["subject"] = subject_context
            results.append(item)
    return results


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


# ══════════════════════════════════════════════════════════════════════════════
# 공통 유틸리티
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_subject(s: str) -> str:
    """과목명 정규화 (공백·특수문자 제거, 소문자)."""
    if not s:
        return ""
    return re.sub(r"[\s·‧\-_]", "", s).lower()


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


def _parse_response_to_questions(raw_response: str, page_nums: List[int] = None) -> Optional[List[Question]]:
    """LLM JSON → Question 리스트. 파싱 실패 시 None."""
    cleaned = _clean_json_response(raw_response)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        data = data.get("questions", data.get("items", []))
    if not isinstance(data, list):
        return None

    questions: List[Question] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue

        if not item.get("question_text", "").strip():
            continue
        if not item.get("options"):
            continue

        # 연결된 options 자동 분리
        if isinstance(item.get("options"), list) and len(item["options"]) == 1:
            single = item["options"][0]
            if re.search(r"[①②③④⑤]", single):
                parts = re.split(r"(?=[①②③④⑤])", single)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    item["options"] = parts

        # answer가 options에 없으면 자동 매칭
        if item.get("answer") and item.get("options") and isinstance(item["options"], list):
            raw_answer = str(item["answer"]).strip()
            if raw_answer not in item["options"]:
                item["answer"] = _match_answer_to_option(raw_answer, item["options"])

        # page_number 기본값
        if not item.get("page_number") and page_nums:
            item["page_number"] = page_nums[0]

        try:
            q = Question(**item)
            questions.append(q)
        except (ValidationError, TypeError) as e:
            logger.warning(f"item[{idx}]: Question 생성 실패 — {e}")
            continue

    return questions


def _clean_json_response(response_text: str) -> str:
    """LLM 응답에서 순수 JSON을 추출."""
    if not response_text:
        return ""

    text = re.sub(r"```(?:json)?\s*", "", response_text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    text = text.strip()

    if text.startswith("{") or text.startswith("["):
        return text

    match = re.search(r"[{[].*[}\]]", text, re.DOTALL)
    if match:
        return match.group(0).strip()

    return ""


# ══════════════════════════════════════════════════════════════════════════════
# OpenAI API 호출
# ══════════════════════════════════════════════════════════════════════════════

_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BACKOFF_BASE = 2.0


def _call_openai(
    system_prompt: str,
    user_content: str | list,
    client: Optional[OpenAI] = None,
    max_retries: int = _MAX_API_RETRIES,
) -> Optional[str]:
    """OpenAI Chat API 호출 + 지수 백오프 재시도. 텍스트(str)와 비전(list) 모두 지원."""
    if client is None:
        return None

    last_exception: Optional[Exception] = None
    effective_retries = max_retries

    for attempt in range(1, effective_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=16384,
            )
            return response.choices[0].message.content
        except RateLimitError as e:
            last_exception = e
            effective_retries = _RATE_LIMIT_MAX_RETRIES
            if attempt < effective_retries:
                wait = _RATE_LIMIT_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(f"Rate Limit, {wait:.1f}초 후 재시도 ({attempt}/{effective_retries})")
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
                logger.warning(f"API 오류, {wait:.1f}초 후 재시도 ({attempt}/{effective_retries})")
                time.sleep(wait)
            else:
                logger.error(f"API 오류: {e}")
                break
        except Exception as e:
            last_exception = e
            logger.error(f"예상치 못한 오류: {type(e).__name__}: {e}")
            break

    logger.error(f"API 최종 실패: {last_exception}")
    return None
