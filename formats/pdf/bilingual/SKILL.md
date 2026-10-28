---
name: PDF-TRANSLATE-PRO-BILINGUAL
description: Add requested target-language translations beside original text in native/mixed PDFs while retaining source text and vectors. Use only the PDF router's bilingual result.
---

# Bilingual PDF overlay

Use the router's bilingual result; scan-only additive output stays in scan.
A named single-language result means replacement unless the user also affirmatively
asks to keep/add the original language. Drawings default to bilingual only for
unspecified `auto` output. Apply [shared translation review](../../../references/page-context-translation-review.md)
and [delivery policy](../../../references/delivery-policy.md).

## Inventory and translate

From the repository root:

```powershell
python formats/pdf/bilingual/scripts/inspect_layout.py <original.pdf> --output <job>/layout.json
```

Compare the full source pages with native spans. Inventory outlined/raster labels
within this same workflow when native extraction is incomplete; do not flatten
vectors or treat sparse native text as full label coverage. Confirm every readable
heading, note, cell and diagram label, including actual requested language pairs.
The PDF router's `already_bilingual_complete` decision alone permits byte-identical
original delivery for a fully paired matching bilingual drawing.

Translate coherent labels/clauses with whole-page context and cement terminology
2.0. Preserve identifiers, numbers, units and standards; localize their qualifiers.
Read [workflow and packet schema](references/workflow.md) for placement records.
Use native span IDs or reviewed page coordinates for outline/image text. Keep
source text visible/selectable, and target text in a separate embedded font layer.

## Place in readable nearby whitespace

Try below/above the source block, then beside it, then a nearby table group or
linked margin notes when local space is truly unavailable. Preserve source links,
reading order and source rotation. Text-only gaps can contain rules or leaders;
inspect artwork before approval. Keep distinct table fields and a whole paragraph
at one size. Wrap at a source-related role size, then reduce only for a real local
fit/readability constraint; 5pt is an exception floor, not a default target.

```powershell
python formats/pdf/bilingual/scripts/bilingual_overlay.py <original.pdf> --translations <job>/translations.json --output <job>/translated.pdf
```

Check `--help` for the actual positional/named interface before invocation.
Source counts, binding coordinates and a successful save do not establish complete
semantic coverage. Keep original page count, page boxes, rotation and artwork.
No source cleanup is authorized in this additive branch.

## Acceptance

Render selected output pages once and compare with source. Inspect changed
regions and any anomalies; repair locally. Read [workflow acceptance](references/workflow.md)
for this adapter's full review/provenance fields. Completed delivery needs the
PDF-TRANSLATE-PRO-BILINGUAL build report bound to source, translations and output,
complete source-label mapping and actual semantic/visual review. Confirm target
font embedding and selectable glyphs, no missing labels, text obstruction or
structural damage. Cosmetic size/alignment differences are warnings.

At the shared budget limit, a useful unresolved candidate may be a labelled
preview with located defects and unchanged failed/unverified evidence.
