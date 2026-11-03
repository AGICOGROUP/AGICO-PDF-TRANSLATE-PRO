# Manifest contract

This is the `preserve_raster` builder contract for every selected scan page,
including prose, tables, additive output and the standalone-image carrier.
The manifest contains all selected pages and their source lines/blocks,
retaining original source page numbers. Record `preserve_raster` throughout
`page-plan.json`.

Record `source_language` as the visually established source language code (such
as `zh`, `en`, `es`, `ru`, `fr` or `pt`), independently from `target_language`.
The compact compiler retains it and rejects conflicting extraction/decision
bindings. Legacy manifests without it remain valid but use conservative residue
checking. Mixed source passages must still be fully inventoried and translated.

Each page may carry `ocr_review_candidates` copied from extraction. These are
suspected omissions, not accepted source lines: `id`, pixel `box`, `reason`,
`ocr_attempts`, and optional rejected `text`/`score`/`quad`. Keep the metadata in
the manifest and draft context. Do not translate rejected guesses automatically.
Verified text enters `source_lines` through the normal supplement contract;
candidate IDs are additionally accounted for in the existing semantic review's
`reviewed_source_ids`. Record non-text decisions or genuine source limitations
with visual reasons. No candidate record authorizes cleanup on its own.

## Original background and output size

Keep `source` bound to the actual immutable PDF and `source_sha256` correct. The
builder verifies this file even during cached repairs, preserves encoded scan
pages with local cleanup patches, and removes stale hidden OCR before adding
selectable target text. Do not point `source` at a render or omit it to bypass
preservation. Painted native glyphs, geometry changes or raster-layout adjustments
use the measured lossless render fallback. No new manifest fields are required.
The build report owns `background_encoding_counts`, `builder_implementation_sha256`,
`size_evidence` and `delivery_ready`. The optional CLI `--max-output-mib` binds the
known channel limit without changing translation or geometry inputs.

## Orientation and source mapping

Copy each OCR line's `quad` and cardinal `rotation` from the extraction report.
`rotation` is the clockwise reading direction in source-render pixels (x right,
y down): 0 reads right, 90 down, 180 left, 270 up. The PDF builder converts this
to a counterclockwise PDF angle by negating it; do not compensate in the manifest.
OCR box geometry alone cannot distinguish upright from upside-down text.
Confirm uncertain directions against the source render; record any correction
on the manifest source line with its visual evidence and propagate it to its block,
leaving the extraction cache unchanged. Every translated block inherits the
confirmed source-line rotation; never assign one angle to all labels merely
because the page is sideways. In a `blank_panel`, one
translation maps to exactly one source-line ID. Summary text cannot satisfy
several source labels.

`below` and `right` placements must remain within 3% of the page diagonal from
their source anchor. A `blank_panel` additionally requires
`companion_kind: table|title_block|legend` and a four-value
`companion_anchor_box` containing the assigned source label. Its target box
must be directly adjacent to that structural anchor under the same distance
limit.

Copy page geometry and `source_lines` from `extraction-report.json`; do not
renumber source-line IDs. Visually confirmed missing lines extend that inventory,
without modifying the cached extraction report.

### Located supplements for replacement continuations

`register_source_supplements.py` accepts this JSON payload. Coordinates must come
from the manifest's exact source render, not a scaled screenshot. Each box is a
tight glyph envelope with the cleanup margin already included. The complete
`source` and `translation` replace the owner's passage; they are not appended.

```json
{
  "source_sha256": "<same source hash as the manifest>",
  "supplements": [{
    "block_id": "p01-body-01",
    "source": "Aumentar progresivamente hasta 6000 daN.",
    "translation": "逐步增至 6000 daN。",
    "source_lines": [{
      "id": "p01-visual-001", "page": 1, "rotation": 0,
      "text": "progresivamente hasta 6000 daN.",
      "box": [100, 585, 1480, 640]
    }]
  }]
}
```

The helper registers each new line with `origin: visual_supplement`, adds its ID
to the existing block and its box to `clean_boxes`, then validates and atomically
saves the manifest. Existing glyph cleanup stays separate; no union rectangle
is introduced. It rejects reused IDs, wrong pages/rotations, out-of-bounds boxes
and non-replacement owners. Do not reapply a saved patch. It does not infer text,
verify that boxes contain only glyphs, or mark a candidate reviewed. If the full
translation needs more space, adjust its target box/font through the normal fit
workflow without dropping content or expanding source cleanup.

## Typography roles

### Explicit prose continuations

Fixed pagination is unchanged unless the manifest supplies `pagination` and
explicit `segments` on overflowing plain-text replacement blocks. This path
supports prose and lists; segmented `table_cell`/`table_header` blocks and rich
text fail rather than attempting unverified complex-table pagination. Do not
enable it just because an extraction box is too tight. First use actual safe
space and a readable source-related role size.
Source bookmarks, named destinations and internal links also block this minimal
path until destination remapping is implemented; the builder never silently
drops them or treats a prose reference-review flag as a technical remapping.

Each segment contains `continuation_index` (`0` for the original output),
`translation`, and a target `box` in the owning source render's pixels. Segment
indices follow physical page order; ordered pieces may share a page when that
avoids unnecessary extra pages. Every piece has a reported segment index and is
independently checked for exactly one render. Concatenating strings, including spaces
and paragraph breaks, must equal the complete block `translation` exactly.
Source IDs and cleanup remain on the real source page and are assigned once.
The complete paragraph/list item keeps its role font settings across segments.

`pagination` requires an actual overflow `reason`, `continuations` with consecutive
one-based `index`, actual `source_page` and reviewed `body_box`, and a `page_numbers`
entry for every original/continued output. Number entries give `source_page`,
`continuation_index`, `text`, original-style pixel `box`, and optional `font_size`;
an actually unnumbered page uses `text: null` with its source-based `reason`.
The builder orders continuations immediately after their owner and reports
`output_page_mapping`; the verifier derives that mapping independently and checks
actual running-number glyphs at the planned output locations.

Continuation `repeat_regions` identify located `header`, `footer`, `table_header`
or an emptied prose `table_frame`. Their backgrounds come from the verified
clean source raster; current translated ordinary headers/footers are redrawn as
selectable text. Never copy body, logos, signatures or seals as repeated content.
An optional `target_box` may shift a repeated region at identical dimensions;
stretching fails. `repeat_blocks` may repeat only an existing ordinary
header/footer/warning title, with its explicit destination box. Repeated format
crop hashes are recorded in `continuation_repeat_regions`.

When a complete *prose callout* moves after its preceding paragraph, an explicit
`moved_table_frames` record may remove its emptied original frame while retaining
the exact frame pixels on a declared continuation. It requires `source_page`,
`box`, `content_kind: prose_callout`, and a source-based `reason`; the same box
must be preserved as a continuation frame. Any intersecting primary-page text or
protected graphic blocks the move. This is not a route for engineering drawings,
complex tables, signatures or page reconstruction.

`reference_updates` has `status: applied|not_present` and a specific `reason`.
Update actual TOC/running-number/internal references before claiming `applied`;
do not silently retain old references. A partial-page repair prototype cannot
establish the correctness of a later whole-document page-number plan.

The existing hash-bound translation review additionally needs `pagination_review`
with the exact `output_page_mapping`, every `reviewed_output_pages` in physical
order, and actual `content_order_checked`, `running_numbers_and_references_checked`
and `format_and_artwork_checked` findings. All added pages must be rendered and
reviewed. Equal-page-count gates remain authoritative for unchanged manifests.

Use semantic roles to keep the three visible text tiers independent on each
page:

- Titles: `title`, `heading`, `subheading` (normally bold or larger).
- Body: `body`, `list_item`, `warning_body` (regular, dominant reading size).
- Annotation: `caption` for drawing labels, callouts, and other less frequent
  small text (regular and smaller than body).

Use `header`, `footer`, `table_header`, and `table_cell` for their structural
regions. They are fitted independently. Do not use `caption` solely because an
OCR box is small; classify from the source text's semantic and visual function.

```json
{
  "source": "C:/docs/input.pdf",
  "source_sha256": "...",
  "target_language": "es",
  "selected_pages": [1],
  "pages": [{
    "source_page": 1,
    "width_pt": 595.28,
    "height_pt": 841.89,
    "render_path": "C:/job/extract/source-pages-400dpi/source-page-01.png",
    "pixel_width": 3307,
    "pixel_height": 4678,
    "dpi": 400,
    "vector_lines": [{"points": [100, 220, 800, 220], "width": 0.45, "color": [0, 0, 0]}]
  }],
  "source_lines": [{"id": "p01-l001", "page": 1, "box": [100, 100, 300, 140], "text": "原文", "score": 0.97}],
  "blocks": [{
    "id": "p01-title",
    "page": 1,
    "source_line_ids": ["p01-l001"],
    "source": "原文",
    "translation": "Professional target text",
    "role": "title",
    "status": "translated",
    "action": "replace",
    "box": [100, 95, 600, 160],
    "clean_box": [98, 98, 305, 144],
    "background": "sample",
    "bold": true,
    "align": "left",
    "valign": "top",
    "color": [0, 0, 0],
    "max_font": 18,
    "min_font": 11
  }]
}
```

For additive bilingual output, use this block shape:

```json
{
  "id": "p01-label-es",
  "page": 1,
  "source_line_ids": ["p01-l001"],
  "source": "袋式收尘器",
  "translation": "Filtro de mangas",
  "role": "diagram_label",
  "status": "translated",
  "action": "add_bilingual",
  "box": [320, 160, 560, 205],
  "source_preserved": true,
  "placement": "below",
  "color": [0, 0.31, 0.55],
  "max_font": 10,
  "min_font": 7
}
```

`add_bilingual` requires top-level `target_language`, forbids `clean_box`, and
accepts only `below`, `right`, or `blank_panel`. Its target box must not overlap
any OCR source line or protected graphic box.

Coordinates are in source-render pixels with origin at top left. Colors are RGB floats from 0 to 1 for text/vector lines; cleanup backgrounds use integer RGB 0–255 or `sample`.

For a replacement region made from several OCR lines, use `clean_boxes` instead
of a broad union `clean_box`:

```json
{
  "id": "p03-body-02",
  "page": 3,
  "source_line_ids": ["p03-l014", "p03-l015", "p03-l016"],
  "source": "First line second line third line.",
  "translation": "完整的区域级译文。",
  "role": "body",
  "status": "translated",
  "action": "replace",
  "box": [100, 500, 1500, 760],
  "clean_boxes": [[100, 500, 1450, 555], [100, 585, 1480, 640], [100, 670, 900, 725]],
  "background": "sample",
  "max_font": 10,
  "min_font": 7
}
```

`clean_box` and `clean_boxes` are mutually exclusive. Every `clean_boxes` entry
must contain four coordinates and tightly cover source glyphs only. The builder
uses their union solely as approved pixel-change evidence; intervening rules,
leaders, signatures, and whitespace remain untouched.
The compact compiler adds a DPI-scaled cleanup margin to OCR glyph boxes while
protecting detected rules and registered source-preservation regions. Explicit
`clean_boxes` and visually authored supplements remain unchanged. Preserved source
pixels are restored after cleanup and excluded from local PDF patch overlays, so
neighboring numeric/code ink is not needlessly re-sampled.

Only for a visually confirmed black caption crossed by a colored signature,
`preserve_colored_ink: true` retains its source colored strokes, including cleanup
boundary pixels, while clearing the black caption. It is a boolean, included in
cache identity, and defaults off. Do not enable it for ordinary colored source
text. Keep the complete original signed identity plus an adjacent translation if
the original content cannot be safely separated.

`preserve_confirm` blocks must use `action: preserve`, keep a nonblank `source`, and state the reason in `translation` (for example `Trademark; preserve exactly`). A manifest is invalid if any source-line ID is missing, duplicated, or assigned to an unknown block.

Use `status: bilingual_complete` with `action: preserve` only for a complete
Chinese/target-language diagram region. `bilingual_evidence` must contain
`clear_source_label_count`, the equal `matched_bilingual_pair_count`,
`unmatched_source_label_count: 0`, and a 64-character
`source_region_sha256`.

Page `layout_adjustments` use source-render pixel coordinates and require
`original_box`, `target_box`, `scale`, `trigger: text_does_not_fit`,
`fit_failure: true`, and `approved_background_regions`. Target boxes must stay
on the same page, preserve aspect ratio, and avoid every `protected_box`.
`source_box`, when present, must equal `original_box`. By default both original
and target avoid all translated/preserved text because image movement does not
transform text coordinates. Explicit `vacate_for_text: true` allows translated
prose to use the vacated image area, while original-image checks protect real
source cleanup/preservation regions and destination checks protect every target
text box, including continuation segments. Image aspect ratio remains unchanged.

For a reviewed **plain prose callout only**, `prose_frame_reflows` may give
`kind: "prose_callout"`, a specific `reason`, integer `original_box`/`target_box`,
`header_height`, and `border_width` (1–8 source pixels). Width stays identical;
height may only grow. After source prose is cleared, the builder requires a blank
white interior and blank destination outside the old frame; remaining text,
symbols or graphics block it. It copies original header/bottom strips and tiles
original side-border pixels without resampling. Translate the header at the
moved position. Complex tables and engineering diagrams are unsupported. This
uses the existing measured lossless fallback; ordinary pages keep original
encoded backgrounds. Prove safe space insufficient before adding continuations.

Use `vector_lines` only when a cleanup box necessarily removed a known straight segment. Coordinates must come from visible anchors on both sides; never guess hidden geometry.

## Rich text and exact source-icon reuse

Use `rich_lines` only when a block needs mixed colors/emphasis or an icon lies inside an unavoidable cleanup area. Each line is an ordered list of runs. Text runs support `color` and `bold`; source-crop runs require an in-bounds `source_box` and non-empty `alt` description.

```json
{
  "id": "p07-command",
  "page": 7,
  "source_line_ids": ["p07-l014"],
  "source": "按图标，然后选择确认",
  "translation": "Press , then select [OK]",
  "role": "list_item",
  "status": "translated",
  "action": "replace",
  "box": [420, 630, 1760, 720],
  "clean_box": [418, 632, 1110, 710],
  "background": [255, 255, 255],
  "min_font": 7,
  "max_font": 10,
  "rich_lines": [[
    {"type": "text", "text": "Press ", "color": [0, 0, 0]},
    {"type": "source_crop", "source_box": [690, 642, 728, 680], "alt": "original menu icon"},
    {"type": "text", "text": ", then select [OK]", "color": [1, 0.35, 0], "bold": true}
  ]]
}
```

Coordinates for `source_box` use the same top-left source-render pixel system. The crop is taken from the immutable `render_path`, not from the cleaned base. Keep its box tight around the original icon. The validator rejects out-of-page crops, blank alt text, unknown run types, invalid RGB values, and rich text that does not match `translation` after normalization.
