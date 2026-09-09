# Scan performance and quality validation

## Scope and acceptance

The 38-page VIA EF 004 scan is the performance fixture. The user's end-to-end
target is 60 minutes, including actual contextual translation and independent
semantic review. This change optimizes the existing scan adapter, without
changing DPI, adding a translation dependency or accepting missing review.

These benchmarks reuse the previous manifest to isolate builder performance.
They do not validate the accuracy of its old translations. An end-to-end
translation acceptance run is still separate from these infrastructure tests.

## Implemented changes

- Sample only the same six-pixel glyph-border strips, avoiding one whole-page
  RGB conversion per cleanup rectangle.
- Cache lossless cleaned page bases with source, cleanup, layout and code hashes;
  verify cached PNG hashes. Rebuild target text on every invocation.
- Save completed OCR pages atomically and resume using source, DPI, OCR package,
  implementation and render hashes. Both 1x/3x passes remain mandatory.
- Emit coherent page context, ordered source IDs and stable region IDs from the
  existing region grouper.
- Require complete, current semantic-review evidence at final verification.
  Record validation is not a machine proof of translation accuracy.
- Keep the previous PDF intact until its official replacement build completes.
- Document direct contextual translation, original-pixel OCR review and honest
  time accounting; disallow isolated phrase/pivot translation as a shortcut.

The working tree already had full-resolution OCR detector/fragment deduplication
edits. Same-baseline grouping also changed in another task during this work.
Those changes were preserved; OCR measurements describe the combined working
tree, not an isolated speedup attributable to the new checkpoints.

## Reproduction and evidence

`tmp/scan-benchmark/` contains before/after PDFs, builder reports, extraction
checkpoints and timing JSON. The baseline builder was taken from HEAD f5b1d57.
Both builders use the same 38-page manifest and source renders. Other local
tasks were active during measurements; elapsed time is workload-dependent.

The equivalence comparison checks all 38 cleaned raster pages pixel-for-pixel,
and every output text character's content, coordinates and size against the old
output. This proves builder equivalence, not that the old layout or translation
was professionally correct.

Tests cover interruption/resumption, damaged render recomputation, cleanup
cache invalidation, bounded sampling, page-context reading order, missing/stale/
incomplete/invalid review records, and rich-text source-image reuse.

Regression command:

```powershell
$env:PYTHONPATH='tmp\pytest-deps'
python -m pytest formats/pdf/scan/tests formats/pdf/native/tests formats/pdf/bilingual/tests formats/image/tests formats/pdf/tests formats/test_independent_quality_gates.py --import-mode=importlib -q
```

Two baseline glossary tests expect SHA-256
`9b74a21a2625e9745666483e0e1b546cc21745b3fcbcccd976a57eeca4a5022f`, but both
HEAD and the unchanged working-tree glossary have
`227c25df5d59fb4ddae9479e313186c98df004539e44ca460b723b1d09419e0d`.
They remain reported as pre-existing failures, not suppressed or rewritten.
All remaining 211 tests and two subtests pass.

Final-code builder measurements: baseline 493.146 s, optimized cold 66.141 s,
optimized cached 23.569 s (38/38 base cache hits). No differing cleaned raster
pages, no differing text/position/size pages, zero pixel changes outside approved
regions. The real verifier CLI also reports `passed: false` with
`translation_review_errors: ["missing translation review"]` when the record is
absent; no semantic passing review was fabricated for the benchmark PDFs.

All 38 pages completed dual-scale OCR without an allocation failure. The sum
of each page's first processing time was 864.863 s (14 min 25 s). This includes
the initial three separately measured sample pages; the subsequent full command
took 816.031 s and reused those three samples. A final resume validated all 38
page checkpoints in 0.152 s inside the extractor, with identical 1792 source
records. Draft grouping produced 1140 regions with exact, unique source-ID
coverage. These counts do not establish absence of OCR omissions or semantic
accuracy. Timing evidence is in `tmp/scan-benchmark/ocr-measurements.json`.

The measured infrastructure leaves substantial room in a 60-minute budget, but
the full translation-plus-review deadline has not yet been demonstrated. No
complete retranslation of this file was performed during this optimization.
