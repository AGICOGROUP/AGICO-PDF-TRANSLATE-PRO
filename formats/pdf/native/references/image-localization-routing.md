# Image localization routing

Use this reference for every image, diagram, engineering drawing, screenshot,
logo, chart, or scanned technical label that contains source-language text.

## Source priority

Use the first available source in this order:

1. Editable native text in a PDF page or Form XObject.
2. Editable SVG, CAD, presentation, or other layered source supplied inside the
   original document package.
3. The original embedded image XObject at native dimensions.
4. A source-page render and crop only when no original asset exists; render at
   least twice final display size and inspect dense drawings at 3x scale.

Never use an earlier translation, viewer screenshot, or recompressed derivative
as the source.

## Required inventory

Create one image record for every original asset and one stable label record for
every detected source-language label. Reuse one adequate-resolution OCR pass. Retry only uncertain or missed regions
at higher resolution, map detections to native coordinates and review residual hits.

Each image record must contain:

- `id`, page/resource identity, source hash, pixel dimensions, and PDF placement;
- `asset_type`: `editable_vector`, `raster_simple`, `raster_structured`,
  `raster_complex`, or `unreadable`;
- `method`, expected/translated/preserved/confirm counts, structural-review
  status, and final page;
- `labels`, including stable ID, box, source text, translation, label type, OCR
  confidence, status, and method.

Use this review shape:

```json
{
  "complete": true,
  "reviewed_image_ids": ["page-6-process-diagram"],
  "images": [
    {
      "id": "page-6-process-diagram",
      "asset_type": "raster_structured",
      "method": "anchored_line_restore",
      "contains_source_text": true,
      "expected_label_count": 2,
      "translated_label_count": 1,
      "preserved_label_count": 1,
      "confirm_count": 1,
      "structural_review_complete": true,
      "labels": [
        {
          "id": "label-001",
          "source_text": "烟囱",
          "translation": "Chimney",
          "ocr_confidence": "high",
          "method": "anchored_line_restore",
          "status": "translated"
        },
        {
          "id": "label-002",
          "source_text": "…",
          "translation": "",
          "ocr_confidence": "low",
          "method": "preserve_confirm",
          "status": "confirm",
          "preserve_reason": "distant_unreadable"
        }
      ]
    }
  ],
  "confirm_items": [
    {"label_id": "label-002", "reason": "source pixels are unreadable"}
  ]
}
```

## Method router

Choose the first method whose predicate is satisfied. Fail closed when its
evidence is incomplete.

In bilingual output mode, if a diagram already contains both the source text
and an English counterpart for its labels, preserve the original image
unchanged. In explicit monolingual mode this shortcut does not apply. Record
preserved labels as reviewed; do not clean the raster,
remove either language, or add another English overlay.

| Method | Use when | Required output |
|---|---|---|
| `native_edit` | Editable PDF/Form/SVG/CAD text exists | Replace native text while preserving vectors and layers. |
| `deterministic_cleanup` | Raster text lies on a verified simple background | Clean only glyph pixels with a reviewed cleanup mode. |
| `anchored_line_restore` | Raster text crosses a recoverable engineering line | Clean glyphs and reconnect only explicit opposite-edge anchors. |
| `constrained_clean_base` | A complex raster region defeats deterministic cleanup | Produce a local text-free clean base candidate and pass structural gates. |
| `preserve_confirm` | A label is genuinely unreadable, or is a logo/seal, signature/stamp, or protected legal-document region | Preserve the original region, record an allowed `preserve_reason`, and create a `[CONFIRM]` record. |
| `preserve_bilingual` | Every clear Chinese label already has a semantic English counterpart | Preserve the exact original asset; record complete pair counts and zero unmatched Chinese labels. |

Do not choose a raster method when an editable native source exists.
The presence of some English never proves a diagram is bilingual-complete.
Inventory all clear Chinese labels; use `preserve_bilingual` only when the
matched-pair count equals the clear-Chinese count and the unmatched count is
zero. Otherwise translate only the unmatched Chinese labels.

## Raster route selection: two co-equal routes

Both raster routes below are first-class. Pick one per image from the risk
profile, not from which one is less work. Both end the same way: a text-free
clean base plus an embedded vector text overlay.

| | Route A `deterministic_cleanup` (+ `anchored_line_restore`) | Route B `constrained_clean_base` |
|---|---|---|
| Removes text by | colour/shape mask inside reviewed `clean_box` regions | high-fidelity image edit of approved local regions only |
| Non-text pixels | provably untouched outside `clean_box` (`outside_region_pixel_changes = 0`) | restored from the original outside approved regions, then diffed |
| Wins when | flat fills, white gutters, few crossings between text and artwork | text overlaps artwork it cannot be separated from: outline crossing a word, diagonal/rotated labels riding on a member, gradients, photo or UI texture |
| Costs when | every box must be measured; crossings need anchors on opposite edges | the model may redraw nearby geometry, so the structural gates are mandatory |
| Choose first when | the asset carries dimensions, tolerances, tags, QR/barcode or legal marks | the asset is illustrative, or A has already failed a gate twice on the same region |

Fail-closed rule: Route B never replaces a dimensioned or legally significant
region that Route A can clean, and it may not be chosen merely because manual
box measurement is tedious. Record the chosen route and the reason on the image
record.

## Label location without OCR

`scripts/locate_image_labels.py` supplies the measurement tooling when no OCR
engine is installed (probe `pytesseract`/`easyocr`/`paddleocr`/`tesseract`
first; reuse one adequate-resolution OCR pass when they exist).

```powershell
# text-line boxes in native pixels (glyph components with cv2, projection fallback)
python scripts/locate_image_labels.py detect images/x.png --out tmp/labels --annotate

# gridded zoom used to read exact box coordinates off the artwork
python scripts/locate_image_labels.py grid images/x.png --box 1820 395 2010 535 `
  --out tmp/grid.png --scale 4 --step 20

# one readable contact sheet of every detected line, indexed
python scripts/locate_image_labels.py sheet images/x.png --lines tmp/labels/lines.json `
  --out tmp/sheet.png --columns 1 --scale 1.3
```

Detection separates characters from artwork by shape: hatch strokes and rules
are long and thin (low ink density), glyphs are compact. Use `detect` output as
candidate boxes only — read the sheet to assign text and use `grid` to confirm
each box against the artwork before writing metadata. Keep the existing
two-tries-then-drop limit per region; never guess a label to fill a gap.

Clear informational captions, photo descriptions, marketing copy, and readable
diagram labels must be translated. A complex photographic background is a
cleanup-routing problem, not permission to use `preserve_confirm`; use a local
clean band or `constrained_clean_base` and add selectable vector text. For a
caption already occupying a broad photo band, `solid_fill` may replace only the
approved text-only caption band with an explicit `fill_rgb`; all pixels outside
that band must remain identical. A border, signature, stamp or artwork inside
the band invalidates solid fill. Broad paragraph/page wipes are not caption
localization. Declare nearby non-text artwork in image `protected_boxes`.

## Anchored line restoration

Declare every restorable segment explicitly in the cleanup region:

```json
{
  "mode": "anchored_line_restore",
  "box": [40, 80, 120, 112],
  "clean_box": [40, 80, 120, 112],
  "line_anchors": [
    {
      "start": [40, 96],
      "end": [119, 96],
      "width": 1,
      "color_tolerance": 40
    }
  ]
}
```

Endpoints must touch opposite cleanup-box edges and have compatible colors. The
script interpolates only the declared segment inside the box. Missing,
same-edge, incompatible, or ambiguous anchors are failures; never infer a new
branch, bend, arrow, pipe, or connection.

## Route B: constrained clean base

Use high-fidelity image editing only for the approved local regions. Supply the
exact original asset, the label inventory, and this output contract:

```text
Use case: text-localization clean-base reconstruction.
Remove only the listed source-language glyphs from the approved regions.
Return a text-free clean base. Do not draw target-language text.
Preserve every device, vessel, pipe, arrow, symbol, border, color, number,
equipment relationship, image boundary, aspect ratio, and resolution.
Do not redesign, crop, sharpen, blur, add objects, remove objects, or alter flow.
If underlying structure cannot be recovered reliably, leave the region
unchanged and report it for confirmation.
```

Restore all pixels outside approved regions from the original before checking
the candidate. Reject any candidate that changes protected colors, line anchors,
topology, symbols, borders, dimensions, or aspect ratio.

Never ask an image model to generate final wording. After the clean base passes,
add requested target text as embedded PDF vector text through `apply_image_vector_text.py`.

## Label plan: machine-enumerated coverage

```powershell
python scripts/locate_image_labels.py plan --image-id p0003-i001 `
  --inventory images/image-inventory.json --out label-plan-p0003-i001.json
```

`plan` enumerates every text-like line in the asset and emits, per line, its box, a
suggested cleanup mode (`text_only_area` when the surround is at least 90% near-white,
otherwise the sampled colour family), the sampled ink colour, and the PDF `placement`
read straight from the inventory. Never type a placement by hand and never flip its Y
axis: inventory `y0/y1` are already PDF bottom-origin. Reuse a plan for the same asset
only while its `source_sha256` still matches.

Name the file `label-plan-<image-id>.json` next to the metadata and `verify` counts
every line that no cleanup box claims. Each plan line must end up either claimed by a
`clean_box` or marked `excluded_artwork` with a non-empty `exclude_reason`; a blank
reason does not exclude it. This closes the only way a label could escape the audit:
leaving it out of the metadata entirely.

## Review contract keys that `annotate-images` enforces

Every reviewed image record must carry all of these; each one failed a real run
before it was written down:

- `method` at image level, not only per label.
- `confirm_count`, not `confirm_label_count`.
- `structural_review_complete: true`.
- `translated + preserved == expected`, and the counts must equal the number of
  labels carrying each status.
- A label with `status: confirm` must appear in `confirm_items` under its exact
  `id`, with an allow-listed `preserve_reason`.

## Two detector threshold sets, on purpose

`plan` and `residue` deliberately use different defaults:

- `plan` runs at `--dark-below 215 --sat-above 60`. Light-tinted labels (pale
  orange/red engineering text) are invisible at 200/90, and an unlisted label is
  never declared, never cleaned, and never counted. Broad recall is the point.
- `residue` runs at `--dark-below 200 --sat-above 90`. The wider net also catches
  hatch dashes, arrow heads and outline slivers, which then masquerade as missed
  glyphs. Precision is the point.

Do not "unify" them. Re-measure both when tuning: a threshold that lowers
`plan_lines` is hiding labels, and one that raises `residue_missed_glyphs`
without a matching label box is reporting artwork.

## Residue audit (both routes)

`review residual hits` is measured, not eyeballed. After the clean base exists,
run the same detector over it and diff against the original:

```powershell
python scripts/locate_image_labels.py residue images/x.png images/x-clean.png \
  --metadata image-vector-metadata.json --plan label-plan-x.json
```

- `residue_missed_glyphs` and `residue_unclaimed_text_lines` must both be 0. Ink that
  survives inside (or overlapping) a declared `clean_box` is reported as
  `MISSED(declared)` even when nothing was removed there, so an under-sized box cannot
  hide as "structure".
- `structure_or_unlisted` holds surviving ink that no cleanup touched: verify
  each one against the label inventory. Arrowheads, grey bars, symbols such as
  `ω`, and intentional logos belong here; any readable word does not.
- `pixels_changed_outside_clean_boxes` must be 0 whenever `--metadata` is given.
- The audit needs a real difference: compare the original against the clean
  base. A zero `changed` count alone never proves a region is clear.
- Route B is audited the same way; the residue gate is not relaxed because a
  model produced the base.

Fix the offending `clean_box` (or the Route B region mask) and rerun the audit.
Do not proceed to the vector overlay with a non-zero missed count, and do not
resolve a crossing by widening the box over the artwork it would erase.

A `MISSED(declared)` hit that survives two box re-placements, with the artwork
edge running parallel to and interleaved through the glyphs, is the switch
condition for Route B on that region: colour and shape masks cannot separate two
parallel bands of the same hue family. Record the switch reason on the image
record; do not keep thinning boxes until the label is only partly removed.

## `[CONFIRM]` policy

Do not guess characters, units, model numbers, equipment tags, or topology. A
confirm item must identify the page, image, label box, OCR text, uncertainty,
current treatment, and recommended source or decision. Each confirmed label
must declare `preserve_reason` as `distant_unreadable`, `legal_document`,
`logo_or_seal`, or `signature_or_stamp`. Clear informational text is never an
allowed confirm reason. `legal_document` applies to a located protected legal
region, not every label in a drawing with a survey title or company stamp.
Inventory and translate readable descriptive labels outside that region.
Reported confirm items may remain preserved only under
this allow-list; unreported or disallowed confirm items block delivery.

## Per-image review

Require all of the following before accepting an edited image:

- all inventoried labels are translated or explicitly confirmed;
- numbers, units, models, standards, and symbols match the source;
- source and clean image dimensions are identical;
- pixels outside approved regions are identical;
- protected engineering colors and declared lines pass;
- original, clean base, difference image, and 50% alpha overlay are reviewed;
- no new object, lost structure, white-box damage, blur, overlap, or clipping is
  visible;
- the final page at actual placement remains clear and correctly anchored.
