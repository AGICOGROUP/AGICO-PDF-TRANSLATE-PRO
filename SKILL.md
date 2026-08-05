---
name: translate-pdf-professionally-auto
description: Use when professionally translating any PDF while preserving layout, selectable text, image text, graphics, tables, colors, and engineering structure. Automatically routes native/mixed PDFs and scan-only/image-only PDFs to separate specialized workflows.
---

# Professional PDF Translation Router

This repository supports PDF files only.

Read `formats/pdf/SKILL.md` completely, classify the uploaded PDF with its router, and invoke exactly one returned adapter:

- Native-text or mixed native/raster PDF: `formats/pdf/native/SKILL.md`
- Scan-only or image-only PDF: `formats/pdf/scan/SKILL.md`

Never merge the two adapter workflows and never route by filename or user wording alone.
