# Scan-only PDF workflow

For additive bilingual engineering drawings, also read
`additive-bilingual-drawings.md` and use `action: add_bilingual`.

## 1. Prepare

Work from the original PDF. Create `<work>/<stem>-<sha8>/` with `extract/`, `manifest/`, `output/`, `review/`, and `qa/`. Keep the source immutable.

```powershell
python scripts/classify_pdf.py --source "input.pdf"
python scripts/extract_scan.py --source "input.pdf" --pages all --output "job/extract" --dpi 400
python scripts/make_manifest_template.py --extraction "job/extract/extraction-report.json" --output "job/manifest/translation-manifest.json"
python scripts/draft_blocks.py --extraction "job/extract/extraction-report.json" --output "job/manifest/draft-groups.json"
```

## 2. OCR inventory and translation

Use cached single-scale OCR first. Retry only uncertain pages with --dual-scale or inspect uncertain crops at higher resolution. Visually compare the source render because OCR can split, merge, hallucinate, or miss text. Every clear source label belongs in the manifest, including text in diagrams, tables, photos, screenshots, seals, logos, headers, footers, and rotated regions.

Each completed page is saved atomically in `extract/page-checkpoints/` before
the next OCR page begins. Resume with the same command/output directory; valid
pages are reused, while changed source/configuration/renders are recomputed.
Use `--no-resume` only for a deliberate cold run. The final extraction report is
assembled from the requested pages in order, so manual batch merging is unnecessary.
Per-page progress and report `elapsed_seconds` provide real timing evidence.
The top-level `elapsed_seconds` is this invocation only. Cached pages retain
their original processing duration. Neither field includes earlier failed
attempts, and neither proves total translation time. Keep an independent task
start timestamp and include retries when assessing the 120-second-per-page budget.

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

In additive bilingual mode, inventory all clear Chinese labels and their
nearby target-language counterparts. Preserve the diagram as `bilingual_complete` only
when every Chinese label is paired. Some target-language text on the image is insufficient;
translate every unmatched Chinese label.

## 3. Choose cleanup geometry

The default is tight glyph-only cleanup:

- Uniform background: use a clean box only 1–3 pixels beyond the glyph envelope.
- Table cells: clean glyphs, not the whole cell. If a rule crosses text, clean the smallest necessary interval and rebuild that verified segment with `vector_lines`.
- Leaders or dotted lines: leave dots outside the target text box intact; rebuild only the verified interrupted segment.
- Engineering/process diagrams: preserve pipes, arrows, wires, beams, borders, symbols, and color coding. Never regenerate the diagram. Use local sampling only when the surrounding region is genuinely uniform.
- Photographs/UI/screenshots: do not synthesize unknown background. If text sits on a nonuniform texture and a clean removal cannot be proved, perform pixel-local clone/inpaint outside these generic scripts, then verify the protected structure at high zoom.
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
unreadability, not a numeric reference floor, requires correction. Record a real
fit failure before using a page `layout_adjustment`.
Try shifting a large image first, then proportional shrink. The old image area
must be verified uniform background and both old and new boxes become approved
difference regions.

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

The builder samples only the original glyph-border pixels and caches lossless
clean bases under `output/clean-bases/`. Cache validation includes source-render
hash, cleanup boxes/colors, raster adjustments and builder implementation hash.
Changing only wording or fonts reuses the base while rebuilding all target text.
Do not change cleanup boxes merely to obtain a cache hit. A failed build keeps
the previous PDF intact; completed output replaces it atomically. The report
records total/per-page elapsed time and base cache hits.

## 5. Review and verify

Review semantic accuracy on every selected page against the original page and
final translation, including text missed by OCR. Save the adapter-owned
`translation-review.json` as specified in the shared reference. Correct and
re-review affected pages before delivery. This is part of the existing
translation-integrity check; the selective visual review below concerns layout.

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
