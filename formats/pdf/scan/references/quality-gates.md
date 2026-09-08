# Scan PDF final gates

The verifier requires the official scan builder identity and matching source,
manifest, and output hashes. It also rejects unassigned source lines and any
translation whose reading direction differs from its source, including
rotation internal to a raster page.
It rejects remote bilingual placements: direct labels must be near their source,
and companion panels must be adjacent to their declared table/title/legend
anchor so every correspondence is immediately traceable.

These gates run once at the end of the scan adapter. They do not inherit native
PDF or standalone-image gates.

## Visual-review evidence

Create this against the exact final PDF after the one final render:

```json
{
  "candidate_sha256": "<64-character SHA-256>",
  "all_pages_rendered": true,
  "reviewed_changed_regions": true,
  "reviewed_anomaly_pages": [],
  "text_overlap_failures": [],
  "clipping_failures": [],
  "untranslated_clear_labels": 0
}
```

`reviewed_anomaly_pages` lists every page flagged by automatic checks after it
has been reviewed. An empty list is valid when there were no anomalies.

## Seven final gates

1. OCR and translation coverage: every source-line ID is assigned exactly once
   and every required translated block is rendered.
2. Translation integrity: terminology, numbers, models, units, and meaningful
   colors are preserved; replacement mode has zero unexplained source-language
   residue and additive mode has no unmatched clear source label.
   Require page-by-page semantic accuracy review using
   `../../../../references/page-context-translation-review.md`. The adapter-owned
   `translation-review.json` must cover every selected page, bind current source
   and candidate hashes, and contain no unresolved issues. This agent review
   includes original source pixels and is not inferred from OCR/block coverage
   or the automated verifier's passing result.
3. Text-layer validity: added target text is extractable/selectable, uses
   embedded fonts, and contains no missing glyphs.
4. Page integrity: page count, order, dimensions, and orientation match the
   selected source pages.
5. Graphic integrity: automatic build evidence reports zero changes outside
   approved regions and exact-source provenance for restored icons/crops.
6. Layout safety: automatic and exception review reports zero overlap,
   clipping, below-minimum text, or protected-structure coverage. Page-level
   typography evidence must show one common fitted size for every title group,
   one for body, and one for annotation. Tables, headers, and footers use
   independent groups. When present together, title is larger than body and body
   is larger than annotation. Annotation fitting must not reduce body size.
7. Final render: render the completed PDF once, automatically check all pages,
   and manually inspect only changed regions and anomaly pages.

The verifier must bind review evidence to the exact candidate SHA-256. Any
output change invalidates the evidence. One gate may aggregate several cheap
automatic assertions; it must not trigger another adapter's workflow or a
second full-document render.
