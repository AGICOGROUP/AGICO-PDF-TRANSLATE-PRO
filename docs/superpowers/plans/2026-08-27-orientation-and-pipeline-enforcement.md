# Orientation and Pipeline Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all four translation adapters preserve visible source-text orientation and reject incomplete or unofficially built deliverables.

**Architecture:** Add reusable orientation/provenance contracts at adapter boundaries while keeping final gates adapter-local. Existing OCR and render results supply orientation evidence; official builders stamp reports, and official verifiers bind source, manifest, builder report, candidate, and QA hashes.

**Tech Stack:** Python 3, RapidOCR, Pillow, ReportLab, pypdf, unittest.

**Spec:** `docs/superpowers/specs/2026-08-27-orientation-and-pipeline-enforcement-design.md`

## Global Constraints

- Reuse existing OCR and render output; no additional OCR pass or full render.
- Added routine processing must remain within 30 seconds per document.
- Do not increase adapter gate counts.
- Native, scan, image, and bilingual final gates remain independent.
- Companion panels require complete one-to-one source-label coverage.

---

### Task 1: Scan PDF orientation and official provenance

**Files:**
- Modify: `formats/pdf/scan/scripts/extract_scan.py`
- Modify: `formats/pdf/scan/scripts/contracts.py`
- Modify: `formats/pdf/scan/scripts/build_scan.py`
- Modify: `formats/pdf/scan/scripts/verify_scan.py`
- Modify: `formats/pdf/scripts/route_pdf_file.py`
- Modify: `formats/pdf/scan/references/manifest-schema.md`
- Modify: `formats/pdf/scan/references/quality-gates.md`
- Test: `formats/pdf/scan/tests/test_text_orientation_and_provenance.py`
- Test: `formats/pdf/tests/test_route_pdf_file.py`

**Interfaces:**
- Produces: `rotation_from_quad(points) -> int` and source-line `rotation`.
- Produces: build report fields `builder`, `manifest_sha256`, `output_sha256`.
- Produces: verifier fields `orientation_mismatch_failures`, `unassigned_source_lines`, and `official_pipeline`.

- [ ] Write failing tests proving rotated OCR quads yield 90/270 degrees, `1002-0204-03.pdf` routes as an engineering drawing, missing/incorrect block rotation fails, incomplete companion coverage fails, and a report without official provenance fails.
- [ ] Run the focused tests and confirm failures are caused by missing behavior.
- [ ] Preserve OCR quadrilateral orientation, copy it into source lines/manifest blocks, and validate rotations are limited to 0/90/180/270.
- [ ] Stamp build reports with official builder identity plus source/manifest/output hashes.
- [ ] Make `verify_scan.py` reject source/target rotation mismatches, unassigned lines, incomplete companion mapping, and nonofficial build reports.
- [ ] Run scan and router regression suites.
- [ ] Commit only Task 1 files with `fix: enforce scan orientation and provenance`.

### Task 2: Native PDF orientation and provenance audit

**Files:**
- Modify: `formats/pdf/native/scripts/pdf_translation_pipeline.py`
- Modify: `formats/pdf/native/scripts/native_selectable_rebuild.py`
- Modify: `formats/pdf/native/scripts/run_v6_job.py`
- Modify: `formats/pdf/native/references/quality-gates.md`
- Test: `formats/pdf/native/tests/test_native_orientation_and_provenance.py`

**Interfaces:**
- Consumes: source block text-matrix direction and embedded-image OCR rotation.
- Produces: native rebuild records with `source_rotation`, `rendered_rotation`, and bound artifact hashes.

- [ ] Write failing tests for rotated native text, rotated embedded-image labels, and candidate/build-report hash mismatch.
- [ ] Run focused tests and confirm expected failures.
- [ ] Preserve text-matrix direction during native rebuild and pass embedded-image rotation to the existing image overlay route.
- [ ] Extend `run_v6_job.py verify` to reject orientation mismatches or an unbound candidate while retaining its six native gates.
- [ ] Run all native tests.
- [ ] Commit only Task 2 files with `fix: bind native orientation and output provenance`.

### Task 3: Standalone image orientation and provenance

**Files:**
- Modify: `formats/image/SKILL.md`
- Modify: `formats/image/scripts/image_pdf_bridge.py`
- Create: `formats/image/scripts/verify_image_output.py`
- Test: `formats/image/tests/test_image_orientation_and_provenance.py`

**Interfaces:**
- Consumes: raster source-line rotations and official intermediate build report.
- Produces: image final report with source/output dimensions, source/intermediate/output hashes, rotation mismatches, and `passed`.

- [ ] Write failing tests for rotated image text, missing intermediate provenance, wrong output format/dimensions, and output hash mismatch.
- [ ] Run focused tests and confirm expected failures.
- [ ] Carry source-line rotations through the one-page raster bridge without invoking scan final gates.
- [ ] Add the image-owned verifier and require its report before delivery.
- [ ] Run all image tests.
- [ ] Commit only Task 3 files with `fix: enforce image orientation and provenance`.

### Task 4: Bilingual overlay orientation and complete pairing

**Files:**
- Modify: `formats/pdf/bilingual/SKILL.md`
- Modify: `formats/pdf/bilingual/scripts/add_bilingual_overlay.py`
- Modify: `formats/pdf/bilingual/references/workflow.md`
- Test: `formats/pdf/bilingual/tests/test_orientation_and_pairing.py`

**Interfaces:**
- Consumes: source block rotation and complete source/target pairing inventory.
- Produces: overlay build report with per-block source/rendered rotation and candidate hash.

- [ ] Write failing tests for rotated overlay text, incomplete source/target pairing, summary-only companion panels, and missing build provenance.
- [ ] Run focused tests and confirm expected failures.
- [ ] Render each translation using the source block rotation and stamp the overlay build report.
- [ ] Reject incomplete pairing and summary-only panels in the bilingual adapter's existing gates.
- [ ] Run all bilingual tests.
- [ ] Commit only Task 4 files with `fix: enforce bilingual orientation and pairing`.

### Task 5: Skill enforcement, synchronization, and budget regression

**Files:**
- Modify: `SKILL.md`
- Modify: `formats/pdf/SKILL.md`
- Modify: the four adapter `SKILL.md` files only where needed
- Create: `formats/test_pipeline_enforcement_contract.py`

**Interfaces:**
- Consumes: adapter-owned official provenance reports.
- Produces: one routing contract that forbids delivery without the selected adapter's `passed` final report.

- [ ] Write failing contract tests forbidding ad-hoc deliverables and cross-adapter final gates.
- [ ] Update routing/adapter instructions to make official final-report provenance the delivery contract.
- [ ] Time orientation/provenance checks on the regression fixtures and require added runtime below 30 seconds.
- [ ] Run all adapter suites and repository self-tests.
- [ ] Synchronize project and installed skills and compare SHA-256 hashes.
- [ ] Commit Task 5 files with `feat: enforce official adapter delivery chain`.
