---
name: PDF-TRANSLATE-PRO-SCAN
description: Translate scan-only PDFs and hidden-OCR scans through OCR or located visual transcription, local source-glyph cleanup and selectable target text over the original raster pages.
---

# Scan PDF translation

Follow the PDF router's mode. Every page uses `preserve_raster`, including prose,
contents and regular tables: keep the full source page, clean only source glyph
regions, then write selectable translations. Additive/bilingual output keeps the
source text and performs no cleanup. There is no scan-page reconstruction branch.
Standalone image carriers use these low-level utilities under their own adapter.

Read [delivery policy](../../../references/delivery-policy.md),
[page-context review](../../../references/page-context-translation-review.md),
[workflow](references/workflow.md) and [acceptance](references/quality-gates.md).
Use [manifest schema](references/manifest-schema.md) when writing a manifest and
[compact decisions](references/compact-decisions.md) rather than hand-expanding
routine block JSON. Commands below run from this adapter.

## Extract once and establish coverage

```powershell
python scripts/classify_pdf.py --source <original.pdf>
python scripts/ocr_language_guard.py require --languages <source-language-codes>
python scripts/extract_scan.py --source <original.pdf> --pages all --output <job>/extract --dpi 400 --no-resume
python scripts/draft_blocks.py --extraction <job>/extract/extraction-report.json --output <job>/draft-groups.json
```

Use a new job and `--no-resume` for every test. Same-run repairs reuse verified page
checkpoints, keyed by source, render, settings, implementation and active OCR
models/config. Cache hits do not initialize ONNX. Normal extraction is one scale;
`--dual-scale` spends both recognition attempts and is for observed uncertain
pages, not a routine whole-document repeat.

The language guard inspects the configured recognizer, not an assumed filename.
Unsupported scripts can yield confident Latin lookalikes; stop that recognizer.
When the capable model can read the rendered source, use explicit `--no-ocr`
rendering and located visual supplements in this same pipeline. Keep that reading
method explicit and source-bound. If reliable reading is unavailable, report the
capability block instead of inventing text or asking the user for manifests.

Inspect whole source pages and the extracted inventory. Readable missed lines
require located source supplements and complete passage ownership. Treat
ocr_review_candidates as unresolved inspection tasks, not proof of illegibility.
Initial reading plus one targeted retry is the limit for genuinely blurry text;
preserve still-illegible pixels and record both attempts as source limitations.

## Translate and build

Reconstruct sentences, list items and complete cells in reading order. Keep list
markers with their own item and separate columns/cells. When a missed fragment is
recovered, repair the complete passage, its IDs, cleanup and translation together.
Use `scripts/glossary_lookup.py` for cement-terminology.md, including English
lookup where relevant; retain the selected sense and technical values.

```powershell
python scripts/compile_translation.py --extraction <job>/extract/extraction-report.json --draft <job>/draft-groups.json --decisions <job>/decisions.json --output <job>/translation-manifest.json
python scripts/audit_scan_inventory.py --help
python scripts/resolve_scan_candidates.py --help
python scripts/build_scan.py --manifest <job>/translation-manifest.json --output <job>/translated.pdf
```

Use the existing audit/resolver interfaces to account for actual ink candidates
before build; direct source reading can resolve them without another OCR pass.
The [acceptance reference](references/quality-gates.md) gives disposition bindings.
For legacy resumed jobs audit all selected pages, not only user screenshots.
Keep page-plan entries `preserve_raster`; source page order/count remain fixed.

Cleanup uses tight source-line/glyph boxes independently of the target layout box.
Sample the local background; use a constant fill only after confirming it fits
that actual region. Preserve rules, leaders, icons, signatures and photos.
Wrap full paragraphs/cells at a consistent role baseline; first use safe space,
then shrink only the genuinely overflowing unit. Preserve color and orientation.

## Review once, repair locally

Render every selected candidate page for initial review. Compare full meaning
against source, then inspect changed regions and anomalies at high zoom. Cached
clean bases/page PDFs and unchanged review evidence remain usable by identity.
Unreadable page caches rebuild locally. If optional object deduplication exceeds
the PDF library's decompression limit, the builder copies the verified encoded
pages without deduplication; do not raise that limit or rerun OCR. This exceptional
output may be larger, while source binding and visual checks remain required.
Store actual semantic and visual findings; IDs and OCR confidence are not proof
of complete detection or correct translation. Readable source-language remnants
in replacement mode are defects even if their translation is present nearby.

```powershell
python scripts/verify_scan.py --source <original.pdf> --manifest <job>/translation-manifest.json --pdf <job>/translated.pdf --visual-review <job>/visual-review.json --translation-review <job>/translation-review.json --report <job>/final-qa.json
```

Deliver completed output only when official build and this adapter's checks pass
with source/candidate-bound reviews. Keep cosmetic warnings. The shared budget
includes model/tool gaps and repair time; a useful result with unresolved checks
is a clearly labelled preview, not a silently passed job.
