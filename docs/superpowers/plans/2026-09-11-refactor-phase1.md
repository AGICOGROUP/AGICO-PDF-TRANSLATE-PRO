# Refactor Phase 1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task. The user approved the audit proposal and requested phased implementation on `codex`.

**Goal:** Prevent wrong-language state reuse, incorrect bilingual passthrough and invisible CAD placements without changing translation/rendering quality policy.

**Architecture:** Retain the four adapters. Bind native jobs to translation intent; bind CAD prepare packets to an explicit target when supplied. Correct the existing bilingual decision and enforce visible CAD layout before source deletion. No new service or translation backend.

**Tech Stack:** Python, pytest, PyMuPDF, existing native runner and JSON artifacts.

**Spec:** `docs/2026-09-11-pdf-skill-refactor-audit-zh.md` (phase 1 only).

## Global Constraints

- Work in the user-selected `codex` checkout; do not move `main`, push, or modify unrelated artifacts.
- Keep the stable source snapshot inside the repository's temporary artifacts, addressed by commit. Do not redirect the installed Junction during work.
- Preserve source files and previous jobs. `fresh` creates independent state, never deletes old results.
- Replace obsolete guidance; no new cosmetic delivery blockers.
- First run failing behavior tests, then implement the minimum correction.

## Task 1: Reproducible baseline and test entrypoint

Files: create `pytest.ini`; update the obsolete adapter/test/environment lines in `AGENTS.md`; record baseline in `docs/2026-09-11-refactor-phase1-results.md`.

- [x] Snapshot `dade7e537b4ca36a8541b40de169b741bdcd68e2` with `git archive` into `tmp/refactor-baselines/dade7e53/`, extract separately and record dependency versions without installing/upgrading packages.
- [x] Reproduce default pytest collection failure, then configure `addopts = --import-mode=importlib` and explicit adapter testpaths, including native-cad and independent gates.
- [x] Run `python -m pytest -q` and confirm the original 295 tests / 13 subtests pass before behavioral edits.

## Task 2: Intent-bound jobs and fresh runs

Files: `formats/pdf/native/scripts/v6_job_state.py`, `run_v6_job.py`, their tests; `formats/pdf/native-cad/scripts/native_cad_pipeline.py`, CAD tests; native/CAD Skill command references.

Interfaces: `create_job(source, jobs_root, *, request=None, fresh=False)`; runner `init ... --source-language ru --target-language zh-CN [--fresh]`; CAD `prepare ... --target-language zh-CN [--fresh]`.

- [x] Add integration tests with a real tiny PDF: initialize one source into English and Chinese under one jobs root; assert different jobs and correct manifest languages. Initialize the same request twice and assert reuse. Fresh initialization must retain the old job but create an independent manifest.

  ```python
  assert english_job != chinese_job
  assert chinese_manifest['target_language'] == 'zh-CN'
  assert fresh_job != chinese_job
  ```

- [x] Run these tests against unchanged production code and record failures.
- [x] Normalize language identity (case and hyphen only), hash the request into new native job identities, validate existing manifest intent before rebinding. Keep direct legacy state API usable.
- [x] CAD: record target identity in inventory and packet; a different target in a nonempty bound job cannot overwrite its contents. Fresh prepare selects an independent directory and returns its actual path. Preserve legacy apply compatibility for old unbound jobs.
- [x] Test mismatched CAD packets, same-target resume and independent fresh jobs. Update existing instructions to supply actual languages at initialization, rather than editing manifest language after extraction.

## Task 3: Language-specific bilingual completion

Files: `formats/pdf/scripts/decide_drawing_translation.py`, `formats/pdf/tests/test_drawing_translation_mode.py`, root/PDF/bilingual Skill and relevant workflow references.

Interfaces: inventory `language_pair` and `requested_language_pair`, each two explicit language codes; existing five coverage counts refer to that inventoried pair. Saved route remains authoritative for output mode.

- [x] Add negative cases: complete zh/en does not satisfy zh/es; missing language identities or a missing coverage count cannot trigger passthrough. Add positive same-pair and reversed-order cases. Explicit replace must still return replace.

  ```python
  assert decide(complete_zh_en_requesting_zh_es)['action'] == 'add_bilingual'
  assert decide(complete_zh_es_requesting_es_zh)['action'] == 'skip_translation'
  ```

- [x] Observe the failing cases, then amend the existing `complete` predicate. Unknown evidence means continue translation/inventory, not fail the job.
- [x] Replace the old “Chinese plus any foreign language” shortcut wherever it governs execution. Exercise the CLI with the documented inventory shape.

## Task 4: CAD visible layout and non-destructive failure

Files: `formats/pdf/native-cad/scripts/native_cad_pipeline.py`, `formats/pdf/native-cad/tests/test_native_phrase_groups.py`.

- [x] Add real apply tests: off-page, empty, nonfinite and reversed native layout boxes must not erase source or create a successful candidate; a valid merged phrase remains selectable and drawn once.
- [x] Observe red tests. Validate layout coordinates before fitting/deleting native text, sharing the safe page-boundary invariant with outline handling. Do not force all relocated labels to overlap the source or impose an unreviewed table heuristic.
- [x] Keep existing fit-overflow preview behavior; verify source bytes are unchanged and error reports identify affected IDs.

## Task 5: Verification and checkpoint

- [x] Run default full pytest, Skill metadata validation for changed entrypoints, and `git diff --check`.
- [x] Review the diff for accidental broader routing/font/quality-gate changes; check main hash and baseline snapshot.
- [x] Record actual red/green outcomes, environment, known limits and next phase. No claim of end-to-end speedup: fresh translation benchmarks belong after semantic-unit/local-repair work.
- [x] Hand off the phase-1 checkpoint with changes left on codex; no remote operations. Phase 2 will separately implement conservative CAD grouping proposals, not automatically merge all nearby text.
