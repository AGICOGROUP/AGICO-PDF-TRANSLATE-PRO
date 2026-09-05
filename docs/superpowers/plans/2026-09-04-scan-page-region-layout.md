# Scan Page-Region Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the scan adapter group OCR lines into page-aware semantic regions and render each page with consistent role-based typography and complete glyph-local cleanup.

**Architecture:** Enhance the existing draft grouping script rather than add a new pipeline. Extend the manifest cleanup contract with optional multiple glyph boxes, then reuse the builder's page typography pass to resolve a single common fitting size per role group.

**Tech Stack:** Python 3.12, unittest/pytest, Pillow, ReportLab, pypdf.

**Spec:** `docs/superpowers/specs/2026-09-04-scan-page-region-layout-design.md`

## Global Constraints

- Change only `formats/pdf/scan/` plus its Skill and reference documentation.
- Do not add OCR passes, full-document renders, or document-specific gates.
- Preserve existing manifest compatibility and official build/verify identity.
- Every source-line ID remains assigned exactly once.
- Use glyph-local cleanup and preserve graphic structure.

---

### Task 1: Page-aware semantic region grouping

**Files:**
- Modify: `formats/pdf/scan/scripts/draft_blocks.py`
- Create: `formats/pdf/scan/tests/test_page_region_grouping.py`

**Interfaces:**
- Consumes: extraction `source_lines` dictionaries with `id`, `page`, `box`, `text`, `score`, and `rotation`.
- Produces: `group_page_lines(lines: list[dict], page_height: float | None = None) -> list[dict]`; each group has `line_ids`, `box`, `clean_boxes`, `text`, `role`, `rotation`, `min_score`, and `grouping_reason`.

- [ ] Write failing tests with hand-authored line fixtures for prose joining, heading separation, columns, lists, tables, headers, footers, and rotated labels.
- [ ] Run `python -m pytest formats/pdf/scan/tests/test_page_region_grouping.py -q` and confirm grouping assertions fail against the current proximity-only implementation.
- [ ] Implement deterministic line classification, column compatibility, reading-order joining, and safe fallback to smaller regions.
- [ ] Run the focused test and confirm all grouping cases pass.

### Task 2: Multi-box glyph cleanup contract

**Files:**
- Modify: `formats/pdf/scan/scripts/contracts.py`
- Modify: `formats/pdf/scan/scripts/build_scan.py`
- Create: `formats/pdf/scan/tests/test_region_cleanup.py`

**Interfaces:**
- Consumes: replacement blocks defining exactly one of `clean_box` or `clean_boxes`.
- Produces: validated manifests and `clean_background()` evidence whose approved mask is the union of all glyph-local boxes.

- [ ] Write failing tests proving multiple cleanup boxes are accepted, overlapping graphics between them remain unchanged, both cleanup fields together are rejected, and legacy `clean_box` remains valid.
- [ ] Run `python -m pytest formats/pdf/scan/tests/test_region_cleanup.py -q` and confirm the new contract tests fail.
- [ ] Implement manifest validation and builder iteration over normalized cleanup boxes.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Common page typography resolution

**Files:**
- Modify: `formats/pdf/scan/scripts/build_scan.py`
- Modify: `formats/pdf/scan/tests/test_page_typography_policy.py`

**Interfaces:**
- Consumes: translated blocks classified by role and page geometry.
- Produces: one resolved font size, weight, and leading ratio for each page typography group; body fit uses the largest size that fits every body region.

- [ ] Add failing tests proving header/footer/table blocks do not affect body sizing, all body blocks receive one common fitted size, and an impossible common fit raises `TextOverflowError`.
- [ ] Run `python -m pytest formats/pdf/scan/tests/test_page_typography_policy.py -q` and confirm the new assertions fail for the expected behavioral gaps.
- [ ] Extend typography grouping and common-fit resolution with role-specific groups and shared leading.
- [ ] Run the focused tests and confirm they pass.

### Task 4: Skill workflow and regression verification

**Files:**
- Modify: `formats/pdf/scan/SKILL.md`
- Modify: `formats/pdf/scan/references/workflow.md`
- Modify: `formats/pdf/scan/references/manifest-schema.md`
- Modify: `formats/pdf/scan/references/quality-gates.md`

**Interfaces:**
- Documents the executable `draft_blocks.py` step, page-context translation payload, `clean_boxes`, and page typography evidence.

- [ ] Update the Skill and references to require page-aware grouping for prose while retaining cell/label granularity for tables and drawings.
- [ ] Run all scan tests: `python -m pytest formats/pdf/scan/tests -q`.
- [ ] Run all PDF adapter tests: `python -m pytest formats/pdf/native/tests formats/pdf/scan/tests formats/pdf/bilingual/tests formats/image/tests formats/pdf/tests -q`.
- [ ] Run `python -m pytest formats/test_independent_quality_gates.py -q`.
- [ ] Run `git diff --check` on modified tracked files and report any pre-existing untracked files separately.
