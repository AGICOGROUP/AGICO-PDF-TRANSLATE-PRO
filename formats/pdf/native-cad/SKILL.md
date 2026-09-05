---
name: translate-native-cad-pdf
description: Use when a native-text or mixed engineering-drawing PDF must replace removable source text with translated text while preserving page geometry, vector lines, images, title blocks, and selectable output. Do not use for scan-only PDFs or bilingual overlay requests.
---

# Native-CAD PDF Replacement

Use this specialized execution adapter only when the PDF router returns all of:

```text
pdf_type: native-text or mixed
document_kind: engineering-drawing
translation_mode: replace
```

This is not a PDF content classification. It is the adapter selected by the
combined content, drawing-kind, and explicit replacement conditions. Ordinary
engineering-drawing wording defaults to bilingual; use this adapter only when
the user explicitly requires the source text removed or replaced.

## Workflow

Prepare a source-bound job:

```powershell
python scripts/native_cad_pipeline.py prepare <source.pdf> --job-dir <job>
```

Translate every `pending` record in `<job>/translation-packet.json`. Preserve
records marked `protected`, including drawing numbers, models, dimensions,
tolerances, units, coordinates, and standard numbers. Set completed records to
`status: translated`; do not edit their IDs or source text.

Apply coordinate-bound replacement:

```powershell
python scripts/native_cad_pipeline.py apply <job> `
  --packet <job>/translation-packet.json
```

Any missing translation, source-hash mismatch, unsafe font, or text-fit failure
must stop the job. Never flatten the page, redraw the drawing, or delete images
or vector graphics. Never switch to another adapter after failure.

Render and create `<job>/visual-review.json`, bound to the candidate SHA-256,
after reviewing every page and changed region. Then run:

```powershell
python scripts/native_cad_pipeline.py verify <job> `
  --candidate <job>/translated-native-cad.pdf `
  --visual-review <job>/visual-review.json
```

Deliver only when `<job>/final-qa.json` contains `"passed": true`. Read
[quality-gates.md](references/quality-gates.md) before verification.

## Boundaries

- Scan-only PDF: use `formats/pdf/scan/SKILL.md`.
- Keep original plus translation: use `formats/pdf/bilingual/SKILL.md`.
- Ordinary native/mixed document: use `formats/pdf/native/SKILL.md`.
- Run exactly one adapter for an input; never merge their workflows.
