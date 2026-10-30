---
name: PDF-TRANSLATE-PRO-NATIVE
description: Translate ordinary native-text and mixed PDFs into selectable target text while preserving tables, images and layout. Use only the PDF router's native result.
---

# Native and mixed PDF translation

Use the router's native result. Scan-only/hidden-OCR files use scan;
engineering drawings use the returned native-CAD or bilingual branch.
Read the root [delivery policy](../../../references/delivery-policy.md) and
[page-context review](../../../references/page-context-translation-review.md).

## Prepare and translate

Commands below run from this adapter. Keep the original immutable.
[Runner workflow](references/direct-v6-workflow.md) describes stage evidence.

```powershell
python scripts/run_v6_job.py init <original.pdf> --jobs-root <jobs-root> --source-language en --target-language zh --fresh
python scripts/run_v6_job.py resume <returned-job>
python scripts/pdf_translation_pipeline.py export-translation --manifest <job>/manifest.json --output <job>/translation-packet.json
```

Use actual language codes; `--fresh` is mandatory for tests. For a same-request
repair resume its existing job. Use the returned job path, not a guessed hash.
The compact packet supplies ordered whole-page context and relevant cement
terminology alongside records; read it once with the source pages. Query
[cement-terminology.md](references/cement-terminology.md) through
`scripts/glossary_lookup.py` for further senses, including `--source-language en`.
Prefer the table over model phrasing only for the matching engineering meaning.

Fill fluent complete translations by stable ID and unchanged source_text. The
packet importer accepts subsets, rejects duplicate IDs, changed source/request,
non-text/blank targets and inappropriate CJK residue before writing any changes.
Chinese/Japanese targets allow their own script without an unrelated override.

```powershell
python scripts/pdf_translation_pipeline.py merge-translation --manifest <job>/manifest.json --packet <job>/translation-packet.json
python scripts/run_v6_job.py build-native <job>
```

## Fit complete paragraphs and cells

Use source-derived role size/alignment/rotation and physical `source_cell_bbox`.
Translate each full cell including its continuation. Keep separate values, units
and neighboring cells separate; shrinking a cross-column extraction is not repair.
For old incorrectly bound rows use reviewed `manual_table_parts` or re-extract.
[Layout reference](references/selectable-and-image-text.md) and
[manifest schema](references/manifest-schema.md) define the existing fields.

Wrap at a consistent source-derived role baseline. First repair avoidably narrow
boxes and use verified whitespace. If translation expansion still cannot fit
readably, prefer necessary continuation pages under the shared
[pagination policy](../../../references/pdf-pagination.md) over excessive shrinking.
Keep emphasis, technical symbols, image aspect ratio and the source formatting.
Only minor local fitting may shrink an overflowing paragraph/cell uniformly.

## Text inside images

Inspect every original image XObject, including logos/photos/diagrams, and decide
whether it has translatable text. Read [image routing](references/image-localization-routing.md)
and [vector overlay](references/image-vector-overlay.md) only for affected images.
Use original XObjects, tight per-line cleanup and protected boxes; place selectable
target text separately. A text-band solid fill requires observed text-only space,
not a whole-cell erasure across signatures, rules or symbols. Mixed raster pages
stay in this job and need complete source-label ownership too.

Follow runner `annotate-images`, `build-images`, `assemble`; review entries must
cover every inventory image, including a true no-text finding. For local image
corrections use `annotate-images ... --revise` instead of restarting extraction.
Unchanged English prose is not completed Chinese output; omitted material cannot
be relabeled `ocr-artifact` or replaced with dots.

## Review and deliver

Render all selected pages once, inspect changed cells/regions and anomalies at a
readable scale, then re-render only repaired pages. Record real source-to-target
findings in translation-review.json and candidate-bound visual-review.json using
[runner review schema](references/direct-v6-workflow.md).

```powershell
python scripts/run_v6_job.py verify <job> --visual-review-report <job>/visual-review.json
```

Completed delivery requires stage `verified`, final-qa.json passed and no unresolved
meaning, readability or structure defects. Empty native draw coverage cannot pass
when native text exists. Typography warnings alone do not require another build.
A useful incomplete result remains a labelled preview under the shared policy.
