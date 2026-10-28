---
name: PDF-TRANSLATE-PRO-IMAGE
description: Translate one static PNG/JPEG by replacing or adding text while preserving dimensions, orientation, alpha and non-text artwork; return the same raster format.
---

# Standalone image translation

Inspect the full-resolution original first. Return the same pixel dimensions and
same image format as the EXIF-normalized source. Preserve PNG alpha. Supported:
one static PNG, JPG or JPEG. GIF, SVG, animated images and multi-page TIFF are not
supported. Use scan raster extraction/build utilities, but do not inherit scan
PDF final gates: this adapter owns acceptance of the final raster image.

Read [page-context review](../../references/page-context-translation-review.md)
and [delivery policy](../../references/delivery-policy.md). A photograph of a
nameplate is still an original to preserve, not an invitation to recreate the
machine. Keep model codes, serial numbers, standard units and technical symbols;
translate every readable language-bearing note and qualifier in context.

## Source inspection and no-op cases

Record task-entry time, fingerprint the immutable original and create a fresh job
for each test. Perform full-image visual inspection before preparation.

- If visually empty, run one OCR pass directly on the source. If OCR finds zero
  readable text and source inspection agrees, record translation_complete_no_text
  with source hash, OCR result and actual review. Do not create a translated image or PDF.
- If every clear item is language-neutral notation/identifiers, record
  translation_complete_no_translatable_text with its inventory. Return the original
  or a byte-identical copy and verify the hash. Uncertain abbreviations do not
  qualify; localize meaningful words and qualifiers.

## Replacement commands

Run from this adapter using the current interpreter:

```powershell
python scripts/image_job.py prepare --source <original.jpeg> --job <new-job> --target-language zh
python scripts/image_job.py build --job <job> --rows <job>/translation.tsv --output <output.jpeg>
```

Prepare wraps a one-page raster carrier, performs the normal OCR pass and prints
a compact line inventory. It refuses nonempty job directories. Its execution
ledger starts before preparation; keep earlier task-entry time separately.
Check source-script capability before accepting OCR readings. When unsupported,
use `prepare --no-ocr` and located TSV supplements in this raster pipeline.
Import TSV rows before recording candidate dispositions, because row import replaces
the region decisions; use the actual extracted candidates and evidence schema.

Use the source view and printed inventory once. Register every readable missed
label before build. TSV is UTF-8: `line-numbers<TAB>role<TAB>translation<TAB>optional box`.
IDs accept ranges (`4-7`) or lists (`2,3`); roles are heading/body/footer/preserve.
A preserve row supplies its actual preservation reason. Boxes use original image
pixels; literal `\n` creates a line break. A supplement is
`+unique-id<TAB>role<TAB>translation<TAB>x0,y0,x1,y1<TAB>source text`.
An optional fifth field for existing IDs supplies source cleanup boxes separated
by semicolons. Read [compact decisions](../pdf/scan/references/compact-decisions.md)
only for advanced grouping/rotation/style overrides.

Translate full passages/cells at one role baseline; shrink only a genuinely
unfittable unit. Keep source text direction. Target layout expansion does not
expand cleanup: source glyph boxes, table rules, bolts, signatures, logos and
nearby artwork remain distinct. Readable OCR misses need actual source ownership;
blurry text gets at most the shared two attempts.

Build uses the official raster builder and original pixels outside approved text
regions. JPEG retains translated-raster.png, composed.png and image-composition.json
as exact composition/encoding evidence. Never overwrite the source with output.
For explicitly additive output, use image_pdf_bridge.py and the existing additive
raster manifest; preserve source text. The bridge unwraps only official hash-bound
raster-build output, never a generated image mislabeled as that build.

## Final gates

1. Translation integrity: every readable source item is correctly handled in
   whole-image context; model codes, values, units, negation and qualifiers remain correct.
2. Raster contract: same format, dimensions and normalized orientation.
3. Channel integrity: PNG alpha preserved; high-quality JPEG encoding.
4. Non-text protection: PNG outside-region pixels are identical. For JPEG,
   exact lossless composition and final byte reproduction prove only approved
   edits preceded encoding; report decoded re-encoding differences visibly.
5. Layout safety: readable text, complete glyphs, no meaningful clipping,
   overlap or structural coverage, with source-aligned reading direction.
6. Final review: inspect the exact final image once; changed regions and anomalies
   receive closer inspection and whole-image semantic review is complete.

After viewing this exact built output and checking all six:

```powershell
python scripts/image_job.py finish --job <job> --output <output.jpeg> --candidate-sha256 <actual-build-hash> --reviewed-all-passed --review-note <actual-findings>
```

Finish binds real findings to source/candidate hashes and runs this adapter's
checks; it does not translate or inspect pixels for the agent. Missing/stale
JPEG composition or human/model reviews fail. It freezes the execution ledger;
do not pause again. Retain true failed/unverified status for preview delivery.
A whole-image regeneration with changed size/format is not a preservation pass.
