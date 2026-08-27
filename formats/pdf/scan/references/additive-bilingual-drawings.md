# Additive bilingual engineering drawings

## Default and completion rule

Engineering drawings use this mode by default, even when the request does not
say “双语”. The business output is Chinese plus one other language.

Before adding text, inventory both language sets. A drawing already containing
Chinese and another language is complete only when every clear label is paired
semantically in both directions and both unmatched counts are zero. In that
case return the exact source PDF with status `already_bilingual_complete`.
Otherwise continue automatically and add only the missing target labels. Do
not stop for clarification once processing has started.

Use this inventory contract:

```json
{
  "document_kind": "engineering-drawing",
  "clear_chinese_label_count": 12,
  "clear_foreign_label_count": 12,
  "matched_bilingual_pair_count": 12,
  "unmatched_chinese_label_count": 0,
  "unmatched_foreign_label_count": 0
}
```

Use this mode when the user wants to retain Chinese and add another language as
selectable PDF text. Treat the scanned drawing as immutable artwork and add a
separate embedded vector-text layer.

## Mode contract

- Set top-level `target_language` to an ISO code such as `es`, `fr`, or `pt`.
- Use `action: add_bilingual`, `status: translated`, and
  `source_preserved: true` for every translated source block.
- Set `placement` to `below`, `right`, or `blank_panel`.
- Do not set `clean_box`: additive bilingual blocks must not erase source pixels.
- Keep equipment tags, instrument codes, numbers, units, arrows, pipes, tables,
  symbols, and Chinese labels unchanged.
- Embed a TrueType font that supports the target language. The target text must
  be extractable, selectable, and copyable.

## Placement order

1. Put the translation immediately below the Chinese label when the lower band
   is clear.
2. Put it immediately to the right when the lower band contains a line, symbol,
   instrument bubble, or another label.
3. For dense legends or narrow table cells, keep the source table intact and
   create a complete target-language companion table in verified page whitespace.
4. For dense title blocks, keep the Chinese title block intact and create a
   target-language companion panel directly above or beside it.

For `below` or `right`, the edge-to-edge gap must not exceed 3% of the page
diagonal (48 source-render pixels minimum tolerance). For `blank_panel`, set
`companion_kind` to `table`, `title_block`, or `legend`; set
`companion_anchor_box` to the complete source structure containing the source
label; and keep the panel within the same gap limit from that structure. The
panel must mirror source rows/order so every translation remains visually
traceable. Free-floating page-center translation lists are forbidden.

Use one consistent target-text color per drawing. A dark engineering blue is a
good default when the source is gray/black, but use black when the customer
requires monochrome output. Never use an opaque text background over drawing
structure.

## Translation and inventory

Inventory every clear Chinese label at 400 DPI and recheck at higher zoom. Group
repeated equipment names, flow labels, signal descriptions, title-block fields,
and instrument legends. Translate by engineering meaning and keep one target
term for each repeated source term.

When the target is English, use an exact cement-glossary match. For other target
languages, record the selected English glossary term as the controlled semantic
pivot, then use the professional target-language equivalent consistently.

## Optional authorized branding update

Change a company banner only when the user explicitly requests it. Limit cleanup
to the exact title-block banner, preserve its border, and insert the exact
user-supplied logo without redrawing, cropping, stretching, or changing its
transparency. Add the new company name as selectable text. Verify visually and
by extraction that the old company name is absent. Record the logo file SHA-256,
placement box, and aspect ratio.

Brand replacement is a separate approved edit; it does not relax the zero-pixel-
change rule for `add_bilingual` blocks elsewhere.

## Acceptance

- `changed_pixel_count` is zero for a pure additive bilingual build.
- Every `add_bilingual` translation is present in extracted PDF text.
- Expected Chinese OCR residuals occur only inside source-line boxes assigned to
  `add_bilingual` or validated `bilingual_complete` blocks.
- No target text intersects source text, protected boxes, drawing lines, symbols,
  table rules, or page boundaries.
- Full-page and 400-DPI crops confirm readable hierarchy, no clipping, and no
  missed labels.
- Page count, geometry, orientation, and source raster placement are unchanged.
