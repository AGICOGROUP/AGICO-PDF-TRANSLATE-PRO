---
name: route-pdf-translation
description: Use when an uploaded PDF must be classified by content before professional translation, especially reports, native/mixed PDFs, scan-only PDFs, engineering drawings, bilingual drawings, or requests for bilingual overlay.
---

# Route PDF Translation

Classify PDF content as exactly one of `native-text`, `mixed`, or `scan-only`,
then select exactly one independent execution adapter. `native-cad` is not a
fourth content classification: it is the specialized adapter for the combined
condition `(native-text | mixed) + engineering-drawing + replace`. Never merge
adapter workflows.

1. Determine the output mode from the request:
   - `auto` for ordinary translation wording;
   - `replace` only when the user explicitly wants source text removed or
     replaced so only the translation remains;
   - `bilingual` when the user wants the original kept beside the translation.
2. Run `python formats/pdf/scripts/route_pdf_file.py <uploaded-file> --mode
   <auto|replace|bilingual>` from the repository root.
3. Stop if the report contains an `error` or returns a nonzero exit code.
4. If an `auto` or `bilingual` report returns
   `document_kind: engineering-drawing`, use its `translation_mode: add_bilingual`.
   Inventory all clear Chinese and foreign labels, save the five coverage
   counts in JSON, then run `python scripts/decide_drawing_translation.py
   --inventory-file <drawing-language-inventory.json>`. Continue automatically; never pause
   for language confirmation after processing starts.
5. If that decision is `already_bilingual_complete`, preserve the exact source
   PDF, mark the task complete, and skip translation. Require Chinese plus one
   other language, complete semantic pairing, and zero unmatched clear labels.
6. If the user wants the original text kept visible with Chinese translation
   added beside it (bilingual / dual-language / 双语版 / 中英对照), use
   `formats/pdf/bilingual/SKILL.md` regardless of the PDF type — as long as
   the PDF contains selectable native text (native-text or mixed).
7. Otherwise, read and follow only the returned `adapter`. Resolve its
   relative commands from that adapter's own directory:

| PDF classification | Adapter |
|---|---|
| Native selectable text | `formats/pdf/native/SKILL.md` |
| Mixed selectable text and raster/image text | `formats/pdf/native/SKILL.md` |
| Scan-only or image-only | `formats/pdf/scan/SKILL.md` |
| Bilingual overlay (keep original + add translation) | `formats/pdf/bilingual/SKILL.md` |
| Native/mixed engineering drawing + explicit replacement | `formats/pdf/native-cad/SKILL.md` |

For scan-only engineering drawings, use `formats/pdf/scan/SKILL.md`; never use
native-CAD on scan-only input. Native/mixed engineering drawings use bilingual
by default and native-CAD only for explicit replacement.

The native adapter rebuilds ordinary selectable documents. The native-CAD
adapter performs coordinate-bound replacement on engineering drawings. The scan
adapter treats each page as an image while preserving all non-text pixels and
graphics. The bilingual overlay adapter keeps all source text unchanged and
adds Chinese translations as a new text layer in surrounding whitespace.

Do not route by extension, filename, or user wording alone. Do not run more than one adapter on the same input.
