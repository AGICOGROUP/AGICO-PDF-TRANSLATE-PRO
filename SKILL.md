---
name: translate-documents-and-images-professionally
description: Use when translating PDFs or static PNG/JPEG images whose professional meaning, page layout, tables, graphics and selectable target text must be preserved.
---

# Professional Document and Image Translation Router

This repository supports PDF, PNG, JPG, and JPEG inputs.

Read `references/delivery-policy.md` for the three blocking requirements,
nonblocking cosmetic diagnostics, incremental review and 120-second-per-page
scan budget. Apply this shared acceptance policy in the selected adapter.

Choose exactly one adapter from the actual file format:

- PDF: read `formats/pdf/SKILL.md` completely and use its content-based router.
- Static PNG or JPEG image: read and follow `formats/image/SKILL.md`.

Reject unsupported formats, animated images, and multi-page image containers. Never merge adapter workflows. File format selects the top-level adapter; PDF content inspection selects the PDF sub-adapter.

Output mode follows the user's requested result, for every target language:

- “翻译为英文/中文”, “翻译成英文/中文”, “英文版/中文版” or another single
  target-language translation means `replace`: replace the source-language text
  with the target language, including on engineering drawings.
- “加上中文/英文/其他语言”, “添加翻译”, “做成双语版”, “变为双语版”,
  “保留原文”, “对照” or an affirmative request for a bilingual version means
  `bilingual`: retain the original language and add the requested target language.
  This explicit additive/bilingual intent takes precedence even when the same
  request also says “翻译为英文/中文”. Interpret negation normally: “不要双语版”
  is not an affirmative bilingual request.

Use `auto` only when neither intent is specified: ordinary documents replace text,
engineering drawings add bilingual text. Scan supports either mode; native-CAD
is specialized replacement for native/mixed engineering drawings. Determine
content with the router, not with the output-language wording.

If a drawing routed to bilingual mode is already a complete
Chinese-plus-one-foreign-language version, preserve the exact source and mark
the task completed only in bilingual mode. This shortcut never satisfies an
explicit monolingual request. Do not ask for redundant language confirmation.
