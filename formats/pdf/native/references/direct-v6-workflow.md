# Direct original-to-v6 workflow

The user supplies only the original PDF. The Skill owns every intermediate
artifact under a source-hash-bound job directory.

## Commands

```powershell
python scripts/run_v6_job.py init <source.pdf> --jobs-root tmp/pdfs --source-language <source-code> --target-language <target-code>
python scripts/run_v6_job.py build-native <job>
# Nonempty image inventories only; images=[] goes directly to assemble.
python scripts/run_v6_job.py annotate-images <job> `
  --metadata <image-vector-metadata.json> --review <image-review.json>
python scripts/run_v6_job.py build-images <job>
python scripts/run_v6_job.py assemble <job>
python scripts/run_v6_job.py verify <job> `
  --visual-review-report <job>/visual-review.json
```

`init` returns the authoritative `job_dir`, binding the source and normalized
language pair in replacement mode for all source pages. The same request resumes
its job; a different language pair selects another job. `--fresh` starts an
independent test without reusing old artifacts and leaves old jobs intact.
Legacy source-only jobs can still be resumed by their explicit path.

After `build-native`, a source/hash-bound inventory with an explicit empty
`images` list needs only `assemble`. It calls the existing `annotate_images` and
`build_images` stages with system-generated empty metadata and complete review,
then assembles normally. The image metadata/review/cleanup artifacts and stage
hash checks remain recorded; final source-to-target semantic and visual reviews
are still required. `resume` returns `assemble` for this case. Do not handwrite an
empty review or infer emptiness from a missing, invalid or changed inventory.
Any nonempty inventory, including logos without translatable text, still needs
the normal complete image review before assembly.

`export-translation` writes one unchanged `source_text` per record. A page's
`ordered_source_ids` reconstructs its complete source in order and determines
the neighboring records without extra per-record references. Read those records
with the original page before translating. The packet does not repeat full page
text or neighboring paragraphs. Compact terminology retains matching technical
phrases and available sense context; `unreviewed: true` is a caution, not approval.
Use explicit glossary lookup for omitted short/ambiguous words. Legacy packets
with textual page/neighbor context still import through the same source, request,
ID and translation validation; the export change does not waive output QA.
Retain valid unchanged numeric/unit/identifier translations and submit only the
pending records through the existing subset importer. This avoids rewriting an
entire second target list while all source IDs remain owned and reviewed.
Latin prose is not exempt from translation merely because it is non-CJK.

Use `status` or `resume` when recovering an interrupted job, rather than between
successful commands in a fresh run. `resume` reports the next internal action. Exit code 2 means Codex must perform
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

Returning to the owning stage is a command, not a hand edit. Re-annotating with
`--revise` rewinds a job that already passed the image station:

```powershell
python scripts/run_v6_job.py annotate-images <job> `
  --metadata <revised-metadata.json> --review <revised-review.json> --revise
python scripts/run_v6_job.py build-images <job>
python scripts/run_v6_job.py assemble <job>
```

The rewind grants only the image station. It refuses unless the source hash and
the rebuilt native PDF still verify, drops every artifact produced at or after
annotation, and increments `image_revision` for audit. Use it after a label box
or cleanup mode fix instead of starting a new job: without it, one corrected box
costs a full re-extract and native rebuild.

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
