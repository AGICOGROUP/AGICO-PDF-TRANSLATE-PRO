---
name: PDF-TRANSLATE-PRO-ROUTER
description: Classify a PDF by visible content and select native, scan, bilingual or native-CAD translation while honoring the requested output mode.
---

# PDF content routing

Run from the repository root, after determining `auto`, `replace` or `bilingual`
from the root skill. The source container and visible content choose the adapter;
the filename and a copyable hidden OCR layer do not.

```powershell
python formats/pdf/scripts/route_pdf_file.py <original.pdf> --mode replace --output <job>/route-report.json
```

Use the returned adapter and translation mode. Nonzero exits include an actionable
error; resolve that cause instead of silently selecting a different adapter.
A scan with non-painting text (`Tr=3` or `Tr=7`) remains scan-only. Native text plus
hidden OCR counts only the visible text. The optional fast backend still inspects
every page and retains the pypdf malformed/encrypted-file checks.

| Content and request | Adapter |
|---|---|
| Ordinary native-text or mixed PDF, replacement | [native](native/SKILL.md) |
| Scan-only, either output mode | [scan](scan/SKILL.md) |
| Native/mixed PDF, retain source and add translation | [bilingual](bilingual/SKILL.md) |
| Native/mixed engineering drawing, replacement | [native-CAD](native-cad/SKILL.md) |

`native-text`, `mixed`, `scan-only` are content classes. `native-cad` is an adapter,
not a fourth content class. Native/mixed drawings use bilingual only for `auto`
or explicit `bilingual`. A single-language target uses replacement, including
engineering sheets. Raster pages within a genuinely mixed PDF stay in its one
selected adapter. All scan-only pages preserve their raster bases.

When translation expansion cannot fit readably, all PDF adapters follow the
shared [pagination policy](../../references/pdf-pagination.md). Necessary added
pages and updated page numbers are authorized; formatting remains preserved.

## Drawing coverage and already-complete originals

For engineering drawings in `add_bilingual`, inventory visible labels in the
requested language pair before deciding translation is unnecessary. Use
`decide_drawing_translation.py --inventory-file <inventory.json> --route-report
<job>/route-report.json`. Its existing schema requires all five coverage counts,
`language_pair` and `requested_language_pair`, each pair two normalized language
codes. The route is authoritative for document kind/mode; counts cannot change it.

Only `already_bilingual_complete` with matching actual/requested language pairs,
complete semantic pairing and no unmatched clear labels permits byte-for-byte
original delivery. Different/unknown pairs continue translation. An existing
Chinese-English drawing is not a completed Chinese-Spanish drawing. This shortcut
never satisfies replacement. Rerun routing if the user changes output mode.

## Source inspection remains necessary

`ocr_recommended_pages` flags sparse drawing text, not proven image-only content.
Compare full-sheet renders with extracted labels, including title/revision tables,
faint layers, symbols and outlined text. A4/A3 sparse vector plots are detected by
path density; the optional drawing probe covers at most 12 pages, so absent
evidence is not proof that a later or unusual page is ordinary prose. On located
missing outline/image labels, OCR stays inside the selected adapter; preserve the
delivered vectors. Resolve reported page rotation on a source-preserving working
copy and reroute that copy before using a scan builder that requires zero rotation.
