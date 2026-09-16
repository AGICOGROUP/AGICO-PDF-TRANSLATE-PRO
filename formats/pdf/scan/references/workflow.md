# Scan-only PDF workflow

The scan Skill selects `reconstruct` or `preserve_raster` **per page** before
translation layout. For reconstruction, follow `reconstruction.md`; steps 2–5
below describe the existing raster path only. Shared source reading, terminology
and semantic review apply to both. Do not send rebuilt pages to the raster
builder/verifier or run a second PDF adapter.

For additive bilingual engineering drawings, also read
`additive-bilingual-drawings.md` and use `action: add_bilingual`.

## 1. Prepare

Work from the original PDF. Create `<work>/<stem>-<sha8>/` with `extract/`, `manifest/`, `output/`, `review/`, and `qa/`. Keep the source immutable.

For a test, add a unique run suffix and start with fresh artifacts even if the
input was tested before. Read whole-page renders to write `manifest/page-plan.json`
with source hash, target language, mode, ordered selected pages and one entry per
page: source page number, strategy, reason, width/height in points and render path.
Preserve source page numbers throughout; output positions are a separate mapping.
OCR does not choose the page strategy automatically.

```powershell
python scripts/classify_pdf.py --source "input.pdf"
python scripts/extract_scan.py --source "input.pdf" --pages all --output "job/extract" --dpi 400
python scripts/make_manifest_template.py --extraction "job/extract/extraction-report.json" --output "job/manifest/translation-manifest.json"
python scripts/draft_blocks.py --extraction "job/extract/extraction-report.json" --output "job/manifest/draft-groups.json"
```

The example manifest/draft commands apply to raster pages. If the extraction
contains both strategies, derive a raster-only extraction JSON in the job:
retain the immutable source path/hash, select only raster entries in `pages`
and `selected_pages`, and retain only their `source_lines`, without renumbering.
Keep the original extraction report unchanged. Feed that subset to the template
and draft commands. A reconstruction-only job does not need a raster manifest.

## 2. OCR inventory and translation

Use single-scale OCR, reusing completed pages only within the current run or an
authorized resumed non-test job. Retry only uncertain regions/pages or inspect
uncertain crops at higher resolution. Compare the existing source render with
the inventory: OCR can split, merge, hallucinate, or miss text, including whole
continuation lines. Include clear text in diagrams, tables, photos, screenshots,
seals, logos, headers, footers, and rotated regions.

When a missing line is visually confirmed, register its source text, stable new
ID, page, rotation and tight glyph box in **source-render pixels**, and bind it
to the appropriate translated block. For a missing continuation in an existing
replacement block, use `scripts/register_source_supplements.py` and the payload
in `manifest-schema.md`. It updates source IDs, full passage text and per-line
cleanup together, leaving the target box and unrelated blocks unchanged:

```powershell
python scripts/register_source_supplements.py --manifest "job/manifest/translation-manifest.json" --supplements "job/manifest/source-supplements.json" --output "job/manifest/translation-manifest.json"
```

Supply the complete reviewed translation; if it already includes the missing
line's meaning, keep it unchanged rather than translating that line twice.
For an unrelated missing label/cell, create its own located source line and
block using the normal manifest contract, not an unrelated paragraph owner.
In additive mode register the label and its translation without source cleanup;
the replacement-only helper deliberately rejects additive blocks. Keep these
additions in the authoritative manifest instead of regenerating it from an old
draft. A correction note or extra translated sentence is not a located supplement.

Each completed page is saved atomically in `extract/page-checkpoints/` before
the next OCR page begins. Resume with the same command/output directory; valid
pages are reused, while changed source/configuration/renders are recomputed.
Use a new directory for every fresh test; `--no-resume` also forces a cold extraction.
The final extraction report is
assembled from the requested pages in order, so manual batch merging is unnecessary.
Per-page progress and report `elapsed_seconds` provide real timing evidence.
The top-level `elapsed_seconds` is this invocation only. Cached pages retain
their original processing duration. Neither field includes earlier failed
attempts, and neither proves total translation time. Keep an independent task
start timestamp and include retries when assessing the 120-second-per-page target
and 180-second-per-page acceptance ceiling. Quality requirements are unchanged.

For replacement pages, prefer [compact decisions](compact-decisions.md) and
`compile_translation.py` over writing a document-specific manifest population
script. Set page-category styles once; supply translations, corrected ownership
and located supplements as data. Keep final semantic and visual review agent-owned.
Batch independent CLI preparation steps and each build/render sequence in one
tool invocation; avoid repeating schema reads or whole inventories within a job.

Use the draft groups to translate prose with the complete ordered page as
context and return one translation per region ID. A normal prose page should
contain a small number of coherent regions, not one output block per OCR line.
Keep table cells, drawing labels, rotations, headers, and footers separate when
their structure requires it. Preserve numbers, units, model names, standards,
URLs, emails, and trademarks exactly unless localization is explicitly required.
Build a document-level glossary before translating repeated technical terms.
Translate meaning, not OCR noise.

`draft-groups.json` includes stable region IDs and a `pages` array containing
ordered source IDs, whole-page text and region IDs. Include that page and the
document glossary with each translation request. Use adjacent page context for
continuations. Do not translate a global set of unique short strings without
context: identical wording can have different meanings in different sections.
Use the available capable model directly; installing a new offline translation
engine or chaining source-to-English-to-target models is not a time-saving fallback
for professional translation. Never lower the review standard to meet a deadline.

Follow `../../../../references/page-context-translation-review.md`: reconstruct
split sentences, use the whole page and glossary in every translation batch,
and confirm OCR corrections against the source pixels. Adjacent pages provide
context when content continues across a page boundary.

For the supported Chinese-pair engineering shortcut in additive bilingual mode,
inventory all clear Chinese labels and their nearby target-language counterparts.
Other bilingual pages keep actual source-language ownership and do not use that
shortcut. Preserve the diagram as `bilingual_complete` only
when every Chinese label is paired. Some target-language text on the image is insufficient;
translate every unmatched Chinese label.

## 3. Choose cleanup geometry

On `preserve_raster` pages the default is tight glyph-only cleanup. This is not
the text-page reconstruction procedure:

- Uniform background: use a clean box only 1–3 pixels beyond the glyph envelope.
- Table cells: clean glyphs, not the whole cell. The builder preserves long straight rules crossing glyph boxes. Inspect the result; use `vector_lines` only for a verified interrupted segment that still needs repair, not for routine redraw.
- Leaders or dotted lines: leave dots outside the target text box intact; rebuild only the verified interrupted segment.
- Engineering/process diagrams: preserve pipes, arrows, wires, beams, borders, symbols, and color coding. Never regenerate the diagram. Use local sampling only when the surrounding region is genuinely uniform.
- Photographs/UI/screenshots and intricate backgrounds: do not synthesize unknown background. The current official builder supports sampled/constant glyph fills, not an external inpainted-base import. If it cannot remove text while preserving the background/structure, record a located unsupported edit and keep the result failed/unverified for preview delivery. Do not modify immutable source renders or fabricate cache provenance to ingest externally edited pixels.
- Logos: translate the readable wording while preserving artwork. A trademark or brand name may use `preserve_confirm` when translation would be incorrect.

### Icon routing and mixed-color text

Classify each icon before cleanup:

1. **Outside the glyph cleanup area:** leave it untouched in the raster base. This is preferred.
2. **Inside an unavoidable cleanup area:** add a `rich_lines` `source_crop` run using the exact source-render pixel coordinates. The builder restores those source pixels inline and records their SHA-256 provenance.
3. **Not safely recoverable:** use `preserve_confirm`, describe the issue, and block delivery pending review.

Do not replace a source icon with Unicode, a font glyph, explanatory text, or a similar icon from another library. For lines containing orange commands, blue links, warnings, or other meaningful color changes, use `rich_lines` text runs and preserve each run's RGB color. The concatenated text runs must equal the block `translation`; source-crop runs do not add text.

The `box` is the target-language text area. In replacement mode, `clean_box` is
one source-glyph removal area and `clean_boxes` is the list of glyph envelopes
for a multi-line region; define exactly one form. They are intentionally
separate from the region union. Never enlarge cleanup geometry merely because
the translation is longer. In additive bilingual
mode, omit `clean_box` and place `box` below, right, or in a verified blank panel.

Plan `major_title`, `minor_title`, `body`, `annotation`, `table`, `header`, and
`footer` typography once per page. Use one font, size, weight, and leading ratio
for each group. Treat `caption` as `annotation`; drawing labels and callouts that
serve the same semantic function must also use the annotation group. Classify by
semantic function and source hierarchy, not OCR-box height alone. Titles are
normally bold or larger, body is regular and dominant, and annotation is regular
and smaller. When all three occur, preserve `title > body > annotation`.

Fit complete paragraphs at the page group's baseline with wrapping first. Only
an overflowing paragraph may shrink, uniformly as a whole; record its baseline,
fitted size and reason. Other paragraphs retain the baseline. A caption, drawing
label, header, footer or table cell must not reduce body text size. Actual
unreadability, not a numeric reference floor, requires correction. Keep engineering
artwork fixed on raster pages. The builder's existing `layout_adjustment`
capability is not permission to move drawing structure. A page containing any
engineering figure or test schematic remains on this raster path even if most
of it is prose. Only text/table pages without such drawings qualify for
reconstruction and within-page reflow.

## 4. Build

```powershell
python scripts/build_scan.py --manifest "job/manifest/translation-manifest.json" --output "job/output/translated.pdf"
```

The builder hard-fails when complete target-language text cannot fit. It records
changed pixels and requires zero changes outside approved cleanup boxes. A pure
`add_bilingual` build requires `changed_pixel_count: 0`. Optional `vector_lines`
are drawn after the cleaned page image and before target text. For every
`source_crop` run it records the source page, source box, output box, pixel
SHA-256, and alt description in the build report.

The builder samples local glyph-border pixels. If a narrow ring is contaminated
by a dark table rule, a wider estimate is used only when both the interior and
wider ring confirm light paper; dark/colored backgrounds retain local sampling.
Straight-rule preservation does not preserve whole connected components or
reconstruct signatures. Keep glyph cleanup tight and inspect nearby artwork.
The builder caches lossless clean bases under `output/clean-bases/`.
Cache validation includes source-render
hash, cleanup boxes/colors, raster adjustments and builder implementation hash.
Changing only wording reuses the base and redraws target text on dirty pages;
changing fonts invalidates the affected page caches. With no valid page caches,
the builder draws one shared-resource document and splits its measured page
caches without drawing again. Repair assembly merges exact duplicate PDF objects,
including font data and glyph maps; it does not equate fonts by subset name.
Resource deduplication reduces output size but adds assembly time. Use the existing
`--no-page-cache` path for full drawing comparisons; it still reuses clean bases.
Do not change cleanup boxes merely to obtain a cache hit. A failed build keeps
the previous PDF intact; completed output replaces it atomically. The report
records total/per-page elapsed time and base cache hits.

## 5. Review and verify

Review semantic accuracy on every selected page against the original page and
rendered candidate, including text missed by OCR. In replacement mode, check both
that the full meaning is translated and that the corresponding source wording
is removed. Once a missed line is found, look for the same omission pattern in
the other pages during this existing pass, not by restarting whole-file OCR.
Save actual findings in `translation-review.json` as specified in the shared
reference. Rebuild through the official builder and re-review affected pages;
the helper's `pages_requiring_review` is a work list, not passing evidence.
This is the existing translation-integrity review; selective high-zoom inspection
below concerns layout.

Render the final output once at the normal verification resolution. Run
automatic checks across every page. Inspect at high zoom only changed regions,
`source_crop` restorations, and pages or regions flagged as anomalies. Do not
create routine page-by-page screenshots or re-review unchanged logos, tables,
headers, footers, and icons. Create `visual-review.json` using the contract in
`quality-gates.md`.

```powershell
python scripts/verify_scan.py --source "input.pdf" --manifest "job/manifest/translation-manifest.json" --pdf "job/output/translated.pdf" --visual-review "job/review/visual-review.json" --report "job/qa/final-qa.json"
```

Schedule the first verification early enough within the existing time budget
to inspect its anomalies and rerun verification. For automatic overlap findings,
inspect the flagged local regions and classify them using `quality-gates.md`
before deciding on repairs or final failure. Record confirmed false positives
against the unchanged candidate and rerun verification without rebuilding.
For actual content/readability/structure defects, correct only affected blocks
within the remaining budget; re-render affected pages and retain traceable
unchanged-page reviews. Cosmetic warnings do not trigger rebuilds. At the limit
share a labelled preview, distinguishing confirmed defects from unreviewed
automatic candidates; the time limit does not extend for this review.
