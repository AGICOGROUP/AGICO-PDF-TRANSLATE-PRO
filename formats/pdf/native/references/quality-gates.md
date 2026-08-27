# Native PDF final gates

These six gates run once at the end of the native/mixed adapter. Do not invoke
scan-PDF or standalone-image gates.

1. Translation integrity: 100% manifest coverage, consistent glossary terms,
   preserved numbers/models/units, and zero unexpected source-language residue.
2. Text validity: translated text is selectable/copyable, fonts are embedded,
   native pages are not flattened, and hidden source text is absent.
3. Document integrity: page count, boxes, rotation, reading order, tables,
   images, links, and key document structure match the source.
4. Layout safety: automated checks report zero overlap, clipping, container
   escape, missing glyph, unreadably small text, or text/image collision.
5. Non-text protection: graphics and images remain intact. Pixel, protected
   line, and image-difference checks apply only to images actually modified by
   this adapter.
6. Final render: render the exact candidate once, automatically check all pages,
   and manually inspect only changed regions and anomaly pages.

The final report must bind the candidate SHA-256 and aggregate the evidence for
these six gates. Do not require per-page screenshots, review of unchanged image
XObjects, or repeated full-document rendering.
