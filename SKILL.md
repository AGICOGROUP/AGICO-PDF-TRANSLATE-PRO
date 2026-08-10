---
name: translate-pdf-professionally-auto
description: Use when professionally translating any PDF while preserving layout, selectable text, image text, graphics, tables, colors, and engineering structure. Automatically routes native/mixed PDFs and scan-only/image-only PDFs to separate specialized workflows. Also supports bilingual overlay mode that keeps the original text visible and adds Chinese translation beside it.
---

# Professional PDF Translation Router

This repository supports PDF files only.

Read `formats/pdf/SKILL.md` completely, classify the uploaded PDF with its router, and invoke exactly one returned adapter:

- Native-text or mixed native/raster PDF (replace source text with translation): `formats/pdf/native/SKILL.md`
- Scan-only or image-only PDF (replace page-image text with translation): `formats/pdf/scan/SKILL.md`
- Bilingual overlay (keep source text, add Chinese translation beside it): `formats/pdf/bilingual/SKILL.md`

Never merge adapter workflows and never route by filename or user wording alone.

**Replacement vs. bilingual overlay:** The native and scan adapters replace
source text with translation — the final document contains only the target
language. The bilingual overlay adapter preserves all source text unchanged and
adds translations in surrounding whitespace — the final document contains both
languages side by side. Choose based on what the user asks for: "translate
this PDF" → replacement; "keep the original and add translation" / "bilingual"
/ "双语版" / "中英对照" → bilingual overlay.
