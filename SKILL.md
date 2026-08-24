---
name: translate-documents-and-images-professionally
description: Use when professionally translating native-text PDFs, scan-only/image-only PDFs, or static PNG and JPEG images while preserving layout, text, graphics, tables, colors, and engineering structure. Routes each input to one specialized workflow and supports bilingual PDF overlay mode.
---

# Professional Document and Image Translation Router

This repository supports PDF, PNG, JPG, and JPEG inputs.

Choose exactly one adapter from the actual file format:

- PDF: read `formats/pdf/SKILL.md` completely and use its content-based router.
- Static PNG or JPEG image: read and follow `formats/image/SKILL.md`.

Reject unsupported formats, animated images, and multi-page image containers. Never merge adapter workflows. File format selects the top-level adapter; PDF content inspection selects the PDF sub-adapter.

**Replacement vs. bilingual overlay:** The native and scan adapters replace
source text with translation — the final document contains only the target
language. The bilingual overlay adapter preserves all source text unchanged and
adds translations in surrounding whitespace — the final document contains both
languages side by side. Choose based on what the user asks for: "translate
this PDF" → replacement; "keep the original and add translation" / "bilingual"
/ "双语版" / "中英对照" → bilingual overlay.
