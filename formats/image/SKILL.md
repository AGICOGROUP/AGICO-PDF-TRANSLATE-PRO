---
name: PDF-TRANSLATE-PRO-IMAGE
description: Use when translating one static PNG, JPG, or JPEG image while preserving its pixel dimensions, layout, photographs, diagrams, tables, icons, logos, colors, and non-text pixels. Reuses the scan-PDF raster workflow through a one-page PDF bridge and returns the same image format.
---

# PDF-TRANSLATE-PRO-IMAGE

## Scope

Translate one static PNG or JPEG image. Return the same image format with the same pixel dimensions. Reject GIF, SVG, multi-page TIFF, animated images, and image batches in this version.

## Required Workflow

Read and follow [page-context translation and accuracy review](../../references/page-context-translation-review.md).
Treat the entire image as one page: use all its text and visual relationships
as translation context, then review every translated item against the source.

Reuse scan raster extraction/build utilities where useful, but do not inherit
the scan PDF acceptance gates. This adapter owns its final checks.
Always use the scan `preserve_raster` path for the image's PDF carrier, even for
text-heavy images, preserving the full original image base.

1. Record task-entry UTC before preparation, fingerprint the immutable source,
   and create an isolated job directory. A test always starts fresh; do not load
   historical translations, OCR, candidates or reviews.
2. Perform full-image visual inspection of the full-resolution source first.
   For a visually empty image, run one OCR pass directly on the source image.
   If OCR finds zero readable text and visual inspection confirms it, record
   `translation_complete_no_text`, source hash, empty OCR result and actual
   visual review. Do not create a translated image or PDF; stop without cleanup,
   build or verification. OCR alone is insufficient. For an image requiring
   translation, do not run a separate preliminary OCR: step 4 supplies the single
   normal OCR pass.
3. If every readable item is language-neutral technical notation—only numbers,
   dimension/tolerance/mathematical symbols, standard units, or unambiguous
   drawing/model identifiers—and the full-image review confirms there is no
   translatable natural language, record
   `translation_complete_no_translatable_text` with the source hash, item
   inventory, and completed visual review. Return the source image, or a
   byte-for-byte copy when a separate output path is required, and verify that
   its SHA-256 equals the source SHA-256. Stop before PDF wrapping, cleanup,
   layout, build, unwrap, or re-encoding. If any word, abbreviation, qualifier,
   note, or other item may require localization, or the classification is
   uncertain, do not use this branch.
4. For replacement output, use `scripts/image_job.py prepare` below. This batches
   wrapping, the single OCR pass and a compact translation inventory; it starts
   execution-time measurement before the tools. Retain the earlier task-entry
   timestamp so instruction reading and handoff time are not lost.
   For additive output use the existing bridge and additive raster manifest.
5. Treat `job/source.pdf` as a one-page raster carrier. Reuse the scan adapter's
   extraction, manifest, cleanup, and build utilities, but do not call its final
   verifier or apply its PDF gates. Do not run the PDF classifier.
6. Use `scripts/image_job.py build` for replacement: it compiles reviewed region
   decisions, invokes the official builder, unwraps, then copies unchanged pixels
   from the immutable source outside approved text regions. This avoids global
   PDF round-trip resampling. Translated pixels still come from the official build.
   Additive output uses `scripts/image_pdf_bridge.py unwrap <translated.pdf> <job/image-metadata.json> <output-image>`.
   Unwrap is allowed only when the sibling scan build report identifies the
   official scan builder and its output hash matches `translated.pdf`.
7. Compare the final image with the original once at full view. Inspect at high
   zoom only changed regions and anomalies reported by automatic checks.
   Complete the whole-image semantic accuracy review. After a passing review,
   call `finish` once to save hash-bound evidence and run final checks. Collect
   actual defects together for a local repair; cosmetic warnings alone do not
   justify another build. Failed/unverified candidates keep their true status.

## Final gates

These six gates belong only to the standalone-image adapter.

1. Translation integrity: all readable source text is handled; terminology,
   numbers, models, and units are correct; no unexpected source text remains.
   Require the whole-image context review with no unresolved accuracy issues.
2. Raster contract: output format, pixel dimensions, and orientation match the
   normalized source.
3. Channel integrity: preserve PNG alpha and use high-quality JPEG encoding.
4. Non-text protection: pixels outside approved text-edit regions remain
   unchanged within the format's defined tolerance.
5. Layout safety: translated text is readable with no overlap, clipping,
   structural coverage, or missing glyphs.
6. Final review: compare the completed image once; manually inspect only
   changed regions and automatically detected anomalies.

## Image Output Contract

- Preserve the same pixel dimensions and same image format as the normalized source.
- Preserve PNG alpha using the source alpha channel; translated visible pixels
  come from the image adapter's verified raster build.
- Save JPEG at high quality without changing its dimensions.
- The raster output cannot contain selectable text. Keep the intermediate PDF
  as an optional secondary artifact only when the user requests selectable text.
- Never resize, crop, stretch, regenerate, or globally inpaint the image.

## Replacement commands and time allocation

From this adapter directory use the existing interpreter. Do not write a new
manifest-population, orchestration or QA program for each document:

```powershell
python scripts/image_job.py prepare --source "source.png" --job "new-job" --target-language zh
python scripts/image_job.py build --job "new-job" --rows "new-job/translation.tsv" --output "translated.png"
# Only AFTER viewing this exact output and completing the source/target review:
python scripts/image_job.py finish --job "new-job" --output "translated.png" --candidate-sha256 "<build-printed hash>" --reviewed-all-passed --review-note "<actual semantic and layout findings>"
```

Between prepare and build, use the line inventory printed by prepare and the
source image already visible in the conversation. Do not read the verbose JSON
again unless a specific uncertainty needs it. Inventory boxes and TSV overrides
both use original-image pixels; extraction JSON retains its render coordinates.
The helper performs OCR at native resolution (2x for small originals) while
retaining the unchanged high-resolution build carrier. This avoids interpreting
PDF-bridge enlargement as real detail. Inspect any uncertain/missed text against
source pixels; only those regions need a higher-scale retry, not routine full OCR.
Use a UTF-8 TSV, one region per line:
`line-numbers<TAB>role<TAB>translation<TAB>optional target box`.
Numbers accept `4-7` or `2,3`; roles are `heading`, `body`, `footer` or `preserve`
(the latter supplies a preservation reason). Default boxes/IDs/hashes are filled
by the tool. Optional boxes use **original image pixels**, not OCR-render pixels.
For a visually missed label use `+unique-id<TAB>role<TAB>translation<TAB>x0,y0,x1,y1<TAB>source text`.
For an existing region, an optional fifth field supplies tight cleanup boxes
separated by semicolons, only when source inspection confirms truncated OCR bounds.
Literal `\n` within a translation makes a line break. Never merge separate list
items just to reduce row count. The [JSON decisions contract](../pdf/scan/references/compact-decisions.md)
remains available for advanced overrides; do not hand-expand routine TSV data.
Translate directly with the current model. Check headings, lists and title-block
fields against pixels **before** building. Draft grouping is only a proposal:
keep list items and cells separate; join only real sentence continuations.
Register all visually clear omissions before the first build. Keep default
per-line glyph cleanup; target-box expansion must not enlarge cleanup. The shared
builder corrects dark border sampling only when the glyph interior and a wider
ring both confirm light paper, and preserves long straight rules crossing the
cleanup area. These safeguards do not authorize whole-cell erasure or claim
automatic signature recovery. Check signatures/logos at the source before choosing
boxes; do not retain entire connected ink components, which can retain source
letters too. Use an explicit measured background or tight cleanup override only
for a located defect; do not hand-tune routine cells before seeing a problem.

Use one execution owner through translation, actual review and final checks.
For a single image, execute directly rather than adding a relay solely for speed.
If the host already delegated the file, the caller checks the returned file/hash
and bound QA evidence and hands off promptly; it does not routinely repeat the
worker's OCR, translation, rendering or whole-image review. Reopen a located
anomaly or stale/missing evidence; an explicitly requested independent audit is
separate work, not an invisible part of the speed benchmark.

Await ordinary preparation in one tool call where possible. Batch TSV writing,
build and final-image display into one ordered call; the following model turn
performs actual review before calling `finish`. No automatic pre-view approval.
Read the compact inventory once, use existing source/final views, and batch
necessary repairs instead of successive speculative edits.

Target 120 seconds end to end; 120–180 seconds is acceptable, over 180 seconds
fails speed acceptance even when quality passes. Include instruction reading,
model/tool gaps, repairs and any dispatch/return/final handoff. Report executor
time separately when measured; do not substitute it for task-entry-to-handoff
time. `finish` freezes the execution ledger automatically: do not call `pause`
again or restart the clock. Keep the earlier task-entry and final-handoff UTC
timestamps to account for work outside that ledger. The shared time-limit/preview
policy remains in force. Repeated samples must pass both quality and complete
timing before claiming stability; unit tests or one fast run are insufficient.

`check` consumes the required agent-authored `review/translation-review.json`
and `review/visual-review.json`; it never manufactures them. Visual evidence uses
`candidate_sha256`, `whole_image_reviewed`, `reviewed_changed_regions`,
`text_overlap_failures`, `clipping_failures`, `unreadable_text_failures` and
`untranslated_clear_labels`. It checks the **final image**, not only a PDF clean
base. Missing/stale reviews remain unverified. PNG requires exact non-text pixel
equality; JPEG re-encoding differences are reported for review and must not be
silently treated as zero. Retain existing format-specific acceptance evidence
for JPEG when its lossy differences are harmless. For paths not using successful
`finish`, freeze an active execution ledger once at completion with
`formats/pdf/scripts/session_metrics.py pause --job <job>` from the repository
root; record the actual handoff timestamp separately.

## Paragraph overflow exception

Use one baseline font size per page text category (title, body, annotation).
Preserve title > body > annotation. Wrap complete paragraphs at that baseline
first. Only a paragraph that cannot fit may shrink as a whole, with one size
throughout the paragraph; other paragraphs retain the baseline. Record the
baseline, fitted size and overflow reason. Do not independently shrink OCR
words or lines. Review readability and hierarchy after fitting; resolve any
conflict through layout correction. Images count as one page and inherit this
policy through the shared scan builder.
