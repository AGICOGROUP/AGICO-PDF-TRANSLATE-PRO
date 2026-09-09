# CAD review and delivery

Prepare provides source crops and cell proposals; apply reports unsafe regions,
missing records, fit failures and font baselines; review combines source/target
crops and script-residual candidates. Inspect these together and repair as a batch.

Cell geometry never approves a cover. Check all members and source protrusions.
Retain tags, numbers, borders, pipes and symbols. Replace a tight bilingual
description once; never estimate a script boundary from character counts.
A genuine separated existing target may use cover_only with target_present.

Verify checks page count/size/rotation, painted image digests/transforms and
retained vector count. Unused image resources and duplicate resource references
may disappear on save without losing visible images; dummy objects are never a
valid repair. These checks do not prove graphical integrity: inspect each
replacement with source pixels.
Confirm contextual meaning, quantities, units, negations, names, selectable
translations, legible sizes, no clipped glyphs and no overlap. Review residual
OCR candidates; identifiers can remain. Zero OCR detections prove no completeness.
Use the enlarged source title block as the field inventory, including vertical
headings; compare corresponding target cells, not just detected-record crops.
Missing glyphs are content loss. Apply validates font coverage before output;
the final render must still be checked after a font change because text can reflow.

Apply writes an incomplete template; fill only after actual review:

```json
{
  "candidate_sha256": "<exact candidate hash>",
  "all_pages_reviewed": false,
  "all_changed_regions_reviewed": false,
  "visible_foreign_descriptive_text": [],
  "text_overlap_failures": [],
  "line_or_graphic_damage": [],
  "notes": "Actual context review, OCR corrections and resolved findings."
}
```

Delivery requires both booleans true, all findings resolved and final QA passed.
A candidate change invalidates approval. Review cache binding includes source,
candidate, packet records, residual script and review format version;
missing/corrupt artifacts rebuild. Review format upgrades reuse the separately
versioned OCR cache and do not require another recognition pass.
The verifier validates the record contract, not the truth of semantic review.

Use one initial candidate and one repair batch as a soft efficiency target.
Report cold prepare (including supplement/crops), apply, review, cache hits and
full translation elapsed separately. Never claim a fresh translation speedup
from script replay or file-modification-time gaps.
