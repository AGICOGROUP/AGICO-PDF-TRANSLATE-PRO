---
name: translate-scan-pdf-professionally
description: Use when translating scan-only or raster PDFs, including hidden OCR layers, with text pages, tables, illustrations or engineering drawings and a requirement to preserve page correspondence and technical artwork.
---

# Professional Scan PDF Translation

## Scope and routing

Follow the PDF router's adapter and output mode. Confirm `scan-only` with
`scripts/classify_pdf.py --source <source>`. Hidden OCR is not visible native
text. Resolve `normalize-rotation-first` without changing visible content;
native/mixed input returns to the PDF router.

This is one scan adapter with two **page strategies**, not two PDF adapters:

| Page content | Strategy | Preservation contract |
|---|---|---|
| Mainly prose, clauses, lists or regular tables, with no engineering drawing or technical schematic | `reconstruct` | Recreate the page with translated text, structured tables and original nontechnical artwork; preserve page correspondence, meaning, hierarchy and relationships; allow within-page reflow |
| Contains any engineering/hand drawing, test diagram or technical schematic, or has intricate backgrounds/uncertain separation | `preserve_raster` | Keep the entire original page image; translate using tight local glyph cleanup and vector text; protect non-text artwork |

Read each whole source page before deciding. Text percentage or OCR confidence
alone is insufficient. Even one small engineering figure or test schematic on a
prose page selects `preserve_raster` for the whole page. Do not crop it out to
qualify the rest of that page for reconstruction. Photos, logos and decorative
artwork alone do not count as engineering drawings; reuse them without redrawing.
A text-heavy security background may require `preserve_raster`. Blank/image-only
pages retain their source artwork.
Record one strategy and its source-based reason for every selected page.

An explicit target-language-only request uses replacement on both strategies.
For explicit bilingual output or an engineering default of `add_bilingual`, use
`preserve_raster` with additive text and no source cleanup. Every bilingual scan
retains its actual source language, including non-Chinese engineering drawings.
Engineering drawings reuse the placement/preservation rules in
`references/additive-bilingual-drawings.md`; that reference's Chinese-specific
inventory/completeness rules apply only to actual Chinese pairs matching the PDF
router's inventory. Other language pairs continue translation without that
shortcut. Prose/table pages place complete translated paragraphs/cells in verified
adjacent whitespace under the existing additive manifest rules. Do not fabricate
Chinese inventory counts or use a drawing-only completeness shortcut for prose.
If no readable placement fits, report an unresolved layout issue. Never switch
replacement to bilingual to avoid a difficult edit.

Standalone PNG/JPEG translation remains under the image adapter: its PDF carrier
always uses `preserve_raster`, even when the image mainly contains text.

## Required workflow

Read `../../../references/delivery-policy.md` and
`../../../references/page-context-translation-review.md`, then
`references/workflow.md` and `references/quality-gates.md`.
Read `references/reconstruction.md` for reconstruction and mixed-strategy jobs;
read `references/manifest-schema.md` for raster manifests only.
For cement terms, consult `references/cement-terminology.md` through
`scripts/glossary_lookup.py`. Its table translations take precedence over model
wording for English output; longest matches and the final duplicate occurrence
take precedence because later table entries contain revisions.

1. Fingerprint the immutable input and establish page geometry, output mode,
   target language and a task start time. Use an isolated job directory. Every
   requested test starts in a new directory with fresh extraction and review;
   reuse within that same run for repairs, never historical test results.
2. Render source pages at a readable resolution and inspect them as whole pages.
   Use `extract_scan.py` for OCR assistance, not as the translation authority.
   Magnify only uncertain names, dimensions, tolerances, formulas and dense cells.
   Record the per-page strategy in `manifest/page-plan.json`.
3. Restore complete sentences across scan lines. Translate headings, paragraphs,
   clauses, lists, cells, captions and diagram labels in whole-page context.
   Keep each readable source item assigned once; register located OCR omissions
   without duplicating existing translations. Confirm numbers, signs, units,
   negation and terminology against source pixels. For cement terminology use
   `scripts/glossary_lookup.py`; use its English terms for English output and
   their controlled concepts consistently for other target languages.
4. Build each page by its chosen strategy:
   - **Reconstruct:** follow `references/reconstruction.md`. Use a reproducible
     job-local ReportLab script, complete paragraphs, explicit table rows/columns
     and measured layout heights. Translate directly into the new page. Retain
     source page boundaries and reuse original illustrations, seals and logos.
   - **Preserve raster:** use `make_manifest_template.py`, `draft_blocks.py`,
     `build_scan.py` and the raster instructions in `references/workflow.md`.
     Original artwork is the base. Clean only source glyph envelopes; translations
     remain selectable vector text. Additive output never cleans source pixels.
5. For a long reconstruction job, validate representative early pages before
   propagating styles: cover/title, contents, prose, a table and an illustration
   where present. The first five pages are a useful starting set, not proof of
   coverage. Ask for sample approval only when the user requested that checkpoint;
   otherwise inspect the samples and continue without an approval pause.
6. Assemble pages in source order with one output page per selected source page.
   Apply `references/quality-gates.md`: raster-only output uses `verify_scan.py`;
   reconstruction/mixed output uses the documented reconstruction and assembly
   checks, retaining raster component build/verification evidence. The current
   `build_scan.py` and `verify_scan.py` do not implement reconstruction; do not
   invent a flag, spoof their builder identity, or apply their pixel-equality
   gate to a rebuilt page.
7. Render every output page for initial coverage, compare complete source/target
   meaning on every page, and inspect changed regions and anomalies at high zoom.
   Correct affected pages only, then check the exact final assembled PDF. Save
   actual semantic and visual evidence, not passing templates. Selectable text
   and correct page counts alone cannot establish translation accuracy.

## Artwork and typography

- Engineering drawings are **never parametrically redrawn**, generated from
  scratch, simplified or replaced by lookalikes. Reuse source pixels, including
  linework, arrows, leaders, hatching, curves and symbols. Translate their labels
  locally; do not interpret the user's reconstruction reference as permission
  to redraw engineering geometry. No whole-page image generation or inpainting.
- On rebuilt text pages, original figures may move within the same page and
  scale proportionally for readable layout. Keep aspect ratio, full extent,
  caption and label relationships. Preserve their source provenance. Cropping
  an asset out of the page is not permission to clip its content.
- On raster pages, keep artwork at source positions. Any unavoidable restoration
  is limited to verified line segments interrupted by glyph cleanup, not new or
  guessed geometry. Never cover a rule, icon, signature or leader to fit text.
- Establish consistent document heading/body/annotation styles and independent
  table/header/footer styles. Wrap full passages, then adjust spacing or column
  widths. If needed, reduce an overflowing paragraph or cell as a whole, retain
  readability, and record the reason. Do not shrink individual OCR words.
- Preserve meaningful emphasis/color, mathematical structure and supported
  special glyphs. Translate all readable prose, including inside illustrations;
  justified identifiers can remain unchanged. Unknown content stays located and
  unresolved, never invented or silently summarized.

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
page-PDF caches; job-local reconstruction rebuilds only affected pages. Never
restart successful whole-file OCR or review merely for a local correction.

Use the current Python interpreter and existing dependencies; inspect script
`--help` before invoking options. Do not redesign the pipeline, install another
translation engine, fabricate quality reports or hide failed checks during a
translation job.
