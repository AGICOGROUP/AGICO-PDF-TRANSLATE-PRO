# Native-CAD packet and cover contract

For a native phrase split across records, keep every ID and source unchanged.
Choose one leader with `status: translated`, the complete fluent translation
and a reviewed `layout_box` for that phrase. Set the other native members to
`status: merged`, `merged_into: <leader-id>`, empty translation and a
`review_note` explaining the shared phrase. All members must share page and
rotation. Apply removes their individual source glyphs and draws the leader
once; if its translation cannot fit, it preserves the whole group's source.
Group by actual sentence/cell and safe whitespace, not by proximity alone;
do not absorb neighboring dimensions or cross table borders. This mechanism
does not authorize outline covers. Never mark native words preserved merely
because the target word order differs. Review the assembled Chinese sentence
in place; isolated legible word crops do not establish semantic correctness.

placement_proposal supplies cell_bbox, inset layout_box, all members and
source_overflows_cell. It is a proposal, not approval:

- For a reviewed text-only description cell, use its inset box for layout.
  Native single fields start with the prepared neighbour-reserving box when
  it contains their source bounds; the packet records this box for review.
  Overlapping OCR duplicates must not reduce that field to its glyph bounds.
  When both languages touch, replace the complete description once. Never
  estimate a script boundary from character counts: it clips English letters.
- Inspect all members first. Identifiers, numbers and separate fields stay
  distinct; never let several records independently cover the same cell.
  Shared cells now propose separate member layout boxes; overlapping OCR still
  requires reconciliation. For native company names, also set layout_box inside
  the actual title cell and clear of the logo, rather than accepting a source
  bounding box that protrudes outside the page.
- Keep covers inside borders. If source_overflows_cell is true, inspect the
  actual protruding glyphs once and preserve neighboring data and structures.
- With a genuine gap and an accurate existing target, an outline record may
  use status: cover_only, target_present and review_note. Cover only the source;
  do not insert a duplicate translation.
- For free labels, inspect OCR boxes and safe whitespace. Set rotation from
  source pixels (0/90/180/270); OCR zero is only a proposal.

For every outline cover, record actual pixel inspection in cover_review:

```json
{"approved":true,"text_only":true,"white_background":true,
 "source_text_paths":true,"restore_conflicting_paths":true,
 "note":"Actual inspected source label and surrounding structures."}
```

Packet field contract, which `apply` enforces by rejection:

- `cover_boxes` is a list of boxes (`[[x0,y0,x1,y1]]`), never one flat box.
- `source_text_paths` and `restore_conflicting_paths` belong **inside**
  `cover_review`; a copy at the record top level is read as absent.
- CAD glyphs are painted as many small filled paths, so any outline cover reports
  `filled_region`/`curve` conflicts. Without `source_text_paths` those own-glyph
  strokes count as real damage and `apply` stops with `unsafe_outline_regions`.
- Only inventory records with `status: "pending"` need a packet decision;
  `protected` records are never covered and need none.
- Every `cover_boxes` entry must intersect its own source bbox, so a
  conflict-free dummy anchor elsewhere on the page is rejected.
- `restore_conflicting_paths` replays paths on top of the page and cannot
  reproduce source z-order: a line hidden in the source under a later wide
  light-coloured stroke reappears as a solid bar once restored. Before
  restoring, check each queued path against its own colour and against the
  source render; when a dark path is hidden in the source, move that record's
  cover box off its ink instead of restoring it. Replaying a near-white stroke
  is harmless, so judge a path by its colour, never by the ink count inside its
  bounding box — that box also contains the text just inserted for it.

These are agent review fields, not a request for user permission. Never approve
from OCR confidence or geometry alone. source_text_paths is only for inspected
font outlines, never to suppress symbols. restore_conflicting_paths requires
reviewing the actual paths; do not restore old glyphs, and expect a restored path
to come back with its own recorded colour and width. Use cover_boxes and
layout_box for reviewed adjustments. Visual replacement is not secure deletion.
