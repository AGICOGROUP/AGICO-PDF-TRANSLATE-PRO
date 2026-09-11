# Bilingual Overlay Workflow

## End-to-end procedure

### Step 1 — Route the PDF

Use the output mode determined by the user's request in the PDF routing skill:

```powershell
python formats/pdf/scripts/route_pdf_file.py <source.pdf> --mode <auto|replace|bilingual>
```

Follow the returned adapter. `scan-only` uses the scan adapter with its returned
mode; a replacement route uses its replacement adapter. Only proceed here when
the returned adapter is bilingual. “翻译为英文版/中文版” alone means replacement.

### Step 2 — Inspect the layout

```powershell
python formats/pdf/bilingual/scripts/inspect_layout.py <source.pdf> --output <job>/layout.json
```

Review the JSON output to understand:
- Page dimensions and orientation (portrait vs. landscape).
- The bounding box of every text span.
- Font families and sizes used in the source.
- Which spans are body text, headers, table headers, table cells, labels.
- Available whitespace around each span (gaps between spans, margins, empty
  cells).

Native text may cover only a company name or tags. Compare with the complete
source drawing; use OCR for missing outline/image labels, particularly on
`ocr_recommended_pages`. Verify pixel-to-PDF coordinates and add these labels
to the same inventory. The overlay accepts coordinate bindings without native
span IDs. Preserve vectors; do not invoke a second output adapter.

### Step 3 — Build the translation packet

Create `<job>/translations.json` as an array of placement records:

```json
[
  {
    "page": 0,
    "source": "PLANO DE INSPEÇÃO E TESTES",
    "translation": "检验和试验计划",
    "x": 227.2,
    "y": 106,
    "fontsize": 7
  },
  {
    "page": 1,
    "source": "Ensaio de tração",
    "translation": "拉伸试验",
    "x": 171.1,
    "y": 296,
    "fontsize": 6
  }
]
```

#### How to choose coordinates

For each source span, examine its bbox `[x0, y0, x1, y1]` and find the nearest
whitespace:

1. **Below or above**: anchor to the source block bbox. Compare usable space
   below and above; prefer below when both fit. Start about 2–4pt beyond the
   source bounds, aligning left edges or centers. Above placement must subtract
   the measured translation height. Include underlines and nearby artwork when
   judging usable space; a text-only gap may contain a dimension or leader.
2. **Beside**: use the nearest side only if neither above nor below fits.
   For rotated text, apply the same proximity rule in its reading direction.
3. **Adjacent empty cell**: for table layouts with empty columns, place inside
   the empty cell's bbox.
4. **Adjacent table group**: if cells are full, inspect the whole table's left
   and right whitespace, then immediately above or below it. Place a compact
   translated table or aligned list there with the same row order and identifiers.
   Avoid existing symbols and lines, including those missed by text extraction.
5. **Nearest usable margin**: only if nearby placement cannot remain readable
   and unobstructed, use linked numbered notes. Existing row numbers/codes can
   supply the link. A larger blank area at the opposite end of the sheet is not
   a reason to separate a table from its translation.

The `x, y` in the record are the top-left corner of the translation text (in
PDF points, origin top-left, y increases downward).

#### How to choose font size

- Start at the corresponding source size, or 1–2pt smaller when needed.
  Keep similar source roles/sizes consistent; do not use a fixed small size
  throughout a large drawing.
- Try the other nearby side or safe wrapping before further reduction.
  The 5pt minimum is a last-resort floor, not a target. Concise wording must
  retain the full technical meaning.

#### How to choose max_width

Set `max_width` when the available horizontal space is limited (e.g., a narrow
table column). The script auto-wraps CJK text character-by-character to stay
within this width. Leave `max_width` unset for single-line labels in open
whitespace.

### Step 4 — Apply the overlay

```powershell
python formats/pdf/bilingual/scripts/bilingual_overlay.py `
  <source.pdf> `
  --translations <job>/translations.json `
  --output <job>/bilingual-output.pdf `
  --font-file C:\Windows\Fonts\simhei.ttf
```

### Step 5 — Render and verify

Render the first candidate once for whole-sheet coverage review. Reuse that
render for crops; use a higher-resolution crop only when detail is unreadable:

```powershell
python -c "import fitz; d=fitz.open('<job>/bilingual-output.pdf'); [p.get_pixmap(matrix=fitz.Matrix(2,2)).save(f'<job>/preview_{i+1}.png') for i,p in enumerate(d)]"
```

Inspect each rendered page for:
- Source content unchanged; originally selectable text remains selectable.
- Requested target-language translations readable and correctly placed.
- No overlap with source text, borders, or images.
- No missing glyphs (tofu boxes).
- Consistent font sizes within each role group.

### Step 6 — Iterate if needed

Before the first build, derive positions and sizes from the inspected source
bounds in one pass. Check proposed table placements against borders and artwork
on the existing source render. This avoids trying several distant table areas.

If review finds overlaps or poor readability, batch the affected records into
one packet update, rebuild, and inspect those changed regions. Reuse unchanged
source inventory and translations within this job. Run final artifact checks
against the final build; do not repeat repository unit tests or recreate
equivalent QA scripts for an ordinary translation with unchanged adapter code.
Do not rebuild for harmless cosmetic warnings alone.
