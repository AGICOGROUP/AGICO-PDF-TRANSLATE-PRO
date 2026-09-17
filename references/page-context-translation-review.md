# Page-context translation and accuracy review

This instruction applies to the image, scan PDF, and native/mixed PDF adapters.
It supplements each adapter's existing translation-integrity check; it does not
invoke another adapter's verifier or add a separate rendering/OCR pipeline.

## Translate with page context

For cement/process/equipment terminology, consult the user-revised
[Chinese-English table](../formats/pdf/scan/references/cement-terminology.md)
before translating relevant passages in every adapter, including bilingual,
native-CAD and standalone images. Native PDF bundles the same table locally.
From the repository root, use `python formats/pdf/scan/scripts/glossary_lookup.py
scan "<Chinese source passage>"` or `lookup "<Chinese term>"`. The helper indexes
Chinese only: for English source, search the table's English column directly;
for other languages, establish the concept from source context, then consult
the corresponding Chinese-English entry. A missing Chinese match does not prove
that an English or other-language term is absent.

Prefer the table's equivalent over model wording when the full phrase and
engineering sense match. Consider returned alternatives in context; longest
Chinese matches and the last duplicate are lookup defaults, not proof that
every later entry has the same sense. For other target languages use the matched
concept consistently. Do not force a conflicting sense or invent a table match.
Reuse the relevant matches within the job and include them with translation
batches. In the existing semantic review, note the matched terms used and any
context-based departures; review their consistency without adding another gate.

Before translating any region, read the complete source page in reading order.
Include its section heading, paragraphs, lists, table headers and cells, captions,
footnotes, diagram labels, and embedded-image text. Treat one static image as
one page. For native/mixed pages combine native text and image-label inventories
in this context, retaining their original IDs and layout containers.

OCR boxes and native text objects are placement units, not independent semantic
units. Reconstruct sentences split across lines or boxes before translating.
Interpret a short term using its sentence, section, table heading, unit, or
diagram relationship. Supply the ordered page text and document glossary with
each translation batch; if the page must be split, carry the page context into
every batch. Use adjacent-page text when a sentence, table, or reference continues
across the page boundary. Preserve one-to-one output IDs without summarizing.

For scan and image inputs, compare OCR with the source pixels, especially for
negation, decimal points, inequality signs, numbers, units, and technical words.
Context may suggest an OCR correction but is not proof: confirm it against the
source and record the original OCR and correction. Do not invent unreadable
content or silently preserve readable prose to avoid translating it.

## Review every page after translation

After the translations are populated, perform a separate source-to-target
accuracy pass over every selected page, not just samples or anomaly pages.
Review the page as a coherent whole and account for every readable source item,
including material OCR failed to detect. Compare against the original page,
not solely the extracted OCR. Use existing source renders and the final candidate
render/text; no additional routine OCR or full-document render is required.

For each page check:

- Meaning: subjects, actions, technical concepts, negation, conditions,
  exceptions, obligations, and causal relationships are preserved.
- Context: sentences split between boxes read coherently; pronouns, headings,
  table cells, captions, and diagram labels have the correct referents.
- Completeness: no omitted, duplicated, fabricated, or untranslated readable
  content; preserved identifiers have a reason. Include headers and footers.
- Terminology and values: consistent glossary meanings, exact quantities,
  tolerances, signs, units, formulas, model codes, and standard references.
- Final output: the rendered wording matches the reviewed translation; reflow
  or shortening has not changed meaning or separated a value from its label.

Correct findings, rebuild only through the adapter's official workflow, and
re-review affected pages plus any pages affected by a terminology change.
An unresolved accuracy issue blocks delivery as a completed translation.
Apply the shared delivery policy's two-attempt limit to blurry source content.
Locate and report regions still illegible after those attempts, without guessing
or retrying during review. These accepted source limitations do not constitute
unresolved translation defects; readable omissions still do.

## Adapter-owned review record

Save `translation-review.json` in the job's review directory (or existing job
root). Bind it to the immutable source and exact final output SHA-256. Record
one entry for each selected source page; images use source page 1. A page with
no text requires a source-based `no_readable_text` reason, not an invented review.
Keep the image adapter's existing no-text early-exit behavior.

Example structure (replace examples with actual reviewed evidence):

```json
{
  "source_sha256": "<source SHA-256>",
  "candidate_sha256": "<final output SHA-256>",
  "adapter": "scan",
  "selected_source_pages": [1],
  "pages": [{
    "source_page": 1,
    "status": "passed",
    "reviewed_source_ids": ["p01-l001", "p01-l002"],
    "context_checked": "Both fragments form the manufacturing requirement under section II.4.",
    "corrections": [],
    "unresolved_issues": []
  }]
}
```

Record accepted illegible regions in a per-page `source_limitations` list with
source IDs or location, both attempted inspections and the reason reading remains
unreliable. This is descriptive review evidence, not a new automated gate. Keep
their IDs in reviewed coverage and use the adapter's existing preservation action
where an inventory item exists. Do not put accepted source limitations into
`unresolved_issues`; that field retains actual unresolved translation defects.
A page may pass only after its remaining readable content and layout are reviewed.

Corrections record source IDs or source location, original OCR when relevant,
old translation, corrected translation, and the source-based reason. Missing
OCR labels enter the adapter's source inventory with IDs, located glyph geometry
and translation ownership before the manifest is finalized. For raster replacement
include their source cleanup; for additive output preserve source pixels.
Labels inside retained artwork still need
located local edit evidence. Adding meaning to a neighboring translation without
the appropriate ownership leaves the original omission unresolved. This distinction
does not change standalone-image rules. Record actual review
only: do not prefill every page as passed from block counts, successful builds,
OCR confidence, or a visual-review boolean. Verify page coverage, current hashes,
and absence of unresolved findings before declaring completion.

This is a required agent semantic review. Existing automated PDF/image checks
do not establish translation accuracy and must not be described as doing so.
