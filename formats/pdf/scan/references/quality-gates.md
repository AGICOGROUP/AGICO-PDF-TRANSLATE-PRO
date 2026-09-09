# Scan PDF acceptance

Apply [the shared delivery policy](../../../../references/delivery-policy.md).
The three blocking requirements are correct content, complete/readable output
and intact key structure. Coverage, selectable text, page geometry, meaningful
color, icon provenance and cleanup checks provide evidence for them.

Source-relative minimum font sizes are warnings. Actual unreadability,
missing glyphs, meaningful overlap/clipping and structural damage still block
completed delivery. A warning is not permission to omit or summarize text.

Use visual-review.json bound to candidate_sha256 with all_pages_rendered,
reviewed_changed_regions, reviewed_anomaly_pages, text_overlap_failures,
clipping_failures, unreadable_text_failures and untranslated_clear_labels.
Only record observed findings; a missing check is not a zero result.
Render initial page coverage, then only affected pages after corrections;
reuse unchanged-page evidence with content identity.

verify_scan.py also reads translation-review.json beside the visual review
(or --translation-review). Review every page against the original, including
OCR omissions. Keep current hashes, reviewed source IDs, actual context and
unresolved findings. Never generate passing entries from counts or merely
rebind old hashes. Automated validation cannot establish semantic accuracy.

At 120 seconds per selected page stop repair loops. Completed output requires
passed verification. Otherwise provide a clearly named preview with its real
failed/unverified report and known issues, never a fabricated passing report.
