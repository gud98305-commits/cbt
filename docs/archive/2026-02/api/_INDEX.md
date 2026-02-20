# Report Index

> **Report Directory**: `docs/04-report/`
> **Last Updated**: 2026-02-20
> **Status**: Actively generating completion reports

---

## Document Inventory

### Completion Reports

| Report | Feature | Completed | Score | Status | Archive |
|--------|---------|-----------|-------|--------|---------|
| [api.report.md](./api.report.md) | PDF Parser Robustness | 2026-02-20 | 96/100 | ✅ Complete | Eligible |

### Metadata

| Type | File | Purpose |
|------|------|---------|
| **Changelog** | [changelog.md](./changelog.md) | Feature release notes and version history |
| **Index** | [_INDEX.md](./_INDEX.md) | This document |

---

## Feature Summary

### api — PDF Parser Robustness (✅ Complete)

**Completion Date**: 2026-02-20
**Final Score**: 96/100 (Iteration 4)
**Project Level**: Dynamic
**Key Achievements**:
- Options Concatenation Fix (rescues ~4 questions per PDF)
- Scanned PDF Detection (early error reporting)
- Complex Layout Chunking (prevents LLM context overflow)
- Token/Rate Limit Hardening (dual-tier retry strategy)
- Error Propagation (422 vs 503 distinction)

**Iteration History**:
- Iteration 1: 92/100
- Iteration 2: 74/100 (regression)
- Iteration 3: 91/100
- Iteration 4: 96/100 (verified)

**Related Documents**:
- Plan: (not created — deferred to analysis)
- Design: (not created — deferred to analysis)
- Analysis: [`docs/03-analysis/api.analysis.md`](../03-analysis/api.analysis.md)
- Report: [`api.report.md`](./api.report.md)

---

## Archive Guidelines

### When to Archive

Archive completed features when:
1. PDCA cycle finished (phase = "completed")
2. Check phase score >= 90%
3. All documentation complete (plan, design, analysis, report)
4. Ready for production deployment

### Archive Command

```bash
/pdca archive {feature} [--summary]
```

Archive paths:
```
docs/archive/YYYY-MM/{feature}/
  ├── {feature}.plan.md
  ├── {feature}.design.md
  ├── {feature}.analysis.md
  └── {feature}.report.md
```

---

## Report Generation Workflow

```
Plan → Design → Do → Check → Act → Report → Archive
                               ↓
                          (if score < 90%)
                               ↓
                           Iterate → Check
```

### PDCA Commands

| Phase | Command | Output | Condition |
|-------|---------|--------|-----------|
| Plan | `/pdca plan {feature}` | `docs/01-plan/features/{feature}.plan.md` | Start new feature |
| Design | `/pdca design {feature}` | `docs/02-design/features/{feature}.design.md` | After plan approved |
| Do | `/pdca do {feature}` | Implementation guide | After design approved |
| Check | `/pdca analyze {feature}` | `docs/03-analysis/{feature}.analysis.md` | After implementation |
| Act | `/pdca iterate {feature}` | Auto-fix code | If score < 90% |
| Report | `/pdca report {feature}` | `docs/04-report/{feature}.report.md` | If score >= 90% |
| Archive | `/pdca archive {feature}` | `docs/archive/YYYY-MM/{feature}/` | If completed |

---

## Statistics

### Current Status

| Metric | Value |
|--------|-------|
| Features Completed | 1 |
| Features In Progress | 0 |
| Features Deferred | 0 |
| Total Iterations | 4 |
| Average Final Score | 96/100 |

### Historical Trends

| Phase | Count | Avg Score |
|-------|-------|-----------|
| Completed | 1 | 96/100 |
| Archived | 0 | — |

---

## Document Standards

All reports in `docs/04-report/` follow the **bkit report template** structure:

### Sections Required

1. **Executive Summary** — One-paragraph overview
2. **PDCA Cycle Summary** — Plan, Design, Do, Check, Act phases
3. **Results** — Completed and incomplete items
4. **Metrics** — Code changes, quality scores, performance
5. **Achievements** — Highlight 3-4 key wins
6. **Lessons Learned** — What went well, improvements, next-time applications
7. **Technical Insights** — Deep dive on tricky implementations
8. **Next Steps** — Immediate, short-term, medium-term follow-ups
9. **Appendix** — File locations and references

### Naming Convention

```
{feature}.report.md          # api.report.md
{date}-status.md             # 2026-02-20-status.md (monthly rollup)
sprint-{N}.md                # sprint-3.md (sprint reports)
```

---

## Cross-References

### Related Documents

- **PDCA Status**: `.bkit-memory.json` (feature tracking)
- **Plan Index**: [`docs/01-plan/_INDEX.md`](../01-plan/_INDEX.md)
- **Design Index**: [`docs/02-design/_INDEX.md`](../02-design/_INDEX.md)
- **Analysis Index**: [`docs/03-analysis/_INDEX.md`](../03-analysis/_INDEX.md)

### Project Documentation

- **Project Overview**: `CLAUDE.md`
- **Contributing Guide**: `CONTRIBUTING.md`
- **Architecture**: `docs/architecture/`

---

## Maintenance

### Regular Tasks

- [ ] Review completed features for archive eligibility (monthly)
- [ ] Update changelog with new reports (per feature)
- [ ] Archive features that meet criteria (quarterly)
- [ ] Clean up archived features from status (as needed)

### Archive Cleanup

When archiving multiple features, use cleanup to reduce status file size:

```bash
/pdca cleanup              # Interactive cleanup
/pdca cleanup all          # Delete all archived from status
/pdca cleanup {feature}    # Delete specific feature
```

---

*Last Updated*: 2026-02-20
*Status*: Active — Ready for additional features
*Next Report*: Upon completion of next feature
