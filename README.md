# AGICO-PDF-TRANSLATE-PRO

Professional PDF and static PNG/JPEG translation Skill with automatic input routing.

It supports three input types and one optional PDF output mode:

- Native-text and mixed PDFs: preserves selectable/copyable text while separately translating text embedded in images.
- Scan-only and image-only PDFs: translates page-image text while preserving non-text pixels, icons, diagrams, colors, and layout.
- Static PNG/JPEG images: reuses the scan workflow and returns the same image format at the same pixel dimensions.
- Optional bilingual PDF overlay: keeps the original text visible and adds Chinese translation beside it in the surrounding whitespace.

The root `SKILL.md` is the single entry point. It routes images to `formats/image/` and classifies PDFs before invoking exactly one adapter under `formats/pdf/`.
