# Scan-heavy reports: spend work where content changes

Use within the selected PDF adapter for scan-heavy reports, mixed report/map
attachments, and repeated borehole or inspection forms. Keep the existing
native, scan, bilingual and native-CAD pipeline boundaries and acceptance.

- Inspect whole source pages first. A photograph containing only reviewed
  identifiers/depth values needs preservation, not prose OCR and translation.
  Readable captions, labels and ordinary prose still require translation.
- Start with one adequate-resolution source OCR pass. Work in complete paragraphs
  and cells; repair clear missed continuation lines in their complete passage.
  Do not tile and rerun the whole document merely because one map is faint.
- Translate repeated form labels once within this fresh job, then verify every
  occurrence against its actual source. Align each page independently; preserve
  changing soil descriptions, numbers, codes, marks and curves. Repeated geometry
  is not evidence that the content is identical. Fresh tests never import old
  translations, OCR or acceptance records.
- For faint raster map labels, inspect a crop from the embedded original image
  at its native pixel resolution before repeatedly enlarging a page render.
  Apply local contrast only to the reading crop. In replacement mode, replace
  labels and legends in their original diagram locations; preserve symbols,
  lines and artwork. Do not substitute a below-image translation key or comparison
  table as a speed optimization. Uncertain readings still have the shared
  two-attempt limit.
- Check actual target-font glyph coverage before building. Technical Unicode
  subscripts/modifiers may be absent even when Chinese is supported. Use a
  capable font or meaning-equivalent conventional variable notation (e.g. N30),
  preserving indices and formulas; never silently drop unsupported characters.
- Redaction can rewrite native PDF font resources. Rebind the actual font after
  cleanup, then verify saved-file rendering and selectable text. A successful
  pre-redaction text-fit probe is not proof that its saved font binding survives.
- Protect real table/drawing rules during cleanup. Isolated prose underlines can
  cross the new wording; inspect and clear those within approved text regions.
  Do not treat every long dark horizontal run as a protected table border.
- Review every candidate page once. After repairs, use exact rendered-pixel
  identities to retain unchanged reviews and inspect changed pages/regions.
  Suspected erased graphics must be checked against actual saved-output pixels;
  a blank-looking repeated image display alone is insufficient evidence.

Record source OCR duration separately from task-entry-to-handoff wall time.
Compare quality, page coverage, artwork and readability before adopting a faster
method. One report is evidence for that workload, not a universal speed claim.
Changing OCR thread settings requires its own controlled comparison; do not infer
an improvement from a single measured run.
