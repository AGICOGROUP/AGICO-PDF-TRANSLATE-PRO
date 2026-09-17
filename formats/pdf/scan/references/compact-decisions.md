# Compact replacement decisions

Use this optional compiler for image carriers and scan `preserve_raster`
replacement pages. It expands model-authored data into the existing manifest;
it does not translate, decide grouping, clean images or approve reviews.
Additive manifests keep their existing workflow.

```powershell
python scripts/compile_translation.py --extraction job/extract/extraction-report.json --draft job/manifest/draft-groups.json --decisions job/manifest/decisions.json --output job/manifest/translation-manifest.json
```

Decisions bind to the extraction PDF hash (for an image, the carrier PDF hash,
not the original image hash). All boxes use the extraction's source-render pixels.

```json
{
  "source_sha256": "<extraction hash>",
  "target_language": "zh",
  "styles": {
    "heading": {"max_font": 13.5, "min_font": 8, "bold": true},
    "body": {"max_font": 12, "min_font": 7, "leading_ratio": 1.12}
  },
  "supplements": [],
  "regions": [
    {"group": "p01-r001", "translation": "一般说明", "role": "heading"},
    {"id": "paragraph", "ids": ["p01-l002", "p01-l003"],
     "translation": "完整段落译文", "box": [100, 200, 800, 400]},
    {"id": "identifier", "ids": ["p01-l004"],
     "preserve_reason": "Manufacturer model identifier; retain verbatim"}
  ]
}
```

Choose `group` only after checking that it is one semantic/layout unit. Explicit
`ids` override group ownership and let the model split lists/cells or join a
paragraph. Every source ID, including supplements, must be assigned exactly once.
Separate page/rotation boundaries are mandatory. Missing and duplicate IDs fail
before rendering. Preservation needs a meaningful reason, not blank translation.

Draft groups are provisional: verify reading order and paragraph boundaries.
Do not accept a continuation assigned across an intervening heading or a new
paragraph. After recovering a missing source line, use explicit IDs to restore
the whole affected sentence, removing superseded block ownership. Resolve the
page's OCR review candidates before treating the translation as complete.

Optional `source` records a visually checked OCR correction. `box` controls target
placement, while `clean_boxes` defaults to the individual source glyph boxes.
Changing target width never enlarges cleanup. Optional `background` is `sample`
or a measured RGB fill. `style` overrides the role's font/weight/alignment settings
for a justified complete paragraph or cell. Avoid word-level shrinkage.

Each supplement is a normal source-line object with `id`, `page`, `text`, `box`,
`rotation` and `origin: visual_supplement`; register its true geometry and assign
it in a region. Inspect readable headers, footers and list labels before the
first build, not through repeated final-image discovery. Retain the manifest
schema for rich text, source crops and advanced cases that this compiler does
not expose; do not flatten those features merely to use the compact path.
