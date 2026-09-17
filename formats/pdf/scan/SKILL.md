---
name: PDF-TRANSLATE-PRO-SCAN
description: Use when translating scan-only or raster PDFs, including hidden OCR layers, with text pages, tables, illustrations or engineering drawings and a requirement to preserve page correspondence and technical artwork.
---

# PDF-TRANSLATE-PRO-SCAN

## Scope and routing

Follow the PDF router's adapter and output mode. Confirm `scan-only` with
`scripts/classify_pdf.py --source <source>`. Hidden OCR is not visible native
text. Resolve `normalize-rotation-first` without changing visible content;
native/mixed input returns to the PDF router.

All scan-only pages use `preserve_raster`: retain the complete original page
image, identify text with OCR, clean the source glyph regions locally using
sampled/constant background fills, and write selectable target-language text.
This applies equally to prose, contents, clauses, lists, regular tables and
engineering drawings. Do not rebuild scanned pages as newly typeset documents
or route text/table pages to a reconstruction workflow.

An explicit target-language-only request uses replacement. Explicit bilingual
output or an engineering default of `add_bilingual` retains source text and adds
target text without cleanup. Engineering drawings follow
`references/additive-bilingual-drawings.md`; its Chinese-specific inventory
shortcut applies only to actual Chinese pairs matching the router's inventory.
Other language pairs continue translation without that shortcut. Record the
actual source language and preserve diagram geometry. If no readable placement
fits, report a located layout issue; do not silently change output mode.

Standalone PNG/JPEG carriers also use `preserve_raster` under the image adapter.

## Required workflow

Read `../../../references/delivery-policy.md` and
`../../../references/page-context-translation-review.md`, then
`references/workflow.md` and `references/quality-gates.md`.
Read `references/manifest-schema.md` for the raster manifest contract.
For cement terms, consult `references/cement-terminology.md` through
`scripts/glossary_lookup.py`. Prefer its user-revised equivalents over model
wording when the full phrase and engineering sense match. Apply the shared
page-context review's lookup, alternatives and non-Chinese source guidance;
the last duplicate is a lookup default, not an unconditional semantic override.

1. Fingerprint the immutable input and establish page geometry, output mode,
   target language and a task start time. Use an isolated job directory. Every
   requested test starts in a new directory with fresh extraction and review;
   reuse within that same run for repairs, never historical test results.
2. Render source pages at a readable resolution and inspect them as whole pages.
   Use `extract_scan.py` for OCR assistance, not as the translation authority.
   Magnify only uncertain names, dimensions, tolerances, formulas and dense cells.
   Apply the shared two-attempt limit for blurry source text, including handwriting:
   initial inspection plus at most one targeted retry. Preserve and record still
   illegible regions; continue translating all readable content without revisiting
   those regions during later review.
   Missing detections, low recognition scores and angle-classifier mistakes do
   not prove source illegibility. Inspect located `ocr_review_candidates` in the
   page/draft metadata. Readable omissions require verified source supplements,
   complete passage translations and matching cleanup; never classify them as
   blurry merely because the OCR engine failed. Direct visual reading needs no
   additional OCR. Keep candidate IDs in the existing semantic review coverage.
   Each candidate also needs an explicit disposition with source-pixel evidence;
   an ID marked reviewed is not evidence that missing text was translated.
   For omissions in a resumed/legacy job, run `audit_scan_inventory.py` on all
   selected pages, then compare new draft grouping with existing source-ID
   ownership. Repair affected passages; do not limit the investigation to user
   screenshots or reuse old grouping just because its source hash matches.
   Record `preserve_raster` for every page in `manifest/page-plan.json`.
3. Restore complete sentences across scan lines. Translate headings, paragraphs,
   clauses, lists, cells, captions and diagram labels in whole-page context.
   Keep each readable source item assigned once; register located OCR omissions
   without duplicating existing translations. Confirm numbers, signs, units,
   negation and terminology against source pixels. For cement terminology use
   `scripts/glossary_lookup.py`; use its English terms for English output and
   their controlled concepts consistently for other target languages.
   Check provisional grouping in reading order: a continuation must not jump
   over a new paragraph or heading to join an earlier paragraph. When an OCR
   omission is recovered, rebuild the complete affected sentence/paragraph and
   its ownership and cleanup together, not only the newly recognized fragment.
   Keep separately detected list markers with their own text; a new list item
   starts a new region. Registered lines in the wrong paragraph need ownership
   review even when the ink audit reports no gap.
4. Use `make_manifest_template.py`, `draft_blocks.py`, compact translation
   decisions and `compile_translation.py`, then the official `build_scan.py`.
   Follow `references/workflow.md`; retain the source image as every page's base.
   Replacement cleans source glyph regions before writing vector translations;
   additive output never cleans source pixels.
5. Assemble pages in source order, with one output page per selected source page.
   Run `verify_scan.py` against the exact candidate and official build report.
6. Render all output pages for initial coverage, compare complete source/target
   meaning on every page, and inspect changed regions and anomalies at high zoom.
   Correct affected pages only and retain unchanged-page evidence by identity.
   Save actual semantic and visual evidence, not passing templates. Selectable
   text and correct page counts alone cannot establish translation accuracy.

## Artwork and typography

- Keep the complete original page image and all non-text artwork at source
  positions. Never redraw engineering geometry, regenerate the page, or replace
  diagrams with lookalikes. No whole-page image generation or inpainting.
- Limit any restoration to verified line segments interrupted by glyph cleanup.
  Never cover a rule, icon, signature or leader merely to fit a translation.
- Establish consistent document heading/body/annotation styles and independent
  table/header/footer styles. Wrap full passages, then adjust spacing within the
  verified target text area. If needed, reduce an overflowing paragraph or cell as a whole, retain
  readability, and record the reason. Do not shrink individual OCR words.
- Preserve meaningful emphasis/color, mathematical structure and supported
  special glyphs. Translate all readable prose, including inside illustrations;
  justified identifiers can remain unchanged. Source text still illegible after
  two attempts stays located, preserved and reported as a source limitation;
  other unknown content remains unresolved. Never invent or silently summarize.

## Time and completion

Target 120 seconds per selected page end to end; 120–180 seconds is acceptable,
and over 180 seconds fails speed acceptance. Include interpretation,
translation, construction, corrections, review and export. Record actual wall
time from entry, including retries and tool gaps, excluding explicit pauses.
Check the budget at stage boundaries and after representative pages. Report
overrun risk early; at the limit stop automatic repair loops and deliver a
labelled readable preview with known defects/unverified items if acceptance is
incomplete. Do not claim faster translation from build-time measurements alone.

Within a run, reuse unchanged extraction, page artifacts and reviews only with
source/content identity. Raster builds retain their existing clean-base and
page-PDF caches; rebuild only affected pages. Never
restart successful whole-file OCR or review merely for a local correction.

Use the current Python interpreter and existing dependencies; inspect script
`--help` before invoking options. Do not redesign the pipeline, install another
translation engine, fabricate quality reports or hide failed checks during a
translation job.
