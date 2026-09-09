# Direct original-to-v6 workflow

The user supplies only the original PDF. The Skill owns every intermediate
artifact under a source-hash-bound job directory.

## Commands

```powershell
python scripts/run_v6_job.py init <source.pdf> --jobs-root tmp/pdfs
python scripts/run_v6_job.py status <job>
python scripts/run_v6_job.py resume <job>
python scripts/run_v6_job.py build-native <job>
python scripts/run_v6_job.py annotate-images <job> `
  --metadata <image-vector-metadata.json> --review <image-review.json>
python scripts/run_v6_job.py build-images <job>
python scripts/run_v6_job.py assemble <job>
python scripts/run_v6_job.py verify <job> `
  --visual-review-report <job>/visual-review.json
```

`resume` reports the next internal action. Exit code 2 means Codex must perform
that action; it is not a request for a user-supplied intermediate.
Legacy `verified` jobs lacking current evidence return `revalidate_evidence`,
not `deliver`. Reclassify the original first; hidden-OCR scans start/resume the
scan route instead. Genuine native jobs can use `verify` to invalidate old
acceptance and check current evidence without rebuilding unchanged artifacts.

## Stage contract

| Stage | Required evidence |
|---|---|
| `initialized` | Source hash, native-text manifest, original-XObject inventory |
| `native_translated` | Complete translations and source-derived selectable PDF |
| `images_annotated` | Every inventory image and label reviewed; source type, route, OCR confidence, coverage, and confirms recorded |
| `images_cleaned` | Clean bases built; no changes outside approved regions; declared structures and evidence pass |
| `assembled` | Vector image labels merged into the native-text PDF |
| `verified` | Three shared blocking requirements passed; warnings retained |

`visual-review.json` must contain the SHA-256 of the exact candidate PDF.
Changing the candidate invalidates the report. The runner executes the native
selectability and typography verifiers itself; never copy zero values into the
final QA report. Native content requires a rebuild report with actual drawn
source IDs; an empty check is not a successful typography check.

Do not skip stages. Every artifact is bound by SHA-256. If the source or a
bound deterministic output changes unexpectedly, return to the owning stage.

## Image review schema

Review every ID in `image-inventory.json`, including logos, icons, diagrams,
photos, headers, and footers. Record whether it contains source-language text,
every stable label ID, asset type, OCR confidence, method, translation status,
coverage counts, structural-review status, and any `[CONFIRM]` regions. Images
with translated raster labels must have matching entries in
`image-vector-metadata.json`.

Use only the extracted original XObject path. Clean only minimum text regions.
Keep the clean drawing raster and place requested target text in an embedded vector
text layer.

## Existing review inputs consumed by verify

Save `translation-review.json` at the job root using the shared page-context
schema, with `adapter: native`. `selected_source_pages` and page records follow
manifest page order. Each `reviewed_source_ids` contains every native block ID
on that page plus every image label as `<image-id>/<label-id>` (page mapping
comes from the original image inventory). Include actual `context_checked`,
`corrections` and `unresolved_issues`; no-text pages need `no_readable_text`.
This validates review coverage, not translation correctness automatically.

`visual-review.json` contains `candidate_sha256`, `all_pages_rendered: true`,
`reviewed_changed_regions: true`, `reviewed_anomaly_pages`, and observed counts
`untranslated_clear_image_labels`, `unreported_confirm_items`. Record findings
in `text_overlap_failures`, `anchored_line_failures`, `unreadable_text_failures`,
`missing_glyph_failures`, `content_failures`, `clipping_failures` and
`structure_failures`. Empty lists mean inspected and no actual failures, never
unchecked. Cosmetic flags belong in warnings, not confirmed-failure lists.

The runner checks source/candidate hashes, page/source-ID coverage, cleanup
measurements and native draw coverage, then computes final acceptance. Do not
manufacture these inputs from a successful build or transplant old passing
booleans. If a page changes, re-review that page before binding new evidence.

## Delivery

For completed translation delivery require:

- `job.json` says `verified`;
- `final-qa.json` says `passed: true`;
- every selected page has completed source-to-target contextual accuracy review
  under `../../../../references/page-context-translation-review.md`, with a
  current hash-bound `translation-review.json` and no unresolved issues;
- initial render coverage and refreshed evidence for affected pages;
- changed regions and anomaly pages were visually inspected;
- no clear source-language text remains;
- source-selectable text and image-label text are selectable;
- image pixel and protected-line gates are zero.
- difference/structural evidence is complete for modified images;
- all confirm items are reported and no declared line failure remains.

Cosmetic typography diagnostics are warnings under
[the shared policy](../../../../references/delivery-policy.md). At the budget
limit, copy a clearly labelled preview with known issues if needed. A preview
keeps its failed/unverified state; the final-only requirements above do not
prohibit sharing it. Do not fabricate passing reports.
