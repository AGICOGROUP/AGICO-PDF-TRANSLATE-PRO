# Scan PDF page-region translation and layout design

## Objective

Improve scan-only PDF translation quality without adding OCR passes, full-page
renders, or document-specific quality gates. Replace line-by-line translation
layout with page-aware semantic regions so body text has consistent typography,
complete source cleanup, and sufficient context for professional translation.

## Scope

- Change only `formats/pdf/scan/`.
- Preserve the current extraction report and manifest contracts.
- Keep native PDF, bilingual overlay, and standalone-image adapters isolated.
- Keep the official build and verification workflow unchanged.
- Remain backward compatible with existing line-level manifests.

## Data flow

The scan adapter will use this flow:

```text
400-DPI dual-scale OCR lines
→ page structure classification
→ page-aware semantic regions
→ page-context translation
→ region-level replacement manifest
→ page-level typography resolution
→ official build, render, and verification
```

Translation operates with the complete ordered page text as context. Output
still maps every source-line ID exactly once, but one translated block may own
several source lines. Rendering remains region-based rather than using one
unstructured page-wide text box.

## Region grouping

Enhance `scripts/draft_blocks.py` to classify and group OCR lines using existing
geometry and text only. It must not invoke OCR again.

Each horizontal source line is classified as one of:

- page header;
- major or minor title;
- body or list text;
- table-like content;
- drawing or isolated label;
- page footer.

Body lines may join one region only when they share rotation, column, reading
order, compatible indentation, and a bounded vertical gap. Sentence-ending
punctuation and numbered headings influence boundaries. Lines in separate
columns must never join. Table-like rows, sparse labels, rotated text, headers,
and footers remain separate unless a safe same-structure grouping is proven.

The normal target for prose pages is three to eight regions, but correctness is
more important than meeting that count. Engineering drawings and dense tables
may legitimately produce more regions.

Each draft region records:

- ordered `line_ids`;
- joined source text;
- union text box;
- per-line glyph boxes for cleanup;
- rotation;
- role;
- minimum OCR confidence;
- grouping reason and confidence.

## Cleanup geometry

The target-language `box` is the region union box. Replacement cleanup remains
glyph-local: the region stores the individual source-line cleanup boxes rather
than replacing the entire union rectangle. This prevents broad white bands and
protects rules, signatures, leaders, and drawing geometry while still removing
every assigned source glyph.

The manifest contract will accept an optional `clean_boxes` list for replacement
blocks. Existing singular `clean_box` remains supported. A block may define one
or the other, never both. The builder applies every approved cleanup box and
includes all of them in its pixel-change evidence.

## Page-context translation

The draft output provides one ordered page payload containing all region IDs and
source texts. A translator processes the page in one request or local inference
batch and returns one translation per region ID. It must preserve numbering,
units, models, standards, names, and repeated terminology.

Low-confidence OCR is not silently converted into fluent but invented target
text. A region with damaged text is either reconstructed from neighboring lines,
translated with an explicit reviewed correction, or assigned `preserve_confirm`
with a supported identifier/artwork reason.

## Typography policy

`scripts/build_scan.py` continues to resolve typography once per page. The
policy groups blocks into major title, minor title, body, table, header, footer,
and special labels.

- Every body block on a page uses one font, size, weight, and leading ratio.
- Every title group uses one consistent style.
- Header, footer, table, and drawing-label sizes do not influence body text.
- The initial group size is derived from the median source-line height and role
  defaults, clamped to a readable range.
- If one body block cannot fit, the entire page body group reduces together to
  the largest common fitting size.
- A single body block may not shrink independently.
- If the common size falls below the readable floor, the build stops with a
  fit error instead of producing tiny text.

Existing manifests continue to build under the same group policy.

## Failure handling

- Ambiguous grouping produces smaller safe regions, never a speculative merge.
- Cross-column, cross-rotation, table-to-body, and header-to-body merges are
  rejected deterministically.
- Complete translation that does not fit stops the build.
- Unsupported cleanup geometry fails manifest validation.
- No fallback may add an OCR pass, broad cleanup rectangle, summary translation,
  or another full-document render.

## Testing

Use red-green-refactor for every behavior change.

Unit fixtures will cover:

- continuous body lines joining one region;
- headings remaining separate from body text;
- numbered list continuation grouping;
- two columns never merging;
- table-like rows remaining separate from prose;
- page headers and footers remaining isolated;
- rotated labels remaining independent;
- region source-line IDs retaining exact one-time coverage;
- multi-box cleanup changing only approved glyph rectangles;
- all page body blocks resolving to one common size;
- dense body content reducing the whole body group together;
- below-floor content producing a fit error;
- legacy single-`clean_box` manifests remaining valid.

Run the scan tests first, then the full PDF adapter test suite and the root
independent quality gates.

## Success criteria

- Prose pages produce a small set of coherent page regions instead of one block
  per OCR line.
- Every OCR source-line ID remains assigned exactly once.
- Body typography is uniform within each page.
- Source text is removed without broad bands or changes outside approved glyph
  boxes.
- Tables, drawings, headers, footers, rotations, signatures, and rules remain
  structurally intact.
- Existing manifests and workflows continue to work.
- No additional OCR pass, full-document render, or document-specific final gate
  is introduced.
