---
name: translate-image-professionally
description: Use when translating one static PNG, JPG, or JPEG image while preserving its pixel dimensions, layout, photographs, diagrams, tables, icons, logos, colors, and non-text pixels. Reuses the scan-PDF raster workflow through a one-page PDF bridge and returns the same image format.
---

# Professional Image Translation

## Scope

Translate one static PNG or JPEG image. Return the same image format with the same pixel dimensions. Reject GIF, SVG, multi-page TIFF, animated images, and image batches in this version.

## Required Workflow

Reuse scan raster extraction/build utilities where useful, but do not inherit
the scan PDF acceptance gates. This adapter owns its final checks.

1. Fingerprint the immutable source image and create an isolated job directory.
2. Run OCR and inspect the full-resolution source image. If OCR finds zero readable text and full-image visual inspection confirms there is no readable text, record `translation_complete_no_text` with the source hash, empty OCR result, and completed visual review. Mark the translation phase complete and stop. Do not create a translated image or PDF, and do not run cleanup, layout, build, or verification. OCR alone is insufficient for this decision.
3. Otherwise, run `scripts/image_pdf_bridge.py wrap <source-image> <job/source.pdf> <job/image-metadata.json>`.
4. Treat `job/source.pdf` as a one-page raster carrier. Reuse the scan adapter's
   extraction, manifest, cleanup, and build utilities, but do not call its final
   verifier or apply its PDF gates. Do not run the PDF classifier.
5. Run `scripts/image_pdf_bridge.py unwrap <translated.pdf> <job/image-metadata.json> <output-image>`.
   Unwrap is allowed only when the sibling scan build report identifies the
   official scan builder and its output hash matches `translated.pdf`.
6. Compare the final image with the original once at full view. Inspect at high
   zoom only changed regions and anomalies reported by automatic checks.

## Final gates

These six gates belong only to the standalone-image adapter.

1. Translation integrity: all readable source text is handled; terminology,
   numbers, models, and units are correct; no unexpected source text remains.
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

## Commands

Use the Python interpreter available in the current runtime:

```powershell
python scripts/image_pdf_bridge.py wrap "source.png" "job/source.pdf" "job/image-metadata.json"
python scripts/image_pdf_bridge.py unwrap "job/translated.pdf" "job/image-metadata.json" "translated.png"
```
