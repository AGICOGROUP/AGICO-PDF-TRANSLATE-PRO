---
name: PDF-TRANSLATE-PRO-NATIVE-CAD
description: Replace text in native/mixed engineering PDFs with selectable translations while preserving vector artwork. Use only the PDF router's native-CAD result.
---

# Native-CAD replacement

Keep native vectors and original raster artwork. This branch is for
(native-text | mixed) + engineering-drawing + replace; scan-only and bilingual
input use their own returned adapters. Read shared
[translation review](../../../references/page-context-translation-review.md) and
[delivery policy](../../../references/delivery-policy.md).

## Prepare a source-bound job

Commands run from this adapter:

```powershell
python scripts/native_cad_pipeline.py prepare <original.pdf> --job-dir <new-job> --target-language zh --ocr auto --fresh
```

Use `--fresh` for tests or changed target requests and the returned job_dir for
subsequent commands. Same-request repairs resume the current job's bound artifacts.
Prepare extracts native spans, proposes closed cells, and exports source-inventory,
translation-packet, translation-units and whole-sheet/crop review artifacts.
For sparse or visibly incomplete outline/image labels use `--ocr always`; inspect
source-script capability before trusting recognizer output. Native extraction is
not proof of coverage of raster or font-outline labels.

Inspect full sheets, including title/revision tables and faint grey layers.
Record crops expose detected items only. If faint/outline source ink is missing
from the inventory, use `scripts/recover_faint.py <job>` once, before translation;
its 600dpi thresholded recovery is a targeted remedy, not a mandatory rerun of
ordinary dense text pages. Decide its needs_translation records before apply.
Still-blurry regions follow the shared two-attempt source-limitation policy.

## Translate complete labels and requirements

Read ordered page_context and original renders. Protection patterns are proposals:
SE may be prose, while numbers/part IDs may be correctly protected. Correct
misclassification with source evidence; never dismiss all OCR because some native
text exists. Dismiss a duplicate only when its full content is covered by retained
records. Translate qualifiers, negation, subclauses and units-in-context without
inventing limits or summarizing technical requirements. Query cement terminology
2.0 through `../scan/scripts/glossary_lookup.py`, including English source lookup.

Fill conservative same-line native phrase units in translation-units.json, with
unchanged source IDs/request/inventory binding. Submit completed units separately:

```powershell
python scripts/native_cad_pipeline.py merge-units <job> --translations <job>/unit-translations.json
```

The importer updates one translated leader and its merged members atomically.
For a multiline paragraph or manually corrected inventory use the existing
packet mechanism in [packet contract](references/packet-contract.md); do not force
unrelated words/cells into a proximity group or rerun prepare over manual decisions.
Keep every ID traceable and place one complete fluent translation per real unit.

## Safe geometry and consistent type

Use prepared neighbor-reserving layout boxes when they contain source bounds.
OCR duplicates must not reduce native short values to tiny glyph boxes. Layout
space differs from source cleanup: inspect all cell members, borders, separate
values and units. A merged paragraph needs the complete group's reviewed space,
not its bullet or leader span. Use source-based title/body/annotation roles.
Wrap at one page/role baseline; shrink only real full-unit overflow after repairing
avoidable narrow/short boxes. Inspect apply-report shrink exceptions together.

Native source glyph removal preserves drawings/images. Outline covers additionally
require actual source-pixel review under the [cover contract](references/packet-contract.md).
Text-only white background, source_text_paths and restore_conflicting_paths are
review fields, not user permission prompts. Confirm own glyph outlines versus
symbols; restored paths can reveal formerly hidden source strokes. Keep covers
inside borders and bound to their own source bbox; dummy anchors are invalid.
Choose rotation from source reading direction, not OCR zero by default.

```powershell
python scripts/native_cad_pipeline.py apply <job> --packet <job>/translation-packet.json
python scripts/native_cad_pipeline.py review <job> --candidate <job>/translated-native-cad.pdf --residual-script latin
```

Choose the actual source residual script (`latin` or `cjk`). The combined review
contains whole sheets, changed crops and residual candidates; inspect those
candidates, since identifiers are not automatically untranslated prose. Review
continuous clauses in place, not only isolated legible word crops.

## Acceptance and local repair

Use [quality gates](references/quality-gates.md), actual semantic and visual
findings, and the exact current candidate hash. An OCR residual check alone cannot
establish accurate or complete translation.

```powershell
python scripts/native_cad_pipeline.py verify <job> --candidate <job>/translated-native-cad.pdf --visual-review <job>/visual-review.json
```

A fit failure preserves affected source and emits a named preview plus failed IDs
in apply-report.json. The old normal output may remain; report the current preview
path, not that stale normal PDF. Resolve genuine meaning/readability/structure
failures; retain cosmetic diagnostics. Rebuild/review changed pages only and keep
cache identities. Report tool measurements separately from full elapsed time;
no fixed percentage speedup is promised before fresh translation comparison.
