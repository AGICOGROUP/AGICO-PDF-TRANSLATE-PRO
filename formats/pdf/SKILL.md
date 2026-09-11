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
   - `bilingual` for “加上中文/英文/其他语言”, “添加翻译”, “做成双语版”,
     “变为双语版”, “保留原文/对照” or any affirmative request for a bilingual
     version: keep the original and add the target language. This takes priority
     even if the same request also says “翻译为英文/中文”. A negated request such
     as “不要双语版” does not select bilingual;
   - otherwise `replace` for a specified single target language, including
     “翻译为英文/中文”, “翻译为英文版/中文版”, “翻译成英文/中文”, monolingual /
     单语 / 仅中文: replace the source-language text with the target language;
   - `auto` only for unspecified output such as “翻译这个文件”.
2. Run `python formats/pdf/scripts/route_pdf_file.py <uploaded-file> --mode
   <auto|replace|bilingual>` from the repository root. Save the returned JSON as
   `<job>/route-report.json` for the language inventory decision.
3. Stop if the report contains an `error` or returns a nonzero exit code.
   Hidden OCR text (`Tr=3`, or clipping-only `Tr=7`) does not count as visible
   native text. A scan with only this layer remains `scan-only` even when its
   OCR can be copied. The router and scan classifier share this check; do not
   override it by relabeling all extracted blocks as `ocr-artifact`.
4. If an `auto` or `bilingual` report returns
   `document_kind: engineering-drawing`, use its `translation_mode: add_bilingual`.
   Inventory all clear Chinese and foreign labels. Save all five coverage counts
   together with `language_pair` (the actual paired languages) and
   `requested_language_pair` (from user intent), each a two-code array such as
   `["zh", "es"]`. Counts refer to that actual pair, not any foreign language.
   Use consistent language codes; never infer the requested pair from what is
   already present. Then run `python formats/pdf/scripts/decide_drawing_translation.py
   --inventory-file <drawing-language-inventory.json> --route-report
   <job>/route-report.json`. The saved route supplies the authoritative document
   kind and output mode; label counts cannot change either. Continue automatically; never pause
   for language confirmation after processing starts.
5. If that decision is `already_bilingual_complete`, preserve the exact source
   PDF, mark the task complete, and skip translation. This requires matching
   actual/requested language pairs, complete semantic pairing and zero unmatched
   clear labels. Unknown or different language pairs continue inventory/translation;
   they do not justify skipping or declaring the whole task failed.
6. If the user wants the original text kept visible with a target-language translation
   added beside it (bilingual / dual-language / 双语版 / 中英对照), use
   `formats/pdf/bilingual/SKILL.md` regardless of the PDF type — as long as
   the PDF contains selectable native text (native-text or mixed).
7. Before selecting an execution workflow, resolve any changed output requirement
   by rerunning the router with the corrected mode; discard the earlier adapter
   selection. Never keep a bilingual adapter with a `replace` decision. A
   language inventory is a coverage check, not a second output-mode selector.
8. Read and follow only the returned `adapter`. Resolve its
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
adds target-language translations as a new text layer in surrounding whitespace.

`native-text` proves that visible extractable text exists, not that it covers
all labels. For engineering drawings, compare the extracted inventory with the
whole sheet. `ocr_recommended_pages` flags sparse native text (at most 100
characters/page); it is a prompt for visual/OCR inspection, not proof that the
page is a scan. Native-CAD replacement uses `prepare --ocr always` for these
pages or any visually confirmed outline/image labels. Bilingual overlay binds
such labels by reviewed page coordinates; it does not require native text IDs.
Do not rasterize the delivered vector drawing because only a few characters
are extractable. OCR runs inside the selected workflow, not a second adapter.

Do not route by extension, filename, or user wording alone. Do not run more than one adapter on the same input.
