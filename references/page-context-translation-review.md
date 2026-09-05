# Page-context translation and accuracy review

This instruction applies to the image, scan PDF, and native/mixed PDF adapters.
It supplements each adapter's existing translation-integrity check; it does not
invoke another adapter's verifier or add a separate rendering/OCR pipeline.

## Translate with page context

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
Unreadable source content must be located and explicitly reported, not guessed.

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

Corrections record source IDs or source location, original OCR when relevant,
old translation, corrected translation, and the source-based reason. Missing
OCR labels receive IDs before the manifest is finalized. Record actual review
only: do not prefill every page as passed from block counts, successful builds,
OCR confidence, or a visual-review boolean. Verify page coverage, current hashes,
and absence of unresolved findings before declaring completion.

This is a required agent semantic review. Existing automated PDF/image checks
do not establish translation accuracy and must not be described as doing so.
