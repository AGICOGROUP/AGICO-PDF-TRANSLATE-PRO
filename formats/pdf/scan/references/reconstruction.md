# Reconstruct text pages and assemble a scan translation

Use for replacement-mode `reconstruct` pages selected by the scan Skill. This
is an agent-directed ReportLab workflow inside the scan adapter. Page strategy,
source understanding and layout are reviewed by the agent; there is no automatic
reconstruction flag in `build_scan.py` or `verify_scan.py`. Do not use the native
adapter on scan pages. The existing raster workflow remains the implementation
for every page containing an engineering drawing, hand drawing or test schematic,
even when the drawing is small and the rest of the page is prose. Those pages
must not use this reconstruction procedure.

## 1. Plan and understand pages

Create `manifest/page-plan.json` following `workflow.md`. Keep the immutable
source SHA-256, source render hashes, selected page order, target language and
output mode. Each page records its strategy, reason and original geometry.
Use source-page numbers in all data; output positions are separately 1-based.

Read the entire original page, using OCR to locate and account for text. Enlarge
uncertain names, tolerances, subscripts, tables and formulas rather than repeatedly
rerunning whole-document OCR. For each reconstructed page, record ordered content
in `manifest/reconstruction.json`:

- Original page number and geometry; ordered heading, paragraph, clause, list,
  table, formula, caption and asset items with stable IDs.
- Each text item's source text, full translation and source-line IDs or located
  visual-supplement IDs. Preserve existing IDs. Record justified preservation or
  OCR-noise exclusions explicitly. A source item has exactly one output owner.
- Tables: cell IDs, row/column indices, row/column spans, source/translation,
  header levels, units and notes. Confirm relationships visually before fitting.
- Assets: source render path/hash, crop box in that render's top-left pixel
  coordinates, original crop pixel hash, destination box in PDF points, caption
  relationship, and any local label-edit record.

This job-local data is not a `build_scan.py` manifest. Do not add dummy cleanup
boxes to recreated text. Its IDs and page mapping provide coverage evidence for
the shared semantic review. Splitting a sentence at a source page boundary must
retain that boundary's content allocation; adjacent pages provide context, not
permission to move clauses between pages.

## 2. Establish styles with representative pages

Use consistent target-language fonts, margins, heading hierarchy, table rules
and caption styles inspired by the source. Check the first five pages when
representative; include a table and an illustration page elsewhere if needed.
Inspect samples before propagating styles. A user-requested sample checkpoint
requires their acceptance; without that request, continue after your own checks.
Sample work counts toward the same task budget and is reused within the run.

## 3. Build reproducibly with ReportLab

Write a job-local `build_reconstructed.py` using the structured data. Record its
path/hash and the dependency/font versions. Use installed ReportLab, pypdf and
Pillow; no new translation engine or automatic scan-to-CAD conversion. Generate
one page PDF per source page, then assemble; replace candidates atomically only
after successful generation. Keep previous readable candidates if a build fails.

- Register fonts that cover the target language and required symbols. Keep
  translated prose selectable; rasterizing an entire rebuilt page is not delivery.
- Use `reportlab.platypus.Paragraph` for full translated passages. Escape literal
  XML-sensitive source characters before adding deliberate formatting markup.
- Use `Table` and `TableStyle` with explicit column widths, `SPAN`, alignment,
  padding and vector rules. A merged cell owns content once; its covered cells
  must not repeat the translation. Use Paragraphs inside cells for wrapping.
- Measure each flowable with `wrap(available_width, available_height)` and place
  it with `drawOn` only after checking its bounds. Advance by actual height plus
  spacing. Use explicit page geometry and page breaks; do not let a document
  template silently spill into extra pages or move content to the next source page.
- Adjust spacing, column widths and same-page placement before reducing a whole
  paragraph/cell's font. If complete readable content cannot fit, record a failed
  fit and deliver a preview at the limit; never omit, summarize or hide overflow.
- Position fraction components, super/subscripts and formula numbers explicitly
  when a Paragraph cannot express them reliably. Compare mathematical meaning
  with the original; any image-only formula requires a justified preservation
  record, with translatable surrounding text rendered as text.
- Preserve source page count, section/appendix starting pages and cross-references.
  Carry existing meaningful bookmarks or create reviewed section/appendix bookmarks
  when needed; record their final destinations during assembly.

This job-local script is the authorized reconstruction builder. It does not
impersonate the raster builder and cannot create raster `official_pipeline`
evidence. Its measured output and independent reviews establish acceptance.

## 4. Reuse nontechnical artwork

Engineering drawings and test schematics select `preserve_raster` for the entire
page; do not crop one into a rebuilt page as a workaround. This section applies
only to nontechnical assets such as photos, seals, signatures and logos.

Crop each complete asset from the immutable source render and keep it separately
lossless with source provenance. It may move or scale proportionally within its
rebuilt page while retaining legibility, full extent and caption relationships.
No stretching, substituted icons, regenerated seals or redraws.

For translatable wording inside such an asset, use tight local glyph cleanup
and vector translated text. Record local masks, original/edited pixel hashes,
source IDs and crop-to-page transforms. Compare equal-size asset pixels before
scaling: pixels outside approved glyph edits must match. Check the composed
asset's labels at final size for direction, overlap, clipping and readability;
keep translated labels selectable. If preservation cannot be established, route
the whole page to `preserve_raster` and record any unresolved edit. Raster routing
does not itself solve an unsafe edit or justify fabricating passing evidence.

## 5. Assemble with provenance

Build/verify the raster subset with the existing scripts, retaining original
source page numbers. Its manifest includes only that subset's pages, source
lines and blocks; its own reviews bind to its own component PDF hash. Preserve
the resulting component PDF, build report and real verification report.

Use `pypdf.PdfWriter.add_page` to assemble reconstructed page PDFs and raster
component pages in `page-plan.json` order without rasterizing or redrawing them.
Map source page to component path/hash and component page index explicitly;
do not use source page number as the index into a shortened component PDF.

Write `output/assembly-report.json` from actual operations: source hash, plan
and reconstruction-data hashes, reconstruction script/font identities, final
PDF SHA-256 and one row per output page with source page, strategy, component
path/hash/index and geometry. Link raster component reports and asset provenance.
The report is a build receipt, not an assertion that quality passed.

## 6. Verify the assembled result

Follow `quality-gates.md`. Run job-local checks on the **actual final PDF**:
page count/order/mapping and geometry, extracted target text coverage per item,
embedded fonts and glyph support, text/asset bounds, asset provenance and bookmark
destinations. Record command/script identities, measured results and findings
in `qa/final-qa.json`. Preserve the final source/output hashes.

Render every final page at readable resolution. Compare each component page's
render and selectable text with its assembled counterpart at identical geometry
and resolution; merging must not introduce changes. Reuse this final render for
full-page semantic/layout comparison against the original. Check table ownership,
formulas, source residue and original artwork, then magnify anomalies only.
Rebuilt pages require full-page visual comparison because the layout is new;
their correct content/structure replaces the raster whole-page pixel-equality
test. Raster pages and edited illustration assets still require non-text protection.

Save separate source-to-target `translation-review.json` and rendered-page
`visual-review.json`, bound to the final PDF hash and all selected source pages.
For mixed jobs, final review records reference the verified component evidence;
do not overwrite component hashes with the assembly hash. After changes, rebuild
and inspect affected pages, retain unchanged evidence by content identity, and
recheck assembly. Missing, stale or unresolved checks remain unverified/failed.

These are agent-run checks, not a new packaged automatic verifier. Do not mark
success from a build receipt, OCR coverage or a plausible-looking contact sheet.
Apply the same three blocking requirements and 120-second-per-page total budget
as raster translation. Report previews honestly when the task cannot finish.
