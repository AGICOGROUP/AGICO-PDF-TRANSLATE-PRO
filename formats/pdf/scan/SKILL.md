---
name: PDF-TRANSLATE-PRO-SCAN
description: Translate scan-only PDFs and hidden-OCR scans through OCR or located visual transcription, local source-glyph cleanup and selectable target text over the original raster pages.
---

# Scan PDF translation

Follow the PDF router's mode. Every page uses `preserve_raster`, including prose,
contents and regular tables: keep the full source page, clean only source glyph
regions, then write selectable translations. Preserve the encoded original PDF
background and overlay local cleanup patches; do not routinely re-embed a full
RGB raster. The official builder selects a measured lossless fallback only for
incompatible geometry, raster layout adjustments or visible painted native text.
Text completely covered by a final opaque full-page scan is not visible native
ink: preserve that encoded scan, and locate cleanup against the rendered source,
not the covered text layer's boxes. Such boxes are reading hints only.
Unrotated pages whose CropBox equals MediaBox can retain their original
background even with a nonzero page origin; the builder normalizes its cloned
coordinates before overlay. Nonzero-origin annotations remain a fallback case.
Additive/bilingual output keeps the source text and performs no cleanup. There is no scan-page reconstruction branch.
Standalone image carriers use these low-level utilities under their own adapter.
Keep source pagination by default. First use verified available space at readable
role sizes. Only genuine remaining prose/list overflow may use explicit,
source-bound continuations supported by this builder and verifier; complex table
flow and internal-destination remapping remain unsupported. Follow the shared
[pagination policy](../../../references/pdf-pagination.md) and manifest schema,
including page-number/TOC review. Never add pages to compensate for tight OCR
boxes or skip source content to satisfy the original page count.

Read [delivery policy](../../../references/delivery-policy.md),
[page-context review](../../../references/page-context-translation-review.md),
[workflow](references/workflow.md) and [acceptance](references/quality-gates.md).
Use [manifest schema](references/manifest-schema.md) when writing a manifest and
[compact decisions](references/compact-decisions.md) rather than hand-expanding
routine block JSON. Commands below run from this adapter.

For scan-heavy report pages or repeated forms, apply the shared
[efficiency guidance](../../../references/scan-report-efficiency.md) without
changing this adapter's artifact contract or acceptance.

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
Source OCR, crop retries and residue QA use the same official engine factory:
at most eight intra-op threads, one inter-op thread and no idle spinning. This
measured policy is part of checkpoint identity; keep it in the official commands
rather than relying on task-local runtime patches or silently ignored keywords.

The language guard inspects the configured recognizer, not an assumed filename.
Unsupported scripts can yield confident Latin lookalikes. For a locally available
script-specific ONNX recognition model, pass the same absolute path via
`--rec-model` to the guard and extractor, with `--languages` on both commands.
Extraction validates the selected model before OCR and binds its hash to the
page checkpoints. Targeted crop retries use that same bound model. Compare the
actual source text with the renders, especially handwritten text and dimensions.
For visibly sideways or inverted scans, set `--recognition-rotation` to the
counterclockwise angle that makes the page readable. This rotates the OCR input
and maps boxes and directions back to the unchanged source raster. Use one angle
only for pages sharing that orientation. For mixed scripts unsupported by a
single model, read each language area with a capable recognizer or located visual
transcription. Reconcile the exact source wording, standards, tolerances and
signed fields before compiling. Never turn a garbled reading into a plausible
technical value.
When visual transcription can reliably read the rendered source, use explicit `--no-ocr`
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
Record the visually established source code in decisions.json `source_language`
(for example `zh` or `en`), separately from `target_language`. The compiler
retains that binding. Chinese→English still checks CJK residue; English→Chinese
accepts Chinese target glyphs. A confirmed non-CJK original with no observed CJK
does not need unrelated whole-document Chinese OCR. Unknown source metadata or
observed CJK keeps conservative checking. Every language pair still requires full
semantic/visual review; skipping this script-specific check does not prove absence
of untranslated prose. QA reports whether the CJK check actually ran.
Its per-page OCR checkpoints bind rendered pixels, source-page mapping, active
models/config, runtime and code. Rechecking unchanged pages does not load ONNX;
changed pages or OCR settings invalidate their measurements. These checkpoints
never replace current candidate-bound semantic/visual acceptance. Fresh tests
must use new job directories.

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
Keep page-plan entries `preserve_raster`; fixed pagination retains source order
and count. Explicit continuations require the additional output/source mapping
and current rendered review; an overflow reason alone does not authorize them.
Before adding pages, measure the complete original column and actual rendered
baseline spacing. Do not accumulate extra top/bottom padding for every short
heading, or impose an arbitrary minimum such as 9 pt. A consistent, genuinely
readable size in the original safe area takes priority over unnecessary pages;
confirm the tightest region in an actual render before changing pagination.

Cleanup uses tight source-line/glyph boxes independently of the target layout box.
Sample the local background; use a constant fill only after confirming it fits
that actual region. In a visually confirmed skewed scan table, use
`preserve_skewed_rules: true` on the affected replacement regions. The builder
copies original pixels of long lines supported on both sides of the cleanup
box. Inspect every restored intersection for surviving letters or missing rule
segments. Use actual blank paper pixels for a reviewed local fill when a dark
table rule dominates the sample ring. Preserve rules, leaders, icons, signatures
and photos.
For a reviewed black caption crossed by a colored signature, explicit
`preserve_colored_ink: true` retains the original colored strokes during cleanup.
Do not use it to leave colored ordinary source prose untranslated. Protect the
complete signed identity field and annotate beside it if its content cannot be
safely separated. Preserved numeric/formula/code or justified proper-name ink
needs no invented OCR transcription: `preserved_ink` records the actual source
classification, and official QA independently renders and compares those source
regions. The builder protects their original pixels from cleanup patches;
translated text must still avoid them. Clear words must be supplemented instead.
If a previous local repair redraws an original number, check whether a preserved
source block already owns those same physical glyphs. Merge duplicate ownership
into the reviewed repair or retain the original once; do not restore original
ink and draw a second copy over it. Distinct OCR IDs alone do not prove distinct
physical content.
A formula or numeric value does not exempt adjacent prose from translation.
Inspect the whole line; when an equation ends in a readable sentence, preserve
the equation pixels and translate only the prose using separate cleanup/layout
boxes. Do not mark the entire mixed line as preserved merely because it starts
with mathematical symbols.
Wrap full paragraphs/cells at a consistent role baseline; first use safe space,
then shrink only the genuinely overflowing unit. Preserve color and orientation.
Keep embedded names, model identifiers and signed decimal values intact when
wrapping Chinese text; repair a narrow frame rather than splitting a value.

## Output size and delivery

Use the official builder rather than a task-specific full-page raster writer.
Its build report records the executing script hash, original-background/fallback
page counts, encoded image bytes, output bytes and growth ratio. Check these
measurements on the first candidate, before spending more time on final assembly.
A fallback is lossless, but can be large; do not force every page into that path.

When a receiving channel has a known limit, pass `--max-output-mib <actual-limit>`
to the build command (for example 200 only for a channel with that limit). The
builder saves an over-limit artifact and its report but exits nonzero with
`delivery_ready: false`. More than 3x growth with over10 MiB added also requests
a size review. QA cannot pass a build marked not ready for delivery. Diagnose
image encoding/fallback counts; never silently raise the limit, discard pages,
flatten target text or lower scan readability to make a file fit.

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
