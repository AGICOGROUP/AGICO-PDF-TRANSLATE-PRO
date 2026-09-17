# Scan PDF acceptance

Apply [the shared delivery policy](../../../../references/delivery-policy.md).
The three blocking requirements are correct content, complete/readable output
and intact key structure. Coverage, selectable text, page geometry, meaningful
color, icon provenance and cleanup checks provide evidence for them.

## Raster workflow acceptance

Every scan-only page uses `preserve_raster`, including prose and regular tables.
Preserve original page geometry, page correspondence, non-text artwork and
table/value relationships. Replacement uses local glyph cleanup and selectable
target text; additive output leaves original pixels unchanged.

Required evidence: the raster manifest, official `build_scan.py` report and
`verify_scan.py` result against the exact delivered PDF, together with actual
source-based semantic and rendered visual review. Missing, stale, failed or
unverified blocking evidence prevents `passed`. Do not fabricate passing results
from OCR confidence, block counts or successful construction alone.

Render every page for initial coverage and inspect edited regions and anomalies.
After repairs, render/review affected pages only; retain unchanged-page evidence
by content identity. Cosmetic differences are not failures unless they damage
meaning, readability or key structure.

Source-relative minimum font sizes are warnings. Actual unreadability,
missing glyphs, meaningful overlap/clipping and structural damage still block
completed delivery. A warning is not permission to omit or summarize text.
Source text confirmed illegible under the shared two-attempt policy is a
documented, nonblocking source limitation. Preserve its pixels and record its
location and attempts in the existing semantic review. Do not count it in
`untranslated_clear_labels` or `unreadable_text_failures`; the latter concerns
unreadability introduced in the output. Readable untranslated content remains
blocking even when OCR missed it. Review does not reset the attempt counter.

Use visual-review.json bound to candidate_sha256 with all_pages_rendered,
reviewed_changed_regions, reviewed_anomaly_pages, text_overlap_failures,
clipping_failures, unreadable_text_failures and untranslated_clear_labels.
Populate these fields from the reviewed candidate, not a template that defaults
to `true`, empty failure lists or `untranslated_clear_labels: 0`. Before inspection,
leave evidence unverified; a translation model's review of text alone is not a
review of the rendered PDF. Inventory coverage counts only registered source
IDs: zero unassigned/missing blocks does not prove OCR found every visible line.
For replacement output, a clear source-language sentence remaining beside its
translation is still a cleanup defect; register its geometry and repair locally.
Direction checks compare actual PDF glyph matrices with the manifest's clockwise
source-image angles, during the existing text extraction pass. Matching manifest
fields alone does not prove rendered orientation. During the existing changed-region
visual review, compare source and target in the same viewing orientation; verify
reading direction and upright glyphs, including title blocks and rotated notes.
Do not mark orientation or other visual checks passed without inspecting them.
Treat automatic overlap results as candidates for the existing anomaly review,
not as visually confirmed defects. Inspect each flagged word pair in a local
render with enough surrounding context to judge readability and field alignment.
Harmless bounding-box intersections are false positives; actual glyph occlusion,
unreadability or damaged field relationships require local correction. If not
inspected, report an unverified overlap candidate, not a confirmed collision.
Dismiss confirmed false positives after that local visual inspection:
copy the exact output_page, first, second, first_box and second_box into
reviewed_overlap_false_positives with a nonempty reason. The existing candidate
hash must match. No whole-page exclusions; actual overlaps recorded in
text_overlap_failures remain blocking. Old reviewed OCR false positives absent
from the current result are warnings, not new translation defects.
Render initial page coverage, then only affected pages after corrections;
reuse unchanged-page evidence with content identity.

verify_scan.py also reads translation-review.json beside the visual review
(or --translation-review). Review every page against the original, including
OCR omissions. Keep current hashes, reviewed source IDs, actual context and
unresolved findings. After rebuilding, inspect affected candidate pages before
updating their evidence and final candidate hash; retain unchanged-page evidence
only with content identity. Do not turn old translation notes into a new visual
pass by rebinding hashes. Automated validation cannot establish semantic accuracy.

At 120 seconds per selected page stop repair loops. Completed output requires
passed verification. Otherwise provide a clearly named preview with its real
failed/unverified report and known issues, never a fabricated passing report.
