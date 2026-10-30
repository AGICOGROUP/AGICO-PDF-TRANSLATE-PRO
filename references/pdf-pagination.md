# PDF pagination when translation expands

Preserve original pagination by default. When a complete translation expands
(for example Chinese to English), first wrap within the correct paragraph/cell
and use verified available space. If it still cannot fit at a readable,
source-related role size, necessary continuation pages are authorized without
asking again. Prefer this to excessive shrinking, overlap, clipping or omissions.
Do not add pages when the content fits, or to repair incorrect extraction boxes.
This permission applies to PDFs, not standalone PNG/JPEG images.

## Preserve formatting while allowing flow

- Keep page size, orientation, margins, columns, fonts and role sizes, emphasis,
  colors, spacing, alignment, table borders/column widths and header/footer style.
  Only the content positions and page breaks required by the overflow may change.
- Insert a continuation immediately after its owning content. Keep paragraph/list
  order and numbering; keep a heading with following text, a figure with its
  caption and table cells with their row. Split tables between rows and repeat
  the existing column headings in the same style. Do not invent headings or text.
- Preserve artwork, image proportions, vector connections, signatures and seals.
  Do not stretch a scan, redraw engineering geometry or reconstruct a scan page.
  Keep original raster bases; any continuation must preserve content ownership
  without duplicating the original body, title block, signature or seal. Drawing
  sheets and inseparable diagrams stay intact; a translated note may continue on
  a same-format page only when its source association remains unambiguous.
- Update displayed running page numbers, totals, TOC page references, bookmarks
  and internal destinations where present. Preserve printed drawing/document IDs,
  clause numbers and source-sheet identifiers; they are not running page numbers.

## Evidence and current execution boundary

Record why overflow required new pages, the original/final page counts, and an
ordered source-to-output page/content mapping in the job review. Every original
content unit must appear exactly once, except repeated table headings or ordinary
running headers. Verify target selectability and complete meaning across breaks.
Render and compare every affected page, including continuations and changed page
references. Review unchanged pages using their bound evidence.

Existing fixed-page builders/verifiers do not acquire pagination support from
this policy. Use a pagination-capable path inside the selected adapter only when
it records the mapping and validates the invariants above. Before using one, extend
its builder and verification together if needed; never bypass a page-count gate,
forge source pages or switch adapters merely to obtain a passing report. For
unchanged pagination, existing equal-page-count checks remain in force. Until a
changed-page candidate has this verification, keep it unverified and report the
implementation limitation accurately.
