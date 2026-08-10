# AGICO-PDF-TRANSLATE-PRO

Professional PDF translation Skill with automatic PDF-type routing.

It supports three independent workflows:

- Native-text and mixed PDFs: preserves selectable/copyable text while separately translating text embedded in images.
- Scan-only and image-only PDFs: translates page-image text while preserving non-text pixels, icons, diagrams, colors, and layout.
- Bilingual overlay: keeps the original text visible and adds Chinese translation beside it in the surrounding whitespace, producing a dual-language PDF.

The root `SKILL.md` is the single entry point. It classifies the input PDF and invokes exactly one adapter under `formats/pdf/`.
