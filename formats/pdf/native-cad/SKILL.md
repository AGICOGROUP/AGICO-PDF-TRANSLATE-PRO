---
name: PDF-TRANSLATE-PRO-NATIVE-CAD
description: Translate native or mixed CAD engineering PDFs in replacement mode while retaining vectors. Uses native extraction, tiled OCR plus a full-page supplement, cell placement proposals, and consolidated review. Excludes scan-only PDFs and bilingual overlay.
---

# PDF-TRANSLATE-PRO-NATIVE-CAD

Use for router result (native-text | mixed) + engineering-drawing + replace.
Commands are relative to this adapter. Retain source vectors in the delivered
PDF; renders serve OCR/review only. Do not run a second adapter.

## Prepare once

```powershell
python scripts/native_cad_pipeline.py prepare <source.pdf> --job-dir <job> --target-language <target-code>
```

Prepare extracts native text, runs cached tiles and a full-page supplement,
deduplicates missing regions, proposes closed CAD cells and creates
source-review/index.html with the whole sheet and label crops. Supplement IDs
use -u; tile IDs stay unchanged. Use --ocr always for sparse outlined drawings.
Reuse the current job on retries with the same target language. For a fresh test
or a different target, use `--fresh`: prepare creates an independent sibling job,
imports no previous translation/OCR artifacts and returns its actual `job_dir`.
Use that returned directory thereafter. Do not relabel an existing translation
packet's language to reuse it. Legacy unbound jobs remain resumable by their
explicit path without adding a new language binding.

Read the whole sheet, translation-packet.json.page_context and
[page-context translation review](../../../references/page-context-translation-review.md).
Before first apply, enlarge the source title block, revision table and legend
until individual characters are readable, and match every populated field to
the inventory, including vertical/spaced headings such as drawing title,
number and type. Record crops show only detected text and cannot expose all
omissions. Use a local high-resolution render if the existing image is too small;
retry OCR only on unresolved regions. Add missing labels with source coordinates
to both inventory and packet, and include them in page context before translation.
Use the supplied commands instead of writing document-specific helper scripts.

## Translate and place in batches

Keep IDs and source unchanged; record corrections in source_correction and
review_note. Before translation, read continuous technical requirements as a
whole and reconcile overlapping OCR fragments. Native spans can be individual
words: translate the complete label, cell or paragraph, never a word dictionary
placed back in source-language order. Reflow each complete phrase or numbered
clause once within its reviewed whitespace, retaining numbering, subclauses,
all constraints, values and units. Do not summarize clauses, combine unrelated
fields, or infer missing limits from engineering convention. Keep original
records traceable; dismiss a duplicate only when its complete content is covered
by the retained record. Translate dimension qualifiers such as hot/cold condition;
only the numeric or identifier portion is language-independent.
Reuse repeated wording after checking equipment and local meaning. Mark confirmed tags or existing target
text preserved with a reason; dismissed is for reviewed OCR false positives,
never unread or inconvenient prose.
Protection patterns are suggestions: tokens such as `SE` can be ordinary
source-language words inside a sentence. Check them in context; if a protected
record is prose, change its inventory status to pending and include it in the
packet with its original ID/source before translating. Likewise, dismiss OCR
only after matching its full content to retained source records, not all OCR
records together merely because native text exists.

Prepare also exports `translation-units.json`: conservative same-line native
phrase proposals plus ordered full-page source context, bound to this inventory
and request. Review membership before translating; different cells, protected
dimensions, rotations and outline text remain separate. Fill one fluent
translation per reviewed unit and a grouping `review_note`. Submit only completed
units (a subset is allowed) in a separate file:

```powershell
python scripts/native_cad_pipeline.py merge-units <job> --translations <job>/unit-translations.json
```

The importer updates the existing packet atomically, preserving source IDs and
expanding each phrase into one translated leader and merged members. It rejects
stale inventories, changed membership and conflicts with existing packet decisions.
After manual inventory corrections, use the existing packet mechanism below;
do not rerun prepare merely to export units, because re-extraction can restore
the original protected-token classification. Proposals are not semantic
approval; multiline clauses and non-proposed groups use the following
existing packet mechanism, not forced word-by-word translation.

For a native phrase split across records, keep every ID and source unchanged.
Choose one leader with `status: translated`, the complete fluent translation
and a reviewed `layout_box` for that phrase. Set the other native members to
`status: merged`, `merged_into: <leader-id>`, empty translation and a
`review_note` explaining the shared phrase. All members must share page and
rotation. Apply removes their individual source glyphs and draws the leader
once; if its translation cannot fit, it preserves the whole group's source.
Group by actual sentence/cell and safe whitespace, not by proximity alone;
do not absorb neighboring dimensions or cross table borders. This mechanism
does not authorize outline covers. Never mark native words preserved merely
because the target word order differs. Review the assembled Chinese sentence
in place; isolated legible word crops do not establish semantic correctness.

placement_proposal supplies cell_bbox, inset layout_box, all members and
source_overflows_cell. It is a proposal, not approval:

- For a reviewed text-only description cell, use its inset box for layout.
  When both languages touch, replace the complete description once. Never
  estimate a script boundary from character counts: it clips English letters.
- Inspect all members first. Identifiers, numbers and separate fields stay
  distinct; never let several records independently cover the same cell.
  Shared cells now propose separate member layout boxes; overlapping OCR still
  requires reconciliation. For native company names, also set layout_box inside
  the actual title cell and clear of the logo, rather than accepting a source
  bounding box that protrudes outside the page.
- Keep covers inside borders. If source_overflows_cell is true, inspect the
  actual protruding glyphs once and preserve neighboring data and structures.
- With a genuine gap and an accurate existing target, an outline record may
  use status: cover_only, target_present and review_note. Cover only the source;
  do not insert a duplicate translation.
- For free labels, inspect OCR boxes and safe whitespace. Set rotation from
  source pixels (0/90/180/270); OCR zero is only a proposal.

For every outline cover, record actual pixel inspection in cover_review:

```json
{"approved":true,"text_only":true,"white_background":true,
 "note":"Actual inspected source label and surrounding structures."}
```

These are agent review fields, not a request for user permission. Never approve
from OCR confidence or geometry alone. source_text_paths is only for inspected
font outlines, never to suppress symbols. restore_conflicting_paths requires
reviewing the actual paths; do not restore old glyphs. Use cover_boxes and
layout_box for reviewed adjustments. Visual replacement is not secure deletion.

Use consistent semantic roles: title, body (including ordinary table text),
annotation. One page/role baseline applies, title > body > annotation; only
a whole overflowing paragraph shrinks. Prefer safe whitespace before shrinking.
OCR box height is an estimate, not a calibrated font size. Inspect
native CAD labels for text-matrix scaling: an implausibly tiny reported size
with a much taller visible line uses a line-height estimate in apply. Assign
roles by meaning and source hierarchy, not just box height.
Inspect representative body, title and annotation regions before applying. Do not force all drawings to
8.5 pt or halve every estimated size based on a single document.
Legacy table/footer roles remain supported, not arbitrary font-size groups.

Apply checks unique translated characters against the requested font before
covering source text. It keeps a compatible font, otherwise tries installed
Arial Unicode MS and Arial; if none covers the text, provide a compatible
--font-file. Do not remove accents or rewrite accurate wording to hide missing
glyphs. The actual font is recorded in apply-report.json.

```powershell
python scripts/native_cad_pipeline.py apply <job> --packet <job>/translation-packet.json
```

## Consolidated review and delivery

```powershell
python scripts/native_cad_pipeline.py review <job> --candidate <job>/translated-native-cad.pdf --residual-script cjk
```

Use cjk for Chinese-to-English; latin for foreign-language-to-Chinese.
Inspect batch-review/index.html (complete page pairs and all record crops),
batch-review/review-report.json (residual candidates with page coordinates) and
apply-report.json (fit failures, baseline and shrink exceptions) together.
Residual detection concerns scripts, not language correctness; Latin identifiers
may legitimately remain. Compare the enlarged source and target title blocks
cell by cell, including fields absent from OCR; check accents, remaining strokes
and adjacent grid lines. Source and residual OCR can share the same blind spots:
zero detections and a successful apply are not evidence of full visual review.
Record only observations actually made; do not mark all regions reviewed from
an overview or a sample of crops.

Collect defects before editing, then rebuild once and inspect changed regions
and the complete page. Review rendering reuses one display list per page and
retains every record, including preserved/dismissed records that may hide errors.
Unchanged review pages are content-cached with their local records and artifacts;
changed or corrupt pages rebuild, and the assembled report binds the exact source
and candidate. OCR keys include page content, settings and runtime/model identity;
valid hits do not start an OCR engine. Cache hits reuse measured artifacts, never
grant semantic/visual approval or rebind old acceptance evidence. Aim for one
initial candidate and one consolidated repair. This is a throughput goal, not a
hard retry gate or permission to deliver defects. Inspect local crops while
resolving a batch of defects; regenerate the full residual review after the batch.
Avoid repeated box nudges and whole-document reviews for one local correction.
Put corrections in the inventory/packet and rebuild reproducibly. Never hand-edit
apply/review hashes, add dummy objects to pass checks, or mark uninspected regions
as reviewed. Structure verification compares painted image content and placement,
allowing unused/duplicate resource cleanup while detecting lost or moved images.

Complete visual-review.json from actual review using the apply-generated
template and exact candidate hash. See [quality-gates.md](references/quality-gates.md).
Record semantic findings/corrections and verify:

```powershell
python scripts/native_cad_pipeline.py verify <job> --candidate <job>/translated-native-cad.pdf --visual-review <job>/visual-review.json
```

Deliver only after final QA passes and source-to-target findings are resolved.
When a label cannot fit, apply retains that label's source and saves
translated-native-cad-preview.pdf with failed IDs in apply-report.json, returning
a nonzero exit code. Inspect it before sharing; a useful partial translation may
be delivered as a clearly labelled preview with those defects, never as passed.
The report's preview path identifies the current result; an older normal output
may still exist and is not the new candidate. Do not present an almost entirely
untranslated drawing as a useful translation. Keep normal verification unchanged.
Report full elapsed time separately from OCR/apply/review seconds. Cached
replays are not fresh translation timings. The target is a 50% reduction in full
elapsed time with equal or better quality; tool-only timing cannot establish that
target. Record first-candidate time, repair rounds and delivery time separately.
Run code tests when changing scripts,
not for every PDF translation.
