# Native-CAD Quality Gates

Every gate is mandatory and bound to the prepared source and final candidate.

1. Source integrity: `SOURCE.pdf` SHA-256 matches `source-inventory.json`.
2. Structure: page count, size, rotation, and image count match; vector objects
   do not decrease.
3. Coverage: every pending record has one non-empty translated record; protected
   engineering tokens remain unchanged.
4. Text: source descriptive text is removed, translated text is selectable and
   extractable, the CJK font is embedded, and `fit_failures` is empty.
5. Graphics: title blocks, borders, dimensions, leaders, hatching, images, and
   other non-text drawing content remain intact.
6. Visual review: every page and changed region is reviewed; foreign descriptive
   residue, overlap, clipping, missing glyphs, and graphic damage are empty lists.
7. Evidence binding: the visual-review candidate SHA-256 matches the candidate,
   and `final-qa.json` reports `passed: true`.

White rectangular covers are not a general fallback. If Form/XObject text cannot
be removed directly, stop unless a separately reviewed cover record proves the
region has a plain background and contains no line, symbol, or graphic.
