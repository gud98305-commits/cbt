/**
 * exam.js — 시험 화면 (사이드바 + 타이머 + 문제 카드 + 네비게이션)
 */

let _timerInterval = null;
let _examState = null;
let _currentQuestion = null;

async function renderExam(container) {
  // 시험 상태 로드
  try {
    _examState = await api('GET', '/api/exam-state');
  } catch (e) {
    container.innerHTML = `<div class="home-wrapper"><div class="cbt-card">
      <p class="cbt-subtitle">시험 정보가 없습니다.</p>
      <button class="btn btn-primary" onclick="navigateTo('home')">홈으로</button>
    </div></div>`;
    return;
  }

  const idx = _examState.current_quest_index;
  try {
    _currentQuestion = await api('GET', `/api/question/${idx}`);
  } catch (e) {
    showToast('문제 로드 실패: ' + e.message, 'error');
    return;
  }

  container.innerHTML = `
    <div class="exam-layout">
      <!-- 사이드바 -->
      <div class="exam-sidebar" id="exam-sidebar">
        <h3 style="font-size:1rem; font-weight:700; color:#1a1a2e; margin-bottom:16px;">📋 문제 목록</h3>
        <div id="timer-display" class="timer-display"></div>
        <div class="progress-bar-wrap">
          <div class="progress-bar-fill" id="progress-fill" style="width:0%"></div>
        </div>
        <hr class="cbt-divider" />
        <div class="nav-grid" id="nav-grid"></div>
        <div class="sidebar-submit">
          <hr class="cbt-divider" />
          <p class="unanswered-warning" id="unanswered-warn"></p>
          <button class="btn btn-primary" id="submit-sidebar-btn">최종 제출</button>
        </div>
      </div>

      <!-- 메인 영역 -->
      <div class="exam-main">
        <div class="flex-between mb-8">
          <h2 style="font-size:1.3rem; font-weight:700; color:#1a1a2e;">국제무역사 1급 CBT</h2>
          <button class="btn btn-primary btn-sm" id="submit-header-btn" style="width:auto;">제출 →</button>
        </div>
        <hr class="cbt-divider" />
        <div id="question-area"></div>
        <div class="nav-buttons">
          <button class="btn btn-secondary btn-sm" id="prev-btn" style="width:auto;">← 이전 문제</button>
          <span class="nav-center-label" id="nav-label"></span>
          <button class="btn btn-primary btn-sm" id="next-btn" style="width:auto;">다음 문제 →</button>
        </div>
      </div>
    </div>
  `;

  _renderSidebar();
  _renderQuestionArea();
  _startTimer();
  _attachExamEvents();
}

// ── 사이드바 렌더 ─────────────────────────────────────────────────────────────
function _renderSidebar() {
  if (!_examState) return;
  const total = _examState.total;
  const answered = Object.keys(_examState.user_answers).length;
  const pct = total ? (answered / total * 100) : 0;

  const fill = document.getElementById('progress-fill');
  if (fill) fill.style.width = pct + '%';

  const unanswered = total - answered;
  const warn = document.getElementById('unanswered-warn');
  if (warn) {
    warn.textContent = unanswered > 0 ? `⚠️ 미응답 문제: ${unanswered}개` : '';
  }

  const grid = document.getElementById('nav-grid');
  if (!grid) return;

  const qids = _examState.question_ids || [];
  let html = '';
  for (let i = 0; i < total; i++) {
    const isCurrent = i === _examState.current_quest_index;
    const qid = qids[i];
    const isAnswered = qid !== undefined && (_examState.user_answers[String(qid)] !== undefined);
    let cls = 'nav-btn';
    if (isCurrent && isAnswered) cls += ' answered current';
    else if (isCurrent) cls += ' current';
    else if (isAnswered) cls += ' answered';
    html += `<button class="${cls}" data-idx="${i}">${i + 1}</button>`;
  }
  grid.innerHTML = html;

  // 네비 버튼 클릭
  grid.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx);
      _navigateToQuestion(idx);
    });
  });
}

// ── 문제 영역 렌더 ────────────────────────────────────────────────────────────
function _renderQuestionArea() {
  if (!_currentQuestion) return;
  const q = _currentQuestion;
  const total = _examState.total;
  const idx = _examState.current_quest_index;

  const contextHtml = q.context
    ? `<div class="context-box"><b>[지문]</b><br>${_esc(q.context)}</div>`
    : '';

  const optionsHtml = q.options.map(opt => {
    const isSelected = opt === q.saved_answer;
    return `
      <li class="option-item${isSelected ? ' selected' : ''}" data-value="${_esc(opt)}">
        <input type="radio" name="q-option" value="${_esc(opt)}" ${isSelected ? 'checked' : ''} />
        ${_esc(opt)}
      </li>
    `;
  }).join('');

  const area = document.getElementById('question-area');
  if (!area) return;

  area.innerHTML = `
    <div class="question-card">
      <span class="question-number-badge">${idx + 1}번 | ${_esc(q.subject)}</span>
      ${contextHtml}
      <p class="question-text">${_esc(q.question_text)}</p>
      <ul class="options-list" id="options-list">
        ${optionsHtml}
      </ul>
    </div>
  `;

  const label = document.getElementById('nav-label');
  if (label) label.textContent = `${idx + 1} / ${total}`;

  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');
  if (prevBtn) prevBtn.disabled = idx === 0;
  if (nextBtn) nextBtn.textContent = idx === total - 1 ? '제출하기 →' : '다음 문제 →';

  // 옵션 클릭
  document.querySelectorAll('.option-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.option-item').forEach(el => el.classList.remove('selected'));
      item.classList.add('selected');
      const val = item.dataset.value;
      _saveAnswer(q.id, val);
    });
  });
}

// ── 답안 저장 ────────────────────────────────────────────────────────────────
async function _saveAnswer(questionId, answer) {
  try {
    const res = await api('POST', '/api/save-answer', { question_id: questionId, answer });
    // 상태 업데이트
    if (answer) {
      _examState.user_answers[String(questionId)] = answer;
    } else {
      delete _examState.user_answers[String(questionId)];
    }
    _examState.answered_count = res.answered_count;
    _renderSidebar();
  } catch (e) {
    showToast('답 저장 실패: ' + e.message, 'error');
  }
}

// ── 문제 이동 ────────────────────────────────────────────────────────────────
async function _navigateToQuestion(idx) {
  try {
    await api('POST', '/api/navigate', { index: idx });
    _examState.current_quest_index = idx;
    _currentQuestion = await api('GET', `/api/question/${idx}`);
    _renderSidebar();
    _renderQuestionArea();
    window.scrollTo(0, 0);
  } catch (e) {
    showToast('이동 실패: ' + e.message, 'error');
  }
}

// ── 타이머 ──────────────────────────────────────────────────────────────────
function _startTimer() {
  if (_timerInterval) clearInterval(_timerInterval);
  _updateTimer();
  _timerInterval = setInterval(_updateTimer, 1000);
}

function _updateTimer() {
  if (!_examState) return;
  const elapsed = Date.now() / 1000 - _examState.start_time;
  const remaining = Math.max(0, 100 * 60 - elapsed);  // 100분
  const m = Math.floor(remaining / 60);
  const s = Math.floor(remaining % 60);
  const display = document.getElementById('timer-display');
  if (!display) { clearInterval(_timerInterval); return; }
  const str = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  display.textContent = str;
  display.className = 'timer-display' + (remaining < 600 ? ' timer-warning' : '');
}

// ── 이벤트 바인딩 ────────────────────────────────────────────────────────────
function _attachExamEvents() {
  // 이전 버튼
  const prevBtn = document.getElementById('prev-btn');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      const idx = _examState.current_quest_index;
      if (idx > 0) _navigateToQuestion(idx - 1);
    });
  }

  // 다음 버튼
  const nextBtn = document.getElementById('next-btn');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const idx = _examState.current_quest_index;
      const total = _examState.total;
      if (idx < total - 1) {
        _navigateToQuestion(idx + 1);
      } else {
        _attemptSubmit();
      }
    });
  }

  // 사이드바 제출 버튼
  const submitSidebar = document.getElementById('submit-sidebar-btn');
  if (submitSidebar) {
    submitSidebar.addEventListener('click', _attemptSubmit);
  }

  // 헤더 제출 버튼
  const submitHeader = document.getElementById('submit-header-btn');
  if (submitHeader) {
    submitHeader.addEventListener('click', _attemptSubmit);
  }
}

// ── 제출 처리 ────────────────────────────────────────────────────────────────
function _attemptSubmit() {
  const unanswered = _examState.total - Object.keys(_examState.user_answers).length;
  if (unanswered > 0) {
    showConfirm(
      '제출 확인',
      `미응답 문제 ${unanswered}개가 있습니다. 그래도 제출하시겠습니까?`,
      _doSubmit,
    );
  } else {
    _doSubmit();
  }
}

async function _doSubmit() {
  clearInterval(_timerInterval);
  try {
    showSpinner('채점 중...');
    await api('POST', '/api/submit-exam');
    hideSpinner();
    navigateTo('result');
  } catch (e) {
    hideSpinner();
    showToast('제출 실패: ' + e.message, 'error');
  }
}
