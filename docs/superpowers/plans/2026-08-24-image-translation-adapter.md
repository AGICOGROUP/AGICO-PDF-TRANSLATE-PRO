# Image Translation Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the translation router with a single-image PNG/JPEG adapter that reuses the scan-PDF raster translation workflow.

**Architecture:** Route PDF inputs through the existing PDF classifier and route PNG/JPEG inputs directly to a new image adapter. The image adapter wraps one source image as a one-page PDF, runs the existing scan workflow, then exports the translated page back to the original image format and pixel dimensions.

**Tech Stack:** Python 3, Pillow, PyMuPDF, unittest/pytest-compatible tests, Markdown skill instructions.

**Spec:** User-approved discussion in the 2026-08-24 task.

## Global Constraints

- Support one static `.png`, `.jpg`, or `.jpeg` input per job.
- Preserve source pixel dimensions and PNG transparency where representable.
- Output the same raster format as the input.
- Do not support GIF, SVG, animated images, or multi-page TIFF in this version.
- Reuse the scan-PDF manifest, cleanup, typography, terminology, and QA rules.

---

### Task 1: Image adapter and routing contract

**Files:**
- Create: `formats/image/SKILL.md`
- Create: `formats/image/agents/openai.yaml`
- Create: `formats/image/tests/test_image_adapter_contract.py`
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: source file suffix and the existing `formats/pdf/scan/SKILL.md` workflow.
- Produces: an explicit image route and a documented same-format output contract.

- [x] Write tests asserting the root router advertises PNG/JPEG and the image adapter declares scan-workflow reuse, supported formats, same-size output, and unsupported formats.
- [x] Run the contract tests and verify they fail because the adapter does not exist.
- [x] Add the minimal router and adapter instructions.
- [x] Run the contract tests and verify they pass.

### Task 2: Lossless image/PDF boundary helpers

**Files:**
- Create: `formats/image/scripts/image_pdf_bridge.py`
- Create: `formats/image/tests/test_image_pdf_bridge.py`

**Interfaces:**
- Consumes: `wrap SOURCE_IMAGE OUTPUT_PDF METADATA_JSON` or `unwrap TRANSLATED_PDF METADATA_JSON OUTPUT_IMAGE`.
- Produces: one-page PDF input for the scan adapter and a same-format, same-pixel-size translated image.

- [x] Write tests for PNG/JPEG validation, one-page PDF creation, pixel-dimension restoration, output suffix preservation, and transparent-PNG preservation.
- [x] Run the tests and verify they fail because the bridge is absent.
- [x] Implement only the tested CLI and conversion behavior.
- [x] Run the bridge and contract tests and verify they pass.

### Task 3: Full verification

**Files:**
- Modify only files required by failing verification.

**Interfaces:**
- Consumes: the completed image adapter.
- Produces: fresh test evidence and skill validation results.

- [x] Run all image adapter tests.
- [x] Run the repository's existing PDF router tests.
- [x] Run skill validation against the root, PDF, scan, and image skill directories.
- [x] Inspect `git diff` and confirm unrelated untracked files remain untouched.
