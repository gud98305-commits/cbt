/**
 * app.js — SPA 라우터 + 전역 유틸리티
 */

// ── 전역 상태 ────────────────────────────────────────────────────────────────
const App = {
  page: 'home',  // 'home' | 'exam' | 'result'
};

// ── API 유틸 ─────────────────────────────────────────────────────────────────
async function api(method, path, body = null, isForm = false) {
  const opts = { method };
  if (body && !isForm) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  } else if (body && isForm) {
    opts.body = body;  // FormData
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── 라우터 ───────────────────────────────────────────────────────────────────
function navigateTo(page) {
  App.page = page;
  render();
}

function render() {
  const appEl = document.getElementById('app');
  if (App.page === 'home') {
    renderHome(appEl);
  } else if (App.page === 'exam') {
    renderExam(appEl);
  } else if (App.page === 'result') {
    renderResult(appEl);
  }
}

// ── 스피너 ──────────────────────────────────────────────────────────────────
function showSpinner(text = '처리 중...') {
  document.getElementById('spinner-text').textContent = text;
  document.getElementById('spinner').style.display = 'flex';
}
function hideSpinner() {
  document.getElementById('spinner').style.display = 'none';
}

// ── 토스트 ──────────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (type ? ' ' + type : '');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = 'toast'; }, 3000);
}

// ── 확인 모달 ────────────────────────────────────────────────────────────────
function showConfirm(title, body, onConfirm) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent = body;
  const modal = document.getElementById('confirm-modal');
  modal.style.display = 'flex';
  const confirmBtn = document.getElementById('modal-confirm');
  const cancelBtn = document.getElementById('modal-cancel');
  const close = () => {
    modal.style.display = 'none';
    confirmBtn.replaceWith(confirmBtn.cloneNode(true));
    cancelBtn.replaceWith(cancelBtn.cloneNode(true));
  };
  confirmBtn.addEventListener('click', () => { close(); onConfirm(); }, { once: true });
  cancelBtn.addEventListener('click', close, { once: true });
}

// ── HTML 이스케이프 (공용 유틸리티) ──────────────────────────────────────────
function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── HTML 이스케이프 + 서식 보존 (줄바꿈, 밑줄) ──────────────────────────────
function _escHtml(str) {
  if (!str) return '';
  return _esc(str)
    .replace(/\[\[u\]\]/g, '<u>')
    .replace(/\[\[\/u\]\]/g, '</u>')
    .replace(/\n/g, '<br>');
}

// ── 서식 보존 렌더링 (밑줄 + HTML 표 허용) ──────────────────────────────────
function _renderFormattedText(str) {
  if (!str) return '';
  // HTML 표 태그를 보존하기 위해 <table> 블록을 먼저 분리
  var parts = String(str).split(/(<table[\s\S]*?<\/table>)/gi);
  var result = '';
  for (var i = 0; i < parts.length; i++) {
    if (/^<table/i.test(parts[i])) {
      // 표는 그대로 삽입 (안전한 태그만 허용)
      result += parts[i]
        .replace(/<(?!\/?(?:table|tr|td|th|thead|tbody|tfoot|caption|colgroup|col)\b)[^>]*>/gi, '');
    } else {
      result += _escHtml(parts[i]);
    }
  }
  return result;
}

// ── 초기 렌더 ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => { render(); });
