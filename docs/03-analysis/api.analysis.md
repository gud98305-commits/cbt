# Gap Analysis: api

**Date**: 2026-02-20
**Feature**: api
**Phase**: Check (Iteration 3)
**Overall Score**: 91/100

## Per-Area Scores

| Area | Score | Summary |
|------|-------|---------|
| API Layer | 90/100 | Thread-safe session, validated inputs, file size limits |
| PDF Parser | 88/100 | Deterministic parser with validation, proper error propagation |
| Frontend JS | 92/100 | Shared utilities, fixed event handler leaks |
| Core Models | 90/100 | Well-designed Pydantic models |
| Exam Service | 95/100 | Correct scoring denominator |

## Issues Fixed in Iteration 3

| # | Issue | Fix Applied |
|---|-------|------------|
| C1 | Thread-unsafe session state | Added `threading.Lock` to all session operations |
| C3 | No API key validation | Added `sk-` prefix format check |
| C4 | Silent empty results on OpenAI failure | Raises `ValueError`/`RuntimeError`, caught as HTTP 422 in routes |
| W3 | `\s+` matches newlines in subject regex | Changed to `[^\S\n]+` (horizontal whitespace only) |
| W4 | Score denominator includes unanswerable questions | Filter to only `scorable` questions in denominator |
| W6 | Cross-file `_esc` dependency | Moved `_esc` to `app.js` as shared utility |
| W8 | No PDF file size limit | Added 50MB limit with HTTP 413 response |
| W10 | showConfirm leaks event handlers | Use `{ once: true }` + `replaceWith(cloneNode)` |
| W2 | Deterministic parser assumes uniform row blocks | Added monotonic question number validation |

## Remaining Minor Issues (Not Blocking)

| # | Issue | Reason Deferred |
|---|-------|-----------------|
| C2 | API key in `os.environ` | Design tradeoff for single-user desktop app, OpenAI SDK reads from env |
| C5 | int/string key asymmetry | Already consistent at API boundary (JSON keys always strings) |
| W5 | Timer clock sync | Acceptable for local desktop app (same machine) |
| W7 | API docs disabled | Production default, not a bug |
| W9 | Fixed question order | Acceptable for practice tool |
| W11 | time.sleep in thread pool | Runs in to_thread, doesn't block event loop |

## Iteration History

- Iteration 1: Score 92/100 (initial analysis)
- Iteration 2: Score 74/100 (post-PDF parser rewrite, new issues)
- Iteration 3: Score 91/100 (9 issues fixed, 6 deferred as acceptable)
