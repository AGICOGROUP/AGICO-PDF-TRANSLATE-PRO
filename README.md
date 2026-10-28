# AGICO-PDF-TRANSLATE-PRO

Professional PDF and static PNG/JPEG translation Skill with automatic input routing.

Version 2.0 keeps five independent execution adapters:

- **Native PDF:** ordinary selectable and mixed documents, with complete page context and source-bound translation packets.
- **Scan PDF:** preserve every page raster, clean local glyph regions and write selectable translations; no page reconstruction.
- **Bilingual PDF:** keep original content and add a separate target-language overlay.
- **Native-CAD PDF:** replace drawing text while preserving vectors and reviewed cell/label structure.
- **Static PNG/JPEG:** preserve source size, format, alpha and non-text artwork, with format-aware final-image evidence.

Shared utilities provide visible-content routing, bidirectional cement terminology 2.0 lookup and optional timing. Model/configuration-bound OCR checkpoints, explicit visual-transcription preparation, atomic image publication and exact JPEG composition evidence improve recovery without weakening source coverage or real review requirements.

The root `SKILL.md` is the single entry point. It routes images to `formats/image/` and classifies PDFs before invoking exactly one adapter under `formats/pdf/`.
