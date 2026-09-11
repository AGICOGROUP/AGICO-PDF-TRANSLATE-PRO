# Remaining PDF Refactor Implementation Plan

> Use executing-plans and test-driven-development; independent scan and timing modules may run under dispatching-parallel-agents. User explicitly requested continuation through all phases and one final integrated review.

**Goal:** Reduce fragment-level work and unchanged-page rework without removing readable content or relaxing quality checks.

**Architecture:** Retain all adapters. CAD gains conservative unit proposals and an atomic unit-to-existing-packet importer. CAD review and scan build cache independent pages with content/configuration binding. A small optional session ledger measures wall time, retries and pauses, separate from script CPU time. Optimize OCR caching/versioning and initialization only where measurable; do not add concurrency by default.

**Spec:** `docs/2026-09-11-pdf-skill-refactor-audit-zh.md`.

## Constraints

- Preserve phase-1 changes, main, sources, older jobs and acceptance policy. No remote writes.
- All edits overwrite their previous rule/implementation; no duplicate workflow.
- New tests must fail against old behavior before production edits.
- Workloads using existing translations may benchmark rendering/building only, never claim fresh end-to-end translation gains.
- Baseline archive remains recoverable. Its hash was verified. Cleanup of the generated unpacked copy was attempted with an exact-path guard but rejected by execution policy; the copy remains, no deletion workaround was attempted. This optional housekeeping is deferred, not an implementation or QA prerequisite. Always use the repository root Skill, not the nested baseline copy.

## Phase 2: CAD coherent units

- [x] Add `cad_units.py` and tests. Propose contiguous native same-line fragments, preserving cell membership, rotation, source IDs, protected records, numbering and reading order. Include whole-page context; multiline clauses stay conservative suggestions/manual units, never proximity-only automatic paragraphs.
- [x] `prepare` exports `translation-units.json` bound to the inventory. `merge-units <job> --translations <file>` translates one reviewed unit once and expands into the existing leader/merged member contract. Validate exact source/member binding and disjoint members; reject stale/conflicting unit updates atomically.
- [x] Test positive phrase, table border/neighbor, dimension/tag, rotated/multiline separation, resume and stale unit rejection. No automatic translation engine or deletions in grouping.

## Phase 3: Local recomputation

- [x] CAD review: content-fingerprint each rendered page plus text/geometry; include local records, rotation and review version. Reuse complete unchanged page artifacts and OCR; rebuild corrupt/changed pages. Preserve all original region filenames/index entries and whole-candidate evidence binding. Fix rotated crop coordinate conversion. Optional-content/form documents conservatively use document-level identity.
- [x] CAD OCR: cache keys include relevant implementation/dependency/model identity; do not initialize an OCR engine on a valid cache hit. Do not remove the existing full-page supplement without quality evidence.
- [x] Scan builder: cache single-page PDFs plus measured reports using source pixels, page manifest/blocks, implementation and font identity. Reassemble in requested order; dirty/corrupt pages rebuild; failed build retains the previous final PDF. Keep original rendering functions and exact visual/selectable behavior.
- [x] Test changed page, source pixels, font/config invalidation, corrupt artifacts, removed records, page ordering, and unchanged-page evidence; keep final QA intact.

## Phase 4: Measured execution and final audit

- [x] Add optional standalone session timing CLI with atomic state, source/request binding, pause/resume, attempt history, true end-to-end active wall time and remaining budget. It records failed attempts, never sets adapter QA passed or manufactures review evidence.
- [x] Benchmark cold/full and one-page repair with source/manifest-bound synthetic multi-page cases. Compare decoded pixels and selectable text, not just speed. Measure grouping reduction on a real source inventory without using its prior translations.
- [x] Revise the affected Skill command/schema references in place; retain fresh-test isolation and original quality requirements.
- [x] Run all tests, metadata validation, diff checks, and independent integrated review. Correct significant findings, rerun full tests, record results and limits. Final: 392 tests + 19 subtests; six Skill metadata validations. Both independent P1/P2 findings fixed and rechecked. No claim that component gains establish the user's 30–60% fresh-translation target. See `docs/2026-09-11-refactor-completion-report-zh.md`.
