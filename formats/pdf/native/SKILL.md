---
name: translate-pdf-professionally
description: Use when translating ordinary native-text or mixed native/raster PDFs whose visible selectable text, tables, images and layout must be preserved. Excludes scan-only PDFs with hidden OCR and engineering drawings.
---

# Professional native/mixed PDF translation

Use this adapter only when the PDF content router returns it. Visible native
content, not merely copyable hidden OCR, selects this route. Engineering
drawings follow the returned bilingual/native-CAD adapter. Scan-only documents,
including non-painting OCR layers, use scan from the original PDF. One document
uses one adapter; raster pages within a genuinely mixed document stay in this
job and retain their own image-label evidence.

Read [delivery policy](../../../references/delivery-policy.md) and
[page-context review](../../../references/page-context-translation-review.md).
The three blocking requirements are correct content, complete/readable output,
and intact key structure. Cosmetic font/alignment differences are warnings.
Use the installed PDF skill to inspect/render, not to create a second pipeline.

## Source-bound execution

Work from the original PDF. Keep artifacts in a source-hash-bound job under
`tmp/pdfs/`. Never use an earlier translation as a raster source, ask the user
for manifests/coordinates, reset stages by hand, or substitute a one-off writer.

Read [runner workflow](references/direct-v6-workflow.md) before execution:

```powershell
python scripts/run_v6_job.py init <source.pdf> --jobs-root <jobs-root> --source-language <source-code> --target-language <target-code>
python scripts/run_v6_job.py resume <job>
```

Supply the actual languages at init. Jobs bind the source and language request;
changing languages selects an independent job. Use `--fresh` for a new test with
no previous extraction, translations or reviews; it retains previous jobs and
returns a new `job_dir`. Use that returned directory for subsequent commands.
Do not change manifest languages to repurpose an existing job. Translate the
compact packet using the available capable model, merge by stable IDs and follow
the runner's next action. Resume the same job to reuse its valid artifacts.
Generic machine translation may supply a draft, but it does not replace the
capable model's page-context translation and technical review. Check extracted
word boundaries before translating Latin-script prose; positioned spaces must
not become fused words. Unchanged English prose is not completed Chinese output.

## Translate and lay out native content

Read [native layout](references/selectable-and-image-text.md). Inspect source
pages, page boxes/rotation, fonts, tables and images. Supply the whole ordered
page and glossary with each translation batch, including image-label context.
Translate every readable heading, paragraph, table cell, caption, header/footer
and label. Preserve negation, conditions, numbers, units, standards and symbols.
For [cement terms](references/cement-terminology.md) query `scripts/glossary_lookup.py`; for non-English output use
the matched glossary meaning with a consistent target equivalent.

Rebuild through `run_v6_job.py build-native <job>`: retain vectors/images and
replace source text operations with embedded selectable target text. Keep each
line's text-matrix rotation. Do not suppress content as `ocr-artifact`, replace
body text with dots, or remove source IDs to obtain a passing report.

Use coherent paragraphs, not independently centered OCR lines. New extraction
binds multi-column ruled-table content to `source_cell_bbox` before translation:
translate the complete cell, including its continuations, while retaining page
and row context. Do not concatenate neighboring cells for translation or split
the target by word counts to recover columns. Old cross-cell manifests need
reviewed `manual_table_parts` or a fresh extraction when mapping fails; shrinking
an incorrectly mapped row is not a repair. Preserve source
alignment, reading order, table cells and image exclusion geometry. Fit by
wrapping at one source-derived baseline per typography group. Only overflowing
paragraphs may shrink, uniformly within each paragraph, with the reason recorded.
Do not shrink every body paragraph because one is crowded. Preserve semantic
heading hierarchy; derive bold from source evidence. Numeric font floors remain
diagnostics, not an instruction to redesign a readable page. Move/shrink original
images only after a real fit failure and into verified whitespace, retaining
aspect ratio, captions and protected structures. Never add pages without approval.

## Text-bearing images

Read [image method routing](references/image-localization-routing.md) and
[vector overlay](references/image-vector-overlay.md) only when images have text.
Inventory original XObjects and their labels with IDs, page, source text, boxes,
translation, method and status. Use one adequate OCR pass; retry missed/uncertain
regions only. Editable source text is preferred to raster editing.

Keep the original raster base and target text as separate layers. Cleanup boxes
are tight source-glyph envelopes, independent of the target placement box.
Multi-line body paragraphs need individual source-line cleanup regions, not one
large white rectangle. Mark image-coordinate `protected_boxes` for signatures,
seals, symbols and other nearby non-text content. `solid_fill` is only for a
verified text-only caption band; a frame or signature inside the box invalidates
that choice even if all outside pixels are unchanged. Automatic long-line
screening is not proof that arbitrary artwork is safe.

Use `role: body` and source `align` for image prose (default left/top); label
centering is for actual centered labels. Choose target-capable embedded fonts.
Build clean bases, overlay target text and assemble using the runner. Preserve
genuinely unreadable material with located `[CONFIRM]` records; readable prose
cannot be skipped because cleanup is difficult. A bilingual-preservation
shortcut cannot override the user's explicit monolingual mode.

## Review once, repair locally, deliver honestly

Read [acceptance](references/quality-gates.md). Render all selected pages once;
reuse unchanged-page evidence and re-render only affected pages after a repair.
Check semantic accuracy on every page against the original, including OCR
omissions. Layout inspection focuses on changed regions and actual anomalies.
Record the real source-to-target comparison in `translation-review.json` and
observed visual findings in `visual-review.json`, both bound to the candidate.

```powershell
python scripts/run_v6_job.py verify <job> --visual-review-report <job>/visual-review.json
```

The runner validates existing reviews and aggregates measured reports. It does
not establish semantic accuracy by itself. Missing evidence is unverified; zero
native draws cannot pass when native content was expected. An empty native page
within a mixed job is legitimate but its image labels still need review.
Do not prefill passing page records from counts or only replace old review hashes.
For dense tables, inspect a readable-size render of changed cells; a contact
sheet alone cannot establish absence of overlap or correct column assignment.
The measured cell checks verify one draw, text retention and physical bounds;
they cannot establish translation meaning or make a fabricated review valid.

Completed delivery requires actual three-requirement acceptance, runner stage
`verified` and `final-qa.json` passed. Retain cosmetic warnings. Scan-dominated
pages have a 120-second/page end-to-end budget including retries and review.
At the limit stop automatic repairs and share a clearly labelled readable
preview with known defects/unverified items; keep its true failed/unverified
state.
