/**
 * result.js — 결과 화면 (점수, 통계, 과목별 분석, 오답 노트)
 */

async function renderResult(container) {
  let data;
  try {
    data = await api('GET', '/api/results');
  } catch (e) {
    container.innerHTML = `<div class="result-wrapper"><div class="cbt-card">
      <p class="cbt-subtitle">결과 정보가 없습니다.</p>
      <button class="btn btn-primary" onclick="navigateTo('home')">홈으로</button>
    </div></div>`;
    return;
  }

  const {
    score, passed, total, correct_count, incorrect_count,
    unanswered_count, subject_scores, incorrect_questions,
  } = data;

  const scoreColor = passed ? '#10b981' : '#ef4444';
  const hasMultiSubject = subject_scores.length > 1;

  const tabsHtml = hasMultiSubject
    ? `<div class="tab-bar">
        <button class="tab-btn active" data-tab="subjects">과목별 점수</button>
        <button class="tab-btn" data-tab="wrong">오답 노트 (${incorrect_count})</button>
      </div>
      <div class="tab-content active" id="tab-subjects">${_renderSubjectScores(subject_scores)}</div>
      <div class="tab-content" id="tab-wrong">${_renderWrongAnswers(incorrect_questions)}</div>`
    : `<div class="tab-bar">
        <button class="tab-btn active" data-tab="wrong">오답 노트 (${incorrect_count})</button>
      </div>
      <div class="tab-content active" id="tab-wrong">${_renderWrongAnswers(incorrect_questions)}</div>`;

  container.innerHTML = `
    <div class="result-wrapper">
      <div class="cbt-card">
        <!-- 점수 -->
        <p class="score-big" style="color:${scoreColor};">${score.toFixed(1)}</p>
        <p class="text-sm text-muted text-center" style="margin-top:-8px; margin-bottom:16px;">/ 100점</p>
        <div class="text-center mb-24">
          <span class="pass-badge ${passed ? 'pass' : 'fail'}">${passed ? '합격' : '불합격'}</span>
        </div>

        <!-- 통계 3분할 -->
        <div class="grid-3 mb-16">
          ${_statCard('정답', correct_count, '#10b981')}
          ${_statCard('오답', incorrect_count, '#ef4444')}
          ${_statCard('미응답', unanswered_count, '#f59e0b')}
        </div>

        <hr class="cbt-divider" />

        <!-- 버튼 행 -->
        <div class="grid-2">
          <button class="btn btn-secondary" id="retry-btn">다시 풀기</button>
          <button class="btn btn-primary" id="home-btn">홈으로</button>
        </div>
      </div>

      <!-- 탭 섹션 -->
      <div class="mt-24">
        ${tabsHtml}
      </div>
    </div>
  `;

  _attachResultEvents();
}

// ── 통계 카드 ────────────────────────────────────────────────────────────────
function _statCard(label, value, color) {
  return `
    <div class="stat-card" style="--stat-color:${color};">
      <p class="stat-value">${value}</p>
      <p class="stat-label">${label}</p>
    </div>
  `;
}

// ── 과목별 점수 ───────────────────────────────────────────────────────────────
function _renderSubjectScores(subject_scores) {
  if (!subject_scores.length) return '<p class="text-muted text-center">과목 정보 없음</p>';
  return subject_scores.map(ss => {
    const passed = ss.score >= 60;
    const barColor = passed ? '#10b981' : '#ef4444';
    const barWidth = Math.max(ss.score, 2);
    const badge = passed ? '합격' : '과락';
    const badgeCls = passed ? 'badge-green' : 'badge-red';
    return `
      <div class="subject-row">
        <div class="flex-between mb-8">
          <span style="font-size:0.95rem; font-weight:600;">${_esc(ss.subject)}</span>
          <span class="badge ${badgeCls}">${badge}</span>
        </div>
        <div class="subject-bar-bg">
          <div class="subject-bar-fill" style="background:${barColor}; width:${barWidth}%;"></div>
        </div>
        <div class="flex-between" style="font-size:0.78rem; color:#6b7280;">
          <span>${ss.score.toFixed(1)}점</span>
          <span>정답 ${ss.correct} / 오답 ${ss.incorrect} / 미응답 ${ss.unanswered} (총 ${ss.total})</span>
        </div>
      </div>
    `;
  }).join('');
}

// ── 오답 노트 ────────────────────────────────────────────────────────────────
function _renderWrongAnswers(incorrect_questions) {
  if (!incorrect_questions.length) {
    return '<p class="text-green text-center" style="padding:24px;">모든 문제를 맞혔습니다! 🎉</p>';
  }
  return `
    <p class="text-sm text-muted mb-16">총 ${incorrect_questions.length}개 오답</p>
    ${incorrect_questions.map((q, i) => {
      const userAns = q.user_answer || '미응답';
      const contextHtml = q.context
        ? `<div class="context-box"><b>[지문]</b><br>${_esc(q.context)}</div>`
        : '';
      const optsHtml = q.options.map(opt => {
        const isCorrect = opt === q.answer;
        const isUser = opt === q.user_answer;
        if (isCorrect) return `<p class="opt-correct">O ${_esc(opt)}</p>`;
        if (isUser) return `<p class="opt-user-wrong">X ${_esc(opt)}</p>`;
        return `<p class="opt-normal">&nbsp;&nbsp;&nbsp;${_esc(opt)}</p>`;
      }).join('');
      const explHtml = q.explanation
        ? `<div class="explanation-box"><b>해설</b>: ${_esc(q.explanation)}</div>`
        : '';
      return `
        <div class="wrong-item" id="wrong-${i}">
          <div class="wrong-header" data-idx="${i}">
            <span>문제 ${q.id} | ${_esc(q.subject)} | 내 답: ${_esc(userAns)} → 정답: ${_esc(q.answer || '없음')}</span>
            <span class="chevron">▼</span>
          </div>
          <div class="wrong-body">
            ${contextHtml}
            <div class="question-card" style="margin-bottom:12px;">
              <p style="font-size:1rem; font-weight:600; line-height:1.7; margin:0;">${_esc(q.question_text)}</p>
            </div>
            ${optsHtml}
            ${explHtml}
          </div>
        </div>
      `;
    }).join('')}
  `;
}

// ── 이벤트 ──────────────────────────────────────────────────────────────────
function _attachResultEvents() {
  // 탭 전환
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const target = document.getElementById('tab-' + btn.dataset.tab);
      if (target) target.classList.add('active');
    });
  });

  // 오답 아코디언
  document.querySelectorAll('.wrong-header').forEach(header => {
    header.addEventListener('click', () => {
      const item = header.closest('.wrong-item');
      item.classList.toggle('open');
    });
  });

  // 다시 풀기
  const retryBtn = document.getElementById('retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', async () => {
      try {
        showSpinner('시험을 다시 준비합니다...');
        await api('POST', '/api/retry-exam');
        hideSpinner();
        navigateTo('exam');
      } catch (e) {
        hideSpinner();
        showToast('오류: ' + e.message, 'error');
      }
    });
  }

  // 홈으로
  const homeBtn = document.getElementById('home-btn');
  if (homeBtn) {
    homeBtn.addEventListener('click', async () => {
      try {
        await api('POST', '/api/reset');
      } catch (_) {}
      navigateTo('home');
    });
  }
}
