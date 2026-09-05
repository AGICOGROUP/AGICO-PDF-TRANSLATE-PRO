# Manifest contract

## Orientation and source mapping

Copy each OCR line's `quad` and cardinal `rotation` from the extraction report.
Every translated block inherits the rotation of its assigned source line; a
nonzero rotation may not be omitted or changed. In a `blank_panel`, one
translation maps to exactly one source-line ID. Summary text cannot satisfy
several source labels.

The final-gate word-overlap check reads rotated replacement blocks as
full-column boxes. Keep each rotated block's `max_font` at or below the
horizontal gap between its box and the nearest other rotated block on the same
page; tighter spacing is reported as a word-overlap failure even when nothing
visually collides.

`below` and `right` placements must remain within 3% of the page diagonal from
their source anchor. A `blank_panel` additionally requires
`companion_kind: table|title_block|legend` and a four-value
`companion_anchor_box` containing the assigned source label. Its target box
must be directly adjacent to that structural anchor under the same distance
limit.

Copy page geometry and `source_lines` from `extraction-report.json`; do not renumber source-line IDs.

## Typography roles

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

A single-line block whose source box is too thin to hold the role's minimum
font (usable height `(box_height_px + 2) × 72 / dpi − 2` under ~5.75 pt) fails
the build. Widen the cleanup geometry across surrounding whitespace or merge
the line into an adjacent block of the same role so the text area gains height.

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
`source_box`, when present, must equal `original_box`. Both the original and
target boxes must avoid all translated/preserved text blocks because this
fallback does not transform text coordinates with the image.

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
