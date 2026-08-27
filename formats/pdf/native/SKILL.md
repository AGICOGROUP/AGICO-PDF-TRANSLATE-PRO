---
name: translate-pdf-professionally
description: Use when translating native-text or mixed native/raster technical PDFs whose selectable/copyable text, layout, graphics, tables, and image labels must be preserved. Do not use for scan-only or image-only PDFs without meaningful native text.
---

# Professional PDF translation

## Engineering-drawing route override

Before using replacement mode, run the PDF router. If it reports
`document_kind: engineering-drawing`, do not rebuild or replace source text.
Use the bilingual overlay adapter and its automatic language-inventory decision.
If the drawing is already a complete Chinese-plus-one-foreign-language version,
preserve the exact source PDF and mark it completed. Otherwise add selectable
target text while preserving the source. Do not pause for language confirmation
after processing starts.

Use Codex for translation and the installed PDF skill for inspection, rendering,
and visual verification.

**Core principle:** rebuild selectable body text first. Process text-bearing
images through a source-aware method router: preserve or reconstruct a clean
drawing base, then add English labels as an embedded PDF vector text layer.

The original PDF is the only user-supplied artifact. Never ask the user for a
manifest, image coordinates, or an intermediate translation. Never use v5 or v6,
a page screenshot, or another translated PDF as an image source.

Start every job through the source-bound runner:

```powershell
python scripts/run_v6_job.py init <source.pdf> --jobs-root tmp/pdfs
python scripts/run_v6_job.py resume <job-directory>
```

Follow the returned internal action until all body blocks are complete. Review
only changed image regions and automatically detected anomalies. Add image
English as selectable PDF vector text.
Finish with:

```powershell
python scripts/run_v6_job.py verify <job-directory> `
  --visual-review-report <job-directory>/visual-review.json
```

Deliver only when the job stage is `verified` and `final-qa.json` has
`"passed": true`. Read
[direct-v6-workflow.md](references/direct-v6-workflow.md) before running the
job.

Do not substitute a custom PDF-writing script for the source-bound runner.
Preserve each native line's text-matrix rotation; page rotation alone is not
sufficient evidence of its reading direction.

Read only the references required by the detected content:

- Native/selectable or mixed PDFs:
  [selectable-and-image-text.md](references/selectable-and-image-text.md)
- Images or engineering diagrams with text:
  [image-localization-routing.md](references/image-localization-routing.md), then
  [image-vector-overlay.md](references/image-vector-overlay.md)
- Cement-industry terminology or sentences:
  [cement-terminology.md](references/cement-terminology.md), queried through
  `scripts/glossary_lookup.py`
- Final acceptance:
  [quality-gates.md](references/quality-gates.md)

## Final gates

These six gates belong to this adapter and run once at its tail. Do not invoke
the scan or standalone-image gate set.

1. Translation integrity: complete coverage, consistent terminology, preserved
   numbers/models/units, zero unexpected source-language residue, and
   `untranslated_clear_image_labels: 0` when embedded image text exists.
2. Text validity: translated text is selectable/copyable, fonts are embedded,
   native pages are not flattened, and no hidden source text survives.
3. Document integrity: page count, boxes, rotation, reading order, tables,
   images, links, and other key structure match the source.
4. Layout safety: automated checks report zero overlap, clipping, container
   escape, missing glyph, or unreadably small text; record
   `text_overlap_failures: []`.
5. Non-text protection: graphics and images remain intact. Run specialized
   pixel/line/image checks only for images actually modified by this adapter.
6. Final render: render the completed PDF once. Automated checks cover all
   pages; manually inspect only changed regions and anomaly pages. Bind the
   evidence as `reviewed_changed_regions` and `reviewed_anomaly_pages`.

## Workflow

### 1. Inspect and classify

- Preserve the source; store intermediates under `tmp/pdfs/<job>/`.
- Record page count, MediaBox/CropBox, rotation, encryption, forms, links,
  bookmarks, text-show operators, embedded images, and native text counts.
- Classify every page as native text, raster text, or mixed.
- Render representative pages and inspect embedded images at native resolution.
- Select native-selectable mode whenever required source text is selectable.
- Classify every image source as editable vector, simple raster, structured
  raster, complex raster, or unreadable before selecting an edit method.

### 2. Create a resumable manifest

```powershell
python scripts/pdf_translation_pipeline.py extract `
  --input <source.pdf> --manifest <job>/manifest.json `
  --source-language zh --target-language en

python scripts/pdf_translation_pipeline.py export-translation `
  --manifest <job>/manifest.json --output <job>/translation-packet.json
```

Translate only the compact packet; do not load character boxes or full layout
geometry into the translation context. Merge with `merge-translation`. Keep
stable block IDs, character boxes, style runs, table cells, symbols, and style
roles intact in the full local manifest.

### 3. Establish terminology

- Create `<job>/glossary.json`.
- Query only the current source block or batch to avoid loading the 1,293-row
  cement table into context:

```powershell
python scripts/glossary_lookup.py scan "<Chinese source block or batch>"
```

- Copy every returned match into `<job>/glossary.json`. Prefer the longest
  source match. When the same Chinese entry occurs more than once, the tool
  selects the document's last occurrence because later sections contain
  revisions. Preserve the selected English lexical form; adjust only necessary
  capitalization or grammatical number.
- If lookup exits with code `4` or a scan returns no match, translate with the
  model using professional cement/process context.
- Standardize equipment, process, table, unit, model, standard, and warning
  terminology.
- Preserve numbers, formulas, units, model codes, URLs, and standards.
- Prefer concise professional translations that fit the original containers.

### 4. Translate and check coverage

- Fill every manifest translation, including repeated labels.
- Apply the same matched glossary translation to native text, tables, captions,
  headers/footers, and translated labels inside images.
- Preserve paragraph, list, table-cell, symbol, and line-break semantics.
- Translate by engineering context.
- Resume from the first incomplete block; do not restart completed batches.

### 5. Rebuild native/selectable text

```powershell
python scripts/native_selectable_rebuild.py `
  <source.pdf> <job>/manifest.json <job>/translated-native.pdf
```

- Clone the source PDF.
- Remove source text-show operations from page and Form streams.
- Preserve non-text vectors, images, geometry, and resources.
- Add translated text with embedded TrueType fonts.
- Fit by concise wording and wrapping first; fail instead of clipping.
- Classify body/heading/table roles from source font family, weight, position,
  and reading-text-weighted size frequency. Do not promote body copy merely
  because its absolute point size is large.
- Derive numbered heading levels from the full section prefix; do not treat
  decimal measurements or punctuated prose as headings. Keep short wrapped
  heading continuations at the same level and translate them as one heading.
- Keep structural role independent from font weight. Derive each page group's
  weight from the dominant source evidence. When a PDF exports visually bold
  text without a bold font flag, record a reviewed `source_bold_override`;
  never apply a document-wide font-family guess.
- Reflow complete paragraphs, not independently extracted lines. Preserve
  source alignment, keep one font size across each paragraph, and harmonize
  equal body roles on the same page.
- Treat source layout as the baseline, not a coordinate prison. Apply controlled
  local changes to alignment, indentation, line spacing, paragraph spacing,
  text-box width, and role-consistent font size when the translated page reads
  better without changing its identity. Restore table-of-contents hierarchy,
  split run-in lists into separate items, and recombine orphaned continuation
  lines when the source semantics support those changes.
- Plan dense pages as a whole before shrinking text. Set one body-size target
  and one target for each heading level. Only after a recorded fit failure,
  reclaim verified whitespace by shifting or proportionally shrinking an image
  and rebalancing vertical content. Preserve image pixels, aspect ratio,
  reading order, captions, and clearances.
- Use the smallest required fitted size across a page role so every member of
  that role stays uniform. Enforce a readable body floor of
  `max(9.5 pt, 60% of source size)`; if prose does not fit, tighten the
  translation or use the controlled image-layout fallback instead of silently
  shrinking below the floor.
- Preserve source header/footer weight and point size. Give the replacement font
  enough metric height so ascent/descent differences do not force unnecessary
  shrinking.
- Treat images as protected exclusion geometry. Never create continuation
  lines through an image or allow body text to cover a picture.
- Treat the physical table cell as the atomic layout container. Segment
  cross-cell extraction blocks, aggregate all fragments per cell, fit once,
  and shrink uniformly until every line remains inside the cell.
- Redraw dense tables as explicit vector cells when automatic overlay collides.
- Do not leave source text invisibly below translated text.

### 6. Translate text inside images

Read [image-localization-routing.md](references/image-localization-routing.md)
and select `native_edit`, `deterministic_cleanup`, `anchored_line_restore`,
`constrained_clean_base`, `preserve_bilingual`, or `preserve_confirm` for every
text-bearing image.
Record every label, OCR confidence, translation, route, and status. Do not
guess unreadable labels; preserve them and create a `[CONFIRM]` item.
Never use `[CONFIRM]` to skip a clear informational caption or readable label
because its background is complex; route it through a local clean base and
selectable vector-text overlay.

Use two separate layers:

1. Extract each original image XObject at native resolution. Never use a page
   screenshot or an earlier translated PDF.
2. Record each image, page, exact placement, pixel dimensions, label box,
   cleanup box, English text, color, rotation, and maximum font size in
   `<job>/image-vector-metadata.json`.
3. Build a clean base image that removes only source text pixels.
4. Overlay the clean image at the original placement.
5. Draw English with an embedded TrueType PDF text layer.

```powershell
python scripts/build_clean_image_bases.py `
  <job>/image-vector-metadata.json `
  --report <job>/clean-image-report.json

python scripts/apply_image_vector_text.py `
  <job>/translated-native.pdf `
  <job>/image-vector-metadata.json `
  <job>/translated-with-image-text.pdf
```

Rules:

- Keep new English out of low-resolution raster diagrams.
- Protect colored process lines and connected black structural lines.
- For software screenshots, use word-level OCR boxes and prefer
  `ui_text_patch`; it reconstructs each tight text box row-by-row from the real
  neighboring pixels, preserving scanlines, gradients, and horizontal
  dividers. Use `ui_glyph` only where a vertical structure crosses the box.
- Run OCR at native resolution and again on a 3x-4x upscaled copy. Merge the
  detections by original-image coordinates, then visually audit all residual
  CJK-like OCR hits. Low-resolution one-glyph labels must not be accepted just
  because one OCR pass missed them.
- Treat repeated UI chrome as a template family. Define one reviewed template
  for recurring headers, status rows, menus, and function keys; scale its boxes
  to each XObject's own pixel dimensions and do not apply full-size coordinates
  to cropped or differently sized variants.
- Clear a whole rectangle only when it is a verified text-only background.
- Use `anchored_line_restore` only with explicit opposite-edge line anchors.
- For complex raster backgrounds, allow a high-fidelity editor to produce only
  a text-free clean base inside approved regions. Never let it generate final
  English or replace the whole drawing.
- Tighten cleanup boxes so leader lines lie outside them.
- Never regenerate the whole drawing, broadly inpaint, blur, sharpen, or cover
  drawing content with an opaque box.
- Rebuild from the source-based native intermediate after a failure.

Verify cleaned images:

```powershell
python scripts/verify_image_text_edit.py `
  <source-image> <clean-image> `
  --regions-json <approved-cleanup-regions.json> `
  --line-anchors-json <declared-line-anchors.json> `
  --evidence-dir <job>/image-evidence/<image-id> `
  --protect-saturation 80
```

Require zero changed pixels outside cleanup regions, zero protected-line
changes, passing declared-line continuity, and reviewed difference and 50%
alpha-overlay evidence.

### 7. Route scan-only input out of this skill

Never flatten a native/mixed PDF. If classification finds no meaningful native
text, stop and use `translate-scan-pdf-professionally` from the original PDF.

### 8. Validate structure and selectability

```powershell
python scripts/verify_selectable_output.py `
  <source.pdf> <job>/manifest.json <job>/translated-with-image-text.pdf `
  --allow-modified-image-page <page-number> `
  --report <job>/selectability-report.json
```

Also require:

- representative title, paragraph, table, header, footer, and image labels copy;
- native text-show operators exist on every source-native page;
- extractable CJK residue is zero;
- page geometry and rotation match;
- pages outside approved image edits have identical content streams;
- clean image pixels embedded in the PDF match generated clean images.

### 9. Final render and exception review

- Render the final PDF once and run automated checks across all pages.
- Manually inspect changed image/text regions and pages flagged by automated
  anomaly detection; do not require routine page-by-page screenshots or review
  of unchanged image XObjects.
- Use high-resolution vision/OCR only for a flagged or modified image-heavy
  region.
- Run a geometric word-overlap scan across native and image-overlay text. Any
  collision is a delivery failure even when both texts are individually valid.
- Require zero container escapes, zero center-alignment drift, zero paragraph
  font-size variance, and zero text/image intersections before delivery.
- Confirm every modified image has completed structural/difference checks and
  every `[CONFIRM]` item is reported.
- Fix every omission, overlap, square glyph, blur, broken line, source-language
  residue, or inconsistent label.

## Failure policy

- If repeated fixes fail, stop patching and return to the original PDF/XObject.
- Identify whether the failure belongs to native text, vector graphics, or
  raster text before changing the method.
- Preserve genuinely unreadable labels and record page/image/region; do not
  invent translations.
- Report exact technical limits instead of lowering acceptance criteria.
- Never claim selectable or pixel-preserving output without automated evidence
  and final visual review.
