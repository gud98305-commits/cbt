# Gap Analysis: api

**Date**: 2026-02-20
**Feature**: api
**Phase**: Check (Iteration 4 -- Robustness Review)
**Overall Score**: 96/100

## Per-Area Scores

| Area | Score | Summary |
|------|-------|---------|
| API Layer | 95/100 | ValueError/RuntimeError separation, descriptive HTTP error codes |
| PDF Parser | 95/100 | Options split fix, scanned PDF detection, chunking, retry hardening |
| Config | 100/100 | MAX_PDF_PAGES and MAX_SECTION_CHARS correctly defined |
| Frontend JS | 92/100 | (Unchanged from Iteration 3) |
| Core Models | 90/100 | (Unchanged from Iteration 3) |
| Exam Service | 95/100 | (Unchanged from Iteration 3) |

## Robustness Implementation Plan -- Gap Analysis

All 5 planned items were evaluated against the actual code.

### Plan Item 1: Fix Options Concatenation Bug

| Requirement | Implementation | File:Line | Status |
|-------------|---------------|-----------|--------|
| Check `len(options) == 1` | `len(item["options"]) == 1` | pdf_parser.py:588 | MATCH |
| Detect circled numbers | `re.search(r"[①②③④⑤]", single)` | pdf_parser.py:590 | MATCH |
| Split by regex | `re.split(r"(?=[①②③④⑤])", single)` | pdf_parser.py:591 | MATCH |
| Require >= 2 parts after split | `if len(parts) >= 2` | pdf_parser.py:593 | MATCH |

Status: FULLY IMPLEMENTED

### Plan Item 2: Edge Case -- Scanned PDFs (Empty Text)

| Requirement | Implementation | File:Line | Status |
|-------------|---------------|-----------|--------|
| Count non-whitespace chars after extraction | `non_ws = len(re.sub(r"\s", "", ...))` | pdf_parser.py:113 | MATCH |
| Raise ValueError if < 100 chars | `if non_ws < 100: raise ValueError(...)` | pdf_parser.py:114-118 | MATCH |
| Descriptive error message | Korean message explaining scanned image PDF | pdf_parser.py:116-118 | MATCH |
| Warn if > 50% pages empty | `if empty_pages / len(doc) > 0.5: logger.warning(...)` | pdf_parser.py:119-122 | MATCH |

Status: FULLY IMPLEMENTED

### Plan Item 3: Edge Case -- Complex Layouts (Jumbled Text)

| Requirement | Implementation | File:Line | Status |
|-------------|---------------|-----------|--------|
| Page-level batching fallback | `_chunk_large_sections()` function | pdf_parser.py:374-401 | MATCH |
| Triggered when section > MAX_SECTION_CHARS | `if len(text) <= MAX_SECTION_CHARS` guard | pdf_parser.py:383 | MATCH |
| 5-page batch chunking | `for i in range(0, len(pages), 5)` | pdf_parser.py:396 | MATCH |
| `max_tokens` in OpenAI call | `max_tokens=16384` | pdf_parser.py:722 | MATCH |
| Called from `parse_pdf()` | `sections = _chunk_large_sections(sections)` | pdf_parser.py:129 | MATCH |

Status: FULLY IMPLEMENTED

### Plan Item 4: Edge Case -- API Token/Rate Limits

| Requirement | Implementation | File:Line | Status |
|-------------|---------------|-----------|--------|
| "context_length" in transient detection | `"context_length"` in error check list | pdf_parser.py:743 | MATCH |
| "token" in transient detection | `"token"` in error check list | pdf_parser.py:743 | MATCH |
| Token estimation warning | `estimated_tokens = len(user_text) // 4` + warning if > 25000 | pdf_parser.py:703-705 | MATCH |
| 5 retries for RateLimitError | `_RATE_LIMIT_MAX_RETRIES = 5` | pdf_parser.py:688 | MATCH |
| Longer backoff for RateLimitError | `_RATE_LIMIT_BACKOFF_BASE = 2.0` with exponential | pdf_parser.py:689, 730 | MATCH |
| `max_tokens=16384` in API call | Present in `client.chat.completions.create()` | pdf_parser.py:722 | MATCH |
| `MAX_PDF_PAGES = 200` in config | Defined in config.py | config.py:21 | MATCH |
| `MAX_SECTION_CHARS = 80000` in config | Defined in config.py | config.py:22 | MATCH |
| MAX_PDF_PAGES enforced in parse_pdf | `if len(doc) > MAX_PDF_PAGES: raise ValueError` | pdf_parser.py:98-101 | MATCH |

Status: FULLY IMPLEMENTED

### Plan Item 5: Better Error Propagation

| Requirement | Implementation | File:Line | Status |
|-------------|---------------|-----------|--------|
| Separate ValueError (422) | `except ValueError as e: raise HTTPException(status_code=422, ...)` | routes.py:86-87 | MATCH |
| Separate RuntimeError (503) | `except RuntimeError as e: raise HTTPException(status_code=503, ...)` | routes.py:88-92 | MATCH |
| Better error messages | Descriptive Korean messages for each case | routes.py:87, 91, 94 | MATCH |

Status: FULLY IMPLEMENTED

## Match Rate Summary

```
+---------------------------------------------+
|  Robustness Plan Match Rate: 100%            |
+---------------------------------------------+
|  Plan Items:        5 / 5 implemented        |
|  Sub-requirements: 26 / 26 matched           |
|  Missing items:     0                        |
|  Changed items:     0                        |
+---------------------------------------------+
```

## Remaining Minor Issues (Not Blocking)

| # | Issue | Reason Deferred |
|---|-------|-----------------|
| C2 | API key in `os.environ` | Design tradeoff for single-user desktop app |
| C5 | int/string key asymmetry | Already consistent at API boundary |
| W5 | Timer clock sync | Acceptable for local desktop app |
| W7 | API docs disabled | Production default |
| W9 | Fixed question order | Acceptable for practice tool |
| W11 | time.sleep in thread pool | Runs in to_thread, does not block event loop |

## Observations

1. **Retry logic is well-structured.** The dual-tier retry approach (3 retries for general errors, 5 for rate limits with longer backoff) is exactly as planned and handles production-scale API usage.

2. **Chunking strategy is robust.** The `_chunk_large_sections()` function correctly splits by `[PAGE N]` markers in 5-page batches, only activating when a section exceeds `MAX_SECTION_CHARS` (80,000 characters).

3. **Error propagation is clean.** The `parse_pdf()` function raises `ValueError` for user-correctable issues (empty PDF, scanned image, too many pages) and `RuntimeError` for infrastructure failures (missing API key). The routes layer maps these to appropriate HTTP status codes (422 vs 503).

4. **Options concatenation fix handles a real LLM edge case.** When the LLM returns all options concatenated into a single string with circled number prefixes, the parser detects and splits them correctly.

## Iteration History

- Iteration 1: Score 92/100 (initial analysis)
- Iteration 2: Score 74/100 (post-PDF parser rewrite, new issues)
- Iteration 3: Score 91/100 (9 issues fixed, 6 deferred as acceptable)
- Iteration 4: Score 96/100 (robustness plan -- 5/5 items verified, all 26 sub-requirements matched)
