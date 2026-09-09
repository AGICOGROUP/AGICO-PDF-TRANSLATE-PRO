---
name: translate-scan-pdf-professionally
description: Use when translating raster or scanned PDFs, including scans with a hidden copyable OCR layer, whose visible text and non-text artwork must be preserved in translated layout.
---

# Professional Scan PDF Translation

## Overview

Translate rasterized PDFs with embedded vector target-language text. Support both replacement output and additive bilingual output that preserves Chinese. Preserve page geometry, colors, photographs, diagram lines, table rules, icons, logos, and all non-text pixels.

## Route Gate

Run `scripts/classify_pdf.py`. Use this skill only when it reports `scan-only`.
If it reports `mixed-or-native`, use the mixed/native PDF route. If it reports
`normalize-rotation-first`, normalize page rotation without rasterizing or
changing visible pixels, then classify again.

## Engineering-drawing default

Follow the router's `translation_mode`. Engineering drawings default to additive
bilingual mode only when no explicit monolingual requirement was given. Explicit
单语 / 仅中文 / replacement uses `replace`; never switch it to bilingual as a
cleanup shortcut. Hidden OCR alone still reports `scan-only` in both classifiers.

For `add_bilingual` only, inventory clear Chinese and foreign labels and run the PDF-level
`scripts/decide_drawing_translation.py --inventory-file
<drawing-language-inventory.json>`. If it returns
`already_bilingual_complete`, preserve and deliver the exact source PDF and mark
the task completed. Require Chinese plus one other language, complete semantic
pairing, and zero unmatched clear labels. Partial bilingual drawings continue
automatically with `add_bilingual`. Never pause for language confirmation after
processing starts.

## Required Workflow

Read these files before acting:

- `../../../references/page-context-translation-review.md` for mandatory
  page-context translation and a separate semantic accuracy review of every page.

- `references/workflow.md` for the complete execution order and image-text handling rules.
- `references/manifest-schema.md` before creating or editing the translation manifest.
- `references/quality-gates.md` before review and delivery.
- `references/additive-bilingual-drawings.md` only for `add_bilingual` output.
- `references/cement-terminology.md` only through
  `scripts/glossary_lookup.py` when cement-industry terms or sentences occur.

Use an isolated job directory named with the source SHA-256 prefix. Never modify the source PDF.

1. Classify the source and fingerprint it.
2. Use `scripts/extract_scan.py` at adequate resolution with supported options.
   Reuse cached extraction; do not require dual-scale OCR on every page.
   Retry only uncertain or missed regions. Batching page ranges is allowed.
   Reuse the same extraction directory when resuming. The extractor checkpoints
   each completed page and validates source/configuration/render hashes before
   reuse. Do not restart successful pages or manually concatenate batch reports.
   Preserve each OCR quadrilateral and its derived cardinal `rotation`. For
   internally rotated drawings, do not infer text direction from PDF `/Rotate`.
3. Create a manifest with `scripts/make_manifest_template.py`.
4. Inventory every OCR line. Run `scripts/draft_blocks.py` to create page-aware
   semantic regions before translation. Translate with the complete ordered page
   as context, while returning one translation per region ID. Prose regions may
   own several source-line IDs; table cells, drawing labels, rotated text,
   headers, and footers remain structurally separate. For each cement
   block or batch, run `python scripts/glossary_lookup.py scan "<Chinese source>"`.
   For English output, use every returned table translation before model
   wording. For another target language, record the selected English term as a
   controlled semantic pivot and translate that concept professionally and
   consistently. The lookup uses longest matches and the final occurrence of
   duplicate entries because later table sections contain revisions. Every
   source-line ID must be assigned exactly once as `translated` or
   `preserve_confirm`.
   Use the draft payload's `pages` context and stable region IDs in each batch.
   Translate directly from the source language with the available capable model;
   do not install another machine-translation stack during a document job or
   substitute isolated phrase/pivot translations for contextual translation.
   Review technical terms, negation, numbers and units against source pixels.
5. Select the output mode. For replacement, approve a tight `clean_box` around
   glyph pixels only, or `clean_boxes` for the individual glyph envelopes in a
   multi-line region. Never use the region union as a broad cleanup rectangle.
   For additive bilingual output, use `action: add_bilingual`
   and verified adjacent whitespace; do not define `clean_box` or alter source
   pixels. Preserve drawing lines crossing or touching text; explicitly
   reconstruct only verified line segments through `vector_lines`. Keep icons
   in the raster base whenever possible. If replacement cleanup must cover an
   icon, use a `rich_lines` `source_crop` run to copy the exact original pixels
   back; never substitute a similar icon.
6. Build with `scripts/build_scan.py`. Target-language text is embedded vector
   text and must be selectable/copyable.
7. Render the completed PDF once. Run automatic checks on all pages, then
   visually inspect only changed regions and anomaly pages. Complete the
   adapter's own visual-review evidence.
   Separately compare the complete source and translation on every selected
   page for contextual accuracy, including OCR omissions. Save the adapter-owned
   `translation-review.json`; visual sampling and block coverage do not replace
   this semantic review. Resolve accuracy findings before delivery.
8. Run `scripts/verify_scan.py` for completed delivery. Apply
   `../../../references/delivery-policy.md` for severity and budget-limited
   preview delivery. Keep the real failed/unverified report for previews.
   The verifier reads `translation-review.json` beside the visual review, or the
   explicit `--translation-review` path. Missing, stale, incomplete or unresolved
   semantic evidence fails verification. A schema-valid review is still not proof
   of accuracy: never generate passing entries from counts or merely rebind old
   review hashes after rebuilding.

## Time budget without quality shortcuts

Budget at most 120 seconds per selected page (10 pages: 20 minutes), including
OCR, translation, layout, semantic review and delivery. Record wall time from task start,
excluding only explicit user pauses, and each stage's timings. Use the first
three representative OCR pages to estimate remaining work; report projected
overruns early. At the limit stop automatic repair loops and provide a labelled
readable preview with actual defects if final acceptance is incomplete. Choose
DPI for legibility. Never fabricate reviews, omit content or hide unreadability.

Use one persistent OCR job directory and the builder's hash-validated lossless
base cache. A wording-only correction reuses its base; cleanup/layout/source
changes invalidate it. Rebuild through the official builder, re-render affected
pages and review them, then run final checks against the exact assembled PDF.
Do not repeat a whole-document render when unaffected page content is unchanged;
reuse requires evidence of unchanged page content, not just matching page numbers.
Never run competing OCR jobs for this document, and do not stop other tasks to
obtain a better benchmark. Report cold and warm measurements separately.

The official build report and its source/manifest/output hashes are mandatory.
Never deliver output made by a one-off PDF-writing script, and never replace
one-to-one source-label translations with a summary panel.

## Shared Layout Rules

- For additive bilingual drawings, place target text below, then right, then in
  a complete companion legend/title panel in verified whitespace. Never squeeze
  long translations into dense source cells or place them over drawing content.
  `below` and `right` must remain within 3% of the page diagonal from the source
  label. A `blank_panel` is allowed only for a table, title block, or legend and
  must be directly adjacent to that structure, declare its full
  `companion_anchor_box`, and mirror the source row/order. Never move unrelated
  table labels into a remote page-center list.

- Mark a diagram `bilingual_complete` and preserve it unchanged only when every
  clear Chinese label has a semantic target-language counterpart. Record the source
  region hash, clear-Chinese count, matched-pair count, and zero unmatched
  labels. Partial bilingual diagrams translate only unmatched Chinese labels.
- Classify visible text into three primary typography tiers before fitting:
  `major_title`/`minor_title` for headings, `body` for the main prose, and
  `annotation` for captions, drawing labels, callouts, and other less frequent
  small text. Headers, footers, and table text remain independent structural
  groups. Do not classify an item as `annotation` merely because its OCR box is
  short or narrow; use its semantic function and the source page's visual
  hierarchy.
- Within one page, each typography group uses one font, size, and weight derived
  from the source. Titles are normally bold or one size larger than body text;
  body text uses regular weight and the page's dominant readable size;
  annotations use regular weight and a smaller size. Keep the ordering
  `title > body > annotation` whenever all three occur on the page.
- Use one baseline size per page typography group. Fit complete paragraphs at
  that baseline with wrapping first. If a paragraph still overflows, reduce
  only that entire paragraph to a single fitting size and record its baseline,
  fitted size and overflow reason. Keep all other paragraphs at the baseline.
  Never shrink individual OCR words or lines independently. A small annotation,
  caption, header, footer or table cell must not reduce body text size.
  Review exceptions for readability and `title > body > annotation`; if this
  hierarchy cannot be retained, adjust layout rather than silently accepting it.
- Preserve image placement first. Only after a recorded text-fit failure may a
  text-free large image shift or shrink proportionally into verified whitespace.
  A shift reuses exact pixels; a shrink may only resample the original crop
  proportionally. Reject any collision, page escape, crop, stretch, redraw, or
  change outside the approved old/new image regions.

## Non-Negotiable Rules

- Do not use broad white rectangles, blur, generative redraw, global inpainting, or whole-page image regeneration.
- Do not cover process lines, borders, leaders, arrows, symbols, photos, or logo artwork.
- Treat icons as immutable artwork. Preserve them in place or reuse exact source pixels; never redraw them, replace them with text, or choose a similar glyph/icon from a library.
- Preserve mixed source-language emphasis and color changes with `rich_lines` text runs when they carry meaning or navigation cues.
- A translated label may be shorter, smaller, or reflowed, but never clipped, omitted, or placed over structure.
- Clear source-language text inside images, logos, UI screenshots, headers and
  footers must be translated to the requested language. Chinese target text is
  expected, not a source-language residue. Complete bilingual preservation is
  available only in bilingual mode. Illegible text needs a located review record.
- OCR confidence never replaces visual review. OCR false positives require exact bounding-box evidence and a documented reason.
- Review all readable content; block actual omissions, icon substitutions,
  meaningful color loss, unreadable overlap/clipping and structural damage.
  Cosmetic and numeric typography deviations are warnings under the shared policy.
- In bilingual mode, preserved source text inside a reviewed paired region is
  expected; an unpaired readable source label remains a content failure. In
  replacement mode inspect unexpected source-language residue, not all CJK.
- For English output, cement glossary hits must use the selected English lexical
  form. For other target languages, retain the selected English concept in the
  job glossary as the semantic pivot and use one consistent professional target
  equivalent.

## Quick Commands

Use the Python interpreter available in the current runtime. Install `scripts/requirements.txt` only when dependencies are missing. Run each script with `--help`; path-safe commands and manifest examples are in `references/workflow.md`.

## Stop Conditions

Repair actual content/readability/structure defects within the shared time
budget. Numeric font deviations alone do not require redesign. At the limit,
provide a labelled preview with known defects rather than looping indefinitely.
Preserve and report genuinely unreadable regions; never invent substitutes.
