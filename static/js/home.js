/**
 * home.js — 홈 화면 (API 키 입력, PDF 업로드, 시험 시작)
 */

async function renderHome(container) {
  // 현재 세션 상태 확인
  let status = { question_count: 0, answer_count: 0, subjects: [], api_key_set: false };
  try {
    status = await api('GET', '/api/session-status');
  } catch (_) {}

  container.innerHTML = `
    <div class="home-wrapper">
      <div class="cbt-card">
        <div class="icon-circle">📄</div>
        <p class="cbt-title">CBT Mock Test</p>

        <!-- API 키 입력 -->
        <div class="mb-16">
          ${!status.api_key_set
            ? `<p class="text-sm text-muted text-center mb-4">PDF 분석을 위해 OpenAI API 키가 필요합니다</p>`
            : ''}
          <input id="api-key-input" class="input-field" type="password"
            placeholder="sk-..." value="" autocomplete="off" />
          ${status.api_key_set
            ? `<p class="text-xs text-green text-center mt-4">API 키 설정 완료</p>`
            : '<div style="height:16px;"></div>'}
        </div>

        ${status.question_count > 0
          ? _renderParsedState(status)
          : _renderUploadState(status)}

        <!-- 구분선 + 샘플 시험 -->
        <hr class="cbt-divider" />
        <p class="text-sm text-muted text-center mb-12">PDF가 없으신가요? 샘플 시험을 체험해 보세요</p>
        <button id="start-sample-btn" class="btn btn-primary">Start Sample Test</button>
      </div>
    </div>
  `;

  _attachHomeEvents(status);
}

function _renderParsedState(status) {
  const subjectCheckboxes = status.subjects.length > 1
    ? `<div class="subject-select mt-12" id="subject-select">
        <p class="text-sm text-muted text-center mb-8">응시할 과목을 선택하세요</p>
        ${status.subjects.map(s => `
          <label>
            <input type="checkbox" value="${_esc(s)}" checked />
            ${_esc(s)}
          </label>
        `).join('')}
      </div>`
    : '';

  return `
    <p class="cbt-subtitle">문제 분석이 완료되었습니다</p>
    <div class="grid-2 mb-16">
      <div class="badge badge-green" style="text-align:center; padding:8px;">📋 ${status.question_count}개 문제 추출 완료</div>
      <div class="badge ${status.answer_count > 0 ? 'badge-green' : 'badge-blue'}" style="text-align:center; padding:8px;">
        ${status.answer_count > 0 ? '📝 ' + status.answer_count + '개 답안 추출 완료' : '📝 답지 없음 (채점 불가)'}
      </div>
    </div>
    ${subjectCheckboxes}
    <div class="mt-16">
      <button id="start-exam-btn" class="btn btn-primary mb-8">시험 시작 →</button>
      <button id="reset-uploads-btn" class="btn btn-secondary btn-sm" style="width:auto; display:block; margin:0 auto;">🔄 다시 업로드</button>
    </div>
    ${status.answer_count === 0 ? `
    <hr class="cbt-divider" />
    <p class="text-sm text-muted text-center mb-8">채점을 원하시면 답지 PDF를 추가해 주세요</p>
    <div class="upload-zone" id="answer-late-zone">
      <input type="file" accept=".pdf" id="answer-late-input" />
      <div class="zone-icon">📝</div>
      <p class="zone-title">답지 PDF</p>
      <p class="zone-sub">클릭하거나 파일을 드래그하세요</p>
      <p class="zone-status" id="answer-late-status"></p>
    </div>
    ` : ''}
  `;
}

function _renderUploadState(status) {
  return `
    <p class="cbt-subtitle">문제 PDF와 답지 PDF를 업로드하여 시험을 시작하세요</p>
    <div class="grid-2">
      <div class="upload-zone" id="q-zone">
        <input type="file" accept=".pdf" id="q-input" />
        <div class="zone-icon">📋</div>
        <p class="zone-title">문제 PDF</p>
        <p class="zone-sub">시험 문제 파일</p>
        <p class="zone-status" id="q-status"></p>
      </div>
      <div class="upload-zone" id="a-zone">
        <input type="file" accept=".pdf" id="a-input" />
        <div class="zone-icon">📝</div>
        <p class="zone-title">답지 PDF</p>
        <p class="zone-sub">정답 및 해설 파일 (선택)</p>
        <p class="zone-status" id="a-status"></p>
      </div>
    </div>
    <div class="mt-16">
      <button id="parse-btn" class="btn btn-primary" disabled>PDF 분석 시작</button>
    </div>
  `;
}

function _attachHomeEvents(status) {
  // API 키 입력 엔터/블러
  const keyInput = document.getElementById('api-key-input');
  if (keyInput) {
    let _lastSavedKey = '';
    async function saveApiKey() {
      const val = keyInput.value.trim();
      if (!val || val === _lastSavedKey) return;
      try {
        await api('POST', '/api/set-api-key', { api_key: val });
        _lastSavedKey = val;
        showToast('API 키가 저장되었습니다', 'success');
        setTimeout(() => renderHome(document.getElementById('app')), 600);
      } catch (e) {
        showToast('키 저장 실패: ' + e.message, 'error');
      }
    }
    keyInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveApiKey(); });
    keyInput.addEventListener('blur', saveApiKey);
  }

  // 샘플 시험 시작
  const sampleBtn = document.getElementById('start-sample-btn');
  if (sampleBtn) {
    sampleBtn.addEventListener('click', async () => {
      try {
        showSpinner('시험을 준비하고 있습니다...');
        await api('POST', '/api/start-sample-exam');
        hideSpinner();
        navigateTo('exam');
      } catch (e) {
        hideSpinner();
        showToast('오류: ' + e.message, 'error');
      }
    });
  }

  if (status.question_count > 0) {
    _attachParsedStateEvents(status);
  } else {
    _attachUploadStateEvents(status);
  }
}

function _attachParsedStateEvents(status) {
  // 시험 시작 버튼
  const startBtn = document.getElementById('start-exam-btn');
  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      const selectedSubjects = _getSelectedSubjects();
      try {
        showSpinner('시험을 준비하고 있습니다...');
        await api('POST', '/api/start-exam', { subjects: selectedSubjects });
        hideSpinner();
        navigateTo('exam');
      } catch (e) {
        hideSpinner();
        showToast('오류: ' + e.message, 'error');
      }
    });
  }

  // 다시 업로드 버튼
  const resetBtn = document.getElementById('reset-uploads-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      try {
        await api('POST', '/api/reset');
        renderHome(document.getElementById('app'));
      } catch (e) {
        showToast('오류: ' + e.message, 'error');
      }
    });
  }

  // 늦게 업로드하는 답지
  _setupUploadZone('answer-late-zone', 'answer-late-input', 'answer-late-status', async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    showSpinner('📝 AI가 답지를 분석하고 있습니다...');
    try {
      const res = await api('POST', '/api/parse-answer', fd, true);
      hideSpinner();
      showToast(`${res.count}개 답안 추출 완료`, 'success');
      setTimeout(() => renderHome(document.getElementById('app')), 800);
    } catch (e) {
      hideSpinner();
      showToast('답안 추출 실패: ' + e.message, 'error');
    }
  });
}

function _attachUploadStateEvents(status) {
  let qFile = null, aFile = null;
  const parseBtn = document.getElementById('parse-btn');

  function updateParseBtn() {
    if (parseBtn) parseBtn.disabled = !qFile;
  }

  _setupUploadZone('q-zone', 'q-input', 'q-status', (file) => {
    qFile = file;
    document.getElementById('q-status').textContent = `✓ ${file.name}`;
    updateParseBtn();
  });

  _setupUploadZone('a-zone', 'a-input', 'a-status', (file) => {
    aFile = file;
    document.getElementById('a-status').textContent = `✓ ${file.name}`;
  });

  if (parseBtn) {
    parseBtn.addEventListener('click', async () => {
      if (!qFile) { showToast('문제 PDF를 선택해 주세요', 'error'); return; }
      if (!status.api_key_set) {
        showToast('API 키를 먼저 입력해 주세요', 'error'); return;
      }
      showSpinner('📖 AI가 문제 PDF를 분석하고 있습니다...');
      try {
        const fd = new FormData();
        fd.append('file', qFile);
        const qRes = await api('POST', '/api/parse-pdf', fd, true);
        if (aFile) {
          document.getElementById('spinner-text').textContent = '📝 AI가 답지 PDF를 분석하고 있습니다...';
          const af = new FormData();
          af.append('file', aFile);
          try {
            await api('POST', '/api/parse-answer', af, true);
          } catch (_) {
            showToast('답지 추출에 실패했습니다. 문제만 사용합니다.', 'error');
          }
        }
        hideSpinner();
        showToast(`${qRes.count}개 문제 추출 완료`, 'success');
        setTimeout(() => renderHome(document.getElementById('app')), 600);
      } catch (e) {
        hideSpinner();
        showToast('PDF 분석 실패: ' + e.message, 'error');
      }
    });
  }
}

// ── 파일 드래그&드롭 업로드 존 설정 ─────────────────────────────────────────
function _setupUploadZone(zoneId, inputId, statusId, onFile) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;

  const handle = (file) => {
    if (!file || file.type !== 'application/pdf') {
      showToast('PDF 파일만 업로드 가능합니다', 'error');
      return;
    }
    onFile(file);
  };

  input.addEventListener('change', () => { if (input.files[0]) handle(input.files[0]); });

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handle(file);
  });
}

// ── 체크된 과목 목록 ──────────────────────────────────────────────────────────
function _getSelectedSubjects() {
  const boxes = document.querySelectorAll('#subject-select input[type="checkbox"]');
  if (!boxes.length) return [];
  return Array.from(boxes).filter(b => b.checked).map(b => b.value);
}

// _esc() is defined in app.js (shared utility)
